import json
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from snowcite.domain.records import (
    Cluster,
    Counts,
    CriteriaRecord,
    ExcludedReason,
    HistoryEntry,
    NewNote,
    PrismaCounts,
    StatusUpdate,
    SummaryRecord,
    UndoResult,
)
from snowcite.domain.results import ClusterError
from snowcite.domain.types import STATUSES
from snowcite.storage.database import Database
from snowcite.storage.models import (
    PaperRow,
    ReviewCriteriaRow,
    ReviewHistoryRow,
    ReviewRow,
    ReviewSummaryRow,
)
from snowcite.storage.repositories.notes import NoteRepository


async def _mark_stale(session: AsyncSession) -> None:
    await session.execute(update(ReviewSummaryRow).where(ReviewSummaryRow.id == 1).values(stale=1))


async def _live_counts(session: AsyncSession) -> Counts:
    total = await session.scalar(select(func.count()).select_from(PaperRow)) or 0
    counts: Counts = {"total": total, "approved": 0, "maybe": 0, "rejected": 0, "unreviewed": 0}
    rows = await session.execute(select(ReviewRow.status, func.count()).group_by(ReviewRow.status))
    for status, n in rows:
        if status in STATUSES:
            counts[status] = n
    return counts


class ReviewRepository:
    def __init__(self, db: Database, notes: NoteRepository) -> None:
        self._db = db
        self._notes = notes

    # ─── Criteria ───────────────────────────────────────────────────────

    async def add_criteria(self, criteria_text: str) -> int:
        async with self._db.session() as session, session.begin():
            row = ReviewCriteriaRow(criteria_text=criteria_text)
            session.add(row)
            await session.flush()
            return row.id

    async def latest_criteria(self) -> CriteriaRecord | None:
        stmt = select(ReviewCriteriaRow).order_by(ReviewCriteriaRow.id.desc()).limit(1)
        async with self._db.session() as session:
            row = await session.scalar(stmt)
        if row is None:
            return None
        return {"id": row.id, "criteria_text": row.criteria_text, "created_at": row.created_at}

    # ─── Selecting papers for bulk operations ───────────────────────────

    async def select_paper_ids(
        self,
        current_status: str | None,
        source: str | None,
        year_from: int | None,
        year_to: int | None,
        within_ids: list[int] | None,
        limit: int | None,
    ) -> list[int]:
        stmt = select(PaperRow.id).join(ReviewRow, ReviewRow.paper_id == PaperRow.id)
        if current_status is not None:
            stmt = stmt.where(ReviewRow.status == current_status)
        if source is not None:
            stmt = stmt.where(PaperRow.source == source)
        if year_from is not None:
            stmt = stmt.where(PaperRow.year >= year_from)
        if year_to is not None:
            stmt = stmt.where(PaperRow.year <= year_to)
        if within_ids is not None:
            stmt = stmt.where(PaperRow.id.in_(within_ids))
        if limit is not None:
            stmt = stmt.limit(limit)
        async with self._db.session() as session:
            return list(await session.scalars(stmt))

    # ─── Writing decisions ──────────────────────────────────────────────

    async def set_status(
        self,
        paper_ids: list[int],
        status: str,
        reason: str,
        note: str | None,
        reviewed_by: str,
        notes: list[NewNote] | None = None,
    ) -> StatusUpdate:
        """Set status for each paper with a history row; marks the summary stale.

        Each paper runs in its own savepoint so a mid-batch failure rolls back that paper
        alone — `reviews` and `review_history` always move together. Inline `notes`
        (validated by the caller) attach only when exactly one paper was updated; if that
        paper was skipped they are dropped rather than orphaned.
        """
        result: StatusUpdate = {"updated": 0, "skipped": [], "note_ids": []}
        async with self._db.session() as session, session.begin():
            for pid in paper_ids:
                try:
                    async with session.begin_nested():
                        old_status = await session.scalar(
                            select(ReviewRow.status).where(ReviewRow.paper_id == pid)
                        )
                        values = {
                            "status": status,
                            "reason": reason,
                            "note": note,
                            "reviewed_by": reviewed_by,
                            "reviewed_at": func.current_timestamp(),
                        }
                        await session.execute(
                            sqlite_insert(ReviewRow)
                            .values(paper_id=pid, **values)
                            .on_conflict_do_update(index_elements=[ReviewRow.paper_id], set_=values)
                        )
                        session.add(
                            ReviewHistoryRow(
                                paper_id=pid,
                                old_status=old_status,
                                new_status=status,
                                reason=reason,
                                reviewed_by=reviewed_by,
                            )
                        )
                        await session.flush()
                except IntegrityError:
                    result["skipped"].append(pid)
                    continue
                result["updated"] += 1
            if result["updated"] > 0:
                await _mark_stale(session)
            if notes and result["updated"] == 1:
                for item in notes:
                    result["note_ids"].append(
                        await self._notes.insert(
                            session, paper_ids[0], item["cluster"], item["type"], item["text"]
                        )
                    )
        return result

    async def undo_last(self) -> UndoResult:
        """Revert the newest review_history entry and delete it (so undo can walk back)."""
        async with self._db.session() as session, session.begin():
            entry = await session.scalar(
                select(ReviewHistoryRow).order_by(ReviewHistoryRow.id.desc()).limit(1)
            )
            if entry is None:
                return {"undone": False, "reason": "review_history is empty"}

            await session.execute(delete(ReviewHistoryRow).where(ReviewHistoryRow.id == entry.id))
            if entry.old_status is None:
                # First-ever classification — back to the row `persist` creates.
                values: dict[str, Any] = {
                    "status": "unreviewed",
                    "reason": None,
                    "note": None,
                    "reviewed_by": None,
                    "reviewed_at": func.current_timestamp(),
                }
                reverted_to = "unreviewed"
            else:
                values = {"status": entry.old_status, "reviewed_at": func.current_timestamp()}
                reverted_to = entry.old_status
            await session.execute(
                update(ReviewRow).where(ReviewRow.paper_id == entry.paper_id).values(**values)
            )
            await _mark_stale(session)
        return {
            "undone": True,
            "paper_id": entry.paper_id,
            "reverted_to": reverted_to,  # type: ignore[typeddict-item]
            "was": entry.new_status,
        }

    # ─── Counts and summary ─────────────────────────────────────────────

    async def count_auto_low(self) -> int:
        """Decisions made at `auto_low` confidence that the user hasn't confirmed."""
        stmt = (
            select(func.count()).select_from(ReviewRow).where(ReviewRow.reviewed_by == "auto_low")
        )
        async with self._db.session() as session:
            return await session.scalar(stmt) or 0

    async def live_counts(self) -> Counts:
        async with self._db.session() as session:
            return await _live_counts(session)

    async def save_summary(self, summary: str, clusters: list[Cluster]) -> None:
        async with self._db.session() as session, session.begin():
            counts = await _live_counts(session)
            values = {
                "summary": summary,
                "clusters_json": json.dumps(clusters),
                "counts_snapshot_json": json.dumps(counts),
                "stale": 0,
                "updated_at": func.current_timestamp(),
            }
            await session.execute(
                sqlite_insert(ReviewSummaryRow)
                .values(id=1, **values)
                .on_conflict_do_update(index_elements=[ReviewSummaryRow.id], set_=values)
            )

    async def load_summary(self) -> SummaryRecord | None:
        """Stored summary (parsed) plus live counts; None before the first save."""
        async with self._db.session() as session:
            row = await session.get(ReviewSummaryRow, 1)
            if row is None:
                return None
            live = await _live_counts(session)
        return {
            "summary": row.summary,
            "clusters": json.loads(row.clusters_json),
            "counts_snapshot": json.loads(row.counts_snapshot_json),
            "counts_live": live,
            "stale": bool(row.stale),
            "updated_at": row.updated_at,
        }

    async def summary_topics(self) -> set[str] | None:
        """Cluster topics in the current summary; None when no summary exists."""
        async with self._db.session() as session:
            row = await session.get(ReviewSummaryRow, 1)
        if row is None:
            return None
        return {c.get("topic") for c in json.loads(row.clusters_json)}

    async def resolve_cluster_paper_ids(self, cluster: str) -> list[int] | ClusterError:
        """Paper ids of a cluster in the current summary, or an error with `available` topics."""
        async with self._db.session() as session:
            row = await session.get(ReviewSummaryRow, 1)
        if row is None:
            return {"error": "no review_summary — run review_summary first"}
        clusters: list[Cluster] = json.loads(row.clusters_json)
        match = next((c for c in clusters if c.get("topic", "").lower() == cluster.lower()), None)
        if match is None:
            return {
                "error": f"cluster {cluster!r} not found",
                "available": [c.get("topic") for c in clusters],
            }
        return match.get("paper_ids") or []

    async def prisma_counts(self) -> PrismaCounts:
        """Aggregate review_history into the PRISMA buckets.

        identified = papers ever recorded; screened = papers whose current status is
        anything but unreviewed; excluded = rejected, grouped by reason.
        """
        async with self._db.session() as session:
            identified = await session.scalar(
                select(func.count(func.distinct(ReviewHistoryRow.paper_id)))
            )
            screened = await session.scalar(
                select(func.count())
                .select_from(ReviewRow)
                .where(ReviewRow.status.in_(("approved", "rejected", "maybe")))
            )
            included = await session.scalar(
                select(func.count()).select_from(ReviewRow).where(ReviewRow.status == "approved")
            )
            reason = func.coalesce(ReviewRow.reason, "(no reason)")
            grouped = await session.execute(
                select(reason.label("reason"), func.count().label("n"))
                .where(ReviewRow.status == "rejected")
                .group_by(ReviewRow.reason)
                .order_by(func.count().desc())
            )
            excluded: list[ExcludedReason] = [{"reason": r.reason, "count": r.n} for r in grouped]
        return {
            "identified": identified or 0,
            "screened": screened or 0,
            "excluded_total": sum(e["count"] for e in excluded),
            "excluded_by_reason": excluded,
            "included": included or 0,
        }

    async def recent_history(self, limit: int) -> list[HistoryEntry]:
        stmt = select(ReviewHistoryRow).order_by(ReviewHistoryRow.id.desc()).limit(limit)
        async with self._db.session() as session:
            rows = (await session.scalars(stmt)).all()
        return [
            {
                "paper_id": r.paper_id,
                "old_status": r.old_status,
                "new_status": r.new_status,
                "reason": r.reason,
                "reviewed_by": r.reviewed_by,
                "at": r.changed_at,
            }
            for r in rows
        ]
