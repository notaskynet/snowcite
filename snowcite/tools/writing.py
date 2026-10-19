from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.citations import GAP_CHECK_MIN_WORDS


# ─── Thesis (thesis-first workflow entry point) ────────────────────────────


@mcp.tool()
async def thesis(content: str | None = None) -> dict[str, Any] | None:
    """Read or set the paper's thesis — 2–5 paragraphs: what it is about, what it contributes.

    Without `content` returns `{content, word_count, updated_at}` (None if never set).
    With `content` overwrites the singleton and returns `{saved, word_count}`.

    Written early in the thesis-first workflow so search, review and the outline can key
    off an explicit statement of intent. Let it change as understanding deepens.
    """
    if content is None:
        record = await container.project.thesis_record()
        if record is None:
            return None
        return {**record, "word_count": len(record["content"].split())}
    text = content.strip()
    if not text:
        return {"error": "thesis content is empty"}
    await container.project.save_thesis(text)
    return {"saved": True, "word_count": len(text.split())}


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
