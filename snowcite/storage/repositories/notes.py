"""Knowledge-graph notes and typed links between them."""

from typing import Any

import aiosqlite

from snowcite.storage.database import Database


class NoteRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    async def insert(
        conn: aiosqlite.Connection,
        paper_id: int | None,
        cluster: str | None,
        note_type: str,
        text: str,
    ) -> int:
        """Insert on a caller's connection so the write can join its transaction."""
        cur = await conn.execute(
            "INSERT INTO notes (paper_id, cluster, type, text) VALUES (?, ?, ?, ?)",
            (paper_id, cluster, note_type, text),
        )
        return cur.lastrowid

    async def add(
        self, paper_id: int | None, cluster: str | None, note_type: str, text: str
    ) -> int:
        async with self._db.connection() as conn:
            note_id = await self.insert(conn, paper_id, cluster, note_type, text)
            await conn.commit()
        return note_id

    async def add_many(self, rows: list[tuple[int | None, str | None, str, str]]) -> list[int]:
        """Insert `(paper_id, cluster, type, text)` rows in one transaction."""
        async with self._db.connection() as conn:
            ids = [await self.insert(conn, *row) for row in rows]
            await conn.commit()
        return ids

    async def find(
        self,
        paper_id: int | None = None,
        cluster: str | None = None,
        note_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, paper_id, cluster, type, text, created_at, updated_at FROM notes WHERE 1=1"
        )
        params: list[Any] = []
        if paper_id is not None:
            query += " AND paper_id = ?"
            params.append(paper_id)
        if cluster is not None:
            query += " AND cluster = ?"
            params.append(cluster)
        if note_type is not None:
            query += " AND type = ?"
            params.append(note_type)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        async with self._db.connection() as conn:
            cur = await conn.execute(query, params)
            return [dict(r) for r in await cur.fetchall()]

    async def get_scope(self, note_id: int) -> dict[str, Any] | None:
        """`{paper_id, type}` of a note, or None if it doesn't exist."""
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT paper_id, type FROM notes WHERE id = ?", (note_id,))
            row = await cur.fetchone()
        return dict(row) if row else None

    async def update(
        self,
        note_id: int,
        text: str | None = None,
        note_type: str | None = None,
        cluster: str | None = None,
    ) -> None:
        # `sets` comes from a fixed allowlist — no user input reaches the SQL.
        sets: list[str] = []
        params: list[Any] = []
        if text is not None:
            sets.append("text = ?")
            params.append(text)
        if note_type is not None:
            sets.append("type = ?")
            params.append(note_type)
        if cluster is not None:
            sets.append("cluster = ?")
            params.append(cluster)
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(note_id)
        async with self._db.connection() as conn:
            await conn.execute(f"UPDATE notes SET {', '.join(sets)} WHERE id = ?", params)  # noqa: S608
            await conn.commit()

    async def delete(self, note_id: int) -> int:
        async with self._db.connection() as conn:
            cur = await conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            await conn.commit()
        return cur.rowcount

    async def link(self, from_note_id: int, to_note_id: int, kind: str) -> None:
        async with self._db.connection() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO note_links (from_note_id, to_note_id, kind) "
                "VALUES (?, ?, ?)",
                (from_note_id, to_note_id, kind),
            )
            await conn.commit()

    async def density(self, cluster: str | None = None) -> dict[str, dict[str, int]]:
        """Note counts per cluster × type."""
        query = "SELECT COALESCE(cluster, '') AS cluster, type, COUNT(*) AS n FROM notes"
        params: list[Any] = []
        if cluster is not None:
            query += " WHERE cluster = ?"
            params.append(cluster)
        query += " GROUP BY cluster, type ORDER BY cluster, type"
        async with self._db.connection() as conn:
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()
        by_cluster: dict[str, dict[str, int]] = {}
        for r in rows:
            by_cluster.setdefault(r["cluster"] or "(unscoped)", {})[r["type"]] = r["n"]
        return by_cluster

    # ─── Reads and writes used by synthesis and critique ────────────────

    async def in_clusters(self, clusters: list[str]) -> list[dict[str, Any]]:
        """Notes whose cluster is in `clusters`: per-paper first, then cross-paper."""
        if not clusters:
            return []
        placeholders = ",".join("?" * len(clusters))
        async with self._db.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT id, paper_id, cluster, type, text
                FROM notes WHERE cluster IN ({placeholders})
                ORDER BY paper_id NULLS LAST, id
                """,  # noqa: S608 — one placeholder per cluster name
                clusters,
            )
            return [dict(r) for r in await cur.fetchall()]

    async def cluster_view(self, cluster: str) -> tuple[list[Any], list[Any]]:
        """`(notes joined with paper title/year, links from those notes)` for one cluster."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                """
                SELECT n.id, n.paper_id, n.type, n.text, n.created_at, p.title, p.year
                FROM notes n LEFT JOIN papers p ON p.id = n.paper_id
                WHERE n.cluster = ?
                ORDER BY n.paper_id NULLS LAST, n.id
                """,
                (cluster,),
            )
            notes = list(await cur.fetchall())
            cur = await conn.execute(
                """
                SELECT from_note_id, to_note_id, kind FROM note_links
                WHERE from_note_id IN (SELECT id FROM notes WHERE cluster = ?)
                """,
                (cluster,),
            )
            return notes, list(await cur.fetchall())

    async def paper_ids_of(self, note_ids: list[int]) -> dict[int, int | None]:
        """`{note_id: paper_id}` for the ids that exist."""
        if not note_ids:
            return {}
        placeholders = ",".join("?" * len(note_ids))
        async with self._db.connection() as conn:
            cur = await conn.execute(
                f"SELECT id, paper_id FROM notes WHERE id IN ({placeholders})",  # noqa: S608
                note_ids,
            )
            return {r["id"]: r["paper_id"] for r in await cur.fetchall()}

    async def add_synthesis(
        self, cluster: str, note_type: str, text: str, source_ids: list[int]
    ) -> int:
        """Insert a cross-paper note and its `derived_from` links atomically."""
        async with self._db.connection() as conn:
            new_id = await self.insert(conn, None, cluster, note_type, text)
            for src in source_ids:
                await conn.execute(
                    "INSERT OR IGNORE INTO note_links (from_note_id, to_note_id, kind) "
                    "VALUES (?, ?, 'derived_from')",
                    (new_id, src),
                )
            await conn.commit()
        return new_id

    async def ids_by_cluster_and_type(
        self, cluster: str | None
    ) -> tuple[dict[str, dict[str, list[int]]], set[int]]:
        """`({cluster: {type: [note ids]}}, ids of notes anchored by derived_from links)`."""
        query = "SELECT cluster, type, id FROM notes WHERE cluster IS NOT NULL"
        params: list[Any] = []
        if cluster is not None:
            query += " AND cluster = ?"
            params.append(cluster)
        async with self._db.connection() as conn:
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()
            cur = await conn.execute(
                "SELECT from_note_id FROM note_links WHERE kind = 'derived_from'"
            )
            anchored = {r["from_note_id"] for r in await cur.fetchall()}
        by_cluster: dict[str, dict[str, list[int]]] = {}
        for r in rows:
            by_cluster.setdefault(r["cluster"], {}).setdefault(r["type"], []).append(r["id"])
        return by_cluster, anchored
