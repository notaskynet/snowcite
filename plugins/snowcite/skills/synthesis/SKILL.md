---
name: synthesis
description: Name patterns across reviewed papers - gaps, contradictions, consensus and open questions - as traceable cross-paper notes. Use when next_step reports phase `synthesis`, after a review pass, or when the user asks what the literature agrees on, where it disagrees or what is missing.
---

# Cross-paper synthesis

Per-paper notes (claim, finding, method, limitation) describe single papers. Synthesis names
what only shows up **across** them. It is a separate pass: don't mix it into reviewing.

## Per cluster

1. `get_cluster_notes(cluster)` — per-paper notes grouped by paper, plus any cross-paper notes
   already recorded, in one call. Clusters are the topics of `review_summary()`.
2. Read across papers and look for:
   - **gap** — something the cluster collectively doesn't cover;
   - **contradiction** — two or more papers with incompatible conclusions on one question;
   - **consensus** — a non-trivial point most papers agree on;
   - **open_question** — raised but not answered.
3. Record each with `add_synthesis_note(cluster, type, text, derived_from_note_ids=[...])`.
   Sources are mandatory: every cross-paper note must point at the per-paper notes that
   justify it, and only per-paper notes qualify. A pattern you can't trace to notes is a guess —
   drop it or read the papers again.
4. `find_gaps()` afterwards flags thin clusters (< 3 per-paper notes), unaggregated
   limitations, contradictions without sources, and cluster names that don't exist in the
   summary (usually a typo — fix the offending notes with `update_note`).

Keep each note to one or two sentences. State the claim, not the evidence trail — the links
carry that.

## Edge cases

- Few notes in a cluster → say so; go back to reviewing or widen the search instead of padding.
- Notes with a wrong cluster: `update_note(note_id, cluster=...)`.
- `link_notes(from, to, kind)` adds extra typed edges (`supports`, `contradicts`, `extends`)
  when two notes relate without being a synthesis.

When at least one cross-paper note exists, `next_step()` moves on to `done`.
