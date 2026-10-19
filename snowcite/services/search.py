"""Search across sources, snowball through citations, read saved papers."""

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

    async def save_papers(self, papers: list[dict[str, Any]]) -> dict[str, Any]:
        return dict(await self._papers.persist([Paper.model_validate(p) for p in papers]))

    async def expand_citations(
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

    async def find_saved(
        self,
        status: str | None,
        source: str | None,
        year_from: int | None,
        year_to: int | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        return await self._papers.find(status, source, year_from, year_to, search, limit, offset)

    async def details(self, paper_id: int) -> dict[str, Any]:
        paper = await self._papers.details(paper_id)
        return paper if paper is not None else {"error": f"paper {paper_id} not found"}

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
