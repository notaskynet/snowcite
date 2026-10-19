from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import ReviewedBy, Source, Status


@mcp.tool()
async def review_criteria(criteria_text: str | None = None) -> dict[str, Any] | None:
    """Read or set the inclusion/exclusion criteria (and user-defined categories).

    Without `criteria_text` returns the latest criteria `{id, criteria_text, created_at}`
    (or None) — the drift guard before each batch; `next_step` also carries them in the
    review payload. With `criteria_text` stores a new version and returns `{id}`.
    """
    if criteria_text is None:
        return await container.review_service.get_criteria()
    return await container.review_service.set_criteria(criteria_text)


@mcp.tool()
async def review_batch(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Record a batch of review decisions (PRISMA trail). Marks the summary stale.

    Each decision: `{paper_id | paper_ids, status, reason, reviewed_by?, note?, notes?}`
    - `status`: approved | maybe | rejected | unreviewed. `reason` is required.
    - `reviewed_by`: `auto_high` (default — clear match / clear off-topic), `auto_low`
      (weaker signal; the user confirms these later), `user` (the user decided).
    - `notes`: `[{type, text, cluster?}]` with per-paper types claim | finding | method |
      limitation. Approved/maybe papers must leave a claim or finding in the graph:
      pass `notes` (one paper per decision) unless the paper already has notes.
      Rejected papers take none.

    Valid decisions are applied; invalid ones come back in `errors` by index so only
    those need resending. Returns `{updated, errors, note_ids?, skipped_invalid_ids?}`.
    """
    return await container.review_service.review_batch(decisions)


@mcp.tool()
async def bulk_reclassify(
    new_status: Status,
    reason: str,
    current_status: Status | None = None,
    source: Source | None = None,
    cluster: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    reviewed_by: ReviewedBy = "auto_high",
    limit: int | None = None,
) -> dict[str, Any]:
    """Reclassify every paper matching the filter. Writes audit entries per paper.

    Filter is AND-joined — provide any subset of:
    - `current_status`: reclassify only papers currently at this status
    - `source`: only papers from this source
    - `cluster`: papers listed in this cluster of the current review_summary
    - `year_from`, `year_to`: publication-year window
    - `limit`: cap the number of papers touched (safety rail)

    Use case: you narrowed the scope and want to move an entire
    "attacks-classic" cluster from `approved` to `maybe` in one shot.
    """
    return await container.review_service.bulk_reclassify(
        new_status,
        reason,
        current_status,
        source,
        cluster,
        year_from,
        year_to,
        reviewed_by,
        limit,
    )


@mcp.tool()
async def undo_last_review_action() -> dict[str, Any]:
    """Revert the most recent review decision (newest `review_history` entry).

    Restores the paper to its `old_status` (typically "unreviewed" if the
    action was the first classification). The history row itself is removed so
    a subsequent undo walks further back.

    Useful when Claude mis-classifies a borderline paper as auto_high and the
    user catches it. Does not undo bulk operations — call multiple times.
    """
    return await container.review_service.undo_last()


@mcp.tool()
async def review_summary(
    summary: str | None = None,
    clusters: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Read or save the rolling review summary (singleton, <= 500 words).

    Without arguments returns `{summary, clusters, counts_snapshot, counts_live, stale,
    warnings}` (None before the first save) — cross-check the live counts against the
    text. With `summary` and `clusters` (`[{topic, paper_ids, count}]`, topics taken
    from the criteria categories) it overwrites the summary; do this after each batch.
    """
    if summary is None:
        return await container.review_service.get_summary()
    if clusters is None:
        return {"error": "clusters are required when saving a summary"}
    return await container.review_service.save_summary(summary, clusters)


@mcp.tool()
async def get_prisma_counts() -> dict[str, Any]:
    """PRISMA flow numbers from the review trail.

    `identified` (papers ever recorded), `screened` (decided, not unreviewed),
    `excluded_total` with `excluded_by_reason`, and `included` (approved). The
    model draws the diagram or writes the prose itself.
    """
    return await container.reviews.prisma_counts()
