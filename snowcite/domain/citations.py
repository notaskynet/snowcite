"""Numeric `[N]` citation refs as they appear in stored section text."""

import re


# Matches `[N]`, `[N, M]`, `[N; M]`.
CITE_REF_RE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")


def count_cites(content: str) -> int:
    """Count citation refs in a section body. `[1, 2]` counts as two cites."""
    return sum(len(re.split(r"[,;]", m.group(1))) for m in CITE_REF_RE.finditer(content))
