from pathlib import Path

from snowcite.domain.records import ProjectMetadata
from snowcite.domain.results import InitResult
from snowcite.storage.database import Database
from snowcite.storage.projects import create_project_dir, find_project_root, migrate_legacy_db
from snowcite.storage.repositories import ProjectRepository


class ProjectService:
    def __init__(self, db: Database, project: ProjectRepository) -> None:
        self._db = db
        self._project = project

    async def init(
        self,
        metadata: ProjectMetadata | None,
        update: bool,
        migrate_from_legacy: bool,
    ) -> InitResult:
        """Initialize (or update) the project in the current working directory.

        `update=True` keeps everything already stored (criteria, sections, papers)
        and only merges metadata.
        """
        metadata = metadata or {}

        already = find_project_root()
        already_initialized = already is not None and already.resolve() == Path.cwd().resolve()
        snow = create_project_dir()
        migrated = migrate_legacy_db() if migrate_from_legacy else False

        await self._db.init()  # schema + migrations

        if metadata:
            effective = {**await self._project.load_metadata(), **metadata} if update else metadata
            await self._project.save_metadata(effective)
        else:
            effective = await self._project.load_metadata()

        return {
            "project_root": str(snow.parent),
            "snowcite_dir": str(snow),
            "already_initialized": already_initialized,
            "migrated_legacy": migrated,
            "metadata_effective": effective,
        }

    async def metadata(self) -> ProjectMetadata:
        return await self._project.load_metadata()
