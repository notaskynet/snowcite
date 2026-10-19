from typing import Any

from snowcite.app import mcp
from snowcite.container import container


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
    return await container.section_service.research(section_id, max_per_query, year_from, year_to)


@mcp.tool()
async def section_papers(
    section_id: int,
    link: list[int] | None = None,
    unlink: list[int] | None = None,
    via_query: str | None = None,
) -> dict[str, Any]:
    """Papers tied to a section; optionally link or unlink some first.

    `link` attaches already-saved papers (idempotent; `research_section` only links
    papers it newly discovers, so existing ones need this). `unlink` removes a link
    without touching the paper. Returns `{papers, errors?}` where `papers` carries
    review status and the query that surfaced each one, newest first.
    """
    errors: list[dict[str, Any]] = []
    for paper_id in link or []:
        res = await container.section_service.link_paper(paper_id, section_id, via_query)
        if "error" in res:
            errors.append({"paper_id": paper_id, "error": res["error"]})
    for paper_id in unlink or []:
        await container.section_service.unlink_paper(paper_id, section_id)
    out: dict[str, Any] = {"papers": await container.section_service.section_papers(section_id)}
    if errors:
        out["errors"] = errors
    return out
