"""Project-level settings stored in the `project_metadata` singleton."""

import json
from typing import Any

import aiosqlite

from snowcite.storage.database import Database
from snowcite.storage.projects import NoProjectError


class ProjectRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def targets(self) -> dict[str, Any]:
        """Non-null target metrics (sources min/max, words, citation density)."""
        async with self._db.connection() as conn:
            cur = await conn.execute(
                """
                SELECT target_sources_min, target_sources_max, target_words,
                       citation_density_target
                FROM project_metadata WHERE id = 1
                """
            )
            meta = await cur.fetchone()
        return {k: meta[k] for k in meta.keys() if meta[k] is not None} if meta else {}

    async def defaults(self) -> dict[str, Any]:
        """The whole `project_metadata` row (title/author/backend/standard/language, targets)."""
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT * FROM project_metadata WHERE id = 1")
            row = await cur.fetchone()
        return {k: row[k] for k in row.keys()} if row else {}

    async def switch_backend(self, new_backend: str, wipe_sections: bool) -> None:
        """Set the backend; optionally clear section text written in the old syntax.

        One transaction: drafts must never survive a backend they can't compile under.
        """
        async with self._db.connection() as conn:
            if wipe_sections:
                await conn.execute(
                    "UPDATE sections SET draft = '', status = 'outline', blockers = 0, "
                    "should_fix = 0, nits = 0, critique_iterations = 0 WHERE draft != ''"
                )
            await conn.execute(
                """
                INSERT INTO project_metadata (id, backend, updated_at)
                VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    backend = excluded.backend,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (new_backend,),
            )
            await conn.commit()

    async def thesis(self) -> str | None:
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT content FROM thesis WHERE id = 1")
            row = await cur.fetchone()
        return row["content"] if row else None

    async def discipline(self) -> str | None:
        """`project_metadata.discipline`; None when no project is active yet.

        Catches only "no active project" / "schema not initialised" / IO errors —
        programmer errors surface normally.
        """
        try:
            async with self._db.connection() as conn:
                cur = await conn.execute("SELECT discipline FROM project_metadata WHERE id = 1")
                row = await cur.fetchone()
        except (NoProjectError, aiosqlite.Error, OSError):
            return None
        return row["discipline"] if row else None

    async def save_thesis(self, content: str) -> None:
        async with self._db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO thesis (id, content, updated_at)
                VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (content,),
            )
            await conn.commit()

    async def thesis_record(self) -> dict[str, Any] | None:
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT content, updated_at FROM thesis WHERE id = 1")
            row = await cur.fetchone()
        return dict(row) if row else None

    # ─── Project metadata (author, standard, backend, targets, ...) ─────

    # Columns of the `project_metadata` singleton that callers may set. Keeping
    # them in one place keeps the INSERT, the template variables and the
    # return value in sync; unknown keys land in `extra_json` untouched.
    METADATA_FIELDS = (
        "author",
        "supervisor",
        "institution",
        "department",
        "year",
        "work_type",
        "target_length",
        "language",
        "discipline",
        "standard",
        "methodology",
        "backend",
        "review_strictness",
        "deadline",
        "target_pages",
        "target_sources_min",
        "target_sources_max",
        "target_words",
        "citation_density_target",
    )

    async def load_metadata(self) -> dict[str, Any]:
        """The metadata row without bookkeeping columns or nulls; {} if never saved."""
        async with self._db.connection() as conn:
            cur = await conn.execute("SELECT * FROM project_metadata WHERE id = 1")
            row = await cur.fetchone()
        if row is None:
            return {}
        data = {k: row[k] for k in row.keys() if k not in ("id", "created_at", "updated_at")}
        if data.get("extra_json"):
            data["extra"] = json.loads(data.pop("extra_json"))
        else:
            data.pop("extra_json", None)
        return {k: v for k, v in data.items() if v is not None}

    async def save_metadata(self, metadata: dict[str, Any]) -> None:
        """Upsert the singleton; keys outside `METADATA_FIELDS` are kept in extra_json."""
        known = {k: metadata.get(k) for k in self.METADATA_FIELDS if k in metadata}
        extra = {k: v for k, v in metadata.items() if k not in self.METADATA_FIELDS}
        extra_json = json.dumps(extra) if extra else "{}"

        cols = ["id", *known.keys(), "extra_json", "updated_at"]
        placeholders = ["1", *["?"] * len(known), "?", "CURRENT_TIMESTAMP"]
        updates = [f"{k} = excluded.{k}" for k in (*known.keys(), "extra_json")]
        updates.append("updated_at = CURRENT_TIMESTAMP")
        # Column names come from the static METADATA_FIELDS tuple, never from user input.
        sql = (
            f"INSERT INTO project_metadata ({', '.join(cols)}) "  # noqa: S608
            f"VALUES ({', '.join(placeholders)}) "
            f"ON CONFLICT(id) DO UPDATE SET {', '.join(updates)}"
        )
        async with self._db.connection() as conn:
            await conn.execute(sql, (*known.values(), extra_json))
            await conn.commit()
