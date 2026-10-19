import json
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from snowcite.domain.dedup import find_title_match, normalize_title
from snowcite.domain.models import Paper
from snowcite.domain.records import (
    ApprovedPaper,
    PaperDetails,
    PaperRecord,
    PersistResult,
    SourceRef,
)
from snowcite.storage.database import Database
from snowcite.storage.models import CitationRow, PaperRow, ReviewRow, ReviewSummaryRow


def _paper_record(paper: PaperRow, review: ReviewRow | None) -> PaperRecord:
    return {
        "id": paper.id,
        "source": paper.source,
        "source_id": paper.source_id,
        "doi": paper.doi,
        "title": paper.title,
        "authors": json.loads(paper.authors_json),
        "year": paper.year,
        "venue": paper.venue,
        "pdf_url": paper.pdf_url,
        "created_at": paper.created_at,
        "review_status": review.status if review else None,
        "review_reason": review.reason if review else None,
        "review_note": review.note if review else None,
        "reviewed_by": review.reviewed_by if review else None,
        "reviewed_at": review.reviewed_at if review else None,
    }


class PaperRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def persist(self, papers: list[Paper]) -> PersistResult:
        """Insert papers with DOI uniqueness + fuzzy-title dedup.

        `new_ids` and `new_titles` are aligned — the i-th title belongs to the i-th id.
        """
        result: PersistResult = {"saved": 0, "duplicates": 0, "new_ids": [], "new_titles": []}
        if not papers:
            return result

        async with self._db.session() as session, session.begin():
            # The fuzzy-title check runs against ALL existing titles, not just no-DOI
            # ones: a no-DOI paper arriving for a paper already stored with a DOI is
            # still a duplicate.
            existing_norms = list(await session.scalars(select(PaperRow.title_normalized)))

            for p in papers:
                norm = normalize_title(p.title)
                if not p.doi and find_title_match(norm, existing_norms) is not None:
                    result["duplicates"] += 1
                    continue
                row = PaperRow(
                    source=p.source,
                    source_id=p.source_id,
                    doi=p.doi,
                    title=p.title,
                    title_normalized=norm,
                    authors_json=json.dumps(p.authors),
                    year=p.year,
                    venue=p.venue,
                    abstract=p.abstract,
                    pdf_url=p.pdf_url,
                    bibtex=p.bibtex,
                    metadata_json=json.dumps(p.metadata),
                )
                try:
                    async with session.begin_nested():
                        session.add(row)
                        await session.flush()
                        session.add(ReviewRow(paper_id=row.id, status="unreviewed"))
                        await session.flush()
                except IntegrityError:
                    result["duplicates"] += 1
                    continue
                result["new_ids"].append(row.id)
                result["new_titles"].append(p.title)
                existing_norms.append(norm)

            if result["new_ids"]:
                await session.execute(
                    update(ReviewSummaryRow).where(ReviewSummaryRow.id == 1).values(stale=1)
                )
        result["saved"] = len(result["new_ids"])
        return result

    async def load_approved(self) -> list[ApprovedPaper]:
        """Every approved paper with what bibliography and table rendering need."""
        stmt = (
            select(PaperRow)
            .join(ReviewRow, ReviewRow.paper_id == PaperRow.id)
            .where(ReviewRow.status == "approved")
            .order_by(PaperRow.year, PaperRow.id)
        )
        async with self._db.session() as session:
            rows = (await session.scalars(stmt)).all()
        return [
            {
                "id": r.id,
                "source": r.source,
                "title": r.title,
                "authors": json.loads(r.authors_json),
                "year": r.year,
                "venue": r.venue,
                "doi": r.doi,
                "abstract": r.abstract,
                "bibtex": r.bibtex,
            }
            for r in rows
        ]

    async def find(
        self,
        status: str | None = None,
        source: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        search: str | None = None,
        reviewed_by: str | None = None,
        within_ids: list[int] | None = None,
        include_abstracts: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaperRecord]:
        """Saved papers joined with review state, AND-filtered, in id order.

        Compact by default (no abstract) so batches stay cheap in the model's context.
        """
        stmt = select(PaperRow, ReviewRow).outerjoin(ReviewRow, ReviewRow.paper_id == PaperRow.id)
        if status is not None:
            stmt = stmt.where(ReviewRow.status == status)
        if reviewed_by is not None:
            stmt = stmt.where(ReviewRow.reviewed_by == reviewed_by)
        if source is not None:
            stmt = stmt.where(PaperRow.source == source)
        if year_from is not None:
            stmt = stmt.where(PaperRow.year >= year_from)
        if year_to is not None:
            stmt = stmt.where(PaperRow.year <= year_to)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(PaperRow.title.like(pattern) | PaperRow.abstract.like(pattern))
        if within_ids is not None:
            stmt = stmt.where(PaperRow.id.in_(within_ids))
        stmt = stmt.order_by(PaperRow.id).limit(limit).offset(offset)

        async with self._db.session() as session:
            rows = (await session.execute(stmt)).all()
        out: list[PaperRecord] = []
        for paper, review in rows:
            record = _paper_record(paper, review)
            if include_abstracts:
                record["abstract"] = paper.abstract
            out.append(record)
        return out

    async def details(self, paper_id: int) -> PaperDetails | None:
        """Full record with review state and stored citation-edge counts."""
        stmt = (
            select(PaperRow, ReviewRow)
            .outerjoin(ReviewRow, ReviewRow.paper_id == PaperRow.id)
            .where(PaperRow.id == paper_id)
        )
        async with self._db.session() as session:
            found = (await session.execute(stmt)).first()
            if found is None:
                return None
            paper, review = found
            counts = {}
            for direction in ("references", "citations"):
                counts[direction] = await session.scalar(
                    select(func.count())
                    .select_from(CitationRow)
                    .where(
                        CitationRow.source_paper_id == paper_id,
                        CitationRow.direction == direction,
                    )
                )
        base = _paper_record(paper, review)
        metadata: dict[str, Any] = json.loads(paper.metadata_json) if paper.metadata_json else {}
        return {
            **base,
            "abstract": paper.abstract,
            "bibtex": paper.bibtex,
            "metadata": metadata,
            "references_count": counts["references"] or 0,
            "citations_count": counts["citations"] or 0,
        }

    async def source_ref(self, paper_id: int) -> SourceRef | None:
        """`{source, source_id, doi}` for a paper — enough to look it up elsewhere."""
        stmt = select(PaperRow.source, PaperRow.source_id, PaperRow.doi).where(
            PaperRow.id == paper_id
        )
        async with self._db.session() as session:
            row = (await session.execute(stmt)).first()
        if row is None:
            return None
        return {"source": row.source, "source_id": row.source_id, "doi": row.doi}

    async def exists(self, paper_id: int) -> bool:
        async with self._db.session() as session:
            return await session.get(PaperRow, paper_id) is not None
