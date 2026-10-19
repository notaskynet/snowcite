"""MCP tools for managing research artifacts (interviews, code, notes, etc.)."""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import ArtifactType


@mcp.tool()
async def import_artifact(
    path: str,
    type: ArtifactType,  # noqa: A002 — field name consistency across artifact API
    label: str | None = None,
    summary: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read a text file from disk and register it as a research artifact.

    `path`: absolute or project-relative path to a text file.
    `type`: one of `interview`, `code`, `document`, `note`, `dataset`.
    `label`: short human-readable name (default: the file basename).
    `summary`: one-sentence gloss that will be shown in the Primary-sources
      appendix. Optional, but strongly recommended — this is what the reader
      sees without the full content.
    `metadata`: free-form JSON for participant ids, tags, anonymisation flags
      (e.g. `{"participant": "P03", "consent": "written", "language": "ru"}`).

    Only text files are supported. Convert PDFs/docx with `pdftotext` /
    `pandoc` first, then import the resulting text.
    """
    return await container.artifact_service.import_file(path, type, label, summary, metadata)


@mcp.tool()
async def add_artifact_inline(
    type: ArtifactType,  # noqa: A002 — field name consistency across artifact API
    label: str,
    content: str,
    summary: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register an artifact from a literal string (no file read).

    Handy for short notes, code snippets already in chat, or interview
    excerpts typed by the user. Same fields as `import_artifact`, minus the
    path.
    """
    return await container.artifact_service.add_inline(type, label, content, summary, metadata)


@mcp.tool()
async def list_artifacts(
    type: ArtifactType | None = None,  # noqa: A002
    included_only: bool = False,
) -> list[dict[str, Any]]:
    """Browse artifacts. Returns metadata + summary (no content bodies).

    Use `get_artifact(id)` for the full content when you need to quote or
    analyse it.
    """
    return await container.artifact_service.list_briefs(type, included_only)


@mcp.tool()
async def get_artifact(artifact_id: int) -> dict[str, Any] | None:
    """Full artifact record including the content body. Use for quoting."""
    return await container.artifact_service.get(artifact_id)


@mcp.tool()
async def delete_artifact(artifact_id: int) -> dict[str, Any]:
    """Remove an artifact. Hard delete — use `set_artifact_included(False)` to
    exclude from the writing pipeline without losing it."""
    return await container.artifact_service.delete(artifact_id)


@mcp.tool()
async def set_artifact_included(artifact_id: int, included: bool) -> dict[str, Any]:
    """Toggle whether the writing pipeline considers this artifact.

    Excluded artifacts stay in the DB but are hidden from
    `list_artifacts(included_only=True)` and don't land in the
    Primary-sources appendix.
    """
    return await container.artifact_service.set_included(artifact_id, included)
