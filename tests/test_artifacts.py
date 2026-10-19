"""Research-artifact persistence, MCP tools, writing-pipeline integration."""

from pathlib import Path

import pytest

from snowcite.container import container
from snowcite.domain.artifacts import citation_label
from tests.helpers import (
    add_artifact_inline,
    delete_artifact,
    get_artifact,
    import_artifact,
    list_artifacts,
    set_artifact_included,
)


# ─── Persistence ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_load_roundtrip(tmp_project: Path):
    aid = await container.artifacts.save(
        "interview",
        "P03 transcript",
        content="Q: ... A: ...",
        summary="First pilot interview",
        metadata={"participant": "P03"},
    )
    record = await container.artifacts.load(aid)
    assert record is not None
    assert record["type"] == "interview"
    assert record["label"] == "P03 transcript"
    assert record["content"] == "Q: ... A: ..."
    assert record["metadata"]["participant"] == "P03"
    assert record["included"] is True


@pytest.mark.asyncio
async def test_list_filters_by_type_and_included(tmp_project: Path):
    await container.artifacts.save(type="interview", label="i1", content="x")
    await container.artifacts.save(type="code", label="c1", content="def f(): pass")
    cid = await container.artifacts.save(type="code", label="c2", content="# notes")
    await container.artifacts.set_included(cid, False)

    interviews = await container.artifacts.list(type="interview")
    assert len(interviews) == 1

    code_all = await container.artifacts.list(type="code")
    assert len(code_all) == 2

    code_included = await container.artifacts.list(type="code", included_only=True)
    assert len(code_included) == 1
    assert code_included[0]["label"] == "c1"


def test_citation_label_format():
    assert citation_label({"id": 3, "type": "interview"}) == "[I:3]"  # type: ignore[arg-type]
    assert citation_label({"id": 7, "type": "code"}) == "[C:7]"  # type: ignore[arg-type]
    assert citation_label({"id": 2, "type": "dataset"}) == "[DS:2]"  # type: ignore[arg-type]


# ─── MCP tools ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_artifact_reads_file(tmp_project: Path):
    src = tmp_project / "transcript.md"
    src.write_text("# Interview P01\n\nQ: ...\nA: ...", encoding="utf-8")

    r = await import_artifact(path=str(src), type="interview", label="P01", summary="Pilot")
    assert "id" in r
    assert r["chars"] > 0
    assert r["citation_label"].startswith("[I:")


@pytest.mark.asyncio
async def test_import_artifact_missing_file_errors(tmp_project: Path):
    r = await import_artifact(path=str(tmp_project / "nope.txt"), type="note", label="missing")
    assert "error" in r


@pytest.mark.asyncio
async def test_add_artifact_inline(tmp_project: Path):
    r = await add_artifact_inline(type="note", label="Idea 1", content="Research idea")
    assert "id" in r
    fetched = await get_artifact(r["id"])
    assert fetched is not None
    assert fetched["content"] == "Research idea"


@pytest.mark.asyncio
async def test_list_artifacts_omits_content(tmp_project: Path):
    await add_artifact_inline(type="note", label="n1", content="long body")
    rows = await list_artifacts()
    assert len(rows) == 1
    # Content omitted from listings for context hygiene.
    assert "content" not in rows[0]
    assert rows[0]["chars"] == len("long body")


@pytest.mark.asyncio
async def test_set_included_excludes_from_list(tmp_project: Path):
    r = await add_artifact_inline(type="note", label="temp", content="x")
    await set_artifact_included(r["id"], False)
    visible = await list_artifacts(included_only=True)
    assert visible == []


@pytest.mark.asyncio
async def test_delete_artifact(tmp_project: Path):
    r = await add_artifact_inline(type="note", label="drop me", content="x")
    out = await delete_artifact(r["id"])
    assert out["deleted"] is True
    assert await get_artifact(r["id"]) is None


@pytest.mark.asyncio
async def test_critique_inputs_list_included_artifacts_without_content(tmp_project: Path):
    keep = await container.artifacts.save(
        type="interview", label="P01", content="Q: secret body", summary="Pilot"
    )
    drop = await container.artifacts.save(type="note", label="skip", content="x")
    await container.artifacts.set_included(drop, False)
    sec = await container.section_service.create("Findings", None, None, None)

    out = await container.section_service.critique_inputs(sec["id"])
    assert [a["id"] for a in out["artifacts"]] == [keep]
    art = out["artifacts"][0]
    assert art["citation_label"] == f"[I:{keep}]" and art["summary"] == "Pilot"
    assert "content" not in art
