import json
from typing import Any

from snowcite.domain.types import ArtifactRecord, ArtifactType
from snowcite.storage.database import Database


_COLUMNS = "id, type, label, source_path, content, summary, metadata_json, included, created_at"


def _to_record(row: Any) -> ArtifactRecord:
    return {
        "id": row["id"],
        "type": row["type"],
        "label": row["label"],
        "source_path": row["source_path"],
        "content": row["content"],
        "summary": row["summary"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "included": bool(row["included"]),
        "created_at": row["created_at"],
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
        async with self._db.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO artifacts
                    (type, label, source_path, content, summary, metadata_json, included)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (type, label, source_path, content, summary, json.dumps(metadata or {})),
            )
            await conn.commit()
            return cur.lastrowid

    async def load(self, artifact_id: int) -> ArtifactRecord | None:
        async with self._db.connection() as conn:
            cur = await conn.execute(
                f"SELECT {_COLUMNS} FROM artifacts WHERE id = ?",  # noqa: S608 — static columns
                (artifact_id,),
            )
            row = await cur.fetchone()
        return _to_record(row) if row else None

    async def list(
        self,
        type: ArtifactType | None = None,  # noqa: A002
        included_only: bool = False,
    ) -> list[ArtifactRecord]:
        query = f"SELECT {_COLUMNS} FROM artifacts WHERE 1=1"  # noqa: S608 — static columns
        params: list[Any] = []
        if type is not None:
            query += " AND type = ?"
            params.append(type)
        if included_only:
            query += " AND included = 1"
        query += " ORDER BY id"
        async with self._db.connection() as conn:
            cur = await conn.execute(query, params)
            return [_to_record(r) for r in await cur.fetchall()]

    async def delete(self, artifact_id: int) -> bool:
        async with self._db.connection() as conn:
            cur = await conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
            await conn.commit()
            return cur.rowcount > 0

    async def set_included(self, artifact_id: int, included: bool) -> bool:
        """Excluded artifacts are ignored by the writing pipeline."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "UPDATE artifacts SET included = ? WHERE id = ?",
                (1 if included else 0, artifact_id),
            )
            await conn.commit()
            return cur.rowcount > 0
