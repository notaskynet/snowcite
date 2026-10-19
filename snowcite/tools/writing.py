"""Writing helpers: thesis, citation checks, and backend-native snippets.

Structure and drafts live in sections (`tools/sections.py`, `tools/critique.py`);
this module holds the pieces around them.
"""

from typing import Any

from snowcite.app import mcp
from snowcite.artifacts import list_artifacts as _list_artifacts_all, load_artifact
from snowcite.container import container
from snowcite.domain.citations import GAP_CHECK_MIN_WORDS
from snowcite.domain.types import Backend
from snowcite.render.snippets import (
    include_code,
    overview_table,
    primary_sources_appendix,
    prisma_flow,
)


# ─── Thesis (thesis-first workflow entry point) ────────────────────────────


@mcp.tool()
async def save_thesis(content: str) -> dict[str, Any]:
    """Persist the paper's thesis — 2–5 paragraphs answering "what is this
    about, what's the contribution". Singleton; re-saving overwrites.

    Written early in the thesis-first workflow (before the outline) so later
    stages — outline, search, review — can key off an explicit statement of
    intent instead of drifting toward whatever papers happened to turn up
    first. Let the thesis change as understanding deepens; just re-save.
    """
    text = content.strip()
    if not text:
        return {"error": "thesis content is empty"}
    await container.project.save_thesis(text)
    return {"saved": True, "word_count": len(text.split())}


@mcp.tool()
async def get_thesis() -> dict[str, Any] | None:
    """Read the stored thesis. Returns None if never set."""
    record = await container.project.thesis_record()
    if record is None:
        return None
    return {**record, "word_count": len(record["content"].split())}


# ─── Citation checks ────────────────────────────────────────────────────────


@mcp.tool()
async def gap_check(
    min_words: int = GAP_CHECK_MIN_WORDS,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Find sentences in section drafts that make no citations.

    Returns a list per section of substantive sentences (≥ `min_words` words)
    that contain no `[N]` cite. These are candidates for either backing up
    with a source or trimming. Short connective sentences are skipped — they
    legitimately don't cite. Not a strict lint; a prompt for the author.

    `sections` optionally restricts to a subset by title. With no drafts,
    returns empty `gaps` and `total_gaps = 0`.
    """
    return await container.citations.gap_check(min_words, sections)


@mcp.tool()
async def rewrite_citations(
    mapping: dict[str, int],
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Bulk-rewrite `[N]` paper-id citations across section drafts.

    `mapping` keys are stringified old paper ids (JSON dicts carry string
    keys); values are the new ids. Only cite refs whose id appears in
    `mapping` are touched — other ids are left alone.

    `sections` optionally restricts the rewrite to a subset of section titles;
    default is every section holding a draft.

    Purpose: give Claude a first-class way to fix citations after paper-id
    renumbering (dedup, merge, deletion) instead of hand-editing the rendered
    `.tex` / `.typ` through sed. See CLAUDE.md "Stuck detection".
    """
    return await container.citations.rewrite(mapping, sections)


# ─── PRISMA flow, overview table, artifact snippets ────────────────────────


@mcp.tool()
async def generate_prisma_flow(backend: Backend = "typst") -> dict[str, Any]:
    """Build a PRISMA flow-diagram snippet from review_history.

    Returns backend-native source (TikZ for LaTeX, Typst figure for Typst)
    plus the raw counts, so Claude can paste the snippet into the document or
    summarize the counts in prose.
    """
    counts = await container.reviews.prisma_counts()
    return {"backend": backend, "counts": counts, "snippet": prisma_flow(counts, backend)}


@mcp.tool()
async def include_code_artifact(artifact_id: int, backend: Backend = "typst") -> dict[str, Any]:
    """Emit a backend-specific code-listing snippet for a `code` artifact.

    Returned `snippet` is ready to paste into a section's content. Uses
    `\\lstinputlisting` for LaTeX and `#raw(read(...))` for Typst; both read
    the file live from disk, so code changes propagate at compile time.
    """
    a = await load_artifact(artifact_id)
    if a is None:
        return {"error": f"artifact {artifact_id} not found"}
    if a["type"] != "code":
        return {"error": f"artifact {artifact_id} is {a['type']!r}, not 'code'"}
    return {"backend": backend, "snippet": include_code(a, backend)}


@mcp.tool()
async def generate_primary_sources_appendix(backend: Backend = "typst") -> dict[str, Any]:
    """Appendix listing every included artifact — pair to the bibliography.

    Paste the returned `snippet` at the end of the document (after the main
    bibliography is fine). Empty `snippet` means no included artifacts.
    """
    items = await _list_artifacts_all(included_only=True)
    snippet = primary_sources_appendix(items, backend)
    return {"backend": backend, "snippet": snippet, "entries": len(items)}


@mcp.tool()
async def generate_overview_table(
    backend: Backend = "typst",
    columns: list[str] | None = None,
) -> dict[str, Any]:
    """Render a table of approved papers with the chosen columns.

    `columns` can include any of `author`, `year`, `title`, `venue`, `doi`.
    Default: ["author", "year", "title", "venue"].
    """
    columns = columns or ["author", "year", "title", "venue"]
    papers = await container.papers.load_approved()
    records: list[dict[str, Any]] = [
        {
            "author": p["authors"][0].split()[-1] if p["authors"] else "",
            "year": p["year"],
            "title": p["title"],
            "venue": p["venue"] or "",
            "doi": p["doi"] or "",
        }
        for p in papers
    ]
    return {
        "backend": backend,
        "rows": len(records),
        "snippet": overview_table(records, columns, backend),
    }
