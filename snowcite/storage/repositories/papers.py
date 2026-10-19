"""Paper reads and the single write path (insert + dedup)."""

import json
from typing import Any

import aiosqlite

from snowcite.domain.dedup import find_title_match, normalize_title
from snowcite.domain.models import ApprovedPaper, Paper, PersistResult
from snowcite.storage.database import Database
from snowcite.storage.rows import paper_row_to_dict


class PaperRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def persist(self, papers: list[Paper]) -> PersistResult:
        """Insert papers with DOI uniqueness + fuzzy-title dedup.

        Returns `{saved, duplicates, new_ids, new_titles}`. `new_ids` and
        `new_titles` are aligned — the i-th title belongs to the i-th id.
        """
        if not papers:
            return {"saved": 0, "duplicates": 0, "new_ids": [], "new_titles": []}

        duplicates = 0
        new_ids: list[int] = []
        new_titles: list[str] = []
        async with self._db.connection() as conn:
            # Fuzzy-title check runs against ALL existing titles, not just no-DOI
            # ones: a no-DOI paper arriving for a paper already in DB with a DOI
            # is still a duplicate.
            cur = await conn.execute("SELECT title_normalized FROM papers")
            existing_norms = [r[0] for r in await cur.fetchall()]

            for p in papers:
                norm = normalize_title(p.title)
                if not p.doi and find_title_match(norm, existing_norms) is not None:
                    duplicates += 1
                    continue
                try:
                    cur = await conn.execute(
                        """
                        INSERT INTO papers
                            (source, source_id, doi, title, title_normalized,
                             authors_json, year, venue, abstract, pdf_url,
                             bibtex, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            p.source,
                            p.source_id,
                            p.doi,
                            p.title,
                            norm,
                            json.dumps(p.authors),
                            p.year,
                            p.venue,
                            p.abstract,
                            p.pdf_url,
                            p.bibtex,
                            json.dumps(p.metadata),
                        ),
                    )
                    new_ids.append(cur.lastrowid)
                    new_titles.append(p.title)
                    await conn.execute(
                        "INSERT INTO reviews (paper_id, status) VALUES (?, 'unreviewed')",
                        (cur.lastrowid,),
                    )
                    existing_norms.append(norm)
                except aiosqlite.IntegrityError:
                    duplicates += 1
            if new_ids:
                await conn.execute("UPDATE review_summary SET stale = 1 WHERE id = 1")
            await conn.commit()
        return {
            "saved": len(new_ids),
            "duplicates": duplicates,
            "new_ids": new_ids,
            "new_titles": new_titles,
        }

    async def load_approved(self) -> list[ApprovedPaper]:
        """Every approved paper with what bibliography + table rendering need."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                """
                SELECT p.id, p.source, p.title, p.authors_json, p.year, p.venue,
                       p.doi, p.abstract, p.bibtex
                FROM papers p JOIN reviews r ON r.paper_id = p.id
                WHERE r.status = 'approved'
                ORDER BY p.year, p.id
                """
            )
            rows = await cur.fetchall()
        return [
            {
                "id": r["id"],
                "source": r["source"],
                "title": r["title"],
                "authors": json.loads(r["authors_json"] or "[]"),
                "year": r["year"],
                "venue": r["venue"],
                "doi": r["doi"],
                "abstract": r["abstract"],
                "bibtex": r["bibtex"],
            }
            for r in rows
        ]

    async def load_by_ids(self, paper_ids: list[int]) -> list[dict[str, Any]]:
        """A subset of papers by id, with abstracts (for review/regeneration bundles)."""
        if not paper_ids:
            return []
        placeholders = ",".join("?" * len(paper_ids))
        async with self._db.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT id, title, authors_json, year, venue, doi, abstract
                FROM papers WHERE id IN ({placeholders})
                ORDER BY year, id
                """,  # noqa: S608 — placeholder count bound from paper_ids
                paper_ids,
            )
            rows = await cur.fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "authors": json.loads(r["authors_json"] or "[]"),
                "year": r["year"],
                "venue": r["venue"],
                "doi": r["doi"],
                "abstract": r["abstract"],
            }
            for r in rows
        ]

    async def exists(self, paper_id: int) -> bool:
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT 1 FROM papers WHERE id = ?", (paper_id,))
            return await cur.fetchone() is not None

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
    ) -> list[dict[str, Any]]:
        """Saved papers joined with review state, AND-filtered, in id order.

        Compact by default (no abstract / bibtex / metadata) so batches stay cheap
        in the model's context; `include_abstracts` adds the abstract.
        """
        query = """
            SELECT p.*, r.status AS review_status, r.reason AS review_reason,
                   r.note AS review_note, r.reviewed_by, r.reviewed_at
            FROM papers p
            LEFT JOIN reviews r ON r.paper_id = p.id
            WHERE 1=1
        """
        params: list[Any] = []
        if status is not None:
            query += " AND r.status = ?"
            params.append(status)
        if reviewed_by is not None:
            query += " AND r.reviewed_by = ?"
            params.append(reviewed_by)
        if source is not None:
            query += " AND p.source = ?"
            params.append(source)
        if year_from is not None:
            query += " AND p.year >= ?"
            params.append(year_from)
        if year_to is not None:
            query += " AND p.year <= ?"
            params.append(year_to)
        if search:
            query += " AND (p.title LIKE ? OR p.abstract LIKE ?)"
            params.extend([f"%{search}%"] * 2)
        if within_ids is not None:
            query += f" AND p.id IN ({','.join('?' * len(within_ids))})"
            params.extend(within_ids)
        query += " ORDER BY p.id LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        async with self._db.connection() as conn:
            cur = await conn.execute(query, params)
            papers = [paper_row_to_dict(r) for r in await cur.fetchall()]
        for p in papers:
            p.pop("bibtex", None)
            p.pop("metadata", None)
            p.pop("title_normalized", None)
            if not include_abstracts:
                p.pop("abstract", None)
        return papers

    async def details(self, paper_id: int) -> dict[str, Any] | None:
        """Full record with review status and stored citation-edge counts."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                """
                SELECT p.*, r.status AS review_status, r.reason AS review_reason,
                       r.note AS review_note, r.reviewed_by, r.reviewed_at
                FROM papers p
                LEFT JOIN reviews r ON r.paper_id = p.id
                WHERE p.id = ?
                """,
                (paper_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            paper = paper_row_to_dict(row)
            for direction in ("references", "citations"):
                cur = await conn.execute(
                    "SELECT COUNT(*) FROM citations WHERE source_paper_id = ? AND direction = ?",
                    (paper_id, direction),
                )
                paper[f"{direction}_count"] = (await cur.fetchone())[0]
        return paper

    async def source_ref(self, paper_id: int) -> dict[str, Any] | None:
        """`{source, source_id, doi}` for a paper — enough to look it up elsewhere."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                "SELECT source, source_id, doi FROM papers WHERE id = ?", (paper_id,)
            )
            row = await cur.fetchone()
        return dict(row) if row else None
