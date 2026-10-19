"""Project-level settings stored in the `project_metadata` singleton."""

from typing import Any

from snowcite.storage.database import Database


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
                await conn.execute("DELETE FROM section_content")
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
