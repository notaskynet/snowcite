"""Thin call helpers for tests: the vocabulary of the services behind the tools.

Tools were consolidated (`review_batch`, `papers`, `get_sections`, ...); most tests
just need to set up state or read it back, so they go through the services directly.
Behaviour of the consolidated tool surface itself is covered in `test_tools.py`.
"""

from typing import Any

from snowcite.container import container
from snowcite.tools.artifacts import add_artifact, get_artifacts, update_artifact
from snowcite.tools.export import export_bibliography
from snowcite.tools.import_refs import import_refs
from snowcite.tools.writing import thesis


# ─── Review ─────────────────────────────────────────────────────────────────


async def set_review_status(
    paper_ids, status, reason, note=None, reviewed_by="auto_high", notes=None
):
    return await container.review_service.set_status(
        paper_ids, status, reason, note, reviewed_by, notes
    )


async def set_review_criteria(text: str):
    return await container.review_service.set_criteria(text)


async def get_review_criteria():
    return await container.review_service.get_criteria()


async def save_review_summary(summary: str, clusters: list[dict[str, Any]]):
    return await container.review_service.save_summary(summary, clusters)


async def get_review_summary():
    return await container.review_service.get_summary()


async def get_review_progress():
    return await container.review_service.progress()


async def get_unreviewed_papers(
    limit=20, source=None, year_from=None, year_to=None, include_abstracts=False
):
    return await container.review_service.list_papers(
        "unreviewed", source, year_from, year_to, None, None, None, include_abstracts, limit, 0
    )


async def get_low_confidence_reviews(status=None, limit=50):
    return await container.review_service.list_papers(
        status, None, None, None, None, None, "auto_low", False, limit, 0
    )


async def get_papers_for_writing(cluster=None, limit=20, offset=0):
    return await container.review_service.list_papers(
        "approved", None, None, None, None, cluster, None, True, limit, offset
    )


async def get_saved_papers(
    status=None, source=None, year_from=None, year_to=None, search=None, limit=100, offset=0
):
    return await container.review_service.list_papers(
        status, source, year_from, year_to, search, None, None, True, limit, offset
    )


async def get_paper_details(paper_id: int):
    return await container.review_service.paper_details(paper_id)


# ─── Notes ──────────────────────────────────────────────────────────────────


async def add_note(type, text, paper_id=None, cluster=None):  # noqa: A002
    return await container.note_service.add(type, text, paper_id, cluster)


async def delete_note(note_id: int):
    return await container.note_service.delete(note_id)


async def get_note_density(cluster=None):
    return await container.note_service.density(cluster)


# ─── Sections ───────────────────────────────────────────────────────────────


async def create_section(title, scope=None, parent_id=None, position=None):
    return await container.section_service.create(title, scope, parent_id, position)


async def bulk_create_sections(sections):
    return await container.section_service.bulk_create(sections)


async def list_sections():
    return await container.section_service.list_all()


async def get_section(section_id: int):
    return await container.section_service.get(section_id)


async def delete_section(section_id: int):
    return await container.section_service.delete(section_id)


async def get_outline_inputs():
    return await container.section_service.outline_inputs()


async def link_paper_to_section(paper_id, section_id, via_query=None):
    return await container.section_service.link_paper(paper_id, section_id, via_query)


async def unlink_paper_from_section(paper_id, section_id):
    return await container.section_service.unlink_paper(paper_id, section_id)


async def get_section_papers(section_id: int):
    return await container.section_service.section_papers(section_id)


# ─── Thesis ─────────────────────────────────────────────────────────────────


async def save_thesis(content: str):
    return await thesis(content)


async def get_thesis():
    return await thesis()


# ─── Artifacts ──────────────────────────────────────────────────────────────


async def import_artifact(path, type, label=None, summary=None, metadata=None):  # noqa: A002
    return await add_artifact(type, label, None, path, summary, metadata)


async def add_artifact_inline(type, label, content, summary=None, metadata=None):  # noqa: A002
    return await add_artifact(type, label, content, None, summary, metadata)


async def list_artifacts(type=None, included_only=False):  # noqa: A002
    return await get_artifacts(None, type, included_only)


async def get_artifact(artifact_id: int):
    return await get_artifacts(artifact_id)


async def delete_artifact(artifact_id: int):
    return await update_artifact(artifact_id, None, True)


async def set_artifact_included(artifact_id: int, included: bool):
    return await update_artifact(artifact_id, included, False)


# ─── Import / export ────────────────────────────────────────────────────────


async def import_bibtex(file_path, enrich_abstracts=True):
    return await import_refs(file_path, enrich_abstracts)


async def import_ris(file_path, enrich_abstracts=True):
    return await import_refs(file_path, enrich_abstracts)


async def export_bibtex(output_path=None):
    return await export_bibliography("bibtex", output_path)


async def export_ris(output_path=None):
    return await export_bibliography("ris", output_path)
