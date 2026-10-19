"""Paper reads and the single write path (insert + dedup)."""

import json
from typing import Any

import aiosqlite

from snowcite.domain.dedup import find_title_match, normalize_title
from snowcite.domain.models import ApprovedPaper, Paper, PersistResult
from snowcite.storage.database import Database


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
