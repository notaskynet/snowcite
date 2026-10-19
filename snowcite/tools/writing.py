"""Writing helpers: thesis, citation checks, and PRISMA counts.

Structure and drafts live in sections (`tools/sections.py`, `tools/critique.py`);
this module holds the pieces around them.
"""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.citations import GAP_CHECK_MIN_WORDS


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


# ─── PRISMA counts ─────────────────────────────────────────────────────────


@mcp.tool()
async def get_prisma_counts() -> dict[str, Any]:
    """PRISMA flow numbers from the review trail.

    `identified` (papers ever recorded), `screened` (decided, not unreviewed),
    `excluded_total` with `excluded_by_reason`, and `included` (approved). The
    model draws the diagram or writes the prose itself.
    """
    return await container.reviews.prisma_counts()
