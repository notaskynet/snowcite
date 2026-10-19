from snowcite.domain import rules
from snowcite.domain.inputs import CritiqueIssue, ScopeInput, SectionInput
from snowcite.domain.records import ErrorResult, LinkedPaper, SectionRecord
from snowcite.domain.results import (
    CritiqueInputs,
    CritiqueRecorded,
    IndexedError,
    OutlineInputs,
    QueryResult,
    ResearchResult,
    SectionCreated,
    SectionDeleted,
    SectionLinked,
    SectionRevised,
    SectionsCreated,
    SectionUnlinked,
    SectionUpdated,
)
from snowcite.domain.types import SectionStatus
from snowcite.services.artifacts import brief
from snowcite.services.search import SearchService
from snowcite.storage.repositories import (
    ArtifactRepository,
    NoteRepository,
    PaperRepository,
    ProjectRepository,
    ReviewRepository,
    SectionRepository,
)
from snowcite.storage.repositories.sections import NewSection, SectionPatch


class SectionService:
    def __init__(
        self,
        sections: SectionRepository,
        notes: NoteRepository,
        papers: PaperRepository,
        reviews: ReviewRepository,
        project: ProjectRepository,
        search: SearchService,
        artifacts: ArtifactRepository,
    ) -> None:
        self._sections = sections
        self._notes = notes
        self._papers = papers
        self._reviews = reviews
        self._project = project
        self._search = search
        self._artifacts = artifacts

    # ─── Structure ──────────────────────────────────────────────────────

    async def create(
        self,
        title: str,
        scope: ScopeInput | None,
        parent_id: int | None,
        position: int | None,
    ) -> SectionCreated | ErrorResult:
        if not title.strip():
            return {"error": "title is empty"}
        (new_id,) = await self._sections.create_many(
            [
                {
                    "title": title.strip(),
                    "scope": rules.normalize_scope(scope),
                    "parent_id": parent_id,
                    "position": position,
                }
            ]
        )
        return {"id": new_id}

    async def bulk_create(self, sections: list[SectionInput]) -> SectionsCreated:
        valid: list[NewSection] = []
        errors: list[IndexedError] = []
        for idx, item in enumerate(sections):
            title = item.get("title", "")
            if not isinstance(title, str) or not title.strip():
                errors.append({"index": idx, "error": "title is empty"})
                continue
            valid.append(
                {
                    "title": title.strip(),
                    "scope": rules.normalize_scope(item.get("scope")),
                    "parent_id": item.get("parent_id"),
                    "position": item.get("position"),
                }
            )
        ids = await self._sections.create_many(valid)
        return {"inserted": len(ids), "ids": ids, "errors": errors}

    async def list_all(self) -> list[SectionRecord]:
        return await self._sections.list_all()

    async def get(self, section_id: int) -> SectionRecord | None:
        return await self._sections.get(section_id)

    async def update(
        self,
        section_id: int,
        title: str | None,
        scope: ScopeInput | None,
        draft: str | None,
        status: str | None,
        parent_id: int | None,
        position: int | None,
    ) -> SectionUpdated | ErrorResult:
        if all(v is None for v in (title, scope, draft, status, parent_id, position)):
            return {"error": "no fields to update"}
        patch: SectionPatch = {}
        if title is not None:
            if not title.strip():
                return {"error": "title is empty"}
            patch["title"] = title.strip()
        if scope is not None:
            patch["scope"] = rules.normalize_scope(scope)
        if draft is not None:
            patch["draft"] = draft
        if status is not None:
            patch["status"] = status
        if parent_id is not None:
            if parent_id == section_id:
                return {"error": "section cannot be its own parent"}
            patch["parent_id"] = parent_id
        if position is not None:
            patch["position"] = position
        if not await self._sections.update(section_id, patch):
            return {"error": f"section {section_id} not found"}
        return {"updated": True, "id": section_id}

    async def delete(self, section_id: int) -> SectionDeleted:
        return {"deleted": await self._sections.delete(section_id)}

    async def outline_inputs(self) -> OutlineInputs:
        summary = await self._reviews.load_summary()
        criteria = await self._reviews.latest_criteria()
        return {
            "thesis": await self._project.thesis(),
            "clusters": summary["clusters"] if summary else [],
            "criteria": criteria["criteria_text"] if criteria else None,
        }

    # ─── Critique loop ──────────────────────────────────────────────────

    async def critique_inputs(self, section_id: int) -> CritiqueInputs | ErrorResult:
        section = await self._sections.get(section_id)
        if section is None:
            return {"error": f"section {section_id} not found"}
        clusters = [c for c in section["scope"]["clusters"] if c]
        linked = await self._sections.linked_papers(section_id, newest_discovery_first=False)
        return {
            "section": {
                "id": section["id"],
                "title": section["title"],
                "scope": section["scope"],
                "draft": section["draft"],
                "status": section["status"],
                "severity": section["severity"],
                "critique_iterations": section["critique_iterations"],
            },
            "notes": await self._notes.in_clusters(clusters),
            "artifacts": [brief(a) for a in await self._artifacts.list(included_only=True)],
            "linked_papers": [_without_discovery(p) for p in linked],
        }

    async def record_critique(
        self, section_id: int, issues: list[CritiqueIssue]
    ) -> CritiqueRecorded | ErrorResult:
        counts = rules.count_severities(issues)
        if isinstance(counts, str):
            return {"error": counts}
        iteration = await self._sections.record_critique(section_id, counts)
        if iteration is None:
            return {"error": f"section {section_id} not found"}
        should_stop, reason = rules.critique_verdict(counts["blocker"], iteration)
        return {
            "should_stop": should_stop,
            "reason": reason,
            "severity": {
                "blockers": counts["blocker"],
                "should_fix": counts["should_fix"],
                "nits": counts["nit"],
            },
            "iteration": iteration,
            "issues": issues,  # type: ignore[typeddict-item]
        }

    async def revise(
        self, section_id: int, new_draft: str, mark_done: bool
    ) -> SectionRevised | ErrorResult:
        status: SectionStatus = "done" if mark_done else "drafting"
        if not await self._sections.revise(section_id, new_draft, status):
            return {"error": f"section {section_id} not found"}
        return {"updated": True, "id": section_id, "status": status}

    # ─── Paper links ────────────────────────────────────────────────────

    async def link_paper(
        self, paper_id: int, section_id: int, via_query: str | None
    ) -> SectionLinked | ErrorResult:
        # Validate both ends for a clear error rather than a foreign-key bark.
        if not await self._papers.exists(paper_id):
            return {"error": f"paper {paper_id} not found"}
        if await self._sections.get(section_id) is None:
            return {"error": f"section {section_id} not found"}
        await self._sections.link_papers(section_id, [(paper_id, via_query)])
        return {"linked": True}

    async def research(
        self, section_id: int, max_per_query: int, year_from: int | None, year_to: int | None
    ) -> ResearchResult | ErrorResult:
        """One search per scope keyword/question; newly saved papers get linked to the section.

        Deliberately no snowball: duplicates are not auto-linked and citation
        expansion stays the user's explicit call.
        """
        section = await self._sections.get(section_id)
        if section is None:
            return {"error": f"section {section_id} not found"}
        scope = section["scope"]
        queries = [q for q in (*scope["keywords"], *scope["questions"]) if q.strip()]
        if not queries:
            return {"error": "section scope has no keywords or questions to search"}

        per_query: list[QueryResult] = []
        failed_sources: set[str] = set()
        for q in queries:
            res = await self._search.search_and_save(q, None, max_per_query, year_from, year_to)
            per_query.append(
                {
                    "query": q,
                    "saved": res["saved"],
                    "duplicates": res["duplicates"],
                    "new_ids": res["new_ids"],
                }
            )
            failed_sources.update(res.get("failed_sources", []))

        links = [(pid, e["query"]) for e in per_query for pid in e["new_ids"]]
        if links:
            await self._sections.link_papers(section_id, links)

        out: ResearchResult = {
            "section_id": section_id,
            "queries": per_query,
            "total_new": len(links),
        }
        if failed_sources:
            out["failed_sources"] = sorted(failed_sources)
        return out

    async def unlink_paper(self, paper_id: int, section_id: int) -> SectionUnlinked:
        return {"deleted": await self._sections.unlink_paper(paper_id, section_id)}

    async def section_papers(self, section_id: int) -> list[LinkedPaper]:
        return await self._sections.linked_papers(section_id, newest_discovery_first=True)


def _without_discovery(paper: LinkedPaper) -> LinkedPaper:
    return {k: v for k, v in paper.items() if k != "discovered_at"}  # type: ignore[return-value]
