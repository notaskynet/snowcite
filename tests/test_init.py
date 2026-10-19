"""init_project onboarding — scaffold, metadata persistence, migrations."""

from pathlib import Path

import aiosqlite
import pytest

from snowcite.container import container
from snowcite.storage.projects import create_project_dir, get_db_path
from snowcite.tools.init import get_project_metadata, init_project


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh cwd with no .snowcite/ and no env override — the init_project target."""
    monkeypatch.delenv("SNOWCITE_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    container.db.reset()
    return tmp_path


@pytest.mark.asyncio
async def test_init_persists_target_metrics(isolated_cwd: Path):
    await init_project(
        metadata={
            "author": "X",
            "target_pages": 20,
            "target_sources_min": 40,
            "target_sources_max": 60,
            "target_words": 5000,
            "citation_density_target": 1.2,
        }
    )
    meta = await get_project_metadata()
    assert meta["target_pages"] == 20
    assert meta["target_sources_min"] == 40
    assert meta["target_sources_max"] == 60
    assert meta["target_words"] == 5000
    assert meta["citation_density_target"] == 1.2


@pytest.mark.asyncio
async def test_init_migrates_existing_db_without_target_columns(
    isolated_cwd: Path, monkeypatch: pytest.MonkeyPatch
):
    # Simulate a pre-0.2 DB by creating `project_metadata` without the target
    # columns, then running init_project and checking the migration added them.
    create_project_dir()
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(
            """
            CREATE TABLE project_metadata (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                author TEXT, supervisor TEXT, institution TEXT, department TEXT, year INTEGER,
                work_type TEXT, target_length TEXT, language TEXT DEFAULT 'en', discipline TEXT,
                standard TEXT DEFAULT 'plain', methodology TEXT, backend TEXT DEFAULT 'typst',
                review_strictness TEXT DEFAULT 'standard', deadline TEXT,
                extra_json TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO project_metadata (id, author) VALUES (1, 'legacy');
            """
        )
        await conn.commit()
    container.db.reset()  # force re-run of migrations on next connect

    await init_project(metadata={"target_pages": 15})
    meta = await get_project_metadata()
    assert meta["author"] == "legacy"
    assert meta["target_pages"] == 15


@pytest.mark.asyncio
async def test_init_scaffolds_dirs_and_writes_no_claude_files(isolated_cwd: Path):
    result = await init_project(metadata={"author": "Jane Doe", "language": "ru"})
    assert (isolated_cwd / ".snowcite" / "papers.db").exists()
    assert (isolated_cwd / ".snowcite" / "cache").is_dir()
    assert result["metadata_effective"]["author"] == "Jane Doe"
    # Instructions ship as skills in the plugin, not as generated project files.
    assert not (isolated_cwd / "CLAUDE.md").exists()
    assert not (isolated_cwd / ".claude").exists()


@pytest.mark.asyncio
async def test_init_persists_metadata_and_reads_back(isolated_cwd: Path):
    await init_project(
        metadata={
            "author": "Alice",
            "institution": "MSU",
            "year": 2026,
            "discipline": "medicine",
            "standard": "vancouver",
            "language": "en",
        }
    )
    md = await get_project_metadata()
    assert md["author"] == "Alice"
    assert md["institution"] == "MSU"
    assert md["year"] == 2026
    assert md["discipline"] == "medicine"


@pytest.mark.asyncio
async def test_init_update_preserves_existing_metadata(isolated_cwd: Path):
    await init_project(metadata={"author": "Alice", "institution": "MSU"})
    await init_project(metadata={"discipline": "medicine"}, update=True)
    md = await get_project_metadata()
    # Old fields survived the update.
    assert md["author"] == "Alice"
    assert md["institution"] == "MSU"
    # New field landed.
    assert md["discipline"] == "medicine"


@pytest.mark.asyncio
async def test_init_without_metadata_keeps_existing(isolated_cwd: Path):
    await init_project(metadata={"author": "Alice"})
    # No metadata + no update — just a rerun. Should not wipe the row.
    await init_project()
    md = await get_project_metadata()
    assert md["author"] == "Alice"


@pytest.mark.asyncio
async def test_legacy_writing_tables_migrate_into_sections(isolated_cwd: Path):
    # A v0.2 database: outline + section_content, no `sections` table yet.
    create_project_dir()
    async with aiosqlite.connect(get_db_path()) as conn:
        await conn.executescript(
            """
            CREATE TABLE outline (
                id INTEGER PRIMARY KEY CHECK (id = 1), sections_json TEXT NOT NULL,
                approved INTEGER DEFAULT 0, created_at TIMESTAMP, updated_at TIMESTAMP
            );
            CREATE TABLE section_content (
                name TEXT PRIMARY KEY, content TEXT NOT NULL, word_count INTEGER,
                version INTEGER DEFAULT 1, polished INTEGER DEFAULT 0, updated_at TIMESTAMP
            );
            INSERT INTO outline (id, sections_json) VALUES
                (1, '[{"name": "Intro", "target_words": 300}, {"name": "Methods"}]');
            INSERT INTO section_content (name, content, polished) VALUES
                ('Intro', 'intro text', 1), ('Extra', 'orphan text', 0);
            """
        )
        await conn.commit()
    container.db.reset()

    sections = await container.section_service.list_all()
    assert [(s["title"], s["status"], s["draft"]) for s in sections] == [
        ("Intro", "done", "intro text"),
        ("Methods", "outline", ""),
        ("Extra", "drafting", "orphan text"),
    ]
    assert sections[0]["target_words"] == 300

    # Running init again must not duplicate the migrated sections.
    container.db.reset()
    assert len(await container.section_service.list_all()) == 3
