from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from snowcite.domain.records import (
    ClusterNote,
    NewNote,
    NoteLinkRecord,
    NoteRecord,
    NoteScope,
)
from snowcite.storage.database import Database, affected
from snowcite.storage.models import NoteLinkRow, NoteRow, PaperRow


def _note_record(row: NoteRow) -> NoteRecord:
    return {
        "id": row.id,
        "paper_id": row.paper_id,
        "cluster": row.cluster,
        "type": row.type,
        "text": row.text,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class NoteRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    async def insert(
        session: AsyncSession,
        paper_id: int | None,
        cluster: str | None,
        note_type: str,
        text: str,
    ) -> int:
        """Insert on a caller's session so the write can join its transaction."""
        row = NoteRow(paper_id=paper_id, cluster=cluster, type=note_type, text=text)
        session.add(row)
        await session.flush()
        return row.id

    async def add_many(self, notes: list[NewNote]) -> list[int]:
        """Insert notes in one transaction."""
        async with self._db.session() as session, session.begin():
            return [
                await self.insert(session, n["paper_id"], n["cluster"], n["type"], n["text"])
                for n in notes
            ]

    async def find(
        self,
        paper_id: int | None = None,
        cluster: str | None = None,
        note_type: str | None = None,
        limit: int = 200,
    ) -> list[NoteRecord]:
        stmt = select(NoteRow)
        if paper_id is not None:
            stmt = stmt.where(NoteRow.paper_id == paper_id)
        if cluster is not None:
            stmt = stmt.where(NoteRow.cluster == cluster)
        if note_type is not None:
            stmt = stmt.where(NoteRow.type == note_type)
        stmt = stmt.order_by(NoteRow.id.desc()).limit(limit)
        async with self._db.session() as session:
            return [_note_record(r) for r in await session.scalars(stmt)]

    async def get_scope(self, note_id: int) -> NoteScope | None:
        async with self._db.session() as session:
            row = await session.get(NoteRow, note_id)
        if row is None:
            return None
        return {"paper_id": row.paper_id, "type": row.type}

    async def update(
        self,
        note_id: int,
        text: str | None = None,
        note_type: str | None = None,
        cluster: str | None = None,
    ) -> None:
        values: dict[str, object] = {"updated_at": func.current_timestamp()}
        if text is not None:
            values["text"] = text
        if note_type is not None:
            values["type"] = note_type
        if cluster is not None:
            values["cluster"] = cluster
        async with self._db.session() as session, session.begin():
            await session.execute(update(NoteRow).where(NoteRow.id == note_id).values(**values))

    async def delete(self, note_id: int) -> int:
        async with self._db.session() as session, session.begin():
            result = await session.execute(delete(NoteRow).where(NoteRow.id == note_id))
        return affected(result)

    async def link(self, from_note_id: int, to_note_id: int, kind: str) -> None:
        stmt = (
            sqlite_insert(NoteLinkRow)
            .values(from_note_id=from_note_id, to_note_id=to_note_id, kind=kind)
            .on_conflict_do_nothing()
        )
        async with self._db.session() as session, session.begin():
            await session.execute(stmt)

    async def density(self, cluster: str | None = None) -> dict[str, dict[str, int]]:
        """Note counts per cluster × type."""
        name = func.coalesce(NoteRow.cluster, "")
        stmt = select(name.label("cluster"), NoteRow.type, func.count().label("n"))
        if cluster is not None:
            stmt = stmt.where(NoteRow.cluster == cluster)
        stmt = stmt.group_by(NoteRow.cluster, NoteRow.type).order_by(name, NoteRow.type)
        async with self._db.session() as session:
            rows = (await session.execute(stmt)).all()
        by_cluster: dict[str, dict[str, int]] = {}
        for r in rows:
            by_cluster.setdefault(r.cluster or "(unscoped)", {})[r.type] = r.n
        return by_cluster

    # ─── Reads and writes used by synthesis and critique ────────────────

    async def in_clusters(self, clusters: list[str]) -> list[NoteRecord]:
        """Notes whose cluster is in `clusters`: per-paper first, then cross-paper."""
        if not clusters:
            return []
        stmt = (
            select(NoteRow)
            .where(NoteRow.cluster.in_(clusters))
            .order_by(NoteRow.paper_id.asc().nulls_last(), NoteRow.id)
        )
        async with self._db.session() as session:
            return [_note_record(r) for r in await session.scalars(stmt)]

    async def cluster_view(self, cluster: str) -> tuple[list[ClusterNote], list[NoteLinkRecord]]:
        """Notes of one cluster joined with paper title/year, and the links from those notes."""
        notes_stmt = (
            select(NoteRow, PaperRow.title, PaperRow.year)
            .outerjoin(PaperRow, PaperRow.id == NoteRow.paper_id)
            .where(NoteRow.cluster == cluster)
            .order_by(NoteRow.paper_id.asc().nulls_last(), NoteRow.id)
        )
        links_stmt = select(NoteLinkRow).where(
            NoteLinkRow.from_note_id.in_(select(NoteRow.id).where(NoteRow.cluster == cluster))
        )
        async with self._db.session() as session:
            notes_rows = (await session.execute(notes_stmt)).all()
            link_rows = (await session.scalars(links_stmt)).all()
        notes: list[ClusterNote] = [
            {
                "id": n.id,
                "paper_id": n.paper_id,
                "type": n.type,
                "text": n.text,
                "title": title,
                "year": year,
            }
            for n, title, year in notes_rows
        ]
        links: list[NoteLinkRecord] = [
            {"from_note_id": r.from_note_id, "to_note_id": r.to_note_id, "kind": r.kind}
            for r in link_rows
        ]
        return notes, links

    async def paper_ids_of(self, note_ids: list[int]) -> dict[int, int | None]:
        """`{note_id: paper_id}` for the ids that exist."""
        if not note_ids:
            return {}
        stmt = select(NoteRow.id, NoteRow.paper_id).where(NoteRow.id.in_(note_ids))
        async with self._db.session() as session:
            return {r.id: r.paper_id for r in await session.execute(stmt)}

    async def add_synthesis(
        self, cluster: str, note_type: str, text: str, source_ids: list[int]
    ) -> int:
        """Insert a cross-paper note and its `derived_from` links atomically."""
        async with self._db.session() as session, session.begin():
            new_id = await self.insert(session, None, cluster, note_type, text)
            for src in source_ids:
                await session.execute(
                    sqlite_insert(NoteLinkRow)
                    .values(from_note_id=new_id, to_note_id=src, kind="derived_from")
                    .on_conflict_do_nothing()
                )
        return new_id

    async def ids_by_cluster_and_type(
        self, cluster: str | None
    ) -> tuple[dict[str, dict[str, list[int]]], set[int]]:
        """`({cluster: {type: [note ids]}}, ids of notes anchored by derived_from links)`."""
        stmt = select(NoteRow.cluster, NoteRow.type, NoteRow.id).where(NoteRow.cluster.is_not(None))
        if cluster is not None:
            stmt = stmt.where(NoteRow.cluster == cluster)
        async with self._db.session() as session:
            rows = (await session.execute(stmt)).all()
            anchored = set(
                await session.scalars(
                    select(NoteLinkRow.from_note_id).where(NoteLinkRow.kind == "derived_from")
                )
            )
        by_cluster: dict[str, dict[str, list[int]]] = {}
        for r in rows:
            by_cluster.setdefault(r.cluster, {}).setdefault(r.type, []).append(r.id)
        return by_cluster, anchored

    async def scope_counts(self) -> tuple[int, int]:
        """`(per_paper_notes, cross_paper_notes)` across the whole project."""
        stmt = select(
            func.count(NoteRow.paper_id),
            func.count().filter(NoteRow.paper_id.is_(None)),
        )
        async with self._db.session() as session:
            per, cross = (await session.execute(stmt)).one()
        return per, cross

    async def paper_ids_with_notes(self, paper_ids: list[int]) -> set[int]:
        """The subset of `paper_ids` that already has at least one per-paper note."""
        if not paper_ids:
            return set()
        stmt = select(func.distinct(NoteRow.paper_id)).where(NoteRow.paper_id.in_(paper_ids))
        async with self._db.session() as session:
            return set(await session.scalars(stmt))
