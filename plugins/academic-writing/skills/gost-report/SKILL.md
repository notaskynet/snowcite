---
name: gost-report
description: Plan and format a research report, coursework, thesis (VKR) or essay under the Russian standard GOST 7.32-2017 - structural elements, margins and font, headings and numbering, figures, tables, formulas, citations, reference list, appendices, and a pre-submission check. Use when the user is writing a work "per GOST", asks for a plan of the work, a formatting check, or preparation for the style check (normokontrol).
---

# Reports under GOST 7.32-2017

GOST 7.32-2017 is the standard for a **research report (otchet o NIR)**. Coursework and
theses usually follow the university's own guidelines (the "metodichka"), which build on it
and change some points. So find out whose rules apply first, then apply them.

This skill covers structure and formatting, not the file format: it works for Word, Typst,
LaTeX or anything else. Write the prose with the `academic-writing-ru` skill. Keep Russian
element names (РЕФЕРАТ, ВВЕДЕНИЕ, ...) exactly as the document needs them.

## 1. Ask first

1. Is there a university or department guideline? If so, ask for it (or for its differences
   from the GOST). **The guideline overrides the GOST** wherever they disagree.
2. What kind of work: research report, coursework, thesis, essay? It decides which
   structural elements are needed.
3. Reference numbering: by first mention in the text, or alphabetical?
4. Output format, and what will assemble the document.

Values below are GOST 7.32-2017 plus what universities most often require. Points where the
guideline usually decides are marked **(guideline)**.

## 2. Structure

The order is fixed. **Bold** elements are mandatory.

| # | Element | Contents |
|---|---|---|
| 1 | **Title page** | the university's or organisation's form, not free design |
| 2 | List of performers | collective work only |
| 3 | **Abstract (реферат)** | volume (pages, figures, tables, references, appendices); 5–15 keywords in the nominative case, uppercase, comma-separated on one line; text: object, aim, methods, results, conclusions |
| 4 | **Table of contents** | every structural element and section with page numbers, appendices included |
| 5 | Terms and definitions; list of abbreviations | if there are more than a few |
| 6 | **Introduction** | relevance, aim and tasks, object and subject, methods **(guideline:** defended statements, novelty, significance**)** |
| 7 | **Main body** | sections and subsections; in a literature review group by ideas, not by paper |
| 8 | **Conclusion** | findings per task, answers to the introduction's questions; no new data |
| 9 | **List of references** | see section 5 |
| 10 | Appendices | see section 6 |

Coursework and essays usually drop the list of performers and the terms list, and replace
the abstract with an annotation **(guideline)**.

## 3. Page and text

| Parameter | Value |
|---|---|
| Format | A4, single-sided |
| Margins | left 30 mm, right 10 mm, top and bottom 20 mm **(guideline:** right is often 15 mm**)** |
| Font | Times New Roman, black, regular; 14 pt **(guideline:** 12–14 allowed**)** |
| Line spacing | 1.5 |
| First-line indent | 1.25 cm |
| Alignment | justified, no hyphenation |
| Page numbers | Arabic, bottom centre, no full stop, continuous; the title page counts but shows no number |

Start every structural element (abstract, contents, introduction, conclusion, references,
each appendix) on a new page. Main-body sections too **(guideline)**.

## 4. Headings, figures, tables, formulas

**Headings.**
- Structural element names (РЕФЕРАТ, СОДЕРЖАНИЕ, ВВЕДЕНИЕ, ЗАКЛЮЧЕНИЕ, СПИСОК ИСПОЛЬЗОВАННЫХ
  ИСТОЧНИКОВ) are uppercase, centred, unnumbered, with no full stop.
- Sections and subsections use Arabic numerals, first-line indent, no full stop after the
  number or at the end: `1 Title`, `1.1 Title`, `1.1.1 Title`.
- No hyphenation in a heading, a blank line after it, never a heading alone at the foot of
  a page.

**Figures.** Caption below, centred: `Рисунок 1 – Title`. Numbering is continuous
**(guideline:** or per section, `Рисунок 1.1`**)**. In the text: "(рисунок 1)", and the
reference comes **before** the figure.

**Tables.** Title above, left-aligned, no indent: `Таблица 1 – Title`. A table that breaks
across pages gets "Продолжение таблицы 1" above the continuation and repeats its header. In
the text: "(таблица 1)".

**Formulas.** On their own line, centred, number in parentheses at the right margin: `(1)`.
Explain symbols right after, introduced by "где", in order of appearance.

**Lists.** One marker style throughout: a dash, or a lowercase letter with a parenthesis
`а)`; second level an Arabic digit with a parenthesis `1)`.

**Dashes.** In captions use a spaced en dash (–), not a hyphen: `Рисунок 1 – …`.

## 5. Citations and the reference list

- In-text citation in square brackets: `[1]`, `[1, с. 25]`, `[1–3]`.
- Order: by first mention **(guideline:** many universities require alphabetical**)**.
- Bibliographic description follows GOST R 7.0.100-2018; older guidelines still ask for
  GOST 7.1-2003. Minimum for an article: authors, title, journal, year, volume, issue,
  pages, DOI. Online sources: URL and access date.
- Every listed source is cited in the text and vice versa; numbers in the text match the list.
- With snowcite: `export_bibliography("bibtex")` returns the entries and a map
  `paper id → key`. Use the map to turn the drafts' `[N]` into numbers in the chosen order,
  and format the entries in the required style.

## 6. Appendices

Lettered with capital Russian letters starting with А, **skipping Ё, З, Й, О, Ч, Ь, Ы, Ъ**:
`ПРИЛОЖЕНИЕ А`, title below. Every appendix is referenced in the text. Figures, tables and
formulas inside an appendix carry its letter: `Рисунок А.1`, `Таблица Б.2`, `(В.1)`.

## 7. Working order

1. Settle the questions in section 1.
2. Draft the plan from the table in section 2 and agree it with the user **before** writing.
3. Write and critique sections (snowcite `sections` skill, `academic-critic`).
4. Format last, by sections 3–6, not while drafting.
5. Final pass with the checklist below.

## 8. Pre-submission checklist

- [ ] Margins, font, spacing and indent are identical throughout, tables and captions included.
- [ ] Structural elements start on new pages; headings have no full stops or hyphenation.
- [ ] Section numbering matches the contents, which lists appendices and page numbers.
- [ ] Every figure, table and appendix is referenced in the text, and the reference comes first.
- [ ] Captions follow the form: `Рисунок 1 – …` below, `Таблица 1 – …` above.
- [ ] References: complete descriptions, chosen order, numbers match the citations.
- [ ] Appendices use the permitted letters.
- [ ] Abstract counters (pages, figures, tables, references, appendices) are correct.
