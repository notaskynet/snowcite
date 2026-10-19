import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import aiosqlite
from sqlalchemy import CursorResult, Result, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from snowcite.storage.migrations import apply_schema
from snowcite.storage.projects import get_db_path


class Database:
    def __init__(self, path_provider: Callable[[], Path] = get_db_path) -> None:
        self._path_provider = path_provider
        # Paths whose schema was applied in this process + a lock per path to
        # serialize init/migration under concurrent callers.
        self._initialized: set[Path] = set()
        self._locks: dict[Path, asyncio.Lock] = {}
        self._engines: dict[Path, AsyncEngine] = {}

    @property
    def path(self) -> Path:
        return self._path_provider()

    def reset(self) -> None:
        """Forget initialized paths and drop engines; the next session re-runs migrations."""
        self._initialized.clear()
        for engine in self._engines.values():
            engine.sync_engine.dispose()
        self._engines.clear()

    async def init(self, path: Path | None = None) -> None:
        """Apply schema.sql and migrations to the active project's DB (or at `path`). Idempotent."""
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

    def _engine_for(self, resolved: Path) -> AsyncEngine:
        engine = self._engines.get(resolved)
        if engine is None:
            # NullPool: one short-lived connection per session, nothing left open
            # when a project directory is deleted or switched.
            engine = create_async_engine(f"sqlite+aiosqlite:///{resolved}", poolclass=NullPool)

            @event.listens_for(engine.sync_engine, "connect")
            def _on_connect(dbapi_connection: Any, _record: Any) -> None:
                # Take transaction control from the driver so SAVEPOINTs work (see the
                # SQLAlchemy SQLite docs, "Serializable isolation / Savepoints").
                dbapi_connection.isolation_level = None
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.close()

            @event.listens_for(engine.sync_engine, "begin")
            def _on_begin(connection: Any) -> None:
                connection.exec_driver_sql("BEGIN")

            self._engines[resolved] = engine
        return engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A session on the active project's DB, initialised on first use.

        Raises `NoProjectError` if no `.snowcite/` exists in cwd or any parent.
        Reads use it as is; writes wrap the block in `async with session.begin():`
        (commit on success, rollback on error).
        """
        target = self.path
        resolved = target.resolve()
        if resolved not in self._initialized:
            await self.init(target)
        factory = async_sessionmaker(self._engine_for(resolved), expire_on_commit=False)
        async with factory() as session:
            yield session


def affected(result: Result[Any]) -> int:
    """Rows changed by an UPDATE / DELETE statement."""
    return cast("CursorResult[Any]", result).rowcount
