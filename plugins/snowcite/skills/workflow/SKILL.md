---
name: workflow
description: How to run a systematic literature review with the snowcite tools. Use whenever the user wants to survey a research area, do a literature review, collect and screen papers, snowball through citations, build a related-work or thesis literature chapter, or continues such work after /clear. Start by calling next_step.
---

# snowcite workflow

snowcite is a set of tools for a literature review done **in chat**: search the scholarly
databases, screen papers in batches, keep a notes graph, synthesise across papers. No web
UI, no second terminal, no PDF or document building — you write the text yourself with the
writing skills.

## Always start with `next_step()`

It derives the phase from the database and returns `phase`, `why`, the ordered `do` actions
and a `payload` with the data that phase needs. Call it first in every session and again
after every batch. Follow `do`; don't improvise the order.

| Phase | Meaning | Skill |
|---|---|---|
| `not_started` | no project here | below |
| `criteria` | agree inclusion / exclusion criteria | [review](../review/SKILL.md) |
| `search` | collect papers | [search](../search/SKILL.md) |
| `review` | screen a batch (or save the summary first) | [review](../review/SKILL.md) |
| `low_confidence` | user confirms `auto_low` decisions | [review](../review/SKILL.md) |
| `synthesis` | name patterns across papers | [synthesis](../synthesis/SKILL.md) |
| `done` | corpus ready; outline and write | [sections](../sections/SKILL.md) |

The server enforces some gates: the next batch is withheld until the rolling summary is
saved, unconfirmed `auto_low` decisions block synthesis and the outline, approved/maybe
decisions without a claim or finding note are rejected. If a call returns an error, read it —
it says what to do.

## Starting a project (`not_started`)

Ask the user (AskUserQuestion) for: language of the work, discipline, formatting standard
(e.g. gost, ieee, apa), work type, optional author / supervisor / institution / deadline and
targets (pages, sources min / max, words). Then `init_project(metadata=...)`. Everything
you write for the user afterwards is in the project's `language`; read it with
`get_project_metadata()`.

## Rules that hold everywhere

- **Reviewing happens in chat.** Never propose a web UI, a browser, or a second terminal.
- **Abstracts stay out of the context** unless needed. Tools return compact records;
  fetch `paper(id)` only for borderline cases and **paraphrase** in one or two neutral
  sentences. Never paste operational or harmful detail from an abstract (security, AI
  safety, dual-use, biosecurity topics) — these are published research, handle them as a
  human reviewer would.
- **Never recommend a decision on a borderline paper.** Show facts and why it is hard.
- **Use the tools, not side channels.** No scripts against `papers.db`, no direct HTTP calls
  to source APIs, no PDF parsing, no Zotero integration. If a tool is missing, tell the user.
- **Cluster names come from the review summary.** Never invent one in a note or section scope.
- **Same problem fails twice → stop.** Summarise what you tried and ask the user.
- **Don't auto-run `snowball` or `research_section`.** They cost API quota and change the
  corpus; the user decides.
