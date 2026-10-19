import re

from snowcite.domain.types import ArtifactRecord


# 200k characters is roughly a 1-hour interview transcript or a small source
# file. Big enough for most materials, small enough to refuse a runaway import.
MAX_ARTIFACT_CHARS = 200_000
# UTF-8 is at most 4 bytes per char; use that to short-circuit before reading a huge file.
MAX_ARTIFACT_BYTES = MAX_ARTIFACT_CHARS * 4

_FILENAME_LIKE_RE = re.compile(r"^[\w\-.]+$")
_PREFIXES = {"interview": "I", "code": "C", "document": "D", "note": "N", "dataset": "DS"}


def citation_label(artifact: ArtifactRecord) -> str:
    """Short inline citation.

    For code artifacts whose label is filename-like (`auth.py`, `utils-v2.ts`),
    the label is used verbatim — `[C:auth.py]` reads better in prose than
    `[C:7]`. For all other types, and for code with spaces / punctuation in
    the label, the numeric id is used: `[I:3]`, `[D:12]`.

    The primary-sources appendix expands either form back to the full record.
    """
    prefix = _PREFIXES[artifact["type"]]
    label = artifact.get("label")
    if artifact["type"] == "code" and label and _FILENAME_LIKE_RE.match(label):
        return f"[{prefix}:{label}]"
    return f"[{prefix}:{artifact['id']}]"
