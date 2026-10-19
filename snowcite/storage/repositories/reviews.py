"""Review summary / cluster lookups."""

import json
from typing import Any

from snowcite.storage.database import Database


class ReviewRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

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
