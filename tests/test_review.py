"""Review tools — include_abstracts flag drives the T1 context-hygiene contract."""

from pathlib import Path

import pytest

from snowcite.container import container
from snowcite.domain.citations import count_cites
from snowcite.domain.models import Paper
from snowcite.tools.init import init_project
from tests.helpers import get_review_progress, get_unreviewed_papers, set_review_status


def test_count_cites_bracketed_numeric_refs():
    # `[1, 2; 3]` counts as three cites; `[note]` is ignored.
    assert count_cites("see [1] and [note]") == 1
    assert count_cites("shown in [1, 2; 3]") == 3
    assert count_cites("no cites here") == 0


@pytest.mark.asyncio
async def test_get_review_progress_computes_density_and_warnings(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
):
    # Target: 3 sources minimum, density 2.0/100 words. Approve 1 paper →
    # expect a warning that sources are below the floor.
    monkeypatch.chdir(tmp_project)
    await init_project(
        metadata={
            "author": "X",
            "target_sources_min": 3,
            "citation_density_target": 2.0,
        }
    )
    await container.papers.persist(
        [Paper(source="arxiv", source_id="a", title="A", authors=["X"], year=2024)]
    )
    await set_review_status([1], "approved", reason="t", reviewed_by="auto_high")
    sec = await container.section_service.create("intro", None, None, None)
    await container.section_service.update(
        sec["id"],
        None,
        None,
        "A short section with one cite [1] and a few words.",
        None,
        None,
        None,
    )
    r = await get_review_progress()
    assert r["counts"]["approved"] == 1
    assert r["writing"]["citations"] == 1
    assert r["writing"]["words"] > 0
    assert r["targets"]["target_sources_min"] == 3
    assert any("approved sources" in w for w in r["warnings"])


@pytest.mark.asyncio
async def test_get_review_progress_no_targets_returns_plain_snapshot(tmp_project: Path):
    r = await get_review_progress()
    assert r["counts"]["total"] == 0
    assert r["writing"]["words"] == 0
    assert r["targets"] == {}
    assert r["warnings"] == []


@pytest.mark.asyncio
async def test_get_unreviewed_omits_abstract_by_default(tmp_project: Path):
    await container.papers.persist(
        [Paper(source="arxiv", source_id="x", title="T", abstract="ABS")]
    )
    rows = await get_unreviewed_papers(limit=10)
    assert len(rows) == 1
    # Compact mode: abstract field is removed entirely, not just nulled.
    assert "abstract" not in rows[0]


@pytest.mark.asyncio
async def test_get_unreviewed_includes_abstract_when_requested(tmp_project: Path):
    await container.papers.persist(
        [Paper(source="arxiv", source_id="x", title="T", abstract="ABS")]
    )
    rows = await get_unreviewed_papers(limit=10, include_abstracts=True)
    assert rows[0]["abstract"] == "ABS"
