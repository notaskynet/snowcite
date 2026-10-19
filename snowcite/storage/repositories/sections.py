"""Section reads shared by document building and metrics."""

import json
from typing import Any

from snowcite.domain.models import DocumentSection
from snowcite.storage.database import Database


class SectionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def load_document_sections(self) -> list[DocumentSection]:
        """Sections to render, in document order.

        v0.3 `sections` rows with a non-empty draft win (parents before their
        children, siblings by position). When there are none, falls back to the
        v0.2 `section_content` rows ordered by the outline.
        """
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT id, title, draft, parent_id, position FROM sections ORDER BY position, id"
            )
            rows = await cur.fetchall()
            cur = await conn.execute("SELECT sections_json FROM outline WHERE id = 1")
            outline_row = await cur.fetchone()
            cur = await conn.execute("SELECT name, content FROM section_content")
            legacy = await cur.fetchall()

        if any(r["draft"].strip() for r in rows):
            return self._ordered_drafts(rows)

        by_name = {r["name"]: r["content"] for r in legacy}
        names: list[str] = []
        if outline_row:
            for entry in json.loads(outline_row["sections_json"]) or []:
                name = entry.get("name") if isinstance(entry, dict) else entry
                if name in by_name and name not in names:
                    names.append(name)
        names += sorted(n for n in by_name if n not in names)
        return [{"title": n, "content": by_name[n]} for n in names]

    @staticmethod
    def _ordered_drafts(rows: list[Any]) -> list[DocumentSection]:
        children: dict[int | None, list[Any]] = {}
        for r in rows:
            children.setdefault(r["parent_id"], []).append(r)
        ordered: list[DocumentSection] = []

        def walk(parent_id: int | None) -> None:
            for r in children.get(parent_id, []):
                if r["draft"].strip():
                    ordered.append({"title": r["title"], "content": r["draft"]})
                walk(r["id"])

        walk(None)
        return ordered
