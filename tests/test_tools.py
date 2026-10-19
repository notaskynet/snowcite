"""The consolidated tool surface: batches, filters, action-style tools."""

from pathlib import Path

from snowcite.container import container
from snowcite.domain.models import Paper
from snowcite.tools.artifacts import add_artifact, get_artifacts, update_artifact
from snowcite.tools.export import export_bibliography
from snowcite.tools.import_refs import import_refs
from snowcite.tools.notes import add_notes, get_notes, update_note
from snowcite.tools.research import section_papers
from snowcite.tools.review import review_batch, review_criteria, review_summary
from snowcite.tools.search import paper, papers
from snowcite.tools.sections import create_sections, get_sections, update_section
from snowcite.tools.writing import thesis


async def _seed(n: int = 3) -> None:
    await container.papers.persist(
        [Paper(source="arxiv", source_id=str(i), title=f"P{i}", year=2020 + i) for i in range(n)]
    )


# ─── review_batch ───────────────────────────────────────────────────────────


async def test_review_batch_requires_notes_for_approved_and_maybe(tmp_project: Path):
    await _seed()
    res = await review_batch(
        [
            {"paper_id": 1, "status": "approved", "reason": "matches X"},
            {
                "paper_id": 2,
                "status": "maybe",
                "reason": "r",
                "notes": [{"type": "method", "text": "m"}],
            },
            {"paper_id": 3, "status": "rejected", "reason": "off-topic"},
        ]
    )
    assert res["updated"] == 1  # only the rejection went through
    assert [e["index"] for e in res["errors"]] == [0, 1]
    assert "no notes" in res["errors"][0]["error"]
    assert "claim or finding" in res["errors"][1]["error"]


async def test_review_batch_accepts_notes_inline_and_prior_notes(tmp_project: Path):
    await _seed()
    res = await review_batch(
        [
            {
                "paper_id": 1,
                "status": "approved",
                "reason": "r",
                "reviewed_by": "auto_low",
                "notes": [{"type": "claim", "text": "c", "cluster": "T"}],
            }
        ]
    )
    assert res["updated"] == 1 and len(res["note_ids"]) == 1

    # Paper 1 already has notes, so a later flip by the user needs none.
    res = await review_batch(
        [{"paper_ids": [1], "status": "maybe", "reason": "manual: hm", "reviewed_by": "user"}]
    )
    assert res["updated"] == 1 and res["errors"] == []
    assert (await paper(1))["review_status"] == "maybe"


async def test_review_batch_validates_shape(tmp_project: Path):
    await _seed(1)
    res = await review_batch(
        [
            {"status": "approved", "reason": "r"},
            {"paper_id": 1, "status": "great", "reason": "r"},
            {"paper_id": 1, "status": "rejected", "reason": " "},
            {"paper_id": 1, "status": "rejected", "reason": "r", "reviewed_by": "robot"},
        ]
    )
    assert res["updated"] == 0 and len(res["errors"]) == 4


# ─── papers / paper ─────────────────────────────────────────────────────────


async def test_papers_filters_and_stays_compact(tmp_project: Path):
    await container.papers.persist(
        [Paper(source="arxiv", source_id="1", title="Has abs", abstract="the abstract", year=2021)]
    )
    await _seed(0)
    await container.review_service.set_status([1], "approved", "r", reviewed_by="auto_low")

    rows = await papers(status="approved")
    assert len(rows) == 1 and "abstract" not in rows[0] and "bibtex" not in rows[0]
    assert (await papers(status="approved", include_abstracts=True))[0][
        "abstract"
    ] == "the abstract"
    assert len(await papers(reviewed_by="auto_low")) == 1
    assert await papers(reviewed_by="user") == []
    assert await papers(status="unreviewed") == []


async def test_papers_cluster_filter_uses_review_summary(tmp_project: Path):
    await _seed()
    await container.review_service.save_summary("s", [{"topic": "T", "paper_ids": [2], "count": 1}])
    assert [p["id"] for p in await papers(cluster="T")] == [2]
    unknown = await papers(cluster="nope")
    assert "error" in unknown and unknown["available"] == ["T"]
    assert "error" in await paper(99)


# ─── criteria / summary / thesis (get-or-set) ───────────────────────────────


async def test_get_or_set_tools(tmp_project: Path):
    assert await review_criteria() is None
    await review_criteria("Include X")
    assert (await review_criteria())["criteria_text"] == "Include X"

    assert await review_summary() is None
    assert "error" in await review_summary("text")  # clusters required
    await review_summary("text", [{"topic": "T", "paper_ids": [], "count": 0}])
    assert (await review_summary())["summary"] == "text"

    assert await thesis() is None
    assert (await thesis("  My thesis here  "))["word_count"] == 3
    assert (await thesis())["content"] == "My thesis here"
    assert "error" in await thesis("   ")


# ─── notes / sections / artifacts ───────────────────────────────────────────


async def test_update_note_can_delete(tmp_project: Path):
    await _seed(1)
    res = await add_notes([{"type": "claim", "text": "c", "paper_id": 1}])
    nid = res["ids"][0]
    assert (await update_note(nid, text="edited"))["updated"] is True
    assert (await get_notes())[0]["text"] == "edited"
    assert (await update_note(nid, delete=True))["deleted"] == 1
    assert await get_notes() == []


async def test_sections_create_get_update_delete(tmp_project: Path):
    res = await create_sections([{"title": "A"}, {"title": ""}, {"title": "B"}])
    assert res["inserted"] == 2 and res["errors"][0]["index"] == 1
    a, b = res["ids"]
    assert [s["title"] for s in await get_sections()] == ["A", "B"]
    assert (await get_sections(a))["title"] == "A" and await get_sections(999) is None

    assert (await update_section(a, title="A2"))["updated"] is True
    assert (await update_section(b, delete=True))["deleted"] == 1
    assert [s["title"] for s in await get_sections()] == ["A2"]


async def test_section_papers_links_unlinks_and_reports_missing(tmp_project: Path):
    await _seed(2)
    (sid,) = (await create_sections([{"title": "S"}]))["ids"]
    res = await section_papers(sid, link=[1, 2, 99], via_query="q")
    assert {p["id"] for p in res["papers"]} == {1, 2}
    assert res["errors"][0]["paper_id"] == 99
    res = await section_papers(sid, unlink=[1])
    assert [p["id"] for p in res["papers"]] == [2]


async def test_artifact_tools(tmp_project: Path):
    assert "error" in await add_artifact("note")  # neither content nor path
    assert "error" in await add_artifact("note", content="x")  # inline needs a label
    res = await add_artifact("note", label="idea", content="body")
    aid = res["id"]
    assert (await get_artifacts(aid))["content"] == "body"
    assert "content" not in (await get_artifacts())[0]

    await update_artifact(aid, included=False)
    assert await get_artifacts(included_only=True) == []
    assert "error" in await update_artifact(aid)
    assert (await update_artifact(aid, delete=True))["deleted"] is True


# ─── import / export ────────────────────────────────────────────────────────


async def test_import_refs_dispatches_on_extension(tmp_project: Path):
    bib = tmp_project / "refs.bib"
    bib.write_text(
        "@article{a, title={Some Title}, author={Doe, Jane}, year={2020}, doi={10.1/zz}}",
        encoding="utf-8",
    )
    res = await import_refs(str(bib), enrich_abstracts=False)
    assert res["saved"] == 1

    ris = tmp_project / "refs.ris"
    ris.write_text(
        "TY  - JOUR\nTI  - Another Title\nAU  - Doe, J\nPY  - 2021\nER  - \n", encoding="utf-8"
    )
    assert (await import_refs(str(ris), enrich_abstracts=False))["saved"] == 1

    (tmp_project / "refs.txt").write_text("x", encoding="utf-8")
    assert "unsupported" in (await import_refs(str(tmp_project / "refs.txt")))["error"]
    assert "not found" in (await import_refs(str(tmp_project / "nope.bib")))["error"]


async def test_export_bibliography_formats(tmp_project: Path):
    await _seed(1)
    await container.review_service.set_status([1], "approved", "r")
    bib = await export_bibliography("bibtex")
    assert bib["entries"] == 1 and Path(bib["path"]).name == "references.bib"
    assert list(bib["keys"]) == ["1"] and bib["keys"]["1"] in Path(bib["path"]).read_text()
    ris = await export_bibliography("ris", str(tmp_project / "out.ris"))
    assert "TY  - " in Path(ris["path"]).read_text(encoding="utf-8")
