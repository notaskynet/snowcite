"""Project initialization — creates `.snowcite/` and persists project metadata.

Claude collects the metadata with the user (AskUserQuestion — MCP tools can't prompt
users themselves), then calls `init_project(metadata=...)`.
"""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container


@mcp.tool()
async def init_project(
    metadata: dict[str, Any] | None = None,
    update: bool = False,
    migrate_from_legacy: bool = True,
) -> dict[str, Any]:
    """Initialize (or update) the snowcite project in the current working directory.

    Creates `.snowcite/` (with `papers.db`, `cache/`) and persists `metadata` into the
    `project_metadata` singleton: author, supervisor, institution, department, year,
    work_type, target_length, language, discipline, standard, methodology,
    review_strictness, deadline and the targets target_pages, target_sources_min/max,
    target_words, citation_density_target. Unknown keys are kept under `extra`.

    `update=True` merges `metadata` into what is stored and keeps criteria, papers,
    notes and sections — use it when the project profile changes mid-work. Without
    `metadata` the call just returns what is stored.
    """
    return await container.project_service.init(metadata, update, migrate_from_legacy)


@mcp.tool()
async def get_project_metadata() -> dict[str, Any]:
    """Return the project profile (language, standard, discipline, targets, ...); {} if never set.

    Writing skills read `language` and `standard` from here.
    """
    return await container.project_service.metadata()
