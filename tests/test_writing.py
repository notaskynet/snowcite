"""PRISMA, overview table, thesis, and citation checks over section drafts."""

from pathlib import Path

import pytest

from snowcite.container import container
from snowcite.domain.models import Paper
from snowcite.tools.review import set_review_status
from snowcite.tools.sections import get_section
from snowcite.tools.writing import (
    gap_check,
    generate_overview_table,
    generate_prisma_flow,
    get_thesis,
    rewrite_citations,
    save_thesis,
)


async def _draft(title: str, text: str) -> int:
    sec = await container.section_service.create(title, None, None, None)
    await container.section_service.update(sec["id"], None, None, text, "drafting", None, None)
    return sec["id"]


# ─── PRISMA flow ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prisma_flow_reflects_review_history(tmp_project: Path):
    await container.papers.persist(
        [Paper(source="arxiv", source_id=str(i), title=f"p{i}") for i in range(1, 5)]
    )
    await set_review_status([1, 2], "approved", reason="r", reviewed_by="auto_high")
    await set_review_status([3], "rejected", reason="off-topic", reviewed_by="auto_high")
    await set_review_status([4], "rejected", reason="off-topic", reviewed_by="auto_high")

    r = await generate_prisma_flow(backend="typst")
    counts = r["counts"]
    assert counts["identified"] == 4
    assert counts["screened"] == 4
    assert counts["included"] == 2
    assert counts["excluded_total"] == 2
    assert r["snippet"].startswith("#figure")


@pytest.mark.asyncio
async def test_prisma_flow_latex_backend(tmp_project: Path):
    r = await generate_prisma_flow(backend="latex")
    assert r["backend"] == "latex"
    assert r["snippet"].startswith(r"\begin{figure}")
    assert "tikzpicture" in r["snippet"]


# ─── Overview table ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overview_table_typst_contains_approved_papers(tmp_project: Path):
    await container.papers.persist(
        [
            Paper(
                source="openalex",
                source_id="1",
                title="Paper A",
                authors=["Alice Smith"],
                year=2023,
                venue="ICML",
            ),
            Paper(
                source="openalex",
                source_id="2",
                title="Paper B",
                authors=["Bob Jones"],
                year=2024,
                venue="Nature",
            ),
        ]
    )
    await set_review_status([1, 2], "approved", reason="r", reviewed_by="auto_high")

    r = await generate_overview_table(backend="typst")
    assert r["rows"] == 2
    snippet = r["snippet"]
    assert snippet.startswith("#table(")
    assert "Paper A" in snippet
    assert "Paper B" in snippet
    assert "Smith" in snippet  # last-name only for author column


@pytest.mark.asyncio
async def test_overview_table_latex_longtable(tmp_project: Path):
    await container.papers.persist(
        [Paper(source="openalex", source_id="1", title="T", authors=["J Doe"], year=2024)]
    )
    await set_review_status([1], "approved", reason="r", reviewed_by="auto_high")

    r = await generate_overview_table(backend="latex", columns=["year", "title"])
    assert r["snippet"].startswith(r"\begin{longtable}")
    assert "Year & Title" in r["snippet"]


@pytest.mark.asyncio
async def test_rewrite_citations_remaps_bracketed_refs(tmp_project: Path):
    # Section with cites [1], [2, 3], [4]. Remap 1→11, 3→13; expect 1→11 and
    # 3→13 replaced, 2 and 4 left alone, structure of grouped cite preserved.
    sid = await _draft("intro", "See [1] and [2, 3]; also [4].")
    r = await rewrite_citations(mapping={"1": 11, "3": 13})
    assert r["refs_replaced"] == 2
    assert len(r["modified"]) == 1
    assert r["modified"][0]["name"] == "intro"

    draft = (await get_section(sid))["draft"]
    assert "[11]" in draft
    assert "[2, 13]" in draft
    assert "[4]" in draft


@pytest.mark.asyncio
async def test_rewrite_citations_skips_sections_without_target_ids(tmp_project: Path):
    await _draft("a", "See [1].")
    b = await _draft("b", "See [99].")
    r = await rewrite_citations(mapping={"1": 2})
    assert r["refs_replaced"] == 1
    assert [m["name"] for m in r["modified"]] == ["a"]
    # Section b is untouched.
    assert (await get_section(b))["draft"] == "See [99]."


@pytest.mark.asyncio
async def test_rewrite_citations_empty_mapping_is_noop(tmp_project: Path):
    await _draft("x", "See [1].")
    r = await rewrite_citations(mapping={})
    assert r["refs_replaced"] == 0
    assert r["modified"] == []


# ─── Thesis + gap_check ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thesis_save_and_get(tmp_project: Path):
    assert await get_thesis() is None
    r = await save_thesis("This paper surveys ML for mining.  \n\nSecond paragraph.")
    assert r["saved"] is True
    assert r["word_count"] > 0
    got = await get_thesis()
    assert got is not None
    assert "surveys ML" in got["content"]


@pytest.mark.asyncio
async def test_thesis_save_empty_is_error(tmp_project: Path):
    r = await save_thesis("   \n  ")
    assert "error" in r


@pytest.mark.asyncio
async def test_thesis_save_overwrites(tmp_project: Path):
    await save_thesis("first version")
    await save_thesis("second version is much longer and more detailed")
    got = await get_thesis()
    assert got["content"].startswith("second version")


@pytest.mark.asyncio
async def test_gap_check_flags_long_uncited_sentences(tmp_project: Path):
    # Two sentences: one with a cite, one without. Both above min_words.
    content = (
        "This claim is well documented in the literature [1]. "
        "A completely different assertion stands here with no supporting citation at all."
    )
    await _draft("intro", content)
    r = await gap_check(min_words=5)
    assert r["total_gaps"] == 1
    assert r["gaps"][0]["section"] == "intro"
    assert "completely different assertion" in r["gaps"][0]["sentences"][0]["sentence"]


@pytest.mark.asyncio
async def test_gap_check_skips_short_connectives(tmp_project: Path):
    # Short sentences below the default min_words are ignored even without cites.
    await _draft("short", "Hi. Also no cite here either really.")
    r = await gap_check()
    assert r["total_gaps"] == 0


@pytest.mark.asyncio
async def test_gap_check_no_sections_returns_empty(tmp_project: Path):
    r = await gap_check()
    assert r["total_gaps"] == 0
    assert r["gaps"] == []
