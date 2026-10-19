"""Notes / knowledge-graph tools (v0.3).

Notes are short structured statements about papers, written during review and
synthesised across papers afterwards. They form the working memory the user
draws on during writing — facts, methods, gaps, contradictions — instead of
re-reading abstracts. Tool layer enforces the per-paper vs cross-paper split:

- per-paper notes (claim/finding/method/limitation) require `paper_id`;
- cross-paper notes (gap/contradiction/consensus/open_question) reject it
  and instead reference other notes via `note_links` (Phase 2).
"""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import NoteLinkKind, NoteType


@mcp.tool()
async def add_note(
    type: NoteType,  # noqa: A002 — natural field name across the notes API
    text: str,
    paper_id: int | None = None,
    cluster: str | None = None,
) -> dict[str, Any]:
    """Record a single graph note. Returns {id} on success, {error} on validation failure.

    `type` ∈ {claim, finding, method, limitation, gap, contradiction, consensus, open_question}.
    Per-paper types require `paper_id`; cross-paper types reject it.
    `cluster` should match a topic from the current `review_summary` clusters
    (Claude must not invent new ones).
    Keep `text` short — one or two sentences, paraphrased.
    """
    return await container.note_service.add(type, text, paper_id, cluster)


@mcp.tool()
async def add_notes(notes: list[dict[str, Any]]) -> dict[str, Any]:
    """Batch-insert notes. Each item: {type, text, paper_id?, cluster?}.

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
) -> dict[str, Any]:
    """Edit fields on an existing note. Pass only the fields to change.

    Type changes are validated against the existing `paper_id` — switching from
    a per-paper type to a cross-paper type (or vice versa) requires also
    nulling/setting paper_id, which this tool will not do; recreate the note
    instead in that case.
    """
    return await container.note_service.update(note_id, text, type, cluster)


@mcp.tool()
async def delete_note(note_id: int) -> dict[str, Any]:
    """Remove a note and any links touching it. Idempotent — missing id is a no-op."""
    return await container.note_service.delete(note_id)


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


@mcp.tool()
async def get_note_density(cluster: str | None = None) -> dict[str, Any]:
    """Note counts per cluster × type — used by Phase 2's `find_gaps`.

    Without `cluster` returns the full breakdown; with `cluster` filters to one.
    Clusters with few per-paper notes or no `gap`/`contradiction` resolution are
    a hint that synthesis is incomplete.
    """
    return await container.note_service.density(cluster)
