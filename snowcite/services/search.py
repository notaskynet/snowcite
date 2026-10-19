import asyncio

from snowcite.domain.models import Paper
from snowcite.domain.records import ErrorResult
from snowcite.domain.results import PaperError, PaperPreview, SearchPreview, SearchSummary
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

    async def _gather(
        self,
        query: str,
        sources: list[Source] | None,
        limit: int,
        year_from: int | None,
        year_to: int | None,
    ) -> tuple[list[Paper], list[str]]:
        """Query the chosen sources in parallel; returns (merged papers, failed source names)."""
        chosen = sources or sources_for_discipline(await self._project.discipline())
        results = await asyncio.gather(
            *(self._sources[s].search(query, limit, year_from, year_to) for s in chosen),
            return_exceptions=True,
        )
        found: list[Paper] = []
        failed: list[str] = []
        for name, res in zip(chosen, results, strict=True):
            if isinstance(res, BaseException):
                log.warning("%s search failed: %r", name, res)
                failed.append(name)
                continue
            found.extend(res)
        return dedup_within_batch(found), failed

    async def search_and_save(
        self,
        query: str,
        sources: list[Source] | None,
        limit: int,
        year_from: int | None,
        year_to: int | None,
    ) -> SearchSummary:
        papers, failed = await self._gather(query, sources, limit, year_from, year_to)
        summary = await self._save(papers)
        if failed:
            summary["failed_sources"] = failed
        return summary

    async def preview(
        self,
        query: str,
        sources: list[Source] | None,
        limit: int,
        year_from: int | None,
        year_to: int | None,
        abstract_max_chars: int,
    ) -> SearchPreview:
        papers, failed = await self._gather(query, sources, limit, year_from, year_to)
        out = _preview(papers, abstract_max_chars)
        if failed:
            out["failed_sources"] = failed
        return out

    async def search(
        self,
        query: str,
        sources: list[Source] | None = None,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
        auto_save: bool = True,
        abstract_max_chars: int = 0,
    ) -> SearchSummary | SearchPreview:
        if auto_save:
            return await self.search_and_save(query, sources, limit, year_from, year_to)
        return await self.preview(query, sources, limit, year_from, year_to, abstract_max_chars)

    async def snowball(
        self,
        paper_ids: list[int],
        direction: Direction,
        limit: int,
        auto_save: bool,
        abstract_max_chars: int,
    ) -> SearchSummary | SearchPreview:
        """Expand several papers in turn and merge the results; failures are per paper."""
        errors: list[PaperError] = []
        related: list[Paper] = []
        for paper_id in paper_ids:
            found = await self._related(paper_id, direction, limit)
            if isinstance(found, dict):
                errors.append({"paper_id": paper_id, "error": found["error"]})
            else:
                related += found

        out: SearchSummary | SearchPreview
        if auto_save:
            out = await self._save(related)
        else:
            out = _preview(related, abstract_max_chars)
        if errors:
            out["errors"] = errors
        return out

    async def _related(
        self, paper_id: int, direction: Direction, limit: int
    ) -> list[Paper] | ErrorResult:
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
        return await self._citations.get_related(ss_id, direction, limit)

    async def _save(self, papers: list[Paper]) -> SearchSummary:
        persisted = await self._papers.persist(papers)
        return {
            "saved": persisted["saved"],
            "duplicates": persisted["duplicates"],
            "new_ids": persisted["new_ids"],
            "titles": persisted["new_titles"],
        }


def _preview(papers: list[Paper], abstract_max_chars: int) -> SearchPreview:
    records: list[PaperPreview] = [compact_paper(p, abstract_max_chars) for p in papers]
    return {"papers": records, "count": len(records)}
