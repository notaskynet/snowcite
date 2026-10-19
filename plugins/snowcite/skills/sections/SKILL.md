---
name: sections
description: Plan and draft the written part from a reviewed corpus - propose an outline of sections with scopes, draft each section from its notes and papers, critique it as a strict reviewer, revise, and finish. Use when next_step reports `done`, or when the user asks to outline, draft or revise a literature review, related-work or thesis chapter from the collected papers.
---

# Sections: outline, draft, critique, revise

snowcite stores sections (title, scope, draft, status, critique counters) but renders nothing.
You write the text; the document itself (Typst, LaTeX, Word, Markdown) is yours to produce
with the `academic-writing` skills and the user's own tools.

## Outline

Sources: the `next_step()` payload in phase `done` (thesis, review clusters, criteria, gaps)
and `thesis()`. Propose sections to the user — title plus **scope** `{clusters, keywords,
questions}` — and after approval `create_sections([...])`. Scope clusters must be topics of the
review summary. Hierarchy via `parent_id`; order via `position`.

## Per section, in order

1. (Optional, only if the user agrees) `research_section(section_id)` runs one search per scope
   keyword or question and links new papers. Snowball stays manual.
2. `get_section_critique_inputs(section_id)` → the draft, the **notes** of the scope's clusters,
   included artifact briefs and linked papers. **No notes → don't draft**: review more papers
   into those clusters or narrow the scope, and ask the user.
3. Draft from the notes and papers only. Cite approved papers as `[N]` with their snowcite id;
   cite artifacts with their `citation_label` (e.g. `[I:3]`). Pull abstracts for quoting with
   `papers(status="approved", cluster=..., include_abstracts=True)` and artifact bodies with
   `get_artifacts(id)`. Save with `update_section(section_id, draft=..., status="drafting")`.
4. **Critique** in a strict reviewer's voice (the `academic-critic` skill, or spawn the
   `academic-reviewer` agent for a cold read). Submit `[{severity, type, text, suggested_action}]`
   with `record_section_critique`. It returns `should_stop`: stop when blockers are 0 or after
   2 iterations. Severity `blocker` is only for a section that must not ship (unsupported claim,
   factual error, contradiction with a cited paper) — style preferences are `nit`.
5. **Revise** with `revise_section(section_id, new_draft)` (resets the counters) and critique
   again. Finish with `update_section(section_id, status="done")` — or `revise_section(...,
   mark_done=True)` when the revision is the last edit.

Don't trigger `research_section` or `snowball` from inside the critique loop: critique reports
gaps, the user decides whether more search is worth it.

## Checks and bibliography

- `gap_check()` lists substantive sentences with no `[N]` citation — candidates to source or cut.
- `rewrite_citations({"old_id": new_id})` remaps ids across all drafts after papers were merged.
- `export_bibliography("bibtex")` writes `references.bib` and returns `keys` — snowcite id →
  BibTeX key. Use it to turn `[N]` into `\cite{key}` / `@key` / numbered references in the final
  document. `get_prisma_counts()` feeds the PRISMA flow.
