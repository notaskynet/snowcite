# CLAUDE.md

Guide for Claude Code sessions in the snowcite repo. (The workflow *users* follow lives in
the plugin skills under `plugins/`, not here.)

## What this is

`snowcite` is an MCP server for systematic literature review plus two Claude Code plugins
that carry the skills. The server searches arXiv / Semantic Scholar / OpenAlex / Crossref /
PubMed, snowballs through citations, stores review decisions, a notes graph, cross-paper
synthesis, sections with a critique loop, and research artifacts. It builds **no document and
no PDF** — the model writes the text, guided by skills.

## Architectural invariants

- **Rails in the server, procedure in skills.** Anything that must hold goes into code
  (`domain/rules.py`, `domain/phases.py`, service validation) and returns an actionable error;
  prose in a skill is only for judgment. Don't re-add a rule as a docstring when it can be a check.
- **Reviewing happens in chat, not in a UI.** No Starlette/Flask/Jinja/htmx, no browser.
- **The server never calls an LLM.** It works on subscription models because the client drives.
  Don't add API-key LLM calls or rely on MCP sampling (Claude Code doesn't support it).
- **No document building.** No Typst/LaTeX/pandoc/PDF in the server. `export_bibliography` is
  the one output that feeds a document.

## Layout

```text
snowcite/
├── server.py          # MCP entrypoint (console script `snowcite`)
├── app.py             # FastMCP instance
├── container.py       # the one wiring point: Database → repositories → services
├── settings.py        # pydantic-settings, env SNOWCITE_*
├── domain/            # pure: models, types, records / results / inputs (TypedDicts), rules, phases, dedup, citations, bibliography, search policy
├── storage/           # Database (SQLAlchemy async), schema.sql (DDL), models.py (ORM rows), migrations.py, projects.py (.snowcite/ resolver), repositories/
├── services/          # Review, Note, Section, Synthesis, Search, Citation, Artifact, Project, Workflow
├── sources/           # SourceClient / CitationSource ABCs + one class per source, _http.py
└── tools/             # thin MCP wrappers over services (parse args → call service)
plugins/
├── snowcite/          # plugin: .mcp.json (uvx snowcite), skills: workflow, search, review, synthesis, sections
└── academic-writing/  # plugin: skills academic-writing-ru, academic-critic, gost-report; agent academic-reviewer
.claude-plugin/marketplace.json   # marketplace `snowcite-plugins` listing both plugins
```

Dependencies point inward: `tools → services → repositories/sources → domain`. Services
receive repositories and clients through the constructor; tests build their own with fakes
(`tests/test_search_service.py`). `<project>/.snowcite/papers.db` is the user project's DB.

## The tool surface

38 tools, entity-oriented: `next_step` (entry point), `search_papers` / `snowball` /
`import_refs` / `papers` / `paper`, `review_criteria` / `review_batch` / `bulk_reclassify` /
`undo_last_review_action` / `review_summary` / `get_prisma_counts`, notes and synthesis,
sections / critique / `research_section` / `section_papers` / `thesis`, artifacts,
`export_bibliography`, `init_project`, `get_project_metadata`, `check_environment`. When
adding a tool, prefer extending an entity tool (get-or-set by argument presence, `delete=True`)
over a new name; keep descriptions actionable — they are the model's only documentation.

`next_step` is the contract with the skills: phases and gates are in `domain/phases.py`
(`decide`, pure) and payloads in `services/workflow.py`. Changing a phase or a `do` string
means updating the matching skill.

## Antipatterns

- **No scripts against `papers.db`** (sqlite CLI, ad-hoc Python). State goes through tools.
- **No direct `httpx` to source APIs** — use `sources/*`, which rate-limit, retry and cap concurrency.
- **No Zotero integration**; BibTeX / RIS via `import_refs` is deliberately narrow.
- **No PDF parsing** — abstracts from the source APIs only.
- **Don't write queries in tools or services** — they belong in a repository, built with SQLAlchemy `select` / `update` over the ORM rows. `schema.sql` is the DDL source of truth; `tests/test_schema.py` keeps `models.py` in step with it.
- **No bare `dict[str, Any]` across layers.** Tool and service results, repository records and tool inputs are TypedDicts (`domain/results.py`, `records.py`, `inputs.py`); leaf shapes returned next to `ErrorResult` are `@final` so `"error" in result` narrows. Free-form JSON (metadata, issues) is the exception. `uv run mypy` must stay clean.
- **No module docstrings.** Tool function docstrings are the model's only documentation — keep them long and actionable.
- **Don't invent cluster names** — clusters come from the review summary; `find_gaps` flags strays.
- **Never recommend a decision on a borderline paper** — it biases the user (skill rule; keep it in `review`).

## Stuck detection

If you fail to resolve the same problem (a failing test, a source API quirk, a migration)
twice in a row: stop, summarise what you tried and why it failed, and ask the user.

## Commands

```bash
uv sync --group dev && uv run python -m snowcite.server    # run from a clone
uv run pytest                                               # full suite
uv run ruff check && uv run ruff format                     # lint + format
uv run mypy                                                 # types
claude plugin validate .                                    # marketplace + plugins
```

CI (`.github/workflows/test.yml`) runs ruff, mypy and pytest on push and PR.

## Conventions

- **Dedup**: DOI is the primary key. No DOI → normalized title (lowercase, strip punctuation, ≥ 0.9 similarity).
- **Sources**: `arxiv | semantic_scholar | openalex | crossref | pubmed`.
- **Review statuses**: `approved | maybe | rejected | unreviewed`. **`reviewed_by`**: `auto_high`
  (confident), `auto_low` (extrapolation, the user confirms), `user`. `reason` is required — it is the PRISMA trail.
- **Notes**: per-paper types (claim, finding, method, limitation) need `paper_id`; cross-paper
  types (gap, contradiction, consensus, open_question) must not, and cite sources via `derived_from`.
- **Sections**: status `outline | drafting | critiqued | done`; critique stops at zero blockers or two iterations.
- **Citations** in drafts are `[N]` with the snowcite paper id; `export_bibliography` returns the id → BibTeX key map.
- **All I/O is async** — aiosqlite, httpx.AsyncClient.
- **Schema**: `storage/schema.sql` is idempotent DDL applied on every open; `storage/migrations.py` holds additive changes for older databases (`ALTER TABLE ADD COLUMN`, one-time data moves behind `PRAGMA user_version`).
- **Commits**: short subject, no `Co-Authored-By`; bump CHANGELOG and `pyproject.toml` version once per release batch.

## Source details

- **arXiv** (`arxiv` lib): 1 req / 3 s. No citation graph — `snowball` resolves through Semantic Scholar via DOI.
- **Semantic Scholar**: 100 req / 5 min unauthenticated, 100 req / s with `SNOWCITE_SEMANTIC_SCHOLAR_API_KEY`. References and citations. `sources/_http.py` retries 429/5xx with backoff and honours `Retry-After`.
- **OpenAlex**: polite pool via `SNOWCITE_OPENALEX_EMAIL`. Abstracts arrive as an inverted index, rebuilt to plaintext at ingestion.
- **Crossref**: DOI metadata; reuses the OpenAlex `mailto`.
- **PubMed**: NCBI E-utilities (`esearch` + `esummary`); abstracts need a separate `efetch` and are left empty on search.

## Plugins

Skills are `plugins/*/skills/<name>/SKILL.md` (frontmatter `name`, `description`; keep bodies
under ~500 lines, details in linked files). The `snowcite` plugin starts the server with
`uvx snowcite`; `userConfig` carries the optional Semantic Scholar key and OpenAlex email.
Plugin names can't start with `claude-` / `anthropic-`. Run `claude plugin validate .` after
editing any manifest.
