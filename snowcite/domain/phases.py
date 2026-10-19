from dataclasses import dataclass, field

from snowcite.domain.types import Phase


@dataclass(frozen=True)
class WorkflowState:
    """Everything `decide` needs, read from the project in one pass."""

    project_active: bool = False
    has_criteria: bool = False
    papers_total: int = 0
    unreviewed: int = 0
    approved: int = 0
    auto_low: int = 0
    summary_current: bool = False  # a summary exists and isn't stale
    per_paper_notes: int = 0
    cross_paper_notes: int = 0


@dataclass(frozen=True)
class Step:
    phase: Phase
    why: str
    do: list[str] = field(default_factory=list)
    # In `review`: the batch is withheld until the rolling summary is saved.
    needs_summary: bool = False


def decide(s: WorkflowState) -> Step:  # noqa: PLR0911 — one return per phase
    """First unmet stage wins. Gates that used to be prose rules are encoded here."""
    if not s.project_active:
        return Step(
            "not_started",
            "No snowcite project in this directory.",
            [
                "Ask the user for project metadata (language, standard, backend, discipline, targets)",
                "init_project(metadata=...), then resolve settings_diff with the user",
            ],
        )
    if not s.has_criteria:
        return Step(
            "criteria",
            "No inclusion/exclusion criteria yet.",
            [
                "Agree inclusion, exclusion and review categories with the user",
                "review_criteria(criteria_text)",
            ],
        )
    if s.papers_total == 0:
        return Step(
            "search",
            "Criteria are set but no papers have been collected.",
            ["search_papers(query=...) for each key topic in the criteria"],
        )
    if s.unreviewed > 0:
        reviewed = s.papers_total - s.unreviewed
        if reviewed > 0 and not s.summary_current:
            return Step(
                "review",
                "The rolling summary is missing or stale; save it before the next batch.",
                [
                    "Rewrite the summary (<= 500 words) from the current approved/maybe papers, "
                    "using the categories from the criteria",
                    "review_summary(summary, clusters)",
                ],
                needs_summary=True,
            )
        return Step(
            "review",
            f"{s.unreviewed} paper(s) still unreviewed.",
            [
                "Re-read the criteria in the payload (drift guard)",
                "Decide each paper in `batch`: confident -> auto_high, leaning -> auto_low, "
                "borderline -> ask the user one at a time without recommending",
                "review_batch(decisions) in one call — approved/maybe papers need at least one "
                "claim or finding note; rejected get none",
                "Call next_step() again after the batch",
            ],
        )
    if s.approved == 0:
        return Step(
            "search",
            "Every paper is reviewed but none is approved.",
            ["Revisit the criteria with the user or search with different queries"],
        )
    if s.auto_low > 0:
        return Step(
            "low_confidence",
            f"{s.auto_low} auto_low decision(s) await the user's confirmation.",
            [
                "Walk the papers one at a time with the user (facts only, no recommendation)",
                "review_batch([{paper_id, status, reason: 'manual: ...', reviewed_by: 'user'}])",
            ],
        )
    if s.per_paper_notes > 0 and s.cross_paper_notes == 0:
        return Step(
            "synthesis",
            "Per-paper notes exist but no cross-paper synthesis has been recorded.",
            [
                "For each cluster: get_cluster_notes(cluster), then name gaps, contradictions, "
                "consensus and open questions",
                "add_synthesis_note(cluster, type, text, derived_from_note_ids=[...]) — sources required",
                "find_gaps() afterwards",
            ],
        )
    return Step(
        "done",
        "The corpus is reviewed and synthesised; the literature work is complete.",
        [
            "Hand over to the writing skills: the notes graph, clusters and papers are the source",
            "papers(status='approved', cluster=..., include_abstracts=True) / get_cluster_notes(cluster) for the material",
        ],
    )
