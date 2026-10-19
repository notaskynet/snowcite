import sqlite3
from pathlib import Path

from snowcite.container import container
from snowcite.storage.models import Base


async def test_orm_models_match_schema_sql(tmp_project: Path):
    await container.db.init()
    conn = sqlite3.connect(tmp_project / ".snowcite" / "papers.db")
    try:
        for table in Base.metadata.sorted_tables:
            declared = {c.name for c in table.columns}
            actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table.name})")}
            assert declared == actual, f"{table.name}: models and schema.sql disagree"
        stored = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        modelled = {t.name for t in Base.metadata.sorted_tables}
        assert (stored - {"sqlite_sequence"}) == modelled
    finally:
        conn.close()


async def test_schema_applies_twice_without_error(tmp_project: Path):
    await container.db.init()
    container.db.reset()
    await container.db.init()
