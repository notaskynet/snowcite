"""Knowledge-graph notes: validation lives here, SQL in `NoteRepository`."""

from typing import Any

from snowcite.domain import rules
from snowcite.storage.repositories import NoteRepository


class NoteService:
    def __init__(self, notes: NoteRepository) -> None:
        self._notes = notes

    async def add(
        self, note_type: str, text: str, paper_id: int | None, cluster: str | None
    ) -> dict[str, Any]:
        error = rules.validate_note_scope(note_type, paper_id)
        if error:
            return {"error": error}
        if not text.strip():
            return {"error": "text is empty"}
        return {"id": await self._notes.add(paper_id, cluster, note_type, text.strip())}

    async def add_many(self, notes: list[dict[str, Any]]) -> dict[str, Any]:
        """Insert the valid items; report the rest by index so the caller can resend them."""
        rows: list[tuple[int | None, str | None, str, str]] = []
        errors: list[dict[str, Any]] = []
        for idx, item in enumerate(notes):
            note_type = item.get("type")
            text = item.get("text", "")
            paper_id = item.get("paper_id")
            if not note_type:
                errors.append({"index": idx, "error": "missing type"})
                continue
            error = rules.validate_note_scope(note_type, paper_id)
            if error:
                errors.append({"index": idx, "error": error})
                continue
            if not isinstance(text, str) or not text.strip():
                errors.append({"index": idx, "error": "text is empty"})
                continue
            rows.append((paper_id, item.get("cluster"), note_type, text.strip()))
        ids = await self._notes.add_many(rows)
        return {"inserted": len(ids), "ids": ids, "errors": errors}

    async def find(
        self, paper_id: int | None, cluster: str | None, note_type: str | None, limit: int
    ) -> list[dict[str, Any]]:
        return await self._notes.find(paper_id, cluster, note_type, limit)

    async def update(
        self, note_id: int, text: str | None, note_type: str | None, cluster: str | None
    ) -> dict[str, Any]:
        if text is None and note_type is None and cluster is None:
            return {"error": "no fields to update"}
        current = await self._notes.get_scope(note_id)
        if current is None:
            return {"error": f"note {note_id} not found"}
        error = rules.validate_note_scope(note_type or current["type"], current["paper_id"])
        if error:
            return {"error": f"type change invalid: {error}"}
        if text is not None and not text.strip():
            return {"error": "text is empty"}
        await self._notes.update(
            note_id, text.strip() if text is not None else None, note_type, cluster
        )
        return {"updated": True, "id": note_id}

    async def delete(self, note_id: int) -> dict[str, Any]:
        return {"deleted": await self._notes.delete(note_id)}

    async def link(self, from_note_id: int, to_note_id: int, kind: str) -> dict[str, Any]:
        await self._notes.link(from_note_id, to_note_id, kind)
        return {"linked": True}

    async def density(self, cluster: str | None) -> dict[str, Any]:
        return {"density": await self._notes.density(cluster)}
