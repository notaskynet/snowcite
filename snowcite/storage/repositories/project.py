import json
from collections.abc import Mapping
from typing import Any

import aiosqlite
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from snowcite.domain.records import ProjectMetadata, ProjectTargets, ThesisRecord
from snowcite.storage.database import Database
from snowcite.storage.models import ProjectMetadataRow, ThesisRow
from snowcite.storage.projects import NoProjectError


# Columns of the `project_metadata` singleton that callers may set; keys outside it
# are kept in `extra_json` untouched.
METADATA_FIELDS = (
    "author",
    "supervisor",
    "institution",
    "department",
    "year",
    "work_type",
    "target_length",
    "language",
    "discipline",
    "standard",
    "methodology",
    "review_strictness",
    "deadline",
    "target_pages",
    "target_sources_min",
    "target_sources_max",
    "target_words",
    "citation_density_target",
)
_TARGET_FIELDS = (
    "target_sources_min",
    "target_sources_max",
    "target_words",
    "citation_density_target",
)


class ProjectRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def targets(self) -> ProjectTargets:
        """Non-null target metrics (sources min/max, words, citation density)."""
        async with self._db.session() as session:
            row = await session.get(ProjectMetadataRow, 1)
        if row is None:
            return {}
        return {k: getattr(row, k) for k in _TARGET_FIELDS if getattr(row, k) is not None}  # type: ignore[return-value]

    async def load_metadata(self) -> ProjectMetadata:
        """The profile without bookkeeping columns or nulls; {} if never saved."""
        async with self._db.session() as session:
            row = await session.get(ProjectMetadataRow, 1)
        if row is None:
            return {}
        data: dict[str, Any] = {
            k: getattr(row, k) for k in METADATA_FIELDS if getattr(row, k) is not None
        }
        extra = json.loads(row.extra_json) if row.extra_json else {}
        if extra:
            data["extra"] = extra
        return data  # type: ignore[return-value]

    async def save_metadata(self, metadata: Mapping[str, Any]) -> None:
        """Upsert the singleton; keys outside `METADATA_FIELDS` go to extra_json."""
        known = {k: metadata[k] for k in METADATA_FIELDS if k in metadata}
        extra = {k: v for k, v in metadata.items() if k not in METADATA_FIELDS}
        values = {**known, "extra_json": json.dumps(extra) if extra else "{}"}
        stmt = (
            sqlite_insert(ProjectMetadataRow)
            .values(id=1, **values)
            .on_conflict_do_update(
                index_elements=[ProjectMetadataRow.id],
                set_={**values, "updated_at": func.current_timestamp()},
            )
        )
        async with self._db.session() as session, session.begin():
            await session.execute(stmt)

    async def discipline(self) -> str | None:
        """`project_metadata.discipline`; None when no project is active yet.

        Catches only "no active project" / "schema not initialised" / IO errors —
        programmer errors surface normally.
        """
        try:
            async with self._db.session() as session:
                return await session.scalar(
                    select(ProjectMetadataRow.discipline).where(ProjectMetadataRow.id == 1)
                )
        except (NoProjectError, aiosqlite.Error, OSError):
            return None

    # ─── Thesis ─────────────────────────────────────────────────────────

    async def thesis(self) -> str | None:
        async with self._db.session() as session:
            return await session.scalar(select(ThesisRow.content).where(ThesisRow.id == 1))

    async def thesis_record(self) -> ThesisRecord | None:
        async with self._db.session() as session:
            row = await session.get(ThesisRow, 1)
        if row is None:
            return None
        return {"content": row.content, "updated_at": row.updated_at}

    async def save_thesis(self, content: str) -> None:
        values = {"content": content, "updated_at": func.current_timestamp()}
        stmt = (
            sqlite_insert(ThesisRow)
            .values(id=1, **values)
            .on_conflict_do_update(index_elements=[ThesisRow.id], set_=values)
        )
        async with self._db.session() as session, session.begin():
            await session.execute(stmt)
