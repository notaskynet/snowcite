"""Ingest and browse research artifacts."""

from pathlib import Path
from typing import Any

from snowcite.domain.artifacts import (
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACT_CHARS,
    citation_label,
)
from snowcite.domain.types import ArtifactRecord, ArtifactType
from snowcite.storage.repositories import ArtifactRepository


def brief(record: ArtifactRecord) -> dict[str, Any]:
    """An artifact without its content body, for listings and bundles."""
    return {
        "id": record["id"],
        "type": record["type"],
        "label": record["label"],
        "citation_label": citation_label(record),
        "summary": record.get("summary"),
        "included": record["included"],
        "chars": len(record["content"]),
        "metadata": record.get("metadata", {}),
        "created_at": record["created_at"],
    }


class ArtifactService:
    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def import_file(
        self,
        path: str,
        type: ArtifactType,  # noqa: A002
        label: str | None,
        summary: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        file = Path(path)
        if not file.exists():
            return {"error": f"file not found: {path}"}

        # Cheap size probe before loading the file into memory.
        size_bytes = file.stat().st_size
        if size_bytes > MAX_ARTIFACT_BYTES:
            return {
                "error": (
                    f"file is {size_bytes} bytes; limit is ~{MAX_ARTIFACT_BYTES} bytes "
                    f"({MAX_ARTIFACT_CHARS} chars). Split the file or trim first."
                )
            }
        try:
            content = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"error": f"file is not UTF-8 text: {path}. Convert to text first."}
        if len(content) > MAX_ARTIFACT_CHARS:
            return {
                "error": (
                    f"content exceeds {MAX_ARTIFACT_CHARS} chars "
                    f"({len(content)} given). Split the file or trim first."
                )
            }
        return await self._save(
            type, label or file.name, content, str(file.resolve()), summary, metadata
        )

    async def add_inline(
        self,
        type: ArtifactType,  # noqa: A002
        label: str,
        content: str,
        summary: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if len(content) > MAX_ARTIFACT_CHARS:
            return {"error": f"content exceeds {MAX_ARTIFACT_CHARS} chars ({len(content)} given)."}
        return await self._save(type, label, content, None, summary, metadata)

    async def _save(
        self,
        type: ArtifactType,  # noqa: A002
        label: str,
        content: str,
        source_path: str | None,
        summary: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        artifact_id = await self._artifacts.save(
            type, label, content, source_path, summary, metadata
        )
        return {
            "id": artifact_id,
            "type": type,
            "label": label,
            "chars": len(content),
            "citation_label": citation_label({"id": artifact_id, "type": type, "label": label}),  # type: ignore[typeddict-item]
        }

    async def list_briefs(
        self,
        type: ArtifactType | None,  # noqa: A002
        included_only: bool,
    ) -> list[dict[str, Any]]:
        records = await self._artifacts.list(type, included_only)
        return [brief(r) for r in records]

    async def get(self, artifact_id: int) -> dict[str, Any] | None:
        record = await self._artifacts.load(artifact_id)
        return dict(record) if record is not None else None

    async def delete(self, artifact_id: int) -> dict[str, Any]:
        return {"deleted": await self._artifacts.delete(artifact_id), "id": artifact_id}

    async def set_included(self, artifact_id: int, included: bool) -> dict[str, Any]:
        if not await self._artifacts.set_included(artifact_id, included):
            return {"updated": False, "error": f"artifact {artifact_id} not found"}
        return {"updated": True, "id": artifact_id, "included": included}
