"""Critique / revise loop (Phase 5 of v0.3).

The third leg of the writing flow: draft → critique → revise. `critique_section`
gives Claude everything it needs to read a section like a strict academic
reviewer (the draft, the notes the section's claims should rest on, the linked
papers); Claude returns a list of severity-tagged issues; `record_section_critique`
persists the severity counts and updates iteration state. `revise_section`
replaces the draft with the rewrite and resets the counters so the next critique
sees a fresh draft.

Issues themselves are transient — they're produced fresh each iteration, so
storing them buys nothing. Only the *aggregate* (blockers / should_fix / nits)
and iteration count live on the section row, because they drive the stop
criterion.

Stop criterion: critique stops when blockers=0 OR critique_iterations >= 2.
The user can always override by calling `revise_section` again or
`update_section(status='done')` regardless of what the counters say.
"""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container


@mcp.tool()
async def get_section_critique_inputs(section_id: int) -> dict[str, Any]:
    """Bundle everything needed to critique a section in one call.

    Returns `{section, notes, artifacts, linked_papers}`:
    - `section`: full section row including current draft and severity state.
    - `notes`: per-paper + cross-paper notes whose `cluster` overlaps the
      section's `scope.clusters`. The corpus the section's claims should rest on.
    - `artifacts`: included research artifacts (interviews, code, …) as briefs —
      id, citation_label, summary, size, no content; fetch bodies with `get_artifacts`.
    - `linked_papers`: papers connected via `paper_section_links`, with title
      / year / venue / review_status. Used to check that cited papers are
      actually approved and on-scope.

    Claude reads this, generates `[{severity, type, text, suggested_action}]`
    issues, and passes them to `record_section_critique`.
    """
    return await container.section_service.critique_inputs(section_id)


@mcp.tool()
async def record_section_critique(
    section_id: int,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist severity aggregates from a critique pass and decide whether to stop.

    `issues` items: `{severity: 'blocker'|'should_fix'|'nit', type, text, suggested_action?}`.
    Only the per-severity counts are stored; the issues list is echoed back so
    Claude can present it to the user without re-running the analysis.

    Returns `{should_stop: bool, reason, severity, iteration, issues}`. Sets
    section.status to 'critiqued'.
    """
    return await container.section_service.record_critique(section_id, issues)


@mcp.tool()
async def revise_section(
    section_id: int,
    new_draft: str,
    mark_done: bool = False,
) -> dict[str, Any]:
    """Replace the section draft and reset critique state for a fresh pass.

    Resets `blockers`, `should_fix`, `nits`, and `critique_iterations` so the
    next `record_section_critique` starts clean. Status moves to 'drafting'
    by default; pass `mark_done=True` when the user signals the section is
    finished (e.g. after a stop on `iteration >= 2` and they accept residual
    nits).
    """
    return await container.section_service.revise(section_id, new_draft, mark_done)
