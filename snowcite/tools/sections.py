"""Section-as-entity tools (Phase 3 of v0.3).

A section row owns its own scope, draft, status, and severity counters. The
critique/revise loop in Phase 5 reads and writes these fields per section,
which is why titles + scope live in the DB (not just in a singleton outline
JSON like the v0.2 path).

`scope` is a structured dict — `{clusters, keywords, questions}` — so that
`research_section` (Phase 4) can build search queries from it without parsing
free-form text.
"""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import SectionStatus


@mcp.tool()
async def create_section(
    title: str,
    scope: dict[str, Any] | None = None,
    parent_id: int | None = None,
    position: int | None = None,
) -> dict[str, Any]:
    """Create a single section. Returns `{id}`.

    `scope` is a dict with optional keys `clusters`, `keywords`, `questions`
    (each a list of strings) — the prompts used by `research_section` and the
    critique loop. Unknown keys are dropped.
    `position` orders siblings; if omitted, appended after current siblings.
    """
    return await container.section_service.create(title, scope, parent_id, position)


@mcp.tool()
async def bulk_create_sections(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Bulk-create sections from a proposed outline.

    Each item: `{title, scope?, parent_id?, position?}`. Order in the input
    list becomes default `position` if not provided. Returns
    `{inserted: N, ids: [...], errors: [{index, error}]}`.

    Use after Claude proposes an outline from `review_summary` clusters and
    the user approves — single round-trip for the whole structure.
    """
    return await container.section_service.bulk_create(sections)


@mcp.tool()
async def list_sections() -> list[dict[str, Any]]:
    """All sections, ordered by (parent_id, position). Hierarchical via parent_id."""
    return await container.section_service.list_all()


@mcp.tool()
async def get_section(section_id: int) -> dict[str, Any] | None:
    """Full record for one section, or None if missing."""
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
) -> dict[str, Any]:
    """Patch fields on a section. Pass only the fields to change.

    Note: severity counters (`blockers`, `should_fix`, `nits`) are written by
    `critique_section` / `revise_section` (Phase 5), not by this tool.
    Setting `parent_id` does not validate against cycles — keep the tree sane.
    """
    return await container.section_service.update(
        section_id, title, scope, draft, status, parent_id, position
    )


@mcp.tool()
async def delete_section(section_id: int) -> dict[str, Any]:
    """Remove a section and all descendants (cascade via parent_id FK)."""
    return await container.section_service.delete(section_id)


@mcp.tool()
async def get_outline_inputs() -> dict[str, Any]:
    """Building blocks for proposing an outline: thesis + clusters + criteria.

    Returns `{thesis, clusters, criteria}` so Claude can propose a section
    structure without three separate round-trips. Designed to be the single
    read before `bulk_create_sections`.
    """
    return await container.section_service.outline_inputs()
