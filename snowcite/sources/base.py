from abc import ABC, abstractmethod

from snowcite.domain.models import Paper
from snowcite.domain.types import Direction, Source


class SourceClient(ABC):
    """A scholarly database we can search."""

    name: Source

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[Paper]: ...


class CitationSource(SourceClient):
    """A source that also exposes the citation graph."""

    @abstractmethod
    async def get_related(
        self, paper_id: str, direction: Direction, limit: int = 20
    ) -> list[Paper]: ...

    @abstractmethod
    async def resolve_by_doi(self, doi: str) -> str | None:
        """The source's own paper id for a DOI, or None if it doesn't know it."""
