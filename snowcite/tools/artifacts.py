"""MCP tools for managing research artifacts (interviews, code, notes, etc.)."""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import ArtifactType


@mcp.tool()
async def add_artifact(
    type: ArtifactType,  # noqa: A002 — field name consistency across artifact API
    label: str | None = None,
    content: str | None = None,
    path: str | None = None,
    summary: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register a research artifact from literal `content` or from a text file at `path`.

    `type`: interview | code | document | note | dataset.
    `label`: short name (default for a file: its basename; required for `content`).
    `summary`: one-sentence gloss shown in the primary-sources listing — strongly
      recommended, it is what a reader sees without the full text.
    `metadata`: free-form JSON (participant ids, consent, language, ...).

    Only UTF-8 text is supported; convert PDFs/docx first. Returns
    `{id, type, label, chars, citation_label}`.
    """
    if (content is None) == (path is None):
        return {"error": "pass exactly one of content or path"}
    if path is not None:
        return await container.artifact_service.import_file(path, type, label, summary, metadata)
    if not label:
        return {"error": "label is required with inline content"}
    return await container.artifact_service.add_inline(type, label, content, summary, metadata)


@mcp.tool()
async def get_artifacts(
    artifact_id: int | None = None,
    type: ArtifactType | None = None,  # noqa: A002
    included_only: bool = False,
) -> list[dict[str, Any]] | dict[str, Any] | None:
    """One artifact with its full content (to quote), or a listing without bodies.

    With `artifact_id`: the full record, or None. Without: briefs (id, type, label,
    citation_label, summary, size) filtered by `type` / `included_only`.
    """
    if artifact_id is not None:
        return await container.artifact_service.get(artifact_id)
    return await container.artifact_service.list_briefs(type, included_only)


@mcp.tool()
async def update_artifact(
    artifact_id: int,
    included: bool | None = None,
    delete: bool = False,
) -> dict[str, Any]:
    """Include/exclude an artifact, or delete it for good.

    Excluded artifacts stay in the DB but are hidden from
    `get_artifacts(included_only=True)` and from critique inputs. `delete=True`
    is a hard delete — prefer `included=False` to keep the material.
    """
    if delete:
        return await container.artifact_service.delete(artifact_id)
    if included is None:
        return {"error": "pass included or delete=True"}
    return await container.artifact_service.set_included(artifact_id, included)
