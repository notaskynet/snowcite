-- snowcite project database. Applied on every open; every statement is idempotent.
-- Additive changes for databases created by older versions live in migrations.py.

-- ─── Papers and review ──────────────────────────────────────────────────────

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
    UNIQUE (source, source_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi ON papers (doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_papers_title_norm ON papers (title_normalized);

CREATE TABLE IF NOT EXISTS reviews (
    paper_id INTEGER PRIMARY KEY REFERENCES papers (id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('approved', 'maybe', 'rejected', 'unreviewed')),
    reason TEXT,
    note TEXT,
    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_by TEXT CHECK (reviewed_by IN ('auto_high', 'auto_low', 'user'))
);

CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews (status);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewed_by ON reviews (reviewed_by);

-- Append-only audit trail behind the PRISMA numbers and undo.
CREATE TABLE IF NOT EXISTS review_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    reason TEXT,
    reviewed_by TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_review_history_paper ON review_history (paper_id);
CREATE INDEX IF NOT EXISTS idx_review_history_changed_at ON review_history (changed_at);

CREATE TABLE IF NOT EXISTS review_criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criteria_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Singleton: the rolling summary of the review so far.
CREATE TABLE IF NOT EXISTS review_summary (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    summary TEXT NOT NULL,
    clusters_json TEXT NOT NULL,
    counts_snapshot_json TEXT NOT NULL,
    stale INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS citations (
    source_paper_id INTEGER NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    cited_paper_id INTEGER NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK (direction IN ('references', 'citations')),
    PRIMARY KEY (source_paper_id, cited_paper_id, direction)
);

-- ─── Knowledge graph ────────────────────────────────────────────────────────

-- Per-paper types (claim, finding, method, limitation) carry paper_id; cross-paper
-- types (gap, contradiction, consensus, open_question) leave it NULL and cite their
-- sources through note_links.
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER REFERENCES papers (id) ON DELETE CASCADE,
    cluster TEXT,
    type TEXT NOT NULL CHECK (type IN (
        'claim', 'finding', 'method', 'limitation',
        'gap', 'contradiction', 'consensus', 'open_question'
    )),
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notes_paper ON notes (paper_id);
CREATE INDEX IF NOT EXISTS idx_notes_cluster ON notes (cluster);
CREATE INDEX IF NOT EXISTS idx_notes_type ON notes (type);

CREATE TABLE IF NOT EXISTS note_links (
    from_note_id INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    to_note_id INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('supports', 'contradicts', 'extends', 'derived_from')),
    PRIMARY KEY (from_note_id, to_note_id, kind)
);

-- ─── Writing ────────────────────────────────────────────────────────────────

-- Singleton: 2-5 paragraphs on what the work is about and what it contributes.
CREATE TABLE IF NOT EXISTS thesis (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    content TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Each section is addressable on its own: a typed scope (clusters / keywords / questions)
-- for targeted research, a draft, and the critique counters that drive the stop criterion.
CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '{}',
    draft TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'outline'
        CHECK (status IN ('outline', 'drafting', 'critiqued', 'done')),
    parent_id INTEGER REFERENCES sections (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    blockers INTEGER NOT NULL DEFAULT 0,
    should_fix INTEGER NOT NULL DEFAULT 0,
    nits INTEGER NOT NULL DEFAULT 0,
    critique_iterations INTEGER NOT NULL DEFAULT 0,
    target_words INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sections_parent ON sections (parent_id);
CREATE INDEX IF NOT EXISTS idx_sections_status ON sections (status);

-- Where a paper entered the corpus while researching a section. Purely additive:
-- it does not touch the paper's review status.
CREATE TABLE IF NOT EXISTS paper_section_links (
    paper_id INTEGER NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL REFERENCES sections (id) ON DELETE CASCADE,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    via_query TEXT,
    PRIMARY KEY (paper_id, section_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_section_links_section ON paper_section_links (section_id);

-- User-supplied material: interviews, code, documents, notes, dataset descriptions.
CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('interview', 'code', 'document', 'note', 'dataset')),
    label TEXT NOT NULL,
    source_path TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    metadata_json TEXT DEFAULT '{}',
    included INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts (type);
CREATE INDEX IF NOT EXISTS idx_artifacts_included ON artifacts (included);

-- ─── Project ────────────────────────────────────────────────────────────────

-- Singleton: the project profile and targets. Unknown keys live in extra_json.
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
    review_strictness TEXT DEFAULT 'standard'
        CHECK (review_strictness IN ('lenient', 'standard', 'phd_committee')),
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
