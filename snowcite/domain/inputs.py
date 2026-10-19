from typing import NotRequired, TypedDict, final


# Shapes the model sends to tools. Values are deliberately plain (`str`, not Literal):
# services validate them and report problems per item, instead of the whole call
# failing at the schema boundary.


class NoteInput(TypedDict):
    type: str
    text: str
    cluster: NotRequired[str | None]


@final
class NewNoteInput(NoteInput):
    paper_id: NotRequired[int | None]


@final
class ReviewDecision(TypedDict):
    status: str
    reason: str
    paper_id: NotRequired[int]
    paper_ids: NotRequired[list[int]]
    reviewed_by: NotRequired[str]
    note: NotRequired[str | None]
    notes: NotRequired[list[NoteInput]]


@final
class ClusterInput(TypedDict):
    topic: str
    paper_ids: NotRequired[list[int]]
    count: NotRequired[int]


@final
class ScopeInput(TypedDict):
    clusters: NotRequired[list[str]]
    keywords: NotRequired[list[str]]
    questions: NotRequired[list[str]]


@final
class SectionInput(TypedDict):
    title: str
    scope: NotRequired[ScopeInput | None]
    parent_id: NotRequired[int | None]
    position: NotRequired[int | None]


@final
class CritiqueIssue(TypedDict):
    severity: str
    type: NotRequired[str]
    text: NotRequired[str]
    suggested_action: NotRequired[str]
