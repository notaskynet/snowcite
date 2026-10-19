"""`next_step` — the entry point for every session, including recovery after `/clear`."""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container


@mcp.tool()
async def next_step() -> dict[str, Any]:
    """Where the project is and what to do next. Call this first, and after every batch.

    Returns `{phase, why, do, payload, counts, targets, warnings, last_actions}`:
    - `phase`: not_started | criteria | search | review | low_confidence | synthesis
      | outline | writing | build | done — derived from the database, never stored.
    - `do`: the ordered actions for this phase (tool calls and user questions).
    - `payload`: the data that phase needs, so no extra reads are required — the
      criteria and next compact batch in `review`, the section and its next action
      in `writing`, and so on.

    Gates are enforced here rather than left to prose: the next review batch is
    withheld until the rolling summary is saved, unconfirmed `auto_low` decisions
    block the outline, and a section with no notes can't be drafted.
    """
    return await container.workflow.next_step()
