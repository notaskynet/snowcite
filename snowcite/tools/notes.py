from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import NoteLinkKind, NoteType


@mcp.tool()
async def add_notes(notes: list[dict[str, Any]]) -> dict[str, Any]:
    """Batch-insert notes. Each item: {type, text, paper_id?, cluster?}.

    `type` ∈ {claim, finding, method, limitation, gap, contradiction, consensus,
    open_question}. Per-paper types require `paper_id`; cross-paper types reject it
    (record those with `add_synthesis_note` so they cite their sources). `cluster`
    must match a topic of the current review summary — never invent one. Keep `text`
    to one or two paraphrased sentences.

    Returns `{inserted: N, ids: [...], errors: [{index, error}]}`. Valid items
    are inserted even if some fail validation; the caller can fix the rejected
    rows and resend just those.
    """
    return await container.note_service.add_many(notes)


@mcp.tool()
async def get_notes(
    paper_id: int | None = None,
    cluster: str | None = None,
    type: NoteType | None = None,  # noqa: A002 — field name consistency across notes API
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Fetch notes filtered by paper, cluster, and/or type. Newest first.

    Without filters returns every note up to `limit`. Use this before drafting a
    section to pull the relevant part of the graph.
    """
    return await container.note_service.find(paper_id, cluster, type, limit)


@mcp.tool()
async def update_note(
    note_id: int,
    text: str | None = None,
    type: NoteType | None = None,  # noqa: A002 — field name consistency across notes API
    cluster: str | None = None,
    delete: bool = False,
) -> dict[str, Any]:
    """Edit or delete an existing note. Pass only the fields to change.

    `delete=True` removes the note and any links touching it (idempotent — a missing
    id is a no-op); the other fields are ignored then.

    Type changes are validated against the existing `paper_id` — switching from
    a per-paper type to a cross-paper type (or vice versa) requires also
    nulling/setting paper_id, which this tool will not do; recreate the note
    instead in that case.
    """
    if delete:
        return await container.note_service.delete(note_id)
    return await container.note_service.update(note_id, text, type, cluster)


@mcp.tool()
async def link_notes(
    from_note_id: int,
    to_note_id: int,
    kind: NoteLinkKind,
) -> dict[str, Any]:
    """Connect two notes with a typed edge.

    `kind` ∈ {supports, contradicts, extends, derived_from}. Used during
    cross-paper synthesis (Phase 2) to anchor `gap`/`contradiction`/etc. notes
    to the per-paper notes that prompted them.
    """
    return await container.note_service.link(from_note_id, to_note_id, kind)
