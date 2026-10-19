from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import SectionStatus


@mcp.tool()
async def create_sections(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Create sections from a proposed outline in one call.

    Each item: `{title, scope?, parent_id?, position?}`; `scope` is
    `{clusters, keywords, questions}` (lists of strings; unknown keys dropped) — the
    prompts used by `research_section` and the critique loop. Order in the list
    becomes the default `position` among siblings. Returns
    `{inserted, ids, errors: [{index, error}]}`.
    """
    return await container.section_service.bulk_create(sections)


@mcp.tool()
async def get_sections(
    section_id: int | None = None,
) -> list[dict[str, Any]] | dict[str, Any] | None:
    """One section by id (full record, or None) — or, without id, all sections.

    Listing is ordered by (parent_id, position) and is hierarchical via `parent_id`.
    """
    if section_id is None:
        return await container.section_service.list_all()
    return await container.section_service.get(section_id)


@mcp.tool()
async def update_section(
    section_id: int,
    title: str | None = None,
    scope: dict[str, Any] | None = None,
    draft: str | None = None,
    status: SectionStatus | None = None,
    parent_id: int | None = None,
    position: int | None = None,
    delete: bool = False,
) -> dict[str, Any]:
    """Patch fields on a section (pass only what changes), or delete it.

    `delete=True` removes the section and all its descendants. Severity counters
    (`blockers`, `should_fix`, `nits`) are written by the critique tools, not here.
    Setting `parent_id` does not validate against cycles — keep the tree sane.
    """
    if delete:
        return await container.section_service.delete(section_id)
    return await container.section_service.update(
        section_id, title, scope, draft, status, parent_id, position
    )
