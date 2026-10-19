# snowcite

MCP server and skills for systematic literature review. Search arXiv / Semantic Scholar / OpenAlex / Crossref / PubMed, snowball through citations, screen papers through chat, keep a notes graph and synthesise across papers. The text itself is written by the model, guided by skills — snowcite builds no PDF.

!!! info "No UI, no browser"
    Review happens in chat. Claude reads compact records in batches, pre-filters autonomously and brings only borderline cases to you.

## What makes it different

- **Rails in the server, procedure in skills.** `next_step()` derives the phase from the database and returns what to do and the data to do it with. Gates are enforced in code: the next batch waits for the rolling summary, unconfirmed low-confidence calls block synthesis, approved papers must leave a note in the graph.
- **A knowledge graph, not a reading list.** Every approved paper leaves `claim` / `finding` notes; synthesis adds traceable gaps, contradictions and consensus on top.
- **Sections with a critique loop.** Draft from notes, critique as a strict reviewer, revise — stops at zero blockers or two iterations.
- **Standalone writing skills.** Russian scientific style, a reviewer rubric and GOST 7.32 report structure work with or without snowcite.
- **Projects live in directories.** `.snowcite/` next to your files, like `.git`. `cd` to switch projects.
- **Multi-discipline source routing.** STEM gets arXiv, medicine gets PubMed, everyone gets OpenAlex, Semantic Scholar and Crossref.

## Next

- [Installation](installation.md)
- [Getting started](getting-started.md) — your first review
- [Workflow](workflow.md) — the phases in detail
- [Artifacts](artifacts.md) — interviews, code and notes as sources
- [Troubleshooting](troubleshooting.md)
