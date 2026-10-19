"""Wiring: one place that builds the database, repositories and services."""

from snowcite.services import NoteService, ReviewService
from snowcite.storage.database import Database
from snowcite.storage.repositories import (
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

        self.review_service = ReviewService(self.reviews, self.sections, self.project)
        self.note_service = NoteService(self.notes)


container = Container()
