from typing import Any, NotRequired, TypedDict, final

from snowcite.domain.records import (
    Cluster,
    Counts,
    HistoryEntry,
    LinkedPaper,
    NoteRecord,
    PaperRecord,
    ProjectBrief,
    ProjectMetadata,
    ProjectTargets,
    SectionScope,
    SeverityCounts,
    SummaryRecord,
)
from snowcite.domain.types import ArtifactType, NoteType, Phase, SectionStatus, Source


@final
class IndexedError(TypedDict):
    index: int
    error: str


@final
class PaperError(TypedDict):
    paper_id: int
    error: str


# ─── Search ─────────────────────────────────────────────────────────────────


@final
class SearchSummary(TypedDict):
    saved: int
    duplicates: int
    new_ids: list[int]
    titles: list[str]
    failed_sources: NotRequired[list[str]]
    errors: NotRequired[list[PaperError]]


@final
class PaperPreview(TypedDict):
    source: Source
    source_id: str
    doi: str | None
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    abstract: str | None
    pdf_url: str | None
    bibtex: str | None
    metadata: dict[str, Any]


@final
class SearchPreview(TypedDict):
    papers: list[PaperPreview]
    count: int
    failed_sources: NotRequired[list[str]]
    errors: NotRequired[list[PaperError]]


@final
class ClusterError(TypedDict):
    error: str
    available: NotRequired[list[str | None]]


@final
class ImportResult(TypedDict):
    parsed: int
    saved: int
    duplicates: int
    new_ids: list[int]
    without_abstract: int
    note: str | None


@final
class ExportResult(TypedDict):
    path: str
    format: str
    keys: dict[str, str]
    entries: int


# ─── Review ─────────────────────────────────────────────────────────────────


@final
class CriteriaSaved(TypedDict):
    id: int


@final
class SetStatusResult(TypedDict):
    updated: int
    skipped_invalid_ids: NotRequired[list[int]]
    note_ids: NotRequired[list[int]]
    error: NotRequired[str]
    note: NotRequired[str]
    available: NotRequired[list[str | None]]


@final
class ReviewBatchResult(TypedDict):
    updated: int
    errors: list[IndexedError]
    skipped_invalid_ids: NotRequired[list[int]]
    note_ids: NotRequired[list[int]]


@final
class SummaryView(SummaryRecord):
    warnings: list[str]


@final
class SummarySaved(TypedDict):
    status: str


@final
class WritingStats(TypedDict):
    words: int
    citations: int
    citation_density_per_100_words: float
    sections_with_content: int


@final
class ProgressView(TypedDict):
    counts: Counts
    writing: WritingStats
    targets: ProjectTargets
    warnings: list[str]


# ─── Notes and synthesis ────────────────────────────────────────────────────


@final
class NoteAdded(TypedDict):
    id: int


@final
class NotesAdded(TypedDict):
    inserted: int
    ids: list[int]
    errors: list[IndexedError]


@final
class NoteUpdated(TypedDict):
    updated: bool
    id: int


@final
class NoteDeleted(TypedDict):
    deleted: int


@final
class NoteLinked(TypedDict):
    linked: bool


class NoteBrief(TypedDict):
    id: int
    type: NoteType
    text: str


@final
class CrossNote(NoteBrief):
    derived_from: list[int]


@final
class PaperNotes(TypedDict):
    paper_id: int
    title: str | None
    year: int | None
    notes: list[NoteBrief]


@final
class ClusterNotes(TypedDict):
    cluster: str
    papers: list[PaperNotes]
    cross_paper: list[CrossNote]
    counts: dict[str, int]


@final
class SynthesisAdded(TypedDict):
    id: int
    links: int


@final
class GapFinding(TypedDict):
    cluster: str
    flags: list[str]
    per_paper_notes: int
    cross_paper_notes: int
    unanchored_contradiction_ids: list[int]


@final
class GapsResult(TypedDict):
    findings: list[GapFinding]
    unknown_clusters_in_summary: list[str]
    total_clusters_with_notes: int


# ─── Sections ───────────────────────────────────────────────────────────────


@final
class SectionCreated(TypedDict):
    id: int


@final
class SectionsCreated(TypedDict):
    inserted: int
    ids: list[int]
    errors: list[IndexedError]


@final
class SectionUpdated(TypedDict):
    updated: bool
    id: int


@final
class SectionDeleted(TypedDict):
    deleted: int


class OutlineInputs(TypedDict):
    thesis: str | None
    clusters: list[Cluster]
    criteria: str | None


@final
class ArtifactBrief(TypedDict):
    id: int
    type: ArtifactType
    label: str
    citation_label: str
    summary: str | None
    included: bool
    chars: int
    metadata: dict[str, Any]
    created_at: str | None


@final
class CritiqueSection(TypedDict):
    id: int
    title: str
    scope: SectionScope
    draft: str
    status: SectionStatus
    severity: SeverityCounts
    critique_iterations: int


@final
class CritiqueInputs(TypedDict):
    section: CritiqueSection
    notes: list[NoteRecord]
    artifacts: list[ArtifactBrief]
    linked_papers: list[LinkedPaper]


@final
class CritiqueRecorded(TypedDict):
    should_stop: bool
    reason: str
    severity: SeverityCounts
    iteration: int
    issues: list[dict[str, Any]]


@final
class SectionRevised(TypedDict):
    updated: bool
    id: int
    status: SectionStatus


@final
class SectionLinked(TypedDict):
    linked: bool


@final
class SectionUnlinked(TypedDict):
    deleted: int


@final
class SectionPapers(TypedDict):
    papers: list[LinkedPaper]
    errors: NotRequired[list[PaperError]]


@final
class QueryResult(TypedDict):
    query: str
    saved: int
    duplicates: int
    new_ids: list[int]


@final
class ResearchResult(TypedDict):
    section_id: int
    queries: list[QueryResult]
    total_new: int
    failed_sources: NotRequired[list[str]]


@final
class UncitedSentence(TypedDict):
    sentence: str
    word_count: int


@final
class SectionGaps(TypedDict):
    section: str
    count: int
    sentences: list[UncitedSentence]


@final
class GapCheckResult(TypedDict):
    total_gaps: int
    min_words: int
    gaps: list[SectionGaps]


@final
class ModifiedSection(TypedDict):
    name: str
    refs_replaced: int


@final
class RewriteResult(TypedDict):
    modified: list[ModifiedSection]
    refs_replaced: int
    sections_scanned: int


@final
class ThesisView(TypedDict):
    content: str
    updated_at: str | None
    word_count: int


@final
class ThesisSaved(TypedDict):
    saved: bool
    word_count: int


# ─── Artifacts ──────────────────────────────────────────────────────────────


@final
class ArtifactAdded(TypedDict):
    id: int
    type: ArtifactType
    label: str
    chars: int
    citation_label: str


@final
class ArtifactDeleted(TypedDict):
    deleted: bool
    id: int


@final
class ArtifactIncluded(TypedDict):
    updated: bool
    id: int
    included: bool


# ─── Project and workflow ───────────────────────────────────────────────────


@final
class InitResult(TypedDict):
    project_root: str
    snowcite_dir: str
    already_initialized: bool
    migrated_legacy: bool
    metadata_effective: ProjectMetadata


@final
class SearchPayload(TypedDict):
    criteria: str | None


@final
class SummaryBrief(TypedDict):
    text: str
    topics: list[str | None]
    stale: bool


@final
class ReviewPayload(TypedDict):
    criteria: str | None
    summary: SummaryBrief | None
    batch: NotRequired[list[PaperRecord]]


@final
class LowConfidencePayload(TypedDict):
    papers: list[PaperRecord]


@final
class SynthesisPayload(TypedDict):
    note_density: dict[str, dict[str, int]]


@final
class DonePayload(OutlineInputs):
    gaps: GapsResult
    project: ProjectBrief


@final
class EmptyPayload(TypedDict):
    pass


type StepPayload = (
    SearchPayload
    | ReviewPayload
    | LowConfidencePayload
    | SynthesisPayload
    | DonePayload
    | EmptyPayload
)


@final
class NextStepResult(TypedDict):
    phase: Phase
    why: str
    do: list[str]
    payload: StepPayload
    project_active: bool
    counts: NotRequired[Counts]
    targets: NotRequired[ProjectTargets]
    warnings: NotRequired[list[str]]
    last_actions: NotRequired[list[HistoryEntry]]


@final
class Probe(TypedDict):
    name: str
    severity: str
    detail: str


@final
class EnvironmentSettings(TypedDict):
    semantic_scholar_api_key_set: bool
    openalex_email_set: bool


@final
class EnvironmentReport(TypedDict):
    verdict: str
    errors: list[Probe]
    warnings: list[Probe]
    ok: list[Probe]
    settings: EnvironmentSettings
