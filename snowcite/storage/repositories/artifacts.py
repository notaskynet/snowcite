import json
from typing import Any

from sqlalchemy import delete, select, update

from snowcite.domain.records import ArtifactRecord
from snowcite.domain.types import ArtifactType
from snowcite.storage.database import Database, affected
from snowcite.storage.models import ArtifactRow


def _artifact_record(row: ArtifactRow) -> ArtifactRecord:
    return {
        "id": row.id,
        "type": row.type,
        "label": row.label,
        "source_path": row.source_path,
        "content": row.content,
        "summary": row.summary,
        "metadata": json.loads(row.metadata_json or "{}"),
        "included": bool(row.included),
        "created_at": row.created_at,
    }


class ArtifactRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(
        self,
        type: ArtifactType,  # noqa: A002 — `type` is the natural field name
        label: str,
        content: str,
        source_path: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        row = ArtifactRow(
            type=type,
            label=label,
            source_path=source_path,
            content=content,
            summary=summary,
            metadata_json=json.dumps(metadata or {}),
            included=1,
        )
        async with self._db.session() as session, session.begin():
            session.add(row)
            await session.flush()
        return row.id

    async def load(self, artifact_id: int) -> ArtifactRecord | None:
        async with self._db.session() as session:
            row = await session.get(ArtifactRow, artifact_id)
        return _artifact_record(row) if row else None

    async def list(
        self,
        type: ArtifactType | None = None,  # noqa: A002
        included_only: bool = False,
    ) -> list[ArtifactRecord]:
        stmt = select(ArtifactRow).order_by(ArtifactRow.id)
        if type is not None:
            stmt = stmt.where(ArtifactRow.type == type)
        if included_only:
            stmt = stmt.where(ArtifactRow.included == 1)
        async with self._db.session() as session:
            return [_artifact_record(r) for r in await session.scalars(stmt)]

    async def delete(self, artifact_id: int) -> bool:
        async with self._db.session() as session, session.begin():
            result = await session.execute(delete(ArtifactRow).where(ArtifactRow.id == artifact_id))
        return affected(result) > 0

    async def set_included(self, artifact_id: int, included: bool) -> bool:
        """Excluded artifacts are ignored by the writing pipeline."""
        stmt = (
            update(ArtifactRow).where(ArtifactRow.id == artifact_id).values(included=int(included))
        )
        async with self._db.session() as session, session.begin():
            result = await session.execute(stmt)
        return affected(result) > 0
