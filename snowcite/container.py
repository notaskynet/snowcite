"""Wiring: one place that builds the database, repositories and services."""

from snowcite.render.compiler import Compiler
from snowcite.services import (
    ArtifactService,
    BuildService,
    CitationService,
    NoteService,
    ReviewService,
    SearchService,
    SectionService,
    SynthesisService,
)
from snowcite.sources.arxiv_client import ArxivSource
from snowcite.sources.crossref import CrossrefSource
from snowcite.sources.openalex import OpenAlexSource
from snowcite.sources.pubmed import PubMedSource
from snowcite.sources.semantic_scholar import SemanticScholarSource
from snowcite.storage.database import Database
from snowcite.storage.repositories import (
    ArtifactRepository,
    NoteRepository,
    PaperRepository,
    ProjectRepository,
    ReviewRepository,
    SectionRepository,
)


class Container:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

        self.papers = PaperRepository(self.db)
        self.notes = NoteRepository(self.db)
        self.reviews = ReviewRepository(self.db, self.notes)
        self.sections = SectionRepository(self.db)
        self.project = ProjectRepository(self.db)
        self.artifacts = ArtifactRepository(self.db)

        self.review_service = ReviewService(self.reviews, self.sections, self.project)
        self.note_service = NoteService(self.notes)
        semantic_scholar = SemanticScholarSource()
        self.search = SearchService(
            self.papers,
            self.project,
            {
                "arxiv": ArxivSource(),
                "semantic_scholar": semantic_scholar,
                "openalex": OpenAlexSource(),
                "crossref": CrossrefSource(),
                "pubmed": PubMedSource(),
            },
            citations=semantic_scholar,
        )
        self.section_service = SectionService(
            self.sections,
            self.notes,
            self.papers,
            self.reviews,
            self.project,
            self.search,
            self.artifacts,
        )
        self.synthesis = SynthesisService(self.notes, self.reviews)
        self.artifact_service = ArtifactService(self.artifacts)
        self.citations = CitationService(self.sections)
        self.build = BuildService(self.papers, self.sections, self.project, Compiler())


container = Container()
