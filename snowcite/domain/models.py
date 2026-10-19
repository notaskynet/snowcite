"""Domain models shared across layers. No I/O."""

from typing import TypedDict

from pydantic import BaseModel, Field, field_validator

from snowcite.domain.dedup import normalize_doi
from snowcite.domain.types import Source


class Paper(BaseModel):
    """Common paper representation across all sources."""

    source: Source
    source_id: str = Field(min_length=1)
    doi: str | None = None
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    pdf_url: str | None = None
    bibtex: str | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("doi", mode="before")
    @classmethod
    def _normalize_doi(cls, v: str | None) -> str | None:
        return normalize_doi(v)


class PersistResult(TypedDict):
    saved: int
    duplicates: int
    new_ids: list[int]
    new_titles: list[str]


class ApprovedPaper(TypedDict):
    """Everything compile/export/rendering need about an approved paper."""

    id: int
    source: str
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    abstract: str | None
    bibtex: str | None


class DocumentSection(TypedDict):
    """A section ready to render: title + body in the project's backend syntax."""

    title: str
    content: str
