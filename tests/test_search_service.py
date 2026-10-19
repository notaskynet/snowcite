"""SearchService with fake source clients — no network."""

from pathlib import Path

from snowcite.container import container
from snowcite.domain.models import Paper
from snowcite.services.search import SearchService
from snowcite.sources.base import CitationSource, SourceClient


class FakeSource(SourceClient):
    def __init__(self, name: str, papers: list[Paper] | Exception):
        self.name = name  # type: ignore[assignment]
        self._papers = papers

    async def search(self, query, limit=20, year_from=None, year_to=None):
        if isinstance(self._papers, Exception):
            raise self._papers
        return self._papers


class FakeCitations(CitationSource):
    name = "semantic_scholar"

    def __init__(self, ss_id: str | None, related: list[Paper]):
        self._ss_id = ss_id
        self._related = related

    async def search(self, query, limit=20, year_from=None, year_to=None):
        return []

    async def get_related(self, paper_id, direction, limit=20):
        return self._related

    async def resolve_by_doi(self, doi):
        return self._ss_id


def _service(sources: dict, citations: CitationSource) -> SearchService:
    return SearchService(container.papers, container.project, sources, citations)


async def test_search_merges_sources_dedups_and_reports_failures(tmp_project: Path):
    a = Paper(source="openalex", source_id="1", title="Same", doi="10.1/x")
    b = Paper(source="crossref", source_id="2", title="Same", doi="10.1/x", abstract="richer")
    svc = _service(
        {
            "openalex": FakeSource("openalex", [a]),
            "crossref": FakeSource("crossref", [b]),
            "arxiv": FakeSource("arxiv", RuntimeError("boom")),
        },
        FakeCitations(None, []),
    )
    res = await svc.search("q", sources=["openalex", "crossref", "arxiv"])
    assert res["saved"] == 1 and res["failed_sources"] == ["arxiv"]
    saved = await container.papers.details(res["new_ids"][0])
    assert saved["abstract"] == "richer"


async def test_search_preview_does_not_save(tmp_project: Path):
    p = Paper(source="openalex", source_id="1", title="T", abstract="x" * 100)
    svc = _service({"openalex": FakeSource("openalex", [p])}, FakeCitations(None, []))
    res = await svc.search("q", sources=["openalex"], auto_save=False, abstract_max_chars=10)
    assert res["count"] == 1 and len(res["papers"][0]["abstract"]) == 10
    assert await container.papers.find(None, None, None, None, None, 10, 0) == []


async def test_expand_citations_resolves_via_doi_and_reports_errors(tmp_project: Path):
    await container.papers.persist(
        [
            Paper(source="openalex", source_id="1", title="With doi", doi="10.1/a"),
            Paper(source="openalex", source_id="2", title="No doi"),
        ]
    )
    related = [Paper(source="semantic_scholar", source_id="r", title="Ref")]
    svc = _service({}, FakeCitations("ss-1", related))
    ok = await svc.expand_citations(1, "references", 10, True, 0)
    assert ok["saved"] == 1

    assert "error" in await svc.expand_citations(2, "references", 10, True, 0)
    assert "not found" in (await svc.expand_citations(99, "references", 10, True, 0))["error"]
