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
