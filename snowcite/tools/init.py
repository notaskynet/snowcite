"""Project initialization — creates `.snowcite/`, persists metadata, writes CLAUDE.md.

Claude drives the onboarding dialog through AskUserQuestion (MCP tools can't initiate
user-facing prompts). It collects metadata, then calls `init_project(metadata=...)`
which persists it, re-renders CLAUDE.md from `templates/claude_md.j2`, and hands
back a diff for `.claude/settings.json` that Claude can apply after asking the user
how to resolve it.
"""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container


@mcp.tool()
async def init_project(
    metadata: dict[str, Any] | None = None,
    update: bool = False,
    migrate_from_legacy: bool = True,
    update_agents: bool = False,
) -> dict[str, Any]:
    """Initialize (or update) the snowcite project in the current working directory.

    Creates `.snowcite/` (with `papers.db`, `cache/`), persists metadata into the
    `project_metadata` singleton, and regenerates `CLAUDE.md` from the bundled
    Jinja template.

    For `.claude/settings.json`, we don't silently overwrite — `settings_diff` in
    the return value lists what's missing. Claude should ask the user via
    `AskUserQuestion` whether to merge / overwrite (backup in .bak) / skip, then
    apply the chosen action itself.

    `update=True` keeps existing `review_criteria`, `sections`, `papers` etc. —
    it only touches metadata + CLAUDE.md + settings diff. Use this when the user
    tweaks their project profile mid-work.
    """
    return await container.project_service.init(
        metadata, update, migrate_from_legacy, update_agents
    )


@mcp.tool()
async def get_project_metadata() -> dict[str, Any]:
    """Return the current project_metadata row (empty dict if never set)."""
    return await container.project_service.metadata()


@mcp.tool()
async def apply_settings_diff(action: str) -> dict[str, Any]:
    """Apply the user's decision for `.claude/settings.json`.

    `action`:
    - `"create"` — create the file fresh (when it didn't exist).
    - `"merge"` — add missing snowcite entries to existing allow list.
    - `"overwrite"` — back up existing file as `settings.json.bak`, then replace.
    - `"skip"` — do nothing. Claude relays the consequence to the user.
    """
    return container.project_service.apply_settings_diff(action)
