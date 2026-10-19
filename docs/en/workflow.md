# Workflow

The server is a set of **rails**; the procedure lives in skills. `next_step()` is the one entry point: it derives the phase from the database (nothing is stored in a flag) and returns `phase`, `why`, ordered `do` actions and a `payload` with the data for that phase, plus counts, targets, warnings and recent actions.

```
not_started → criteria → search → review ⇄ (summary) → low_confidence → synthesis → done
```

## Gates enforced by the server

| Gate | Effect |
|---|---|
| Rolling summary missing or stale | `review` returns no batch; the first action is `review_summary(...)` |
| `auto_low` decisions unconfirmed | `low_confidence` blocks synthesis and the outline |
| Approved / maybe without a claim or finding | `review_batch` rejects that decision (`errors` by index) |
| Cross-paper note without sources | `add_synthesis_note` refuses it |
| Section with no notes for its scope | a skill rule, not a server gate: an empty `notes` in `get_section_critique_inputs` means don't draft — review more or narrow the scope |

## Review loop

1. Read `payload.criteria` (drift guard) and the summary; compare its text with the live counts.
2. Decide the batch autonomously with a confidence grade: confident match → `auto_high`, leaning → `auto_low`, borderline → the user.
3. `review_batch([...])`: `{paper_id, status, reason, reviewed_by, notes}`. `reason` is required — it is the PRISMA trail. Valid decisions apply, invalid ones come back by index.
4. Borderline papers go to you one at a time, facts only, no recommendation.
5. `review_summary(summary, clusters)` — at most 500 words, rewritten from scratch; clusters use the criteria categories.

Undo with `undo_last_review_action`; move a whole filter with `bulk_reclassify`; read the PRISMA numbers with `get_prisma_counts`.

## Snowball

After the first pass, `snowball(paper_ids, "references" | "citations")` on approved papers. New papers land in `unreviewed` and mark the summary stale. It is always your call; it never runs automatically.

## Synthesis

Per cluster: `get_cluster_notes` → `add_synthesis_note(cluster, type, text, derived_from_note_ids)`; afterwards `find_gaps`. Types: `gap`, `contradiction`, `consensus`, `open_question`.

## Sections

Each section is an entity with scope (`clusters`, `keywords`, `questions`), draft, status and critique counters. Per section: `get_section_critique_inputs` → draft → `record_section_critique` (stops at zero blockers or two iterations) → `revise_section` → done. `research_section` adds papers for a scope on request; `gap_check` lists uncited sentences; `rewrite_citations` remaps `[N]` ids.

## Skills

| Plugin | Skills |
|---|---|
| `snowcite` | `workflow`, `search`, `review`, `synthesis`, `sections` |
| `academic-writing` | `academic-writing-ru`, `academic-critic`, `gost-report`, agent `academic-reviewer` |
