from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from snowcite.domain.types import (
    ArtifactType,
    Direction,
    NoteLinkKind,
    NoteType,
    ReviewedBy,
    SectionStatus,
    Source,
    Status,
)


class Base(DeclarativeBase):
    pass


# Timestamps are kept as the TEXT SQLite stores them ("YYYY-MM-DD HH:MM:SS");
# schema.sql is the source of truth for DDL, these classes mirror it for queries.


class PaperRow(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[Source]
    source_id: Mapped[str]
    doi: Mapped[str | None]
    title: Mapped[str]
    title_normalized: Mapped[str]
    authors_json: Mapped[str]
    year: Mapped[int | None]
    venue: Mapped[str | None]
    abstract: Mapped[str | None]
    pdf_url: Mapped[str | None]
    bibtex: Mapped[str | None]
    metadata_json: Mapped[str | None]
    created_at: Mapped[str | None]


class ReviewRow(Base):
    __tablename__ = "reviews"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    status: Mapped[Status]
    reason: Mapped[str | None]
    note: Mapped[str | None]
    reviewed_at: Mapped[str | None]
    reviewed_by: Mapped[ReviewedBy | None]


class ReviewHistoryRow(Base):
    __tablename__ = "review_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int]
    old_status: Mapped[Status | None]
    new_status: Mapped[Status]
    reason: Mapped[str | None]
    reviewed_by: Mapped[ReviewedBy | None]
    changed_at: Mapped[str | None]


class ReviewCriteriaRow(Base):
    __tablename__ = "review_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    criteria_text: Mapped[str]
    created_at: Mapped[str | None]


class ReviewSummaryRow(Base):
    __tablename__ = "review_summary"

    id: Mapped[int] = mapped_column(primary_key=True)
    summary: Mapped[str]
    clusters_json: Mapped[str]
    counts_snapshot_json: Mapped[str]
    stale: Mapped[int | None]
    updated_at: Mapped[str | None]


class CitationRow(Base):
    __tablename__ = "citations"

    source_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    cited_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    direction: Mapped[Direction] = mapped_column(primary_key=True)


class NoteRow(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id"))
    cluster: Mapped[str | None]
    type: Mapped[NoteType]
    text: Mapped[str]
    created_at: Mapped[str | None]
    updated_at: Mapped[str | None]


class NoteLinkRow(Base):
    __tablename__ = "note_links"

    from_note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), primary_key=True)
    to_note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), primary_key=True)
    kind: Mapped[NoteLinkKind] = mapped_column(primary_key=True)


class ThesisRow(Base):
    __tablename__ = "thesis"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str]
    updated_at: Mapped[str | None]


class SectionRow(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    scope_json: Mapped[str]
    draft: Mapped[str]
    status: Mapped[SectionStatus]
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id"))
    position: Mapped[int]
    blockers: Mapped[int]
    should_fix: Mapped[int]
    nits: Mapped[int]
    critique_iterations: Mapped[int]
    target_words: Mapped[int | None]
    created_at: Mapped[str | None]
    updated_at: Mapped[str | None]


class PaperSectionLinkRow(Base):
    __tablename__ = "paper_section_links"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), primary_key=True)
    discovered_at: Mapped[str | None]
    via_query: Mapped[str | None]


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[ArtifactType]
    label: Mapped[str]
    source_path: Mapped[str | None]
    content: Mapped[str]
    summary: Mapped[str | None]
    metadata_json: Mapped[str | None]
    included: Mapped[int | None]
    created_at: Mapped[str | None]


class ProjectMetadataRow(Base):
    __tablename__ = "project_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    author: Mapped[str | None]
    supervisor: Mapped[str | None]
    institution: Mapped[str | None]
    department: Mapped[str | None]
    year: Mapped[int | None]
    work_type: Mapped[str | None]
    target_length: Mapped[str | None]
    language: Mapped[str | None]
    discipline: Mapped[str | None]
    standard: Mapped[str | None]
    methodology: Mapped[str | None]
    review_strictness: Mapped[str | None]
    deadline: Mapped[str | None]
    target_pages: Mapped[int | None]
    target_sources_min: Mapped[int | None]
    target_sources_max: Mapped[int | None]
    target_words: Mapped[int | None]
    citation_density_target: Mapped[float | None]
    extra_json: Mapped[str | None]
    created_at: Mapped[str | None]
    updated_at: Mapped[str | None]
