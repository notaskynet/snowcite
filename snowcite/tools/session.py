"""T26: session state snapshot for `/clear`-friendly workflow recovery.

After a context reset Claude loses track of what's already done in this
project. `get_session_state()` reads the DB and returns a compact (~200-word)
structured summary so Claude can restore bearings with one MCP call instead
of probing half a dozen tools.
"""

from typing import Any

import aiosqlite

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import Phase
from snowcite.storage.projects import find_project_root


async def _infer_phase(conn: aiosqlite.Connection) -> Phase:
    """Derive workflow phase from DB state.

    Walks later stages first — once sections hold drafts we're 'writing' (or
    'polishing' when every drafted section is done), regardless of the review
    state. Falls back to earlier phases when the later tables are empty.
    """
    cur = await conn.execute(
        "SELECT COUNT(*), SUM(draft != ''), SUM(draft != '' AND status != 'done') FROM sections"
    )
    total, drafted, unfinished = await cur.fetchone()
    if drafted:
        return "writing" if unfinished else "polishing"
    if total:
        return "outlined"

    # Any papers yet?
    cur = await conn.execute("SELECT COUNT(*) FROM papers")
    total_papers = (await cur.fetchone())[0]
    if total_papers == 0:
        cur = await conn.execute("SELECT 1 FROM review_criteria LIMIT 1")
        return "criteria_set" if await cur.fetchone() else "not_started"

    # Review in flight?
    cur = await conn.execute("SELECT COUNT(*) FROM reviews WHERE status = 'unreviewed'")
    unreviewed = (await cur.fetchone())[0]
    cur = await conn.execute("SELECT COUNT(*) FROM reviews WHERE status = 'approved'")
    approved = (await cur.fetchone())[0]
    if approved > 0 and unreviewed == 0:
        return "snowballing"
    return "reviewing"


_NEXT_ACTION_HINTS: dict[Phase, str] = {
    "not_started": "Run init_project() if you haven't, then set_review_criteria().",
    "criteria_set": "Run search_papers(query=...) to pull in candidates.",
    "reviewing": "Batch through get_unreviewed_papers(limit=20). Use reviewed_by='auto_low' for uncertain cases.",
    "snowballing": "Walk approved papers via expand_citations(), or move on to propose an outline.",
    "outlined": "Draft sections one at a time: get_section_critique_inputs(), then update_section(draft=...).",
    "writing": "Critique and revise drafted sections (record_section_critique, revise_section); draft the rest.",
    "polishing": "All drafted sections are done — write_document(), then compile_pdf().",
    "done": "Document compiled. Nothing outstanding.",
}


@mcp.tool()
async def get_session_state() -> dict[str, Any]:
    """Compact snapshot of the current project for post-`/clear` recovery.

    Returns phase, next_action hint, counts, and the last few review actions.
    No abstracts, no section bodies — this is a restore beacon, not a dump.
    """
    if find_project_root() is None:
        return {
            "phase": "not_started",
            "next_action": _NEXT_ACTION_HINTS["not_started"],
            "project_active": False,
        }

    async with container.db.connection() as conn:
        phase = await _infer_phase(conn)

        cur = await conn.execute("SELECT COUNT(*) FROM papers")
        total = (await cur.fetchone())[0]
        counts: dict[str, int] = {"papers_total": total}
        cur = await conn.execute("SELECT status, COUNT(*) FROM reviews GROUP BY status")
        for row in await cur.fetchall():
            counts[row[0]] = row[1]

        sections = await container.sections.progress_counts()
        counts["sections_total"] = sections["total"]
        counts["sections_written"] = sections["drafted"]
        counts["sections_done"] = sections["done"]

        cur = await conn.execute(
            """
            SELECT target_pages, target_sources_min, target_sources_max,
                   target_words, citation_density_target
            FROM project_metadata WHERE id = 1
            """
        )
        meta_row = await cur.fetchone()
        targets = (
            {k: meta_row[k] for k in meta_row.keys() if meta_row[k] is not None} if meta_row else {}
        )

    last_actions = await container.reviews.recent_history(5)

    return {
        "phase": phase,
        "next_action": _NEXT_ACTION_HINTS[phase],
        "project_active": True,
        "counts": counts,
        "last_actions": last_actions,
        "targets": targets,
    }
