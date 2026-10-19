"""Section drafts feed the citation tools and the document-section loader."""

from pathlib import Path

from snowcite.container import container
from snowcite.tools.sections import update_section
from snowcite.tools.writing import gap_check, rewrite_citations
from tests.helpers import create_section, get_section


async def _draft(title: str, draft: str, parent_id: int | None = None) -> int:
    await container.db.init()
    sec = await create_section(title, parent_id=parent_id)
    await update_section(sec["id"], draft=draft, status="drafting")
    return sec["id"]


async def test_loader_orders_children_after_parent_and_skips_empty(tmp_project: Path):
    parent = await _draft("Parent", "p text")
    await _draft("Child", "c text", parent_id=parent)
    await _draft("Empty", "")
    await _draft("Last", "l text")

    got = await container.sections.load_document_sections()
    assert [s["title"] for s in got] == ["Parent", "Child", "Last"]


async def test_gap_check_and_rewrite_citations_see_v03_drafts(tmp_project: Path):
    sid = await _draft("Intro", "This sentence has quite enough words but cites nothing at all.")
    assert (await gap_check())["total_gaps"] == 1

    await update_section(sid, draft="Claim [1, 2] holds.")
    out = await rewrite_citations({"1": 7})
    assert out["refs_replaced"] == 1
    assert (await get_section(sid))["draft"] == "Claim [7, 2] holds."
