import asyncio
from typing import Any

from snowcite.domain.models import Paper
from snowcite.domain.search import compact_paper, dedup_within_batch, sources_for_discipline
from snowcite.domain.types import Direction, Source
from snowcite.logging import log
from snowcite.sources.base import CitationSource, SourceClient
from snowcite.storage.repositories import PaperRepository, ProjectRepository


class SearchService:
    def __init__(
        self,
        papers: PaperRepository,
        project: ProjectRepository,
        sources: dict[Source, SourceClient],
        citations: CitationSource,
    ) -> None:
        self._papers = papers
        self._project = project
        self._sources = sources
        self._citations = citations

    async def search(
        self,
        query: str,
        sources: list[Source] | None = None,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
        auto_save: bool = True,
        abstract_max_chars: int = 0,
    ) -> dict[str, Any]:
        chosen = sources or sources_for_discipline(await self._project.discipline())
        results = await asyncio.gather(
            *(self._sources[s].search(query, limit, year_from, year_to) for s in chosen),
            return_exceptions=True,
        )

        found: list[Paper] = []
        failed: list[str] = []
        for name, res in zip(chosen, results, strict=True):
            if isinstance(res, Exception):
                log.warning("%s search failed: %r", name, res)
                failed.append(name)
                continue
            found.extend(res)

        result = await self._save_or_preview(
            dedup_within_batch(found), auto_save, abstract_max_chars
        )
        if failed:
            result["failed_sources"] = failed
        return result

    async def snowball(
        self,
        paper_ids: list[int],
        direction: Direction,
        limit: int,
        auto_save: bool,
        abstract_max_chars: int,
    ) -> dict[str, Any]:
        """Expand several papers in turn and merge the results; failures are per paper."""
        totals: dict[str, Any] = {"saved": 0, "duplicates": 0, "new_ids": [], "titles": []}
        previews: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for paper_id in paper_ids:
            res = await self._expand(paper_id, direction, limit, auto_save, abstract_max_chars)
            if "error" in res:
                errors.append({"paper_id": paper_id, "error": res["error"]})
            elif auto_save:
                totals["saved"] += res["saved"]
                totals["duplicates"] += res["duplicates"]
                totals["new_ids"] += res["new_ids"]
                totals["titles"] += res["titles"]
            else:
                previews += res["papers"]
        out = totals if auto_save else {"papers": previews, "count": len(previews)}
        if errors:
            out["errors"] = errors
        return out

    async def _expand(
        self,
        paper_id: int,
        direction: Direction,
        limit: int,
        auto_save: bool,
        abstract_max_chars: int,
    ) -> dict[str, Any]:
        """References or citations of one paper, via Semantic Scholar (DOI lookup as fallback)."""
        ref = await self._papers.source_ref(paper_id)
        if ref is None:
            return {"error": f"paper {paper_id} not found"}

        ss_id: str | None = None
        if ref["source"] == "semantic_scholar":
            ss_id = ref["source_id"]
        elif ref["doi"]:
            ss_id = await self._citations.resolve_by_doi(ref["doi"])
        if ss_id is None:
            return {
                "error": (
                    f"Cannot resolve paper {paper_id} (source={ref['source']}) to a Semantic "
                    f"Scholar id. No DOI available."
                )
            }

        related = await self._citations.get_related(ss_id, direction, limit)
        return await self._save_or_preview(related, auto_save, abstract_max_chars)

    async def _save_or_preview(
        self, papers: list[Paper], auto_save: bool, abstract_max_chars: int
    ) -> dict[str, Any]:
        """Persist and return a compact summary, or return a trimmed preview list."""
        if auto_save:
            persisted = await self._papers.persist(papers)
            return {
                "saved": persisted["saved"],
                "duplicates": persisted["duplicates"],
                "new_ids": persisted["new_ids"],
                "titles": persisted["new_titles"],
            }
        out = [compact_paper(p, abstract_max_chars) for p in papers]
        return {"papers": out, "count": len(out)}
