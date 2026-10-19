# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/0.3.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.4.0] — 2026-10-19

### Added

- **Plugins and skills.** `.claude-plugin/marketplace.json` (`snowcite-plugins`) lists two plugins: `snowcite` (the MCP server via `uvx snowcite`, optional Semantic Scholar key and OpenAlex email as plugin settings, skills `workflow`, `search`, `review`, `synthesis`, `sections`) and `academic-writing` (skills `academic-writing-ru`, `academic-critic`, `gost-report`, agent `academic-reviewer`; works without snowcite). Install with `claude plugin marketplace add cop1cat/snowcite`.
- `export_bibliography` returns `keys`: snowcite paper id → BibTeX cite key.
- **`next_step()`** — one entry point that derives the phase from the database (`not_started`, `criteria`, `search`, `review`, `low_confidence`, `synthesis`, `outline`, `writing`, `build`, `done`) and returns the ordered actions plus the data for that phase (criteria and the next compact batch while reviewing, the current section and its next action while writing). Gates are enforced in code: the next review batch is withheld until the rolling summary is saved, unconfirmed `auto_low` decisions block the outline, and a section without notes for its scope can't be drafted.
- `get_prisma_counts` — PRISMA numbers from the review trail.
- `ProjectService` owns project init.

### Changed

- **Tool surface: 68 → 38.** Related tools merged into entity-oriented ones; behaviour is unchanged unless noted.
  - Review: `review_batch(decisions)` replaces `set_review_status` — one call per batch, valid decisions applied and invalid ones reported by index. **Approved/maybe papers must leave a claim or finding in the knowledge graph** (inline `notes`, or notes recorded earlier); the server rejects the decision otherwise. `review_criteria`, `review_summary` read when called bare and write when given arguments.
  - Reading papers: `papers(status, cluster, reviewed_by, include_abstracts, ...)` replaces `get_saved_papers`, `get_unreviewed_papers`, `get_low_confidence_reviews`, `get_papers_for_writing`; `paper(id)` replaces `get_paper_details`. Records are compact (no abstract/bibtex) unless asked.
  - `snowball(paper_ids, direction)` replaces `expand_citations` (batch, per-paper errors); `import_refs` replaces `import_bibtex`/`import_ris`; `export_bibliography(format)` replaces `export_bibtex`/`export_ris`.
  - Notes: `add_notes`, `get_notes`, `update_note(..., delete=True)`, `link_notes`. Sections: `create_sections`, `get_sections`, `update_section(..., delete=True)`, `section_papers(link=, unlink=)`, `thesis`. Artifacts: `add_artifact`, `get_artifacts`, `update_artifact`.
  - Gone without replacement: `save_papers`, `get_review_progress` (use `next_step`), `get_note_density`, `get_outline_inputs` (carried by `next_step` in phase `done`), `add_note`/`delete_note`/`create_section`/`delete_section`/`link_paper_to_section`/`unlink_paper_from_section`/`get_section_papers` (folded into the tools above).
- **Layered package layout.** `domain/` (pure models, types, rules), `storage/` (`Database`, schema, repositories), `services/` (Review, Note, Section, Synthesis, Search, Citation, Artifact, Project, Workflow), `sources/` (`SourceClient` + one class per source), wired in `container.py`. MCP tools are thin wrappers over services; workflow invariants live in `domain/rules.py`.
- `get_session_state` is replaced by `next_step`; phases derive from the database and the old `outline_*` / `skeleton_approved` / `polishing` phases are gone.

### Fixed

- v0.3 section drafts now reach the document: `get_review_progress`, `gap_check`, `rewrite_citations` and the workflow state read `sections.draft` (previously the v0.2 `section_content` table).
- The v0.2 `get_section`/`list_sections` tools shadowed the v0.3 ones; they are gone.

### Removed

- **Generated project files.** `init_project` no longer writes `CLAUDE.md`, `.claude/agents/*` or `.claude/settings.json`, and `apply_settings_diff` is gone; the instructions ship as plugin skills. The Jinja templates and the `jinja2` dependency are removed.
- **Document building and PDF.** snowcite no longer renders or compiles anything: `write_document`, `compile_pdf`, `estimate_pages`, `set_backend`, `export_docx`, the PRISMA/overview/code/appendix snippet tools, the Typst and LaTeX backends and templates, Hayagriva output, and the `backend` project field. Writing the document is the model's job (skills); `export_bibtex`/`export_ris` stay. `generate_prisma_flow` became `get_prisma_counts` (numbers only).
- `next_step` ends at synthesis (`done` = corpus ready, hand over to writing skills); the `outline`, `writing` and `build` phases are gone.
- The v0.2 writing pipeline: `save_outline`, `get_outline`, `approve_outline`, `save_skeleton`, `get_skeleton`, `approve_skeleton`, `check_section_drift`, `save_section`, `get_section_content`, `list_section_contents`, `polish_section`, `polish_document`, `regenerate_section_brief`, `prepare_section_for_review`. Use sections + the critique loop.
- Per-section `artifact_ids` assignment (it lived in the outline). `get_section_critique_inputs` now returns every included artifact as a brief (id, citation label, summary — no content); fetch bodies with `get_artifact`.

### Migrated

- Existing `outline` + `section_content` rows are folded into `sections` once per database (outline order, `target_words` kept in the new `sections.target_words` column, assigned papers linked, polished content → `done`). The old tables are left in place but no longer read.

## [0.3.0] — 2026-04-28

### Added

- **Knowledge-graph notes layer.** New `notes` table holds short structured statements about papers (claim / finding / method / limitation per-paper, gap / contradiction / consensus / open_question cross-paper) with optional `note_links` typed edges. Tools: `add_note`, `add_notes`, `get_notes`, `update_note`, `delete_note`, `link_notes`, `get_note_density`. `set_review_status` accepts inline `notes=[...]` so review and extraction stay in one tool call.
- **Cross-paper synthesis.** `get_cluster_notes(cluster)` returns per-paper notes grouped by paper plus existing cross-paper notes for one round-trip. `add_synthesis_note` atomically inserts a cross-paper note + `derived_from` links to its source per-paper notes (sources are required — synthesis must be traceable). `find_gaps` flags clusters that look thin, unsynthesised, or have unanchored contradictions; also reports cluster names absent from the current `review_summary`.
- **Sections as first-class entities.** New `sections` table with structured `scope` (clusters / keywords / questions), `draft`, `status` (`outline | drafting | critiqued | done`), severity counters, and parent/position for hierarchy. Tools: `create_section`, `bulk_create_sections`, `list_sections`, `get_section`, `update_section`, `delete_section`, `get_outline_inputs` (thesis + clusters + criteria in one read for outline proposals).
- **Section-scoped research.** `research_section(section_id)` runs `search_papers` once per `scope.keywords`/`scope.questions` and links newly persisted papers to the section via `paper_section_links`. `link_paper_to_section` / `unlink_paper_from_section` for manual edits, `get_section_papers` to list. Snowball is deliberately not auto-triggered.
- **Critique / revise loop.** `get_section_critique_inputs` bundles draft + relevant notes (filtered by `scope.clusters`) + linked papers. `record_section_critique` accepts severity-tagged issues, persists aggregates (`blockers / should_fix / nits`) and `critique_iterations`, returns `should_stop` (true when blockers=0 OR iterations≥2). `revise_section(new_draft, mark_done?)` replaces the draft and resets critique state.

### Migrated

- `notes` + `note_links` + `sections` + `paper_section_links` are created by `init_db` on existing v0.2 projects. `sections.critique_iterations` arrives via additive `ALTER TABLE` for anyone who pulled an intermediate Phase-3 snapshot.

## [0.2.0] — 2026-04-19

### Added

- `save_thesis` / `get_thesis` tools — store a 2–5 paragraph statement of intent that anchors outline, search, and review in the optional thesis-first workflow.
- `gap_check` tool — flags substantive sentences (≥ 8 words by default) across stored sections that make no `[N]` citation. Candidates to cite or trim.
- `rewrite_citations` tool — bulk-remap `[N]` paper-id references across `section_content` through MCP, replacing the previous pattern of hand-patching generated `.tex` / `.typ` files.
- `estimate_pages` tool — renders the current draft to a temp PDF and reports actual page count, word total, and delta to `target_pages`.
- Target metrics on `project_metadata`: `target_pages`, `target_sources_min`, `target_sources_max`, `target_words`, `citation_density_target`. Surfaced in `get_session_state().targets`.
- `get_review_progress` now also reports writing stats (words, citations, citations per 100 words) and emits warnings when approved sources or citation density fall below targets.
- Self-contained ГОСТ Typst template (margins 30/15/20/20 mm, Times New Roman 14 pt, 1.5 line spacing, `gost-r-705-2008-numeric` bibliography). No longer depends on `@preview/modern-g7-32`.

### Fixed

- `write_document` now rewrites `[N]` paper-id citations in section content to the cite keys actually published in the bibliography (`\cite{key}` for LaTeX, `@key` for Typst). Previously the document and `.bib`/`.yml` used unrelated keys and the PDF failed to resolve references.
- Cite-key fallback for papers without structured authors derives the prefix from the first meaningful title word instead of a literal `unknown`.

### Changed

- CLAUDE.md template now documents the optional thesis-first flow, mandates a `get_low_confidence_reviews()` pass before `approve_outline()`, and explicitly bans `sed`/`grep` patching of generated compile artifacts after a failed `compile_pdf`.

### Migrated

- Additive `ALTER TABLE` on `project_metadata` to add the new target columns for pre-0.2 databases; runs on first `init_db` call.

## [0.1.0] — 2026-04-18

First public release of `snowcite` — an MCP server for systematic literature review.

### Added

- FastMCP-based MCP server, installed as the `snowcite` console command.
- Multi-source search: arXiv, Semantic Scholar, OpenAlex, Crossref, PubMed.
- Unified HTTP client (`sources/_http.py`) with rate limiting, exponential backoff, and `Retry-After` handling.
- DOI-first deduplication with a normalized-title fallback (fuzzy match ≥ 0.9).
- aiosqlite-backed storage in `<project>/.snowcite/papers.db`; project resolver walks up the directory tree.
- Review tools: `get_review_criteria`, `get_unreviewed_papers`, `get_paper_details`, `set_review_status`, `get_review_progress`, `get_low_confidence_reviews`.
- Rolling review summary (`save_review_summary` / `get_review_summary`) with a `stale` flag after snowball expansion.
- Snowball expansion: `expand_citations` over references and citations, with an arXiv → Semantic Scholar DOI fallback.
- Review statuses (`approved` / `maybe` / `rejected` / `unreviewed`) and an audit trail via `reviewed_by` (`auto_high` / `auto_low` / `user`) and a required `reason`.
- LaTeX and Typst generation from Jinja2 templates; BibTeX and Hayagriva bibliography assembly.
- PDF compilation via `tectonic` (LaTeX) and `typst` (Typst).
- External reference import: BibTeX and RIS (`import_refs`).
- Export, environment doctor checks, project init, and session management tools.
- Backend-aware PRISMA and overview diagram templates.
- MkDocs documentation, GitHub Actions CI (ruff + pytest), and a deploy workflow.

### Architectural decisions

- Review happens in chat — no web UI, no second terminal.
- All source access goes through `snowcite/sources/*` clients; direct `httpx` calls are disallowed.
- State transitions go through MCP tools only; direct edits to `papers.db` are unsupported.
- PDFs are not parsed — abstracts come from source APIs.
- Only `tectonic` and `typst` are supported; no system TeX Live.

[0.2.0]: https://github.com/cop1cat/snowball-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/cop1cat/snowball-mcp/releases/tag/v0.1.0
