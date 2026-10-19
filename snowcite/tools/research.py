"""Section-scoped research (Phase 4 of v0.3).

Drives `search_papers` from a section's `scope` so the user can fill gaps in
one section without manually composing queries. Newly persisted papers get
linked to the section via `paper_section_links` for traceability — the user
can later see "this paper entered the corpus while researching the methods
section". Existing papers (duplicates) are not auto-linked: rediscovery isn't
the same as discovery, and the user may link them manually if they consider
the paper relevant.

Snowball is expensive — this tool deliberately does not call
`expand_citations` automatically. The user runs it explicitly once they've
seen what `research_section` brought in.
"""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.tools.search import search_papers


@mcp.tool()
async def research_section(
    section_id: int,
    max_per_query: int = 10,
    year_from: int | None = None,
    year_to: int | None = None,
) -> dict[str, Any]:
    """Run scoped searches from a section's scope and link new papers to it.

    Builds one query per entry in `scope.keywords` and `scope.questions`,
    calls `search_papers` for each, persists new papers (default search behaviour),
    and links the freshly-saved ids to this section in `paper_section_links`.

    Returns `{queries: [{query, saved, new_ids}], total_new, failed_sources?}`.
    Sections without keywords/questions return early — set scope first via
    `update_section`.
    """
    section = await container.section_service.get(section_id)
    if section is None:
        return {"error": f"section {section_id} not found"}

    scope = section["scope"]
    queries: list[str] = []
    queries.extend(q for q in scope.get("keywords", []) if q.strip())
    queries.extend(q for q in scope.get("questions", []) if q.strip())
    if not queries:
        return {"error": "section scope has no keywords or questions to search"}

    per_query: list[dict[str, Any]] = []
    all_new_ids: list[int] = []
    failed_sources: set[str] = set()
    for q in queries:
        res = await search_papers(
            query=q,
            limit=max_per_query,
            year_from=year_from,
            year_to=year_to,
            auto_save=True,
        )
        new_ids = res.get("new_ids", [])
        all_new_ids.extend(new_ids)
        per_query.append(
            {
                "query": q,
                "saved": res.get("saved", 0),
                "duplicates": res.get("duplicates", 0),
                "new_ids": new_ids,
            }
        )
        for f in res.get("failed_sources", []) or []:
            failed_sources.add(f)

    if all_new_ids:
        await container.section_service.link_new_papers(
            section_id, list(_zip_ids_with_queries(per_query))
        )

    out: dict[str, Any] = {
        "section_id": section_id,
        "queries": per_query,
        "total_new": len(all_new_ids),
    }
    if failed_sources:
        out["failed_sources"] = sorted(failed_sources)
    return out


def _zip_ids_with_queries(per_query: list[dict[str, Any]]):
    """Flatten per-query results to (paper_id, query) pairs for link inserts."""
    for entry in per_query:
        for pid in entry["new_ids"]:
            yield pid, entry["query"]


@mcp.tool()
async def link_paper_to_section(
    paper_id: int,
    section_id: int,
    via_query: str | None = None,
) -> dict[str, Any]:
    """Manually attach a paper to a section. Idempotent.

    Use when an already-saved paper turns out to be relevant to a section —
    `research_section` only links *newly discovered* papers, so existing ones
    need this hook.
    """
    return await container.section_service.link_paper(paper_id, section_id, via_query)


@mcp.tool()
async def unlink_paper_from_section(paper_id: int, section_id: int) -> dict[str, Any]:
    """Remove a paper↔section link without touching the paper itself."""
    return await container.section_service.unlink_paper(paper_id, section_id)


@mcp.tool()
async def get_section_papers(section_id: int) -> list[dict[str, Any]]:
    """Papers linked to this section, with current review status and the query
    that surfaced them (if any). Newest first."""
    return await container.section_service.section_papers(section_id)
