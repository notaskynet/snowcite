from typing import Literal


# ─── Literal aliases ────────────────────────────────────────────────────────

Status = Literal["approved", "maybe", "rejected", "unreviewed"]
Source = Literal["arxiv", "semantic_scholar", "openalex", "crossref", "pubmed"]
Direction = Literal["references", "citations"]
# `auto_high` = Claude confident (direct criterion match); `auto_low` = extrapolation
# the user should sanity-check; `user` = user decided.
ReviewedBy = Literal["auto_high", "auto_low", "user"]
Confidence = Literal["high", "low"]
STATUSES: tuple[str, ...] = ("approved", "maybe", "rejected", "unreviewed")
REVIEWED_BY: tuple[str, ...] = ("auto_high", "auto_low", "user")
Severity = Literal["ok", "warn", "error"]
Phase = Literal[
    "not_started",
    "criteria",
    "search",
    "review",
    "low_confidence",
    "synthesis",
    "done",
]
ArtifactType = Literal["interview", "code", "document", "note", "dataset"]
SectionStatus = Literal["outline", "drafting", "critiqued", "done"]
# Knowledge-graph note types. Per-paper extraction during review yields the
# first four; cross-paper synthesis (Phase 2) yields the last four.
NoteType = Literal[
    "claim",
    "finding",
    "method",
    "limitation",
    "gap",
    "contradiction",
    "consensus",
    "open_question",
]
NoteLinkKind = Literal["supports", "contradicts", "extends", "derived_from"]
# Per-paper types must carry paper_id; cross-paper types must leave it NULL.
PER_PAPER_NOTE_TYPES: frozenset[str] = frozenset({"claim", "finding", "method", "limitation"})
CROSS_PAPER_NOTE_TYPES: frozenset[str] = frozenset(
    {"gap", "contradiction", "consensus", "open_question"}
)
