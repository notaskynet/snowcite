import json
from pathlib import Path

import aiosqlite


_SCHEMA_FILE = Path(__file__).with_name("schema.sql")


# Columns added to `project_metadata` after the initial release. Each one is
# appended lazily via `_migrate_project_metadata_add_columns` — SQLite's
# `CREATE TABLE IF NOT EXISTS` doesn't touch existing tables, so pre-existing
# DBs need the additive ALTER-TABLE dance.
_TARGET_METRIC_COLUMNS: tuple[tuple[str, str], ...] = (
    ("target_pages", "INTEGER"),
    ("target_sources_min", "INTEGER"),
    ("target_sources_max", "INTEGER"),
    ("target_words", "INTEGER"),
    ("citation_density_target", "REAL"),
)


async def _migrate_reviews_confidence(conn: aiosqlite.Connection) -> None:
    """T27: broaden `reviewed_by` from {auto,user} to {auto_high,auto_low,user}.

    SQLite CHECK constraints are baked into the table's stored DDL and don't
    update on `CREATE TABLE IF NOT EXISTS`. For pre-T27 databases we rebuild
    the table and remap `auto` → `auto_high` (the only sane default — pre-T27
    auto decisions were implicitly "high confidence").
    """
    cur = await conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='reviews'")
    row = await cur.fetchone()
    if row is None:
        return  # fresh DB
    if row[0] and "auto_high" in row[0]:
        return  # already migrated

    await conn.executescript(
        """
        CREATE TABLE reviews_new (
            paper_id INTEGER PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
            status TEXT NOT NULL CHECK (status IN ('approved','maybe','rejected','unreviewed')),
            reason TEXT,
            note TEXT,
            reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_by TEXT CHECK (reviewed_by IN ('auto_high','auto_low','user'))
        );
        INSERT INTO reviews_new
            SELECT paper_id, status, reason, note, reviewed_at,
                   CASE reviewed_by WHEN 'auto' THEN 'auto_high' ELSE reviewed_by END
            FROM reviews;
        DROP TABLE reviews;
        ALTER TABLE reviews_new RENAME TO reviews;
        CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
        CREATE INDEX IF NOT EXISTS idx_reviews_reviewed_by ON reviews(reviewed_by);
        """
    )


async def _migrate_sections_add_columns(conn: aiosqlite.Connection) -> None:
    """Add critique_iterations to pre-Phase-5 `sections` tables."""
    cur = await conn.execute("PRAGMA table_info(sections)")
    existing = {row[1] for row in await cur.fetchall()}
    if not existing:
        return
    if "critique_iterations" not in existing:
        await conn.execute(
            "ALTER TABLE sections ADD COLUMN critique_iterations INTEGER NOT NULL DEFAULT 0"
        )
    if "target_words" not in existing:
        await conn.execute("ALTER TABLE sections ADD COLUMN target_words INTEGER")


async def _migrate_project_metadata_add_columns(conn: aiosqlite.Connection) -> None:
    """Append missing target-metric columns to pre-existing `project_metadata` tables.

    `CREATE TABLE IF NOT EXISTS` doesn't add columns to an existing table, so
    every new nullable column introduced after v0.1 needs an additive ALTER
    here. Ordering doesn't matter — SQLite appends to the end either way.
    """
    cur = await conn.execute("PRAGMA table_info(project_metadata)")
    existing = {row[1] for row in await cur.fetchall()}
    if not existing:
        return  # fresh DB — main SCHEMA will create the table with all columns
    for name, coltype in _TARGET_METRIC_COLUMNS:
        if name not in existing:
            await conn.execute(f"ALTER TABLE project_metadata ADD COLUMN {name} {coltype}")


async def _migrate_legacy_writing(conn: aiosqlite.Connection) -> None:
    """Fold the v0.2 writing store (outline + section_content) into `sections`.

    Outline entries become sections in outline order (target_words kept, assigned
    paper_ids linked); section_content bodies become drafts (polished → 'done',
    otherwise 'drafting'). Content whose name isn't in the outline is appended.
    The old tables are left untouched but no longer read. Gated by
    `PRAGMA user_version` so it runs once per database.
    """
    cur = await conn.execute("PRAGMA user_version")
    row = await cur.fetchone()
    if row is not None and row[0] >= 1:
        return
    cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in await cur.fetchall()}

    outline: list[dict] = []
    if "outline" in tables:
        cur = await conn.execute("SELECT sections_json FROM outline WHERE id = 1")
        row = await cur.fetchone()
        if row:
            outline = [e if isinstance(e, dict) else {"name": e} for e in json.loads(row[0]) or []]
    content: dict[str, tuple[str, int]] = {}
    if "section_content" in tables:
        cur = await conn.execute("SELECT name, content, polished FROM section_content")
        content = {r[0]: (r[1], r[2] or 0) for r in await cur.fetchall()}

    entries = list(outline)
    known = {e.get("name") for e in entries}
    entries += [{"name": n} for n in sorted(content) if n not in known]
    for position, entry in enumerate(entries):
        name = entry.get("name")
        if not name:
            continue
        body, polished = content.get(name, ("", 0))
        status = "done" if polished else ("drafting" if body else "outline")
        cur = await conn.execute(
            "INSERT INTO sections (title, scope_json, draft, status, position, target_words) "
            "VALUES (?, '{}', ?, ?, ?, ?)",
            (name, body, status, position, entry.get("target_words")),
        )
        for paper_id in entry.get("paper_ids") or []:
            await conn.execute(
                "INSERT OR IGNORE INTO paper_section_links (paper_id, section_id, via_query) "
                "SELECT id, ?, 'legacy outline' FROM papers WHERE id = ?",
                (cur.lastrowid, paper_id),
            )
    await conn.execute("PRAGMA user_version = 1")


async def apply_schema(conn: aiosqlite.Connection) -> None:
    """Bring `conn`'s database up to the current schema. Idempotent."""
    await _migrate_reviews_confidence(conn)
    await conn.executescript(_SCHEMA_FILE.read_text(encoding="utf-8"))
    await _migrate_sections_add_columns(conn)
    await _migrate_project_metadata_add_columns(conn)
    await _migrate_legacy_writing(conn)
    await conn.commit()
