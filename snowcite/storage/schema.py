import json

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    doi TEXT,
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL,
    authors_json TEXT NOT NULL,
    year INTEGER,
    venue TEXT,
    abstract TEXT,
    pdf_url TEXT,
    bibtex TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi
    ON papers(doi) WHERE doi IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_papers_title_norm
    ON papers(title_normalized);

CREATE TABLE IF NOT EXISTS reviews (
    paper_id INTEGER PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('approved','maybe','rejected','unreviewed')),
    reason TEXT,
    note TEXT,
    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_by TEXT CHECK (reviewed_by IN ('auto_high','auto_low','user'))
);

CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewed_by ON reviews(reviewed_by);

CREATE TABLE IF NOT EXISTS review_criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criteria_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS citations (
    source_paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    cited_paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK (direction IN ('references','citations')),
    PRIMARY KEY (source_paper_id, cited_paper_id, direction)
);

CREATE TABLE IF NOT EXISTS review_summary (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    summary TEXT NOT NULL,
    clusters_json TEXT NOT NULL,
    counts_snapshot_json TEXT NOT NULL,
    stale INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Thesis: 2–5 paragraphs answering "what is this paper about, what's the
-- contribution". Singleton. Written early (before outline) in the thesis-first
-- workflow so outline + search can key off it.
CREATE TABLE IF NOT EXISTS thesis (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    content TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    reason TEXT,
    reviewed_by TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_review_history_paper ON review_history(paper_id);
CREATE INDEX IF NOT EXISTS idx_review_history_changed_at ON review_history(changed_at);

-- User-supplied research materials: interviews, code, documents, notes, datasets.
-- Cited inline alongside `papers` when the outline assigns them to a section; do
-- not land in the main bibliography — a separate Primary-sources appendix lists
-- them.
CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('interview','code','document','note','dataset')),
    label TEXT NOT NULL,
    source_path TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    metadata_json TEXT DEFAULT '{}',
    included INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(type);
CREATE INDEX IF NOT EXISTS idx_artifacts_included ON artifacts(included);

-- Knowledge graph layer (v0.3). `notes` are short structured statements
-- extracted from papers during review and synthesised across papers afterward.
-- per-paper types (claim/finding/method/limitation) carry paper_id;
-- cross-paper types (gap/contradiction/consensus/open_question) leave it NULL
-- and instead reference other notes via `note_links`.
-- v0.3 sections-as-entities. Coexists with the v0.2 outline/skeleton/section_content
-- triple — those describe the legacy single-shot writing flow; this table backs
-- the new draft → critique → revise loop where each section is independently
-- addressable, has a typed scope (clusters/keywords/questions) for targeted
-- research, and tracks severity counters that drive the critique stop criterion.
CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '{}',
    draft TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'outline'
        CHECK (status IN ('outline','drafting','critiqued','done')),
    parent_id INTEGER REFERENCES sections(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    blockers INTEGER NOT NULL DEFAULT 0,
    should_fix INTEGER NOT NULL DEFAULT 0,
    nits INTEGER NOT NULL DEFAULT 0,
    critique_iterations INTEGER NOT NULL DEFAULT 0,
    target_words INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sections_parent ON sections(parent_id);
CREATE INDEX IF NOT EXISTS idx_sections_status ON sections(status);

-- Records which papers were discovered while researching a particular section.
-- A paper can link to multiple sections (typical for cross-cutting topics);
-- the link is purely additive — does not affect the global paper pool or its
-- review status, just answers "where did this paper enter the corpus?".
CREATE TABLE IF NOT EXISTS paper_section_links (
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    via_query TEXT,
    PRIMARY KEY (paper_id, section_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_section_links_section
    ON paper_section_links(section_id);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER REFERENCES papers(id) ON DELETE CASCADE,
    cluster TEXT,
    type TEXT NOT NULL CHECK (type IN (
        'claim','finding','method','limitation',
        'gap','contradiction','consensus','open_question'
    )),
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notes_paper ON notes(paper_id);
CREATE INDEX IF NOT EXISTS idx_notes_cluster ON notes(cluster);
CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(type);

CREATE TABLE IF NOT EXISTS note_links (
    from_note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    to_note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('supports','contradicts','extends','derived_from')),
    PRIMARY KEY (from_note_id, to_note_id, kind)
);

CREATE TABLE IF NOT EXISTS project_metadata (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    author TEXT,
    supervisor TEXT,
    institution TEXT,
    department TEXT,
    year INTEGER,
    work_type TEXT,
    target_length TEXT,
    language TEXT DEFAULT 'en',
    discipline TEXT,
    standard TEXT DEFAULT 'plain',
    methodology TEXT,
    backend TEXT DEFAULT 'typst' CHECK (backend IN ('typst','latex')),
    review_strictness TEXT DEFAULT 'standard'
        CHECK (review_strictness IN ('lenient','standard','phd_committee')),
    deadline TEXT,
    target_pages INTEGER,
    target_sources_min INTEGER,
    target_sources_max INTEGER,
    target_words INTEGER,
    citation_density_target REAL,
    extra_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

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
    if (await cur.fetchone())[0] >= 1:
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
    await conn.executescript(SCHEMA)
    await _migrate_sections_add_columns(conn)
    await _migrate_project_metadata_add_columns(conn)
    await _migrate_legacy_writing(conn)
    await conn.commit()
