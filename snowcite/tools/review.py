"""Review tools — criteria, status, progress, summary."""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import ReviewedBy, Source, Status


@mcp.tool()
async def set_review_criteria(criteria_text: str) -> dict[str, int]:
    """Store inclusion/exclusion criteria (and optionally user-defined categories). Returns {id}."""
    return await container.review_service.set_criteria(criteria_text)


@mcp.tool()
async def get_review_criteria() -> dict[str, Any] | None:
    """Latest criteria. Claude must call this before each review batch (drift guard)."""
    return await container.review_service.get_criteria()


@mcp.tool()
async def get_unreviewed_papers(
    limit: int = 20,
    source: Source | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    include_abstracts: bool = False,
) -> list[dict[str, Any]]:
    """Batch of unreviewed papers for pre-filtering.

    By default (include_abstracts=False) returns compact records — title / year / venue /
    authors / doi. This keeps the context lean on large reviews. For borderline cases,
    pull the full abstract via `get_paper_details(paper_id)`.
    """
    return await container.review_service.unreviewed(
        limit, source, year_from, year_to, include_abstracts
    )


@mcp.tool()
async def get_low_confidence_reviews(
    status: Status | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Auto-classified papers that Claude flagged as low-confidence.

    Use this on a second pass: after the main review loop, walk these with the user
    to confirm or flip them. They're the auto-review's blind spots.
    Returns title/year/authors/current-status + reason, without abstracts — fetch
    those via `get_paper_details` for borderline ones.
    """
    return await container.review_service.low_confidence(status, limit)


@mcp.tool()
async def set_review_status(
    paper_ids: list[int],
    status: Status,
    reason: str,
    note: str | None = None,
    reviewed_by: ReviewedBy = "auto_high",
    notes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Batch-set review status with required reason (PRISMA trail). Marks summary stale.

    Use `reviewed_by`:
    - `"auto_high"` — clear match or clear off-topic, you're confident.
    - `"auto_low"` — weaker signal (extrapolation, partial keyword match). The
      user should sanity-check these. Fetch with `get_low_confidence_reviews()`
      during a second pass, or surface them proactively.
    - `"user"` — the user decided.

    `notes` — optional graph notes recorded in the same call so review and
    extraction stay co-located. Each item: `{type, text, cluster?}` where `type`
    is a per-paper note type (claim/finding/method/limitation). Only allowed
    when `paper_ids` has exactly one entry — otherwise the same notes would
    duplicate across papers, which is almost never what you mean.
    """
    return await container.review_service.set_status(
        paper_ids, status, reason, note, reviewed_by, notes
    )


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
    """Revert the most recent `set_review_status` entry in review_history.

    Restores the paper to its `old_status` (typically "unreviewed" if the
    action was the first classification). The history row itself is removed so
    a subsequent undo walks further back.

    Useful when Claude mis-classifies a borderline paper as auto_high and the
    user catches it. Does not undo bulk operations — call multiple times.
    """
    return await container.review_service.undo_last()


@mcp.tool()
async def get_review_progress() -> dict[str, Any]:
    """Progress snapshot against the project's targets.

    Always returns review counts (total / approved / maybe / rejected /
    unreviewed). When the project has target metrics set in `init_project`
    (sources min/max, words, citation density) this tool also returns how
    far the current state is from those targets plus a `warnings` list for
    anything below its floor.

    Writing metrics (words, citations, density) come from stored section
    drafts; they're zero when no sections are written yet.
    """
    return await container.review_service.progress()


@mcp.tool()
async def save_review_summary(
    summary: str,
    clusters: list[dict[str, Any]],
) -> dict[str, str]:
    """UPSERT singleton review summary (≤500 words). Called after each review batch."""
    return await container.review_service.save_summary(summary, clusters)


@mcp.tool()
async def get_review_summary() -> dict[str, Any] | None:
    """Rolling summary + clusters + live counts + stale check.

    Returns None if no summary exists yet (first batch).
    Includes 'warnings' list if counts diverge from snapshot.
    """
    return await container.review_service.get_summary()


@mcp.tool()
async def get_papers_for_writing(
    cluster: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Approved papers with abstracts, optionally filtered by cluster topic.

    When cluster is given, filters to paper IDs listed in the matching cluster
    from the review summary. Without cluster, returns all approved papers.
    """
    return await container.review_service.papers_for_writing(cluster, limit, offset)
