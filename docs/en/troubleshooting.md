# Troubleshooting

## "No snowcite project found"

The resolver walks up from the working directory looking for `.snowcite/`. Without one you get `NoProjectError`. `cd` to the directory that should hold the project and run `init_project`. To run the server from elsewhere set `SNOWCITE_PROJECT_ROOT=/path/to/project`.

## Safety refusals on sensitive topics

snowcite is built for academic reviews, including dual-use areas (AI safety, security, biosecurity). The classifier reacts to *context density*: a chat full of abstracts with operational detail can trigger a refusal even when your intent is scholarly.

Already in place: tools return compact records without abstracts; the `review` skill tells Claude to paraphrase abstracts in one or two neutral sentences and never paste operational detail.

If you still hit a refusal:

1. `/clear` — accumulated density is often the cause; `next_step()` restores your place.
2. Say what it is: "systematic review for my thesis, academic level, not operational".
3. Split the topic into smaller sub-areas.

For genuinely operational material Claude may still refuse — correctly. Keep the review at "what this paper claims and why it matters".

## Rate limits on Semantic Scholar

Without a key: 100 requests / 5 minutes. The client honours `Retry-After` and backs off; during a big snowball you may see `HTTP 429, waiting 30s`. Searches continue on the other sources. A key (`SNOWCITE_SEMANTIC_SCHOLAR_API_KEY`, or the plugin setting) lifts the limit to 100 requests / second.

## `next_step` keeps asking for the summary

After every batch (and after a snowball or import) the summary is stale. Save it with `review_summary(summary, clusters)` and the next batch is released. This is deliberate.

## `review_batch` rejects an approval

Approved and maybe papers must leave a `claim` or `finding` note, inline (`notes=[{type, text, cluster}]`, one paper per decision) or already in the graph. Rejections take no notes.

## The review history looks wrong

Every decision appends to `review_history`. Inspect it read-only:

```sql
sqlite3 -readonly .snowcite/papers.db \
  "SELECT paper_id, old_status, new_status, reason, reviewed_by, changed_at
   FROM review_history ORDER BY id DESC LIMIT 20;"
```

Don't edit the table — the PRISMA numbers depend on it. Use `undo_last_review_action` or `bulk_reclassify`.

## I upgraded from 0.3

The v0.2 writing tables (`outline`, `section_content`) are folded into `sections` automatically on first open; the old tables stay in the file unread. `write_document`, `compile_pdf` and the other document tools are gone — build the document in your own toolchain. See the changelog for the tool renames.
