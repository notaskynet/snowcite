from typing import Any, NotRequired, TypedDict, final

from snowcite.domain.types import (
    ArtifactType,
    NoteLinkKind,
    NoteType,
    ReviewedBy,
    SectionStatus,
    Source,
    Status,
)


@final
class ErrorResult(TypedDict):
    error: str


@final
class Counts(TypedDict):
    total: int
    approved: int
    maybe: int
    rejected: int
    unreviewed: int


@final
class Cluster(TypedDict):
    topic: str
    paper_ids: list[int]
    count: int


# ─── Papers ─────────────────────────────────────────────────────────────────


class PaperRecord(TypedDict):
    id: int
    source: Source
    source_id: str
    doi: str | None
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    pdf_url: str | None
    created_at: str | None
    review_status: Status | None
    review_reason: str | None
    review_note: str | None
    reviewed_by: ReviewedBy | None
    reviewed_at: str | None
    # Present only when requested (`include_abstracts`) or in `PaperDetails`.
    abstract: NotRequired[str | None]


@final
class PaperDetails(PaperRecord):
    bibtex: str | None
    metadata: dict[str, Any]
    references_count: int
    citations_count: int


@final
class ApprovedPaper(TypedDict):
    id: int
    source: str
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    abstract: str | None
    bibtex: str | None


@final
class SourceRef(TypedDict):
    source: Source
    source_id: str
    doi: str | None


@final
class PersistResult(TypedDict):
    saved: int
    duplicates: int
    new_ids: list[int]
    new_titles: list[str]


# ─── Review ─────────────────────────────────────────────────────────────────


@final
class CriteriaRecord(TypedDict):
    id: int
    criteria_text: str
    created_at: str | None


@final
class HistoryEntry(TypedDict):
    paper_id: int
    old_status: Status | None
    new_status: Status
    reason: str | None
    reviewed_by: ReviewedBy | None
    at: str | None


@final
class StatusUpdate(TypedDict):
    updated: int
    skipped: list[int]
    note_ids: list[int]


@final
class UndoResult(TypedDict):
    undone: bool
    reason: NotRequired[str]
    paper_id: NotRequired[int]
    reverted_to: NotRequired[Status]
    was: NotRequired[Status]


class SummaryRecord(TypedDict):
    summary: str
    clusters: list[Cluster]
    counts_snapshot: Counts
    counts_live: Counts
    stale: bool
    updated_at: str | None


@final
class ExcludedReason(TypedDict):
    reason: str
    count: int


@final
class PrismaCounts(TypedDict):
    identified: int
    screened: int
    excluded_total: int
    excluded_by_reason: list[ExcludedReason]
    included: int


# ─── Notes ──────────────────────────────────────────────────────────────────


@final
class NoteRecord(TypedDict):
    id: int
    paper_id: int | None
    cluster: str | None
    type: NoteType
    text: str
    created_at: str | None
    updated_at: str | None


@final
class NoteScope(TypedDict):
    paper_id: int | None
    type: NoteType


@final
class ClusterNote(TypedDict):
    id: int
    paper_id: int | None
    type: NoteType
    text: str
    title: str | None
    year: int | None


@final
class NoteLinkRecord(TypedDict):
    from_note_id: int
    to_note_id: int
    kind: NoteLinkKind


@final
class NewNote(TypedDict):
    paper_id: int | None
    cluster: str | None
    type: str
    text: str


# ─── Sections ───────────────────────────────────────────────────────────────


@final
class SeverityCounts(TypedDict):
    blockers: int
    should_fix: int
    nits: int


@final
class SectionScope(TypedDict):
    clusters: list[str]
    keywords: list[str]
    questions: list[str]


@final
class SectionRecord(TypedDict):
    id: int
    title: str
    scope: SectionScope
    draft: str
    status: SectionStatus
    parent_id: int | None
    position: int
    severity: SeverityCounts
    critique_iterations: int
    target_words: int | None
    created_at: str | None
    updated_at: str | None


@final
class SectionDraft(TypedDict):
    id: int
    title: str
    draft: str


@final
class DocumentSection(TypedDict):
    title: str
    content: str


@final
class SectionProgress(TypedDict):
    total: int
    drafted: int
    done: int


@final
class LinkedPaper(TypedDict):
    id: int
    title: str
    year: int | None
    venue: str | None
    doi: str | None
    review_status: Status | None
    via_query: str | None
    discovered_at: NotRequired[str | None]


# ─── Artifacts ──────────────────────────────────────────────────────────────


@final
class ArtifactRecord(TypedDict):
    id: int
    type: ArtifactType
    label: str
    source_path: str | None
    content: str
    summary: str | None
    metadata: dict[str, Any]
    included: bool
    created_at: str | None


# ─── Project ────────────────────────────────────────────────────────────────


@final
class ProjectTargets(TypedDict, total=False):
    target_sources_min: int
    target_sources_max: int
    target_words: int
    citation_density_target: float


@final
class ProjectMetadata(TypedDict, total=False):
    author: str
    supervisor: str
    institution: str
    department: str
    year: int
    work_type: str
    target_length: str
    language: str
    discipline: str
    standard: str
    methodology: str
    review_strictness: str
    deadline: str
    target_pages: int
    target_sources_min: int
    target_sources_max: int
    target_words: int
    citation_density_target: float
    extra: dict[str, Any]


@final
class ProjectBrief(TypedDict, total=False):
    language: str
    standard: str
    discipline: str
    target_pages: int
    target_words: int


@final
class ThesisRecord(TypedDict):
    content: str
    updated_at: str | None
