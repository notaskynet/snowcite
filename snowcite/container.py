"""Wiring: one place that builds the database and the repositories on top of it."""

from snowcite.storage.database import Database
from snowcite.storage.repositories import PaperRepository, ReviewRepository, SectionRepository


class Container:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.papers = PaperRepository(self.db)
        self.reviews = ReviewRepository(self.db)
        self.sections = SectionRepository(self.db)


container = Container()
