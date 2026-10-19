"""Section reads shared by document building and metrics."""

import json
from typing import Any

from snowcite.domain.models import DocumentSection
from snowcite.storage.database import Database


_COLUMNS = (
    "id, title, scope_json, draft, status, parent_id, position, "
    "blockers, should_fix, nits, critique_iterations, target_words, created_at, updated_at"
)


def _to_record(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "scope": json.loads(row["scope_json"]),
        "draft": row["draft"],
        "status": row["status"],
        "parent_id": row["parent_id"],
        "position": row["position"],
        "severity": {
            "blockers": row["blockers"],
            "should_fix": row["should_fix"],
            "nits": row["nits"],
        },
        "critique_iterations": row["critique_iterations"],
        "target_words": row["target_words"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class SectionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ─── CRUD ───────────────────────────────────────────────────────────

    async def create_many(
        self, items: list[tuple[str, dict[str, Any], int | None, int | None]]
    ) -> list[int]:
        """Insert `(title, scope, parent_id, position)` rows.

        A missing position appends after the parent's current siblings; the next
        free position is cached per parent so a batch packs sequentially instead
        of colliding at MAX+1 of the pre-call state.
        """
        ids: list[int] = []
        next_pos: dict[int | None, int] = {}
        async with self._db.connection() as conn:
            for title, scope, parent_id, requested in items:
                position = requested
                if position is None:
                    if parent_id not in next_pos:
                        cur = await conn.execute(
                            "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM sections "
                            "WHERE parent_id IS ?",
                            (parent_id,),
                        )
                        next_pos[parent_id] = (await cur.fetchone())["next"]
                    position = next_pos[parent_id]
                    next_pos[parent_id] += 1
                cur = await conn.execute(
                    "INSERT INTO sections (title, scope_json, parent_id, position) "
                    "VALUES (?, ?, ?, ?)",
                    (title, json.dumps(scope), parent_id, position),
                )
                ids.append(cur.lastrowid)
            await conn.commit()
        return ids

    async def list_all(self) -> list[dict[str, Any]]:
        async with self._db.connection() as conn:
            cur = await conn.execute(
                f"SELECT {_COLUMNS} FROM sections "  # noqa: S608 — static column list
                "ORDER BY COALESCE(parent_id, 0), position, id"
            )
            return [_to_record(r) for r in await cur.fetchall()]

    async def get(self, section_id: int) -> dict[str, Any] | None:
        async with self._db.connection() as conn:
            cur = await conn.execute(
                f"SELECT {_COLUMNS} FROM sections WHERE id = ?",  # noqa: S608 — static column list
                (section_id,),
            )
            row = await cur.fetchone()
        return _to_record(row) if row else None

    async def update(self, section_id: int, fields: dict[str, Any]) -> bool:
        """Patch columns; keys must come from the service's allowlist. False if missing."""
        sets = [f"{col} = ?" for col in fields]
        sets.append("updated_at = CURRENT_TIMESTAMP")
        async with self._db.connection() as conn:
            cur = await conn.execute(
                f"UPDATE sections SET {', '.join(sets)} WHERE id = ?",  # noqa: S608
                [*fields.values(), section_id],
            )
            if cur.rowcount == 0:
                return False
            await conn.commit()
        return True

    async def delete(self, section_id: int) -> int:
        """Remove a section and its descendants (cascade via parent_id)."""
        async with self._db.connection() as conn:
            cur = await conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
            await conn.commit()
        return cur.rowcount

    # ─── Critique state ─────────────────────────────────────────────────

    async def record_critique(self, section_id: int, counts: dict[str, int]) -> int | None:
        """Store severity counts, bump the iteration, set status 'critiqued'.

        Returns the new iteration number, or None if the section doesn't exist.
        """
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT critique_iterations FROM sections WHERE id = ?", (section_id,)
            )
            row = await cur.fetchone()
            if row is None:
                return None
            iteration = row["critique_iterations"] + 1
            await conn.execute(
                """
                UPDATE sections
                SET blockers = ?, should_fix = ?, nits = ?,
                    critique_iterations = ?, status = 'critiqued',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (counts["blocker"], counts["should_fix"], counts["nit"], iteration, section_id),
            )
            await conn.commit()
        return iteration

    async def revise(self, section_id: int, draft: str, status: str) -> bool:
        """Replace the draft and reset critique counters. False if the section is missing."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE sections
                SET draft = ?, blockers = 0, should_fix = 0, nits = 0,
                    critique_iterations = 0, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (draft, status, section_id),
            )
            if cur.rowcount == 0:
                return False
            await conn.commit()
        return True

    # ─── Paper links ────────────────────────────────────────────────────

    async def link_papers(self, section_id: int, pairs: list[tuple[int, str | None]]) -> None:
        """Idempotently link `(paper_id, via_query)` pairs to the section."""
        async with self._db.connection() as conn:
            for paper_id, via_query in pairs:
                await conn.execute(
                    "INSERT OR IGNORE INTO paper_section_links "
                    "(paper_id, section_id, via_query) VALUES (?, ?, ?)",
                    (paper_id, section_id, via_query),
                )
            await conn.commit()

    async def unlink_paper(self, paper_id: int, section_id: int) -> int:
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "DELETE FROM paper_section_links WHERE paper_id = ? AND section_id = ?",
                (paper_id, section_id),
            )
            await conn.commit()
        return cur.rowcount

    async def linked_papers(self, section_id: int, newest_discovery_first: bool) -> list[Any]:
        """Papers linked to a section with their review status and the surfacing query."""
        order = (
            "l.discovered_at DESC, p.id DESC"
            if newest_discovery_first
            else "p.year DESC, p.id DESC"
        )
        async with self._db.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT p.id, p.title, p.year, p.venue, p.doi,
                       r.status AS review_status, l.via_query, l.discovered_at
                FROM paper_section_links l
                JOIN papers p ON p.id = l.paper_id
                LEFT JOIN reviews r ON r.paper_id = p.id
                WHERE l.section_id = ?
                ORDER BY {order}
                """,  # noqa: S608 — `order` is one of two static strings
                (section_id,),
            )
            return [dict(r) for r in await cur.fetchall()]

    # ─── Document view ──────────────────────────────────────────────────

    async def load_document_sections(self) -> list[DocumentSection]:
        """Sections with a non-empty draft in document order (parents before children)."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT id, title, draft, parent_id, position FROM sections ORDER BY position, id"
            )
            rows = await cur.fetchall()
        return self._ordered_drafts(rows)

    async def drafts(self) -> list[dict[str, Any]]:
        """`{id, title, draft}` for every section holding text, in document order."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT id, title, draft FROM sections WHERE draft != '' "
                "ORDER BY COALESCE(parent_id, 0), position, id"
            )
            return [dict(r) for r in await cur.fetchall()]

    async def progress_counts(self) -> dict[str, int]:
        """`{total, drafted, done}` section counts."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*), SUM(draft != ''), SUM(status = 'done') FROM sections"
            )
            total, drafted, done = await cur.fetchone()
        return {"total": total, "drafted": drafted or 0, "done": done or 0}

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
