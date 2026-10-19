---
name: academic-writing-ru
description: Write scientific prose in Russian that reads as native Russian, not as translation from English - short sentences, established terminology, careful claims and citations. Use when writing or editing a literature review, thesis chapter, article, abstract or any academic text in Russian, or when text sounds like machine translation.
---

# Scientific Russian

Write Russian natively; don't translate English word by word. The reader is a supervisor or a
committee: they need clarity and verifiability, not ornament. Examples below are Russian on
purpose; the instructions are in English.

## Sentences

- Short sentences: one thought each, rarely two subordinate clauses.
- Avoid chains of participial and adverbial participial phrases (причастные и деепричастные
  обороты). Three in a row means split the sentence.
- Don't mirror English syntax: stacks of genitive nouns ("оценка эффективности защиты от атак
  на модели"), passive where active is natural, "было показано, что…" instead of
  "авторы показали, что…".
- Prefer the active voice when there is a subject: "Авторы сравнивают три метода", not
  "Сравнение трёх методов проводится авторами".
- Cut filler openers unless something follows: "следует отметить, что", "стоит
  подчеркнуть", "в рамках данного исследования", "таким образом, можно сделать вывод".

## Terminology

- Keep established English terms as they are, in *italics* on first mention: *alignment*,
  *prompt injection*, *jailbreak*, *fine-tuning*, *red teaming*, *RLHF*, *embeddings*,
  *guardrails*, *effect size*, *confounder*. Don't calque them into awkward Russian
  ("выравнивание безопасности" for *safety alignment*).
- Never translate method or system names: GCG, SmoothLLM, PAIR, HarmBench, AutoDAN, LLaMA.
- One term, one spelling across the whole text. Once you decide on a term, apply it
  consistently to the end of the document.
- **If unsure about a term, ask the user** rather than choosing silently.

## Claims and citations

- Every factual claim rests on a source. No source: soften the wording or remove the claim.
- The verb matches the source's strength: "показывает", "подтверждает" for strong results;
  "указывает на", "предполагает" for weak ones. Not "доказывает" where the authors only
  observe a correlation.
- Never attribute to a paper what its abstract or your notes don't contain. Take a direct
  quotation verbatim, and only from a source you have in front of you.
- A review is not a paper-by-paper retelling. Group by ideas: what is known, where authors
  agree, where they disagree, what is missing. One thought and one takeaway per paragraph.

## Paragraph shape in a review

1. A one-sentence thesis for the paragraph.
2. Two to four sources that support or contest it, cited.
3. A conclusion or bridge: what it means for the question of the work.

## Before handing over

Read it back (mentally). If a phrase sounds like a translation, rewrite it from the meaning,
not from the original wording. A separate editing pass for machine-sounding style (for
example a humanizer skill) belongs after the content is stable, not before.
