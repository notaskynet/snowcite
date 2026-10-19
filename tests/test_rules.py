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


def test_normalize_scope_keeps_known_keys_only():
    got = rules.normalize_scope({"clusters": ["a"], "junk": 1, "keywords": "not-a-list"})
    assert got == {"clusters": ["a"], "keywords": [], "questions": []}


def test_count_severities_and_bad_severity():
    issues = [{"severity": "blocker"}, {"severity": "nit"}, {"severity": "nit"}]
    assert rules.count_severities(issues) == {"blocker": 1, "should_fix": 0, "nit": 2}
    assert "issues[0].severity" in rules.count_severities([{"severity": "huge"}])


def test_critique_verdict_stops_without_blockers_or_at_cap():
    assert rules.critique_verdict(0, 1)[0] is True
    assert rules.critique_verdict(2, 1)[0] is False
    stop, reason = rules.critique_verdict(2, rules.MAX_CRITIQUE_ITERATIONS)
    assert stop and "max critique iterations" in reason


def test_validate_synthesis_requires_traceable_per_paper_sources():
    sources = {1: 10, 2: None}
    assert rules.validate_synthesis("gap", "x", [1], sources) is None
    assert rules.validate_synthesis("claim", "x", [1], sources) is not None
    assert rules.validate_synthesis("gap", "x", [], sources) is not None
    assert "not found" in rules.validate_synthesis("gap", "x", [9], sources)
    assert "cross-paper" in rules.validate_synthesis("gap", "x", [2], sources)


def test_cluster_gap_flags():
    types = {"claim": [1, 2], "limitation": [3], "contradiction": [4, 5]}
    flags, per_paper, unanchored = rules.cluster_gap_flags(types, anchored={4})
    assert per_paper == 3
    assert flags == ["unsynthesised", "unresolved_contradiction"]
    assert unanchored == [5]
