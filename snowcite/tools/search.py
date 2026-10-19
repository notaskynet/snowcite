"""Search and persistence tools."""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import Direction, Source, Status


@mcp.tool()
async def search_papers(
    query: str,
    sources: list[Source] | None = None,
    limit: int = 20,
    year_from: int | None = None,
    year_to: int | None = None,
    auto_save: bool = True,
    abstract_max_chars: int = 0,
) -> dict[str, Any]:
    """Search arXiv / Semantic Scholar / OpenAlex in parallel, dedup by DOI/title.

    By default (auto_save=True) persists new papers to the DB and returns a compact
    summary {saved, duplicates, new_ids, titles} — abstracts never enter the chat
    context, which keeps review sessions lean and avoids false-positive safety triggers
    when harmful-sounding abstracts accumulate.

    Set auto_save=False for preview mode; then the response includes the full paper list
    (with abstracts trimmed to abstract_max_chars; 0 drops the field entirely).

    A single source failure is logged and does not abort the search.
    """
    return await container.search.search(
        query, sources, limit, year_from, year_to, auto_save, abstract_max_chars
    )


@mcp.tool()
async def save_papers(papers: list[dict[str, Any]]) -> dict[str, Any]:
    """Insert papers with DOI uniqueness + fuzzy-title fallback dedup.

    Returns {saved, duplicates, new_ids, new_titles}. Prefer
    `search_papers(auto_save=True)`; this tool exists for manual re-insertion
    or imported data.
    """
    return await container.search.save_papers(papers)


@mcp.tool()
async def get_saved_papers(
    status: Status | None = None,
    source: Source | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Fetch saved papers with optional filters. Joins review status."""
    return await container.search.find_saved(
        status, source, year_from, year_to, search, limit, offset
    )


@mcp.tool()
async def get_paper_details(paper_id: int) -> dict[str, Any]:
    """Full paper record by id, including review status and citation counts."""
    return await container.search.details(paper_id)


@mcp.tool()
async def expand_citations(
    paper_id: int,
    direction: Direction,
    limit: int = 20,
    auto_save: bool = True,
    abstract_max_chars: int = 0,
) -> dict[str, Any]:
    """Fetch references or citations for one paper; by default persist new ones.

    Uses Semantic Scholar API. For arXiv / OpenAlex papers without a Semantic Scholar
    id, falls back to DOI lookup.

    With auto_save=True (default), new papers land in `unreviewed` and the response is
    {saved, duplicates, new_ids, titles}. With auto_save=False, returns full paper list
    with abstracts trimmed to abstract_max_chars (0 = omitted).
    """
    return await container.search.expand_citations(
        paper_id, direction, limit, auto_save, abstract_max_chars
    )
