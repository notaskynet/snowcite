---
name: search
description: Collect papers for a literature review with snowcite - search arXiv, Semantic Scholar, OpenAlex, Crossref and PubMed, snowball through references and citations, import BibTeX or RIS exports. Use when next_step reports phase `search`, or when the user asks to find papers, extend the corpus, or import their reference list.
---

# Collecting papers

All of it saves to the database as `unreviewed`; DOI is the primary key, a normalised title
(>= 0.9 similarity) the fallback, so repeated searches don't duplicate.

## Search

`search_papers(query, limit=20, year_from, year_to)`

- Sources default from the project's discipline: STEM adds arXiv, medicine adds PubMed,
  everyone gets Semantic Scholar, OpenAlex and Crossref. Pass `sources=[...]` to override.
- The response is a summary (`saved`, `duplicates`, `new_ids`, `titles`) — abstracts never
  reach the chat. Use `auto_save=False` only to preview; then trim with `abstract_max_chars`.
- One query per distinct idea from the criteria. Short topical phrases beat long sentences.
  Vary phrasing (synonyms, the field's own jargon) across queries rather than raising `limit`.
- A failing source shows up in `failed_sources`; the rest still ran. Retry later or move on.

## Snowball

`snowball(paper_ids, direction="references" | "citations", limit=20)`

Use it on **approved** papers (`papers(status="approved")`), after the first review pass.
`references` finds what they build on, `citations` finds what built on them. New papers land
in `unreviewed` and mark the summary stale, so the next `next_step` asks for a fresh summary
before the next batch. Do not run it automatically — confirm with the user how deep to go.
arXiv and OpenAlex papers are resolved through their DOI; papers without one come back in
`errors`.

## Import

`import_refs(file_path)` takes a `.bib` or `.ris` export (Mendeley, EndNote, Zotero-via-BibTeX).
By default it fetches missing abstracts by DOI; pass `enrich_abstracts=False` to stay offline.
`without_abstract` in the result tells how many papers will be thin during review.

## Limits

Semantic Scholar allows about 100 requests per 5 minutes without a key; an API key (plugin
setting) lifts that. arXiv is throttled to one request per 3 seconds. Rate-limit retries are
automatic — if a call is slow, it is waiting, not stuck. `check_environment()` diagnoses
connectivity and missing keys.
