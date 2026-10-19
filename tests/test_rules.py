"""Pure workflow rules — no DB needed."""

from snowcite.domain import rules


def test_note_scope_requires_paper_for_per_paper_types():
    assert rules.validate_note_scope("claim", None) is not None
    assert rules.validate_note_scope("claim", 3) is None


def test_note_scope_rejects_paper_for_cross_paper_types():
    assert rules.validate_note_scope("gap", 3) is not None
    assert rules.validate_note_scope("gap", None) is None


def test_inline_notes_need_exactly_one_paper_and_valid_items():
    ok = [{"type": "claim", "text": "x"}]
    assert rules.validate_inline_notes(ok, 1) is None
    assert rules.validate_inline_notes(ok, 2) is not None
    assert rules.validate_inline_notes([{"type": "gap", "text": "x"}], 1) is not None
    assert rules.validate_inline_notes([{"type": "claim", "text": "  "}], 1) is not None


def test_progress_warnings_flag_low_sources_and_density():
    targets = {"target_sources_min": 10, "citation_density_target": 3.0}
    assert len(rules.progress_warnings(4, targets, words=100, density=1.0)) == 2
    assert rules.progress_warnings(12, targets, words=100, density=3.5) == []
    # No words written yet → density isn't judged.
    assert len(rules.progress_warnings(12, targets, words=0, density=0.0)) == 0


def test_summary_warnings_report_stale_and_diverging_counts():
    snap = {"approved": 2, "maybe": 0, "rejected": 1, "unreviewed": 5}
    live = {**snap, "approved": 3}
    got = rules.summary_warnings(True, snap, live)
    assert len(got) == 2 and "approved: snapshot=2, actual=3" in got
    assert rules.summary_warnings(False, snap, snap) == []
