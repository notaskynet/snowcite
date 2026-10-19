from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import NoteType


@mcp.tool()
async def get_cluster_notes(cluster: str) -> dict[str, Any]:
    """Bundled view of one cluster: per-paper notes grouped by paper + existing cross-paper notes.

    Use this as the input to a synthesis pass — it returns everything Claude
    needs to reason across the cluster in one round-trip:

    - `papers`: list of `{paper_id, title, year, notes: [...]}` for every paper
      with at least one note in this cluster.
    - `cross_paper`: list of cross-paper notes (gap/contradiction/consensus/
      open_question) already recorded against the cluster, with their
      `derived_from` source ids.
    - `counts`: per-type counts in the cluster.
    """
    return await container.synthesis.cluster_notes(cluster)


@mcp.tool()
async def add_synthesis_note(
    cluster: str,
    type: NoteType,  # noqa: A002 — natural field name across the notes API
    text: str,
    derived_from_note_ids: list[int],
) -> dict[str, Any]:
    """Atomic insert of a cross-paper note + `derived_from` links to its sources.

    `type` must be a cross-paper type (gap, contradiction, consensus,
    open_question). `derived_from_note_ids` must reference existing per-paper
    notes — at least one is required, so the synthesis is traceable. Returns
    `{id, links: N}` or `{error}`.
    """
    return await container.synthesis.add_synthesis(cluster, type, text, derived_from_note_ids)


@mcp.tool()
async def find_gaps(cluster: str | None = None) -> dict[str, Any]:
    """Surface clusters where cross-paper synthesis is thin or missing.

    Heuristics (each cluster can hit multiple):
    - `thin`: fewer than 3 per-paper notes — synthesis is premature, read more
      papers first.
    - `unsynthesised`: ≥1 `limitation` note but no `gap`/`open_question` —
      limitations were noted per-paper but never aggregated into a cross-paper gap.
    - `unresolved_contradiction`: `contradiction` notes without `derived_from`
      links — recorded but not anchored to source papers.
    - `cluster_unknown_in_summary`: cluster name doesn't match any cluster in
      the current `review_summary` — likely a typo or invented label.

    With `cluster` filters to that one cluster; otherwise scans all clusters
    that have any notes.
    """
    return await container.synthesis.find_gaps(cluster)
