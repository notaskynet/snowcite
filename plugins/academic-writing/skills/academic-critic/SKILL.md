---
name: academic-critic
description: Critique a section of academic text as a strict reviewer - find unsupported claims, citation misuse, overclaiming, fabricated quotes and logical gaps, and report them as severity-tagged, actionable issues without rewriting. Use when a draft section needs review, before marking it done, or when the user asks for a critical read, a referee report or a check of claims against sources.
---

# Strict academic critique

Switch voice: you are a referee or thesis committee member seeing the text cold. You do
**not** rewrite; you produce a list of issues the author can act on.

## What to check

Compare every factual statement against the material you were given (notes, abstracts,
artifact text). Look for:

- **Unsupported claims** — a factual statement with no citation, or a citation to a paper
  that doesn't support it. Read the abstract or note before flagging.
- **Overclaiming** — "proves", "demonstrates conclusively", "solves" where the source only
  suggests or indicates.
- **Citation misuse** — cited for X, but the source says Y; wrong paper id; a citation to a
  paper that isn't approved or isn't on scope.
- **Quote fidelity** — a direct quotation that does not appear verbatim in the cited source
  or artifact. Treat a fabricated quote as a blocker.
- **Contradictions** — the section asserts something a cited paper (or another note)
  contradicts, or two sentences contradict each other.
- **Logical gaps** — a conclusion that doesn't follow, a missing step, an unexplained jump
  between paragraphs.
- **Coverage** — the scope names clusters, notes or questions the draft never touches; or the
  draft leans on one paper where the notes show several.
- **Duplication** — repeats a point made in a neighbouring section.

Do not list aesthetic preferences as blockers. Language and naturalness are a separate pass.

## Severity

| Severity | Use it for |
|---|---|
| `blocker` | The section must not ship: unsupported or false claim, factual error, fabricated quote, contradiction with a cited paper. |
| `should_fix` | Weakens the section but doesn't falsify it: overclaiming, thin evidence, missing counter-view, logical gap. |
| `nit` | Wording, ordering, minor style. |

Be sparing with `blocker`. If everything is a blocker, nothing is.

## Issue format

Each issue is actionable and anchored:

```
{severity, type, text, suggested_action}
```

- `type`: unsupported_claim | overclaim | citation_misuse | fabricated_quote | contradiction |
  logical_gap | coverage | duplication | style
- `text`: quote or point at the sentence, then say what is wrong, in one or two sentences.
- `suggested_action`: a concrete fix — cite note N, resolve the contradiction with paper M,
  soften "proves" to "suggests", drop the sentence.

With snowcite, submit the list through `record_section_critique(section_id, issues)`; it
returns `should_stop` (no blockers, or the second iteration). Show the issues to the user,
ordered blockers first. Stop criterion: blockers = 0 or iteration >= 2 — then surface what
remains instead of looping.

## Discipline

- Cite your evidence: name the note id or paper the claim fails against.
- If you can't verify a claim because the material wasn't provided, say "unverifiable with
  the given material" — don't guess it is wrong or right.
- One pass, one list. Don't trickle issues over several messages.
