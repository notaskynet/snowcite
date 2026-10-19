import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from snowcite.storage.projects import get_db_path
from snowcite.storage.schema import apply_schema


class Database:
    def __init__(self, path_provider: Callable[[], Path] = get_db_path) -> None:
        self._path_provider = path_provider
        # Paths whose schema was applied in this process + a lock per path to
        # serialize init/migration under concurrent `connection()` callers.
        self._initialized: set[Path] = set()
        self._locks: dict[Path, asyncio.Lock] = {}

    @property
    def path(self) -> Path:
        return self._path_provider()

    def reset(self) -> None:
        """Forget which paths are initialized; the next connection re-runs migrations."""
        self._initialized.clear()

    async def init(self, path: Path | None = None) -> None:
        """Create the schema in the active project's DB (or at `path`). Idempotent."""
        target = path if path is not None else self.path
        resolved = target.resolve()
        lock = self._locks.setdefault(resolved, asyncio.Lock())
        async with lock:
            if resolved in self._initialized:
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(target) as conn:
                await apply_schema(conn)
            self._initialized.add(resolved)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Async connection to the active project's DB.

        Raises `NoProjectError` if no `.snowcite/` exists in cwd or any parent.
        """
        target = self.path
        if target.resolve() not in self._initialized:
            await self.init(target)
        async with aiosqlite.connect(target) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = aiosqlite.Row
            yield conn
