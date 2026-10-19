from snowcite.domain import rules
from snowcite.domain.citations import count_cites
from snowcite.domain.inputs import ClusterInput, NoteInput, ReviewDecision
from snowcite.domain.records import (
    Cluster,
    CriteriaRecord,
    ErrorResult,
    NewNote,
    PaperDetails,
    PaperRecord,
    UndoResult,
)
from snowcite.domain.results import (
    ClusterError,
    CriteriaSaved,
    IndexedError,
    ProgressView,
    ReviewBatchResult,
    SetStatusResult,
    SummarySaved,
    SummaryView,
)
from snowcite.storage.repositories import (
    NoteRepository,
    PaperRepository,
    ProjectRepository,
    ReviewRepository,
    SectionRepository,
)


def _new_notes(notes: list[NoteInput]) -> list[NewNote]:
    return [
        {
            "paper_id": None,
            "cluster": n.get("cluster"),
            "type": n["type"],
            "text": n["text"].strip(),
        }
        for n in notes
    ]


class ReviewService:
    def __init__(
        self,
        reviews: ReviewRepository,
        sections: SectionRepository,
        project: ProjectRepository,
        papers: PaperRepository,
        notes: NoteRepository,
    ) -> None:
        self._papers = papers
        self._notes = notes
        self._reviews = reviews
        self._sections = sections
        self._project = project

    # ─── Criteria and reading ───────────────────────────────────────────

    async def set_criteria(self, criteria_text: str) -> CriteriaSaved:
        return {"id": await self._reviews.add_criteria(criteria_text)}

    async def get_criteria(self) -> CriteriaRecord | None:
        return await self._reviews.latest_criteria()

    async def list_papers(
        self,
        status: str | None,
        source: str | None,
        year_from: int | None,
        year_to: int | None,
        search: str | None,
        cluster: str | None,
        reviewed_by: str | None,
        include_abstracts: bool,
        limit: int,
        offset: int,
    ) -> list[PaperRecord] | ClusterError:
        """Saved papers with review state; `cluster` narrows to a summary cluster's papers."""
        within: list[int] | None = None
        if cluster:
            resolved = await self._reviews.resolve_cluster_paper_ids(cluster)
            if isinstance(resolved, dict):
                return resolved
            within = resolved
        return await self._papers.find(
            status,
            source,
            year_from,
            year_to,
            search,
            reviewed_by,
            within,
            include_abstracts,
            limit,
            offset,
        )

    async def batch(
        self, status: str | None, reviewed_by: str | None, limit: int
    ) -> list[PaperRecord]:
        """A compact batch of papers by review state (the next unreviewed ones, auto_low calls, ...)."""
        return await self._papers.find(status=status, reviewed_by=reviewed_by, limit=limit)

    async def paper_details(self, paper_id: int) -> PaperDetails | ErrorResult:
        paper = await self._papers.details(paper_id)
        return paper if paper is not None else {"error": f"paper {paper_id} not found"}

    # ─── Decisions ──────────────────────────────────────────────────────

    async def set_status(
        self,
        paper_ids: list[int],
        status: str,
        reason: str,
        note: str | None = None,
        reviewed_by: str = "auto_high",
        notes: list[NoteInput] | None = None,
    ) -> SetStatusResult:
        """Set one status for several papers, with a history entry per paper."""
        if notes:
            error = rules.validate_inline_notes(notes, len(paper_ids))
            if error:
                return {"updated": 0, "error": error}

        result = await self._reviews.set_status(
            paper_ids, status, reason, note, reviewed_by, _new_notes(notes) if notes else None
        )
        out: SetStatusResult = {"updated": result["updated"]}
        if result["skipped"]:
            out["skipped_invalid_ids"] = result["skipped"]
        if result["note_ids"]:
            out["note_ids"] = result["note_ids"]
        return out

    async def review_batch(self, decisions: list[ReviewDecision]) -> ReviewBatchResult:
        """Apply a batch of decisions; valid ones go through, invalid ones are reported by index.

        Approving or "maybe"-ing a paper must leave something in the knowledge graph:
        either `notes` containing a claim/finding (single paper only) or per-paper
        notes recorded earlier. Rejected papers take no notes.
        """
        out: ReviewBatchResult = {"updated": 0, "errors": []}
        skipped: list[int] = []
        note_ids: list[int] = []
        for idx, decision in enumerate(decisions):
            ids = decision.get("paper_ids") or (
                [decision["paper_id"]] if "paper_id" in decision else []
            )
            error = rules.validate_decision(decision, ids)
            if error is None and rules.requires_extraction(decision["status"]):
                error = await self._extraction_error(decision, ids)
            if error:
                out["errors"].append(IndexedError(index=idx, error=error))
                continue
            result = await self.set_status(
                ids,
                decision["status"],
                decision["reason"],
                decision.get("note"),
                decision.get("reviewed_by", "auto_high"),
                decision.get("notes"),
            )
            if "error" in result:
                out["errors"].append(IndexedError(index=idx, error=result["error"]))
                continue
            out["updated"] += result["updated"]
            skipped += result.get("skipped_invalid_ids", [])
            note_ids += result.get("note_ids", [])
        if skipped:
            out["skipped_invalid_ids"] = skipped
        if note_ids:
            out["note_ids"] = note_ids
        return out

    async def _extraction_error(self, decision: ReviewDecision, ids: list[int]) -> str | None:
        notes = decision.get("notes")
        if notes:
            if not rules.validate_extraction(notes):
                return "approved/maybe notes need at least one claim or finding"
            return None
        missing = sorted(set(ids) - await self._notes.paper_ids_with_notes(ids))
        if missing:
            return (
                f"papers {missing} have no notes: pass notes=[{{type: claim|finding, text}}] "
                "(one paper per decision) so the knowledge graph isn't left empty"
            )
        return None

    async def bulk_reclassify(
        self,
        new_status: str,
        reason: str,
        current_status: str | None,
        source: str | None,
        cluster: str | None,
        year_from: int | None,
        year_to: int | None,
        reviewed_by: str,
        limit: int | None,
    ) -> SetStatusResult:
        cluster_ids: list[int] | None = None
        if cluster is not None:
            resolved = await self._reviews.resolve_cluster_paper_ids(cluster)
            if isinstance(resolved, dict):
                return {"updated": 0, **resolved}
            cluster_ids = resolved
            if not cluster_ids:
                return {"updated": 0, "note": f"cluster {cluster!r} is empty"}

        target_ids = await self._reviews.select_paper_ids(
            current_status, source, year_from, year_to, cluster_ids, limit
        )
        if not target_ids:
            return {"updated": 0, "note": "filter matched no papers"}
        # Same path as a manual decision, so every paper gets its audit entry.
        return await self.set_status(target_ids, new_status, reason, None, reviewed_by, None)

    async def undo_last(self) -> UndoResult:
        return await self._reviews.undo_last()

    # ─── Progress and summary ───────────────────────────────────────────

    async def progress(self) -> ProgressView:
        counts = await self._reviews.live_counts()
        targets = await self._project.targets()

        document_sections = await self._sections.load_document_sections()
        words = sum(len(s["content"].split()) for s in document_sections)
        cites = sum(count_cites(s["content"]) for s in document_sections)
        density = round(cites * 100 / words, 2) if words else 0.0

        return {
            "counts": counts,
            "writing": {
                "words": words,
                "citations": cites,
                "citation_density_per_100_words": density,
                "sections_with_content": len(document_sections),
            },
            "targets": targets,
            "warnings": rules.progress_warnings(counts["approved"], targets, words, density),
        }

    async def save_summary(self, summary: str, clusters: list[ClusterInput]) -> SummarySaved:
        normalized: list[Cluster] = [
            {
                "topic": c["topic"],
                "paper_ids": c.get("paper_ids", []),
                "count": c.get("count", len(c.get("paper_ids", []))),
            }
            for c in clusters
        ]
        await self._reviews.save_summary(summary, normalized)
        return {"status": "saved"}

    async def get_summary(self) -> SummaryView | None:
        data = await self._reviews.load_summary()
        if data is None:
            return None
        warnings = rules.summary_warnings(
            data["stale"], data["counts_snapshot"], data["counts_live"]
        )
        return {**data, "warnings": warnings}
