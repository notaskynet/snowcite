"""next_step: phase decision (pure) and the end-to-end walk through a project."""

from dataclasses import replace
from pathlib import Path

from snowcite.container import container
from snowcite.domain import rules
from snowcite.domain.models import Paper
from snowcite.domain.phases import WorkflowState, decide
from snowcite.tools.review import save_review_summary, set_review_criteria, set_review_status
from snowcite.tools.session import next_step


# ─── decide(): pure ─────────────────────────────────────────────────────────

BASE = WorkflowState(project_active=True, has_criteria=True, papers_total=4, approved=2)


def test_decide_early_phases():
    assert decide(WorkflowState()).phase == "not_started"
    assert decide(WorkflowState(project_active=True)).phase == "criteria"
    assert decide(WorkflowState(project_active=True, has_criteria=True)).phase == "search"


def test_review_withholds_batch_until_summary_saved():
    reviewing = replace(BASE, unreviewed=2)
    assert decide(reviewing).needs_summary is True
    assert decide(replace(reviewing, summary_current=True)).needs_summary is False
    # Nothing reviewed yet → the first batch needs no summary.
    first = replace(BASE, papers_total=2, unreviewed=2, approved=0)
    assert decide(first).needs_summary is False


def test_all_rejected_goes_back_to_search():
    assert decide(replace(BASE, approved=0)).phase == "search"


def test_low_confidence_blocks_synthesis_and_outline():
    assert decide(replace(BASE, auto_low=1)).phase == "low_confidence"


def test_synthesis_only_when_notes_exist_but_none_cross_paper():
    assert decide(replace(BASE, per_paper_notes=3)).phase == "synthesis"
    assert decide(replace(BASE, per_paper_notes=3, cross_paper_notes=1)).phase == "outline"
    assert decide(BASE).phase == "outline"  # no notes at all: don't loop on synthesis


def test_late_phases():
    s = replace(BASE, cross_paper_notes=1, sections_total=2)
    assert decide(replace(s, has_unfinished_section=True)).phase == "writing"
    assert decide(s).phase == "build"
    assert decide(replace(s, document_current=True)).phase == "done"


def test_next_section_action():
    sec = {"draft": "", "status": "outline", "severity": {"blockers": 0}, "critique_iterations": 0}
    assert rules.next_section_action(sec) == "draft"
    assert rules.next_section_action({**sec, "draft": "x", "status": "drafting"}) == "critique"
    crit = {**sec, "draft": "x", "status": "critiqued"}
    assert rules.next_section_action({**crit, "severity": {"blockers": 2}}) == "revise"
    assert (
        rules.next_section_action(
            {
                **crit,
                "severity": {"blockers": 2},
                "critique_iterations": rules.MAX_CRITIQUE_ITERATIONS,
            }
        )
        == "finish"
    )
    assert rules.next_section_action(crit) == "finish"


# ─── next_step(): integration ───────────────────────────────────────────────


async def test_no_project_returns_not_started(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SNOWCITE_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    r = await next_step()
    assert r["phase"] == "not_started" and r["project_active"] is False
    assert any("init_project" in d for d in r["do"])


async def test_walk_from_criteria_to_review(tmp_project: Path):
    r = await next_step()
    assert r["phase"] == "criteria" and r["project_active"] is True

    await set_review_criteria("Include X. Exclude Y.")
    assert (await next_step())["phase"] == "search"

    await container.papers.persist(
        [Paper(source="arxiv", source_id=str(i), title=f"P{i}") for i in range(3)]
    )
    r = await next_step()
    assert r["phase"] == "review"
    assert r["payload"]["criteria"] == "Include X. Exclude Y."
    assert [p["id"] for p in r["payload"]["batch"]] == [1, 2, 3]
    assert "abstract" not in r["payload"]["batch"][0]


async def test_review_batch_withheld_until_summary_then_low_confidence_gate(tmp_project: Path):
    await set_review_criteria("c")
    await container.papers.persist(
        [Paper(source="arxiv", source_id=str(i), title=f"P{i}") for i in range(3)]
    )
    await set_review_status(
        [1],
        "approved",
        reason="r",
        reviewed_by="auto_low",
        notes=[{"type": "claim", "text": "a claim"}],
    )
    r = await next_step()
    assert r["phase"] == "review" and "batch" not in r["payload"]
    assert any("save_review_summary" in d for d in r["do"])

    await save_review_summary("summary", [{"topic": "T", "paper_ids": [1], "count": 1}])
    r = await next_step()
    assert [p["id"] for p in r["payload"]["batch"]] == [2, 3]

    await set_review_status([2, 3], "rejected", reason="off-topic", reviewed_by="auto_high")
    await save_review_summary("summary", [{"topic": "T", "paper_ids": [1], "count": 1}])
    r = await next_step()
    assert r["phase"] == "low_confidence"
    assert [p["id"] for p in r["payload"]["papers"]] == [1]

    await set_review_status([1], "approved", reason="manual: ok", reviewed_by="user")
    assert (await next_step())["phase"] == "synthesis"


async def test_writing_requires_notes_then_walks_the_critique_loop(tmp_project: Path):
    await set_review_criteria("c")
    await container.papers.persist([Paper(source="arxiv", source_id="1", title="P")])
    await set_review_status([1], "approved", reason="r", reviewed_by="auto_high")
    await save_review_summary("s", [{"topic": "T", "paper_ids": [1], "count": 1}])
    sec = await container.section_service.create("Intro", {"clusters": ["T"]}, None, None)
    sid = sec["id"]

    r = await next_step()
    assert r["phase"] == "writing" and r["payload"]["action"] == "draft"
    assert "no notes" in r["why"]  # gate: can't draft without notes for the scope

    added = await container.note_service.add("claim", "A claim", 1, "T")
    assert (await next_step())["phase"] == "synthesis"  # per-paper notes, nothing synthesised
    await container.synthesis.add_synthesis("T", "consensus", "Agreed.", [added["id"]])

    r = await next_step()
    assert r["phase"] == "writing" and r["payload"]["action"] == "draft"
    assert "no notes" not in r["why"]

    await container.section_service.update(sid, None, None, "Draft [1].", "drafting", None, None)
    assert (await next_step())["payload"]["action"] == "critique"

    await container.section_service.record_critique(sid, [{"severity": "blocker"}])
    assert (await next_step())["payload"]["action"] == "revise"

    await container.section_service.record_critique(sid, [{"severity": "blocker"}])
    assert (await next_step())["payload"]["action"] == "finish"

    await container.section_service.update(sid, None, None, None, "done", None, None)
    assert (await next_step())["phase"] == "build"


async def test_last_actions_reflect_review_history(tmp_project: Path):
    await container.papers.persist([Paper(source="arxiv", source_id="x", title="T")])
    await set_review_status([1], "approved", reason="matches X", reviewed_by="auto_high")
    a = (await next_step())["last_actions"][0]
    assert (a["paper_id"], a["old_status"], a["new_status"], a["reason"]) == (
        1,
        "unreviewed",
        "approved",
        "matches X",
    )
