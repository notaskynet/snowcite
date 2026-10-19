"""Review criteria, statuses, history and the rolling summary."""

import json
from typing import Any

import aiosqlite

from snowcite.storage.database import Database
from snowcite.storage.repositories.notes import NoteRepository
from snowcite.storage.rows import paper_row_to_dict


_STATUSES = ("approved", "maybe", "rejected", "unreviewed")


class ReviewRepository:
    def __init__(self, db: Database, notes: NoteRepository) -> None:
        self._db = db
        self._notes = notes

    # ─── Criteria ───────────────────────────────────────────────────────

    async def add_criteria(self, criteria_text: str) -> int:
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "INSERT INTO review_criteria (criteria_text) VALUES (?)", (criteria_text,)
            )
            await conn.commit()
            return cur.lastrowid

    async def latest_criteria(self) -> dict[str, Any] | None:
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT id, criteria_text, created_at FROM review_criteria ORDER BY id DESC LIMIT 1"
            )
            row = await cur.fetchone()
        return dict(row) if row else None

    # ─── Reading papers by review state ─────────────────────────────────

    async def unreviewed(
        self,
        limit: int,
        source: str | None,
        year_from: int | None,
        year_to: int | None,
        include_abstracts: bool,
    ) -> list[dict[str, Any]]:
        # Two static query variants avoid a dynamic f-string (and the S608 lint).
        if include_abstracts:
            query = """
                SELECT p.id, p.source, p.title, p.year, p.venue, p.abstract,
                       p.authors_json, p.doi
                FROM papers p JOIN reviews r ON r.paper_id = p.id
                WHERE r.status = 'unreviewed'
            """
        else:
            query = """
                SELECT p.id, p.source, p.title, p.year, p.venue, NULL AS abstract,
                       p.authors_json, p.doi
                FROM papers p JOIN reviews r ON r.paper_id = p.id
                WHERE r.status = 'unreviewed'
            """
        params: list[Any] = []
        query, params = _with_filters(query, params, source, year_from, year_to)
        query += " ORDER BY p.id LIMIT ?"
        params.append(limit)
        async with self._db.connection() as conn:
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()
        out = [paper_row_to_dict(r) for r in rows]
        if not include_abstracts:
            for d in out:
                d.pop("abstract", None)
        return out

    async def low_confidence(self, status: str | None, limit: int) -> list[dict[str, Any]]:
        query = """
            SELECT p.id, p.source, p.title, p.year, p.venue, p.authors_json, p.doi,
                   r.status, r.reason, r.reviewed_at
            FROM papers p JOIN reviews r ON r.paper_id = p.id
            WHERE r.reviewed_by = 'auto_low'
        """
        params: list[Any] = []
        if status is not None:
            query += " AND r.status = ?"
            params.append(status)
        query += " ORDER BY r.reviewed_at DESC LIMIT ?"
        params.append(limit)
        async with self._db.connection() as conn:
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()
        return [paper_row_to_dict(r) for r in rows]

    async def approved_for_writing(
        self, paper_ids: list[int] | None, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        query = """
            SELECT p.id, p.source, p.doi, p.title, p.year, p.venue, p.abstract,
                   p.authors_json, p.bibtex
            FROM papers p JOIN reviews r ON r.paper_id = p.id
            WHERE r.status = 'approved'
        """
        params: list[Any] = []
        if paper_ids is not None:
            query += f" AND p.id IN ({','.join('?' * len(paper_ids))})"
            params.extend(paper_ids)
        query += " ORDER BY p.year, p.id LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        async with self._db.connection() as conn:
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()
        return [paper_row_to_dict(r) for r in rows]

    async def select_paper_ids(
        self,
        current_status: str | None,
        source: str | None,
        year_from: int | None,
        year_to: int | None,
        within_ids: list[int] | None,
        limit: int | None,
    ) -> list[int]:
        query = "SELECT p.id FROM papers p JOIN reviews r ON r.paper_id = p.id WHERE 1=1"
        params: list[Any] = []
        if current_status is not None:
            query += " AND r.status = ?"
            params.append(current_status)
        query, params = _with_filters(query, params, source, year_from, year_to)
        if within_ids is not None:
            query += f" AND p.id IN ({','.join('?' * len(within_ids))})"
            params.extend(within_ids)
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        async with self._db.connection() as conn:
            cur = await conn.execute(query, params)
            return [r["id"] for r in await cur.fetchall()]

    # ─── Writing decisions ──────────────────────────────────────────────

    async def set_status(
        self,
        paper_ids: list[int],
        status: str,
        reason: str,
        note: str | None,
        reviewed_by: str,
        notes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Set status for each paper with a history row; marks the summary stale.

        Each paper runs in its own SAVEPOINT so a mid-batch failure rolls back
        that paper alone — `reviews` and `review_history` always move together.
        Inline `notes` (validated by the caller) attach only when exactly one
        paper was updated; if that paper was skipped they are dropped rather
        than orphaned.
        """
        updated = 0
        skipped: list[int] = []
        note_ids: list[int] = []
        async with self._db.connection() as conn:
            for idx, pid in enumerate(paper_ids):
                # Loop index, not paper id: savepoint names stay valid SQL identifiers.
                savepoint = f"rsp_{idx}"
                await conn.execute(f"SAVEPOINT {savepoint}")
                try:
                    cur = await conn.execute(
                        "SELECT status FROM reviews WHERE paper_id = ?", (pid,)
                    )
                    row = await cur.fetchone()
                    old_status = row["status"] if row else None
                    await conn.execute(
                        """
                        INSERT INTO reviews
                            (paper_id, status, reason, note, reviewed_by, reviewed_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(paper_id) DO UPDATE SET
                            status = excluded.status,
                            reason = excluded.reason,
                            note = excluded.note,
                            reviewed_by = excluded.reviewed_by,
                            reviewed_at = CURRENT_TIMESTAMP
                        """,
                        (pid, status, reason, note, reviewed_by),
                    )
                    await conn.execute(
                        """
                        INSERT INTO review_history
                            (paper_id, old_status, new_status, reason, reviewed_by)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (pid, old_status, status, reason, reviewed_by),
                    )
                except aiosqlite.IntegrityError:
                    await conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    skipped.append(pid)
                    continue
                await conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                updated += 1
            if updated > 0:
                await self._mark_stale(conn)
            if notes and updated == 1:
                for item in notes:
                    note_ids.append(
                        await self._notes.insert(
                            conn,
                            paper_ids[0],
                            item.get("cluster"),
                            item["type"],
                            item["text"].strip(),
                        )
                    )
            await conn.commit()
        return {"updated": updated, "skipped": skipped, "note_ids": note_ids}

    async def undo_last(self) -> dict[str, Any]:
        """Revert the newest review_history entry and delete it (so undo can walk back)."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT id, paper_id, old_status, new_status FROM review_history "
                "ORDER BY id DESC LIMIT 1"
            )
            row = await cur.fetchone()
            if row is None:
                return {"undone": False, "reason": "review_history is empty"}

            # Delete the history row first so the revert doesn't add its own.
            await conn.execute("DELETE FROM review_history WHERE id = ?", (row["id"],))
            if row["old_status"] is None:
                # First-ever classification — back to the row `persist` creates.
                await conn.execute(
                    """
                    UPDATE reviews
                    SET status = 'unreviewed', reason = NULL, note = NULL,
                        reviewed_by = NULL, reviewed_at = CURRENT_TIMESTAMP
                    WHERE paper_id = ?
                    """,
                    (row["paper_id"],),
                )
                reverted_to = "unreviewed"
            else:
                await conn.execute(
                    "UPDATE reviews SET status = ?, reviewed_at = CURRENT_TIMESTAMP "
                    "WHERE paper_id = ?",
                    (row["old_status"], row["paper_id"]),
                )
                reverted_to = row["old_status"]
            await self._mark_stale(conn)
            await conn.commit()
        return {
            "undone": True,
            "paper_id": row["paper_id"],
            "reverted_to": reverted_to,
            "was": row["new_status"],
        }

    # ─── Counts and summary ─────────────────────────────────────────────

    @staticmethod
    async def _mark_stale(conn: aiosqlite.Connection) -> None:
        await conn.execute("UPDATE review_summary SET stale = 1 WHERE id = 1")

    @staticmethod
    async def _live_counts(conn: aiosqlite.Connection) -> dict[str, int]:
        cur = await conn.execute("SELECT COUNT(*) FROM papers")
        counts = {"total": (await cur.fetchone())[0], **dict.fromkeys(_STATUSES, 0)}
        cur = await conn.execute("SELECT status, COUNT(*) FROM reviews GROUP BY status")
        for row in await cur.fetchall():
            counts[row[0]] = row[1]
        return counts

    async def count_auto_low(self) -> int:
        """Decisions made at `auto_low` confidence that the user hasn't confirmed."""
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM reviews WHERE reviewed_by = 'auto_low'")
            return (await cur.fetchone())[0]

    async def live_counts(self) -> dict[str, int]:
        async with self._db.connection() as conn:
            return await self._live_counts(conn)

    async def save_summary(self, summary: str, clusters: list[dict[str, Any]]) -> None:
        async with self._db.connection() as conn:
            counts = await self._live_counts(conn)
            await conn.execute(
                """
                INSERT INTO review_summary
                    (id, summary, clusters_json, counts_snapshot_json, stale, updated_at)
                VALUES (1, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    summary = excluded.summary,
                    clusters_json = excluded.clusters_json,
                    counts_snapshot_json = excluded.counts_snapshot_json,
                    stale = 0,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (summary, json.dumps(clusters), json.dumps(counts)),
            )
            await conn.commit()

    async def load_summary(self) -> dict[str, Any] | None:
        """Stored summary row (parsed) plus live counts; None before the first save."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT summary, clusters_json, counts_snapshot_json, stale, updated_at "
                "FROM review_summary WHERE id = 1"
            )
            row = await cur.fetchone()
            if row is None:
                return None
            live = await self._live_counts(conn)
        return {
            "summary": row["summary"],
            "clusters": json.loads(row["clusters_json"]),
            "counts_snapshot": json.loads(row["counts_snapshot_json"]),
            "counts_live": live,
            "stale": bool(row["stale"]),
            "updated_at": row["updated_at"],
        }

    async def prisma_counts(self) -> dict[str, Any]:
        """Aggregate review_history into the PRISMA buckets.

        identified = papers ever recorded; screened = papers whose current status
        is anything but unreviewed; excluded = rejected, grouped by reason.
        """
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT COUNT(DISTINCT paper_id) FROM review_history")
            identified = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT COUNT(*) FROM reviews WHERE status IN ('approved','rejected','maybe')"
            )
            screened = (await cur.fetchone())[0]
            cur = await conn.execute("SELECT COUNT(*) FROM reviews WHERE status = 'approved'")
            included = (await cur.fetchone())[0]
            cur = await conn.execute(
                """
                SELECT COALESCE(reason, '(no reason)') AS reason, COUNT(*) AS n
                FROM reviews WHERE status = 'rejected'
                GROUP BY reason ORDER BY n DESC
                """
            )
            excluded = [{"reason": r["reason"], "count": r["n"]} for r in await cur.fetchall()]
        return {
            "identified": identified,
            "screened": screened,
            "excluded_total": sum(e["count"] for e in excluded),
            "excluded_by_reason": excluded,
            "included": included,
        }

    async def recent_history(self, limit: int) -> list[dict[str, Any]]:
        async with self._db.connection() as conn:
            cur = await conn.execute(
                """
                SELECT paper_id, old_status, new_status, reason, reviewed_by, changed_at
                FROM review_history ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            )
            return [
                {
                    "paper_id": r["paper_id"],
                    "old_status": r["old_status"],
                    "new_status": r["new_status"],
                    "reason": r["reason"],
                    "reviewed_by": r["reviewed_by"],
                    "at": r["changed_at"],
                }
                for r in await cur.fetchall()
            ]

    async def summary_topics(self) -> set[str] | None:
        """Cluster topics in the current summary; None when no summary exists."""
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT clusters_json FROM review_summary WHERE id = 1")
            row = await cur.fetchone()
        if row is None:
            return None
        return {c.get("topic") for c in json.loads(row["clusters_json"])}

    async def resolve_cluster_paper_ids(self, cluster: str) -> list[int] | dict[str, Any]:
        """Look up paper_ids for a cluster in the current review_summary.

        Returns a list of ints on success, or an error dict with an `available`
        list when the cluster name isn't found.
        """
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT clusters_json FROM review_summary WHERE id = 1")
            row = await cur.fetchone()
        if not row:
            return {"error": "no review_summary — run save_review_summary first"}
        clusters_data = json.loads(row["clusters_json"])
        match = next(
            (c for c in clusters_data if c.get("topic", "").lower() == cluster.lower()), None
        )
        if match is None:
            return {
                "error": f"cluster {cluster!r} not found",
                "available": [c.get("topic") for c in clusters_data],
            }
        return match.get("paper_ids") or []


def _with_filters(
    query: str,
    params: list[Any],
    source: str | None,
    year_from: int | None,
    year_to: int | None,
) -> tuple[str, list[Any]]:
    if source is not None:
        query += " AND p.source = ?"
        params.append(source)
    if year_from is not None:
        query += " AND p.year >= ?"
        params.append(year_from)
    if year_to is not None:
        query += " AND p.year <= ?"
        params.append(year_to)
    return query, params
