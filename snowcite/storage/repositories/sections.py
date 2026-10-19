import json
from collections.abc import Sequence
from typing import NotRequired, TypedDict

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from snowcite.domain.records import (
    DocumentSection,
    LinkedPaper,
    SectionDraft,
    SectionProgress,
    SectionRecord,
    SectionScope,
)
from snowcite.storage.database import Database, affected
from snowcite.storage.models import PaperRow, PaperSectionLinkRow, ReviewRow, SectionRow


class SectionPatch(TypedDict):
    title: NotRequired[str]
    scope: NotRequired[SectionScope]
    draft: NotRequired[str]
    status: NotRequired[str]
    parent_id: NotRequired[int]
    position: NotRequired[int]


class NewSection(TypedDict):
    title: str
    scope: SectionScope
    parent_id: int | None
    position: int | None


def _section_record(row: SectionRow) -> SectionRecord:
    return {
        "id": row.id,
        "title": row.title,
        "scope": json.loads(row.scope_json),
        "draft": row.draft,
        "status": row.status,
        "parent_id": row.parent_id,
        "position": row.position,
        "severity": {"blockers": row.blockers, "should_fix": row.should_fix, "nits": row.nits},
        "critique_iterations": row.critique_iterations,
        "target_words": row.target_words,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class SectionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ─── CRUD ───────────────────────────────────────────────────────────

    async def create_many(self, items: list[NewSection]) -> list[int]:
        """Insert sections.

        A missing position appends after the parent's current siblings; the next free
        position is cached per parent so a batch packs sequentially instead of colliding
        at MAX+1 of the pre-call state.
        """
        ids: list[int] = []
        next_pos: dict[int | None, int] = {}
        async with self._db.session() as session, session.begin():
            for item in items:
                parent_id = item["parent_id"]
                position = item["position"]
                if position is None:
                    if parent_id not in next_pos:
                        siblings = (
                            SectionRow.parent_id.is_(None)
                            if parent_id is None
                            else SectionRow.parent_id == parent_id
                        )
                        next_pos[parent_id] = (
                            await session.scalar(
                                select(func.coalesce(func.max(SectionRow.position), -1) + 1).where(
                                    siblings
                                )
                            )
                            or 0
                        )
                    position = next_pos[parent_id]
                    next_pos[parent_id] += 1
                row = SectionRow(
                    title=item["title"],
                    scope_json=json.dumps(item["scope"]),
                    draft="",
                    status="outline",
                    parent_id=parent_id,
                    position=position,
                    blockers=0,
                    should_fix=0,
                    nits=0,
                    critique_iterations=0,
                )
                session.add(row)
                await session.flush()
                ids.append(row.id)
        return ids

    async def list_all(self) -> list[SectionRecord]:
        stmt = select(SectionRow).order_by(
            func.coalesce(SectionRow.parent_id, 0), SectionRow.position, SectionRow.id
        )
        async with self._db.session() as session:
            return [_section_record(r) for r in await session.scalars(stmt)]

    async def get(self, section_id: int) -> SectionRecord | None:
        async with self._db.session() as session:
            row = await session.get(SectionRow, section_id)
        return _section_record(row) if row else None

    async def update(self, section_id: int, patch: SectionPatch) -> bool:
        """Apply a patch; False if the section doesn't exist."""
        values: dict[str, object] = {"updated_at": func.current_timestamp()}
        for key, value in patch.items():
            values["scope_json" if key == "scope" else key] = (
                json.dumps(value) if key == "scope" else value
            )
        async with self._db.session() as session, session.begin():
            result = await session.execute(
                update(SectionRow).where(SectionRow.id == section_id).values(**values)
            )
        return affected(result) > 0

    async def delete(self, section_id: int) -> int:
        """Remove a section and its descendants (cascade via parent_id)."""
        async with self._db.session() as session, session.begin():
            result = await session.execute(delete(SectionRow).where(SectionRow.id == section_id))
        return affected(result)

    # ─── Critique state ─────────────────────────────────────────────────

    async def record_critique(self, section_id: int, counts: dict[str, int]) -> int | None:
        """Store severity counts, bump the iteration, set status 'critiqued'.

        Returns the new iteration number, or None if the section doesn't exist.
        """
        stmt = (
            update(SectionRow)
            .where(SectionRow.id == section_id)
            .values(
                blockers=counts["blocker"],
                should_fix=counts["should_fix"],
                nits=counts["nit"],
                critique_iterations=SectionRow.critique_iterations + 1,
                status="critiqued",
                updated_at=func.current_timestamp(),
            )
            .returning(SectionRow.critique_iterations)
        )
        async with self._db.session() as session, session.begin():
            return await session.scalar(stmt)

    async def revise(self, section_id: int, draft: str, status: str) -> bool:
        """Replace the draft and reset critique counters. False if the section is missing."""
        stmt = (
            update(SectionRow)
            .where(SectionRow.id == section_id)
            .values(
                draft=draft,
                blockers=0,
                should_fix=0,
                nits=0,
                critique_iterations=0,
                status=status,
                updated_at=func.current_timestamp(),
            )
        )
        async with self._db.session() as session, session.begin():
            result = await session.execute(stmt)
        return affected(result) > 0

    # ─── Paper links ────────────────────────────────────────────────────

    async def link_papers(self, section_id: int, pairs: Sequence[tuple[int, str | None]]) -> None:
        """Idempotently link `(paper_id, via_query)` pairs to the section."""
        async with self._db.session() as session, session.begin():
            for paper_id, via_query in pairs:
                await session.execute(
                    sqlite_insert(PaperSectionLinkRow)
                    .values(paper_id=paper_id, section_id=section_id, via_query=via_query)
                    .on_conflict_do_nothing()
                )

    async def unlink_paper(self, paper_id: int, section_id: int) -> int:
        stmt = delete(PaperSectionLinkRow).where(
            PaperSectionLinkRow.paper_id == paper_id, PaperSectionLinkRow.section_id == section_id
        )
        async with self._db.session() as session, session.begin():
            result = await session.execute(stmt)
        return affected(result)

    async def linked_papers(
        self, section_id: int, newest_discovery_first: bool
    ) -> list[LinkedPaper]:
        """Papers linked to a section with their review status and the surfacing query."""
        order = (
            (PaperSectionLinkRow.discovered_at.desc(), PaperRow.id.desc())
            if newest_discovery_first
            else (PaperRow.year.desc(), PaperRow.id.desc())
        )
        stmt = (
            select(PaperRow, ReviewRow.status, PaperSectionLinkRow)
            .join(PaperSectionLinkRow, PaperSectionLinkRow.paper_id == PaperRow.id)
            .outerjoin(ReviewRow, ReviewRow.paper_id == PaperRow.id)
            .where(PaperSectionLinkRow.section_id == section_id)
            .order_by(*order)
        )
        async with self._db.session() as session:
            rows = (await session.execute(stmt)).all()
        return [
            {
                "id": paper.id,
                "title": paper.title,
                "year": paper.year,
                "venue": paper.venue,
                "doi": paper.doi,
                "review_status": status,
                "via_query": link.via_query,
                "discovered_at": link.discovered_at,
            }
            for paper, status, link in rows
        ]

    # ─── Document view ──────────────────────────────────────────────────

    async def load_document_sections(self) -> list[DocumentSection]:
        """Sections with a non-empty draft in document order (parents before children)."""
        stmt = select(SectionRow).order_by(SectionRow.position, SectionRow.id)
        async with self._db.session() as session:
            rows = (await session.scalars(stmt)).all()
        children: dict[int | None, list[SectionRow]] = {}
        for r in rows:
            children.setdefault(r.parent_id, []).append(r)
        ordered: list[DocumentSection] = []

        def walk(parent_id: int | None) -> None:
            for r in children.get(parent_id, []):
                if r.draft.strip():
                    ordered.append({"title": r.title, "content": r.draft})
                walk(r.id)

        walk(None)
        return ordered

    async def drafts(self) -> list[SectionDraft]:
        """Every section holding text, in document order."""
        stmt = (
            select(SectionRow.id, SectionRow.title, SectionRow.draft)
            .where(SectionRow.draft != "")
            .order_by(func.coalesce(SectionRow.parent_id, 0), SectionRow.position, SectionRow.id)
        )
        async with self._db.session() as session:
            return [
                {"id": r.id, "title": r.title, "draft": r.draft}
                for r in await session.execute(stmt)
            ]

    async def progress_counts(self) -> SectionProgress:
        stmt = select(
            func.count(),
            func.coalesce(func.sum(case((SectionRow.draft != "", 1), else_=0)), 0),
            func.coalesce(func.sum(case((SectionRow.status == "done", 1), else_=0)), 0),
        )
        async with self._db.session() as session:
            total, drafted, done = (await session.execute(stmt)).one()
        return {"total": total, "drafted": drafted, "done": done}
