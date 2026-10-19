"""v0.3 section drafts feed document building, citation tools and backend switching."""

from pathlib import Path

from snowcite.db import init_db
from snowcite.persistence import load_document_sections
from snowcite.tools.compile import set_backend, write_document
from snowcite.tools.sections import create_section, get_section, update_section
from snowcite.tools.writing import gap_check, rewrite_citations, save_section


async def _draft(title: str, draft: str, parent_id: int | None = None) -> int:
    await init_db()
    sec = await create_section(title, parent_id=parent_id)
    await update_section(sec["id"], draft=draft, status="drafting")
    return sec["id"]


async def test_loader_orders_children_after_parent_and_skips_empty(tmp_project: Path):
    parent = await _draft("Parent", "p text")
    await _draft("Child", "c text", parent_id=parent)
    await _draft("Empty", "")
    await _draft("Last", "l text")

    got = await load_document_sections()
    assert [s["title"] for s in got] == ["Parent", "Child", "Last"]


async def test_loader_falls_back_to_v02_section_content(tmp_project: Path):
    await init_db()
    await save_section("intro", "legacy text")
    assert await load_document_sections() == [{"title": "intro", "content": "legacy text"}]


async def test_write_document_builds_from_db_when_sections_omitted(tmp_project: Path):
    await _draft("Intro", "Hello from the db")
    result = await write_document(
        title="T", author="A", backend="typst", output_dir=str(tmp_project)
    )
    assert "Hello from the db" in Path(result["doc_path"]).read_text(encoding="utf-8")


async def test_gap_check_and_rewrite_citations_see_v03_drafts(tmp_project: Path):
    sid = await _draft("Intro", "This sentence has quite enough words but cites nothing at all.")
    assert (await gap_check())["total_gaps"] == 1

    await update_section(sid, draft="Claim [1, 2] holds.")
    out = await rewrite_citations({"1": 7})
    assert out["refs_replaced"] == 1
    assert (await get_section(sid))["draft"] == "Claim [7, 2] holds."


async def test_set_backend_wipes_v03_drafts_only_when_confirmed(tmp_project: Path):
    await init_db()
    await set_backend("typst", confirm_wipe_sections=True)
    sid = await _draft("Intro", "text")

    refused = await set_backend("latex")
    assert refused["changed"] is False and refused["needs_wipe"] == 1

    await set_backend("latex", confirm_wipe_sections=True)
    section = await get_section(sid)
    assert section["draft"] == "" and section["status"] == "outline"
