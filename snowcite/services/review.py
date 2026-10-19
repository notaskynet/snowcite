from typing import Any

from snowcite.domain import rules
from snowcite.domain.citations import count_cites
from snowcite.storage.repositories import (
    NoteRepository,
    PaperRepository,
    ProjectRepository,
    ReviewRepository,
    SectionRepository,
)


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

    # ─── Criteria and batches ───────────────────────────────────────────

    async def set_criteria(self, criteria_text: str) -> dict[str, int]:
        return {"id": await self._reviews.add_criteria(criteria_text)}

    async def get_criteria(self) -> dict[str, Any] | None:
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
    ) -> list[dict[str, Any]]:
        """Saved papers with review state; `cluster` narrows to a summary cluster's papers."""
        within: list[int] | None = None
        if cluster:
            resolved = await self._reviews.resolve_cluster_paper_ids(cluster)
            if isinstance(resolved, dict):
                return [resolved]
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

    async def paper_details(self, paper_id: int) -> dict[str, Any]:
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
        notes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if notes:
            error = rules.validate_inline_notes(notes, len(paper_ids))
            if error:
                return {"updated": 0, "error": error}

        result = await self._reviews.set_status(paper_ids, status, reason, note, reviewed_by, notes)
        out: dict[str, Any] = {"updated": result["updated"]}
        if result["skipped"]:
            out["skipped_invalid_ids"] = result["skipped"]
        if result["note_ids"]:
            out["note_ids"] = result["note_ids"]
        return out

    async def review_batch(self, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply a batch of decisions; valid ones go through, invalid ones are reported by index.

        A decision is `{paper_id | paper_ids, status, reason, reviewed_by?, note?, notes?}`.
        Approving or "maybe"-ing a paper must leave something in the knowledge graph:
        either `notes` containing a claim/finding (single paper only) or per-paper
        notes recorded earlier. Rejected papers take no notes.
        """
        updated = 0
        errors: list[dict[str, Any]] = []
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
                errors.append({"index": idx, "error": error})
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
                errors.append({"index": idx, "error": result["error"]})
                continue
            updated += result["updated"]
            skipped += result.get("skipped_invalid_ids", [])
            note_ids += result.get("note_ids", [])
        out: dict[str, Any] = {"updated": updated, "errors": errors}
        if skipped:
            out["skipped_invalid_ids"] = skipped
        if note_ids:
            out["note_ids"] = note_ids
        return out

    async def _extraction_error(self, decision: dict[str, Any], ids: list[int]) -> str | None:
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
    ) -> dict[str, Any]:
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

    async def undo_last(self) -> dict[str, Any]:
        return await self._reviews.undo_last()

    # ─── Progress and summary ───────────────────────────────────────────

    async def progress(self) -> dict[str, Any]:
        counts = await self._reviews.live_counts()
        targets = await self._project.targets()

        document_sections = await self._sections.load_document_sections()
        words = sum(len((s["content"] or "").split()) for s in document_sections)
        cites = sum(count_cites(s["content"] or "") for s in document_sections)
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
            "warnings": rules.progress_warnings(counts.get("approved", 0), targets, words, density),
        }

    async def save_summary(self, summary: str, clusters: list[dict[str, Any]]) -> dict[str, str]:
        await self._reviews.save_summary(summary, clusters)
        return {"status": "saved"}

    async def get_summary(self) -> dict[str, Any] | None:
        data = await self._reviews.load_summary()
        if data is None:
            return None
        data["warnings"] = rules.summary_warnings(
            data["stale"], data["counts_snapshot"], data["counts_live"]
        )
        return data
