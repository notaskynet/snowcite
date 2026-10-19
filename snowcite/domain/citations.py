"""Numeric `[N]` citation refs as they appear in stored section text."""

import re


# Matches `[N]`, `[N, M]`, `[N; M]`.
CITE_REF_RE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")


def count_cites(content: str) -> int:
    """Count citation refs in a section body. `[1, 2]` counts as two cites."""
    return sum(len(re.split(r"[,;]", m.group(1))) for m in CITE_REF_RE.finditer(content))


# Splits on `.`/`?`/`!` followed by whitespace. Good enough for a rough "which
# sentence has no cite" signal; not a linguistic tokenizer (abbreviations like
# "etc." split wrongly).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Short sentences (connectives, transitions) rarely need a citation.
GAP_CHECK_MIN_WORDS = 8


def uncited_sentences(
    content: str, min_words: int = GAP_CHECK_MIN_WORDS
) -> list[dict[str, int | str]]:
    """Substantive sentences (>= `min_words` words) that carry no `[N]` cite."""
    out: list[dict[str, int | str]] = []
    for sentence in _SENTENCE_SPLIT_RE.split(content):
        stripped = sentence.strip()
        words = len(stripped.split())
        if words >= min_words and not CITE_REF_RE.search(stripped):
            out.append({"sentence": stripped, "word_count": words})
    return out


def rewrite_cite_ids(text: str, mapping: dict[int, int]) -> tuple[str, int]:
    """Remap `[N]` ids in `text` through `mapping`; returns (new_text, refs_replaced)."""
    replaced = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal replaced
        # Preserve original separators so `[1, 2; 3]` keeps its shape.
        out: list[str] = []
        for part in re.split(r"([,;]\s*)", match.group(1)):
            new = mapping.get(int(part)) if part.isdigit() else None
            if new is None:
                out.append(part)
            else:
                out.append(str(new))
                replaced += 1
        return "[" + "".join(out) + "]"

    return CITE_REF_RE.sub(_replace, text), replaced
