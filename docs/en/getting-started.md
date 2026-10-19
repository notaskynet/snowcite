# Getting started

A first review from an empty directory.

## 1. Start a project

```
> I want a literature review on <topic>, thesis in Russian, GOST 7.32.
```

Claude calls `next_step()` → phase `not_started`, asks for the project profile (language, discipline, standard, optional author, institution, targets) and runs `init_project`. A `.snowcite/` folder appears next to your files; nothing else is generated.

## 2. Criteria

Phase `criteria`. Agree what to include, what to exclude and the **categories** the corpus will be organised into. They are stored with `review_criteria` and become the clusters of the summary.

## 3. Search

Phase `search`. Claude runs `search_papers` for each topic from the criteria; results are saved as `unreviewed` and only titles come back, never abstracts. You can also `import_refs` a `.bib` / `.ris` export.

## 4. Review

Phase `review`. Claude takes batches of 20 compact records from `next_step()`, decides each (approved / maybe / rejected, with a confidence grade) and submits them in one `review_batch` call. Approved and maybe papers carry `claim` / `finding` notes. Only genuinely borderline papers reach you, one at a time:

```
Paper 7/87: "Title" (2023, Authors)
Brief: ...
Why borderline: ...
include / exclude / maybe?
```

After each batch Claude rewrites the rolling summary (`review_summary`); the next batch is withheld until it does.

## 5. Confirm uncertain calls

Phase `low_confidence`. Every `auto_low` decision is walked through with you before synthesis.

## 6. Synthesis

Phase `synthesis`. Claude reads the notes cluster by cluster and records gaps, contradictions, consensus and open questions, each traced to its source notes.

## 7. Write

Phase `done`: the corpus is ready. Claude proposes an outline (`create_sections`), then per section drafts from notes, critiques and revises. With the `academic-writing` plugin it follows Russian scientific style and, for a report, the GOST 7.32 structure. The final document (Word, Typst, LaTeX, Markdown) is produced in whatever format you use; `export_bibliography` gives the `.bib` and the `[N]` → cite-key map.

## After `/clear` or in a new session

Call `next_step()` first. It carries the phase, counts and the data for it — you lose nothing.
