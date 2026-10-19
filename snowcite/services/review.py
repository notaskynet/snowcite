"""Review workflow: criteria, batch decisions, progress, rolling summary."""

from typing import Any

from snowcite.domain import rules
from snowcite.domain.citations import count_cites
from snowcite.storage.repositories import ProjectRepository, ReviewRepository, SectionRepository


class ReviewService:
    def __init__(
        self,
        reviews: ReviewRepository,
        sections: SectionRepository,
        project: ProjectRepository,
    ) -> None:
        self._reviews = reviews
        self._sections = sections
        self._project = project

    # ─── Criteria and batches ───────────────────────────────────────────

    async def set_criteria(self, criteria_text: str) -> dict[str, int]:
        return {"id": await self._reviews.add_criteria(criteria_text)}

    async def get_criteria(self) -> dict[str, Any] | None:
        return await self._reviews.latest_criteria()

    async def unreviewed(
        self,
        limit: int,
        source: str | None,
        year_from: int | None,
        year_to: int | None,
        include_abstracts: bool,
    ) -> list[dict[str, Any]]:
        return await self._reviews.unreviewed(limit, source, year_from, year_to, include_abstracts)

    async def low_confidence(self, status: str | None, limit: int) -> list[dict[str, Any]]:
        return await self._reviews.low_confidence(status, limit)

    # ─── Decisions ──────────────────────────────────────────────────────

    async def set_status(
        self,
        paper_ids: list[int],
        status: str,
        reason: str,
        note: str | None,
        reviewed_by: str,
        notes: list[dict[str, Any]] | None,
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

    async def papers_for_writing(
        self, cluster: str | None, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        paper_ids: list[int] | None = None
        if cluster:
            resolved = await self._reviews.resolve_cluster_paper_ids(cluster)
            if isinstance(resolved, dict):
                return [resolved]
            paper_ids = resolved
        return await self._reviews.approved_for_writing(paper_ids, limit, offset)
