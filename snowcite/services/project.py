"""Project lifecycle: scaffold `.snowcite/`, store metadata, generate Claude files."""

from pathlib import Path
from typing import Any

from snowcite.services.claude_files import ClaudeFiles
from snowcite.storage.database import Database
from snowcite.storage.projects import create_project_dir, find_project_root, migrate_legacy_db
from snowcite.storage.repositories import ProjectRepository


class ProjectService:
    def __init__(self, db: Database, project: ProjectRepository, files: ClaudeFiles) -> None:
        self._db = db
        self._project = project
        self._files = files

    async def init(
        self,
        metadata: dict[str, Any] | None,
        update: bool,
        migrate_from_legacy: bool,
        update_agents: bool,
    ) -> dict[str, Any]:
        """Initialize (or update) the project in the current working directory.

        `update=True` keeps everything already stored (criteria, sections, papers)
        and only merges metadata and regenerates the Claude files.
        """
        metadata = metadata or {}

        # 1. Directory scaffold + legacy DB migration (pre-T20 layout).
        already = find_project_root()
        already_initialized = already is not None and already.resolve() == Path.cwd().resolve()
        snow = create_project_dir()
        root = snow.parent
        migrated = migrate_legacy_db() if migrate_from_legacy else False

        # 2. DB + schema (runs migrations too).
        await self._db.init()

        # 3. Persist metadata. With update=True, merge into what's stored.
        if metadata:
            effective = {**await self._project.load_metadata(), **metadata} if update else metadata
            await self._project.save_metadata(effective)
        else:
            effective = await self._project.load_metadata()

        # 4. Files for Claude Code. settings.json is never silently modified —
        # the diff goes back so Claude can ask the user.
        claude_md = self._files.write_claude_md(root, effective)
        agents_written = self._files.write_agents(root, effective, overwrite=update_agents)

        return {
            "project_root": str(root),
            "snowcite_dir": str(snow),
            "already_initialized": already_initialized,
            "migrated_legacy": migrated,
            "metadata_effective": effective,
            "claude_md_path": str(claude_md),
            "agents_written": agents_written,
            "settings_diff": self._files.settings_diff(root),
        }

    async def metadata(self) -> dict[str, Any]:
        return await self._project.load_metadata()

    def apply_settings_diff(self, action: str) -> dict[str, Any]:
        root = find_project_root()
        if root is None:
            return {"applied": False, "error": "no active project"}
        return self._files.apply_settings(root, action)
