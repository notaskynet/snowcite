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


# ─── Sections and critique ──────────────────────────────────────────────────

MAX_CRITIQUE_ITERATIONS = 2
_SEVERITIES = ("blocker", "should_fix", "nit")


def normalize_scope(scope: dict[str, Any] | None) -> dict[str, list[str]]:
    """Coerce arbitrary scope payloads into the canonical `{clusters, keywords, questions}`.

    Unknown keys are dropped; empty lists are kept (they mean "intentionally empty").
    """
    scope = scope or {}
    out: dict[str, list[str]] = {"clusters": [], "keywords": [], "questions": []}
    for key in out:
        val = scope.get(key, [])
        if isinstance(val, list):
            out[key] = [str(v) for v in val if isinstance(v, str | int | float)]
    return out


def count_severities(issues: list[dict[str, Any]]) -> dict[str, int] | str:
    """Per-severity counts of critique issues, or an error message for a bad severity."""
    counts = dict.fromkeys(_SEVERITIES, 0)
    for idx, item in enumerate(issues):
        sev = item.get("severity")
        if sev not in counts:
            return f"issues[{idx}].severity must be one of {sorted(counts)}; got {sev!r}"
        counts[sev] += 1
    return counts


def critique_verdict(blockers: int, iteration: int) -> tuple[bool, str]:
    """Stop criterion: no blockers left, or the iteration cap reached."""
    if blockers == 0:
        return True, "no blockers remaining"
    if iteration >= MAX_CRITIQUE_ITERATIONS:
        return True, (
            f"reached max critique iterations ({MAX_CRITIQUE_ITERATIONS}) — "
            "surface remaining blockers to the user"
        )
    return False, "blockers remain; revise and re-critique"


# ─── Synthesis ──────────────────────────────────────────────────────────────

# Fewer per-paper notes than this and synthesis can't be meaningful yet.
MIN_PER_PAPER_NOTES = 3


def validate_synthesis(
    note_type: str, text: str, source_ids: list[int], source_paper_ids: dict[int, int | None]
) -> str | None:
    """A cross-paper note must be non-empty and traceable to existing per-paper notes.

    `source_paper_ids` maps each *existing* note id to its paper_id.
    """
    if note_type not in CROSS_PAPER_NOTE_TYPES:
        return f"type must be cross-paper ({sorted(CROSS_PAPER_NOTE_TYPES)}); got {note_type!r}"
    if not text.strip():
        return "text is empty"
    if not source_ids:
        return "derived_from_note_ids cannot be empty — synthesis must cite sources"
    missing = [i for i in source_ids if i not in source_paper_ids]
    if missing:
        return f"derived_from_note_ids not found: {missing}"
    cross = [i for i in source_ids if source_paper_ids[i] is None]
    if cross:
        return f"derived_from must point to per-paper notes; these are cross-paper: {cross}"
    return None


def cluster_gap_flags(
    types: dict[str, list[int]], anchored: set[int]
) -> tuple[list[str], int, list[int]]:
    """`(flags, per_paper_note_count, unanchored_contradiction_ids)` for one cluster."""
    per_paper_n = sum(len(ids) for t, ids in types.items() if t in PER_PAPER_NOTE_TYPES)
    flags: list[str] = []
    if per_paper_n < MIN_PER_PAPER_NOTES:
        flags.append("thin")
    if types.get("limitation") and not (types.get("gap") or types.get("open_question")):
        flags.append("unsynthesised")
    unanchored = [nid for nid in types.get("contradiction", []) if nid not in anchored]
    if unanchored:
        flags.append("unresolved_contradiction")
    return flags, per_paper_n, unanchored
