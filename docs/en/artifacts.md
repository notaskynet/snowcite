# Research artifacts

Beyond scholarly papers, snowcite can ingest your own research material — interview transcripts, code, archival documents, notes, dataset descriptions — and cite it next to the literature.

## Types

| Type | What it is | Typical use |
|---|---|---|
| `interview` | Transcript of a conversation | Quotes in findings and discussion |
| `code` | Source file or snippet | Methodology |
| `document` | Archival text, letter, internal document | Cited like a primary source |
| `note` | Free-form research note | Background, discussion |
| `dataset` | Description of a dataset (not the data) | Methodology, data availability |

Only UTF-8 text is supported. Convert PDF and `.docx` first (`pdftotext`, pandoc).

## Tools

- `add_artifact(type, label, path=... | content=..., summary, metadata)` — from a file, or from text typed in chat. Returns the id and the `citation_label`.
- `get_artifacts()` — briefs without bodies; `get_artifacts(id)` — the full text, for quoting. Filters: `type`, `included_only`.
- `update_artifact(id, included=False)` — exclude without losing it; `delete=True` removes it for good.

Limit: about 200,000 characters per artifact. Split larger material.

## Citing

Inline labels are short: `[I:3]` interview 3, `[C:auth.py]` code (filename-like labels are used verbatim), `[D:5]` document, `[N:2]` note, `[DS:1]` dataset. Keep them consistent across the document. The critique inputs of a section list every included artifact as a brief, so the reviewer can check quotes against `get_artifacts(id)` character by character.

## What it does not do

No transcription from audio, no PDF or docx parsing, no data analysis, no document building. A quote attributed to a participant must appear verbatim in the artifact — the critic flags anything else as fabrication.
