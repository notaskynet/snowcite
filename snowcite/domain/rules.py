"""Workflow invariants as pure functions.

Each validator returns an error message (or None) so callers decide how to
surface it. Keeping them here — instead of in tool docstrings — means the rule
is enforced, not just documented.
"""

from typing import Any

from snowcite.domain.types import CROSS_PAPER_NOTE_TYPES, PER_PAPER_NOTE_TYPES


def validate_note_scope(note_type: str, paper_id: int | None) -> str | None:
    """Per-paper types need a paper_id; cross-paper types must not have one."""
    if note_type in PER_PAPER_NOTE_TYPES and paper_id is None:
        return f"note type {note_type!r} requires paper_id"
    if note_type in CROSS_PAPER_NOTE_TYPES and paper_id is not None:
        return f"note type {note_type!r} is cross-paper; leave paper_id null"
    return None


def validate_inline_notes(notes: list[dict[str, Any]], paper_count: int) -> str | None:
    """Notes attached to a review decision: one paper, per-paper types, non-empty text."""
    if paper_count != 1:
        return "inline notes require exactly one paper_id; record them per-paper"
    for idx, item in enumerate(notes):
        ntype = item.get("type")
        ntext = item.get("text", "")
        if ntype not in PER_PAPER_NOTE_TYPES:
            return (
                f"notes[{idx}].type must be a per-paper type "
                f"({sorted(PER_PAPER_NOTE_TYPES)}); got {ntype!r}"
            )
        if not isinstance(ntext, str) or not ntext.strip():
            return f"notes[{idx}].text is empty"
    return None


def progress_warnings(
    approved: int, targets: dict[str, Any], words: int, density: float
) -> list[str]:
    """Warnings for a progress snapshot that falls below its project targets."""
    warnings: list[str] = []
    floor = targets.get("target_sources_min")
    if floor and approved < floor:
        warnings.append(
            f"approved sources ({approved}) below target floor ({floor}) — need {floor - approved} more"
        )
    target_density = targets.get("citation_density_target")
    if target_density and words > 0 and density < target_density:
        warnings.append(
            f"citation density ({density} per 100 words) below target "
            f"({target_density}) — undercited"
        )
    return warnings


def summary_warnings(stale: bool, snapshot: dict[str, int], live: dict[str, int]) -> list[str]:
    """Warnings when the stored review summary has drifted from the live counts."""
    warnings: list[str] = []
    if stale:
        warnings.append(
            "Summary is marked stale (papers added or statuses changed since last update)"
        )
    for key in ("approved", "maybe", "rejected", "unreviewed"):
        if snapshot.get(key, 0) != live.get(key, 0):
            warnings.append(f"{key}: snapshot={snapshot.get(key, 0)}, actual={live.get(key, 0)}")
    return warnings
