---
name: review
description: Screen papers in batches for a literature review - read criteria, decide approve, maybe or reject with confidence grades, extract claim and finding notes into the knowledge graph, keep the rolling summary, and ask the user only about borderline papers. Use when next_step reports phase `criteria`, `review` or `low_confidence`, or when the user asks to review, screen, classify or re-check papers.
---

# Reviewing papers

You pre-filter autonomously and only bring genuinely borderline papers to the user.
Work from the `payload` of `next_step()`; it carries the criteria, the summary state and the
next compact batch (20 papers, no abstracts).

## Criteria (`criteria` phase)

Agree with the user: what to include, what to exclude, and the **categories** the corpus
will be organised into (these become the summary clusters). `review_criteria(criteria_text)`
stores a new version; `review_criteria()` reads the latest. Re-read them before every batch —
they are your drift guard.

## The loop

1. `next_step()` → read `payload.criteria` and `payload.summary`. If the summary text and
   the live counts disagree, say so.
2. For each paper in `payload.batch` decide with a confidence grade, from title, venue, year
   and authors. Only for unclear papers call `paper(id)` for the abstract.
   - **Confident match** → `approved`, `reviewed_by="auto_high"`.
   - **Confident reject** → `rejected`, `auto_high`. No notes; rejected papers stay out of the graph.
   - **Leaning but unsure** → decide anyway with `reviewed_by="auto_low"`; the user confirms later.
   - **Genuinely borderline** (two criteria conflict, mixed signal) → ask the user.
3. Send the batch in **one** `review_batch([...])` call:
   ```
   {paper_id, status, reason: "auto: matches criterion X", reviewed_by, notes: [{type, text, cluster}]}
   ```
   `reason` is required (it is the PRISMA trail). Several rejected papers with one reason can
   share a decision via `paper_ids`. Approved and maybe papers need **at least one `claim` or
   `finding` note** — the server rejects the decision otherwise. Notes are one or two
   paraphrased sentences; `cluster` is a topic from the criteria categories.
   Fix and resend only the decisions listed in `errors`.
4. Borderline papers go to the user **one at a time**, in the project's language, facts only:
   ```
   Paper 7/87: "Title" (Year, Authors)
   Brief: <one or two neutral sentences>
   Why borderline: <which criteria pull apart>
   include / exclude / maybe?
   ```
   Do not recommend an answer. Record it with `reviewed_by="user"`, `reason="manual: <their comment>"`.
5. After the batch `next_step()` withholds the next batch until the summary is saved:
   `review_summary(summary, clusters)` — at most 500 words, **rewritten from scratch** to include
   everything so far (it is a singleton, not an append log), `clusters` as
   `[{topic, paper_ids, count}]` using only the criteria categories.

Mistakes: `undo_last_review_action()` steps back one decision; `bulk_reclassify(...)` moves a
whole filter (status, source, years, cluster) with an audit entry per paper.

## `low_confidence` phase

Walk every paper with `reviewed_by="auto_low"` (`papers(reviewed_by="auto_low")`) through the
user, one at a time, as above. Their answer replaces the guess (`reviewed_by="user"`). Do not
skip this: it is the only safeguard against unconfirmed guesses shaping the synthesis.

## Abstract hygiene

Tool records omit abstracts on purpose — it keeps context small and avoids piling up
harmful-sounding terminology. For a borderline paper summarise the abstract in your own
words; never copy passages with operational detail.

## Done reviewing?

`get_prisma_counts()` gives identified / screened / excluded-by-reason / included for the
flow diagram. The next phase is [synthesis](../synthesis/SKILL.md).
