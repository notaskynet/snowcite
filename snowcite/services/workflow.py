from snowcite.domain.phases import Step, WorkflowState, decide
from snowcite.domain.records import ProjectBrief
from snowcite.domain.results import (
    DonePayload,
    EmptyPayload,
    LowConfidencePayload,
    NextStepResult,
    ReviewPayload,
    SearchPayload,
    StepPayload,
    SummaryBrief,
    SynthesisPayload,
)
from snowcite.services.review import ReviewService
from snowcite.services.sections import SectionService
from snowcite.services.synthesis import SynthesisService
from snowcite.storage.projects import find_project_root
from snowcite.storage.repositories import (
    NoteRepository,
    ProjectRepository,
    ReviewRepository,
)


_BATCH_SIZE = 20


class WorkflowService:
    def __init__(
        self,
        reviews: ReviewRepository,
        notes: NoteRepository,
        project: ProjectRepository,
        review_service: ReviewService,
        section_service: SectionService,
        synthesis: SynthesisService,
    ) -> None:
        self._reviews = reviews
        self._notes = notes
        self._project = project
        self._review = review_service
        self._section_service = section_service
        self._synthesis = synthesis

    async def next_step(self) -> NextStepResult:
        if find_project_root() is None:
            step = decide(WorkflowState())
            return {
                "phase": step.phase,
                "why": step.why,
                "do": step.do,
                "payload": EmptyPayload(),
                "project_active": False,
            }

        step = decide(await self._read_state())
        progress = await self._review.progress()
        return {
            "phase": step.phase,
            "why": step.why,
            "do": step.do,
            "payload": await self._payload(step),
            "project_active": True,
            "counts": progress["counts"],
            "targets": progress["targets"],
            "warnings": progress["warnings"],
            "last_actions": await self._reviews.recent_history(5),
        }

    async def _read_state(self) -> WorkflowState:
        counts = await self._reviews.live_counts()
        summary = await self._reviews.load_summary()
        per_paper, cross_paper = await self._notes.scope_counts()
        return WorkflowState(
            project_active=True,
            has_criteria=await self._reviews.latest_criteria() is not None,
            papers_total=counts["total"],
            unreviewed=counts["unreviewed"],
            approved=counts["approved"],
            auto_low=await self._reviews.count_auto_low(),
            summary_current=bool(summary and not summary["stale"]),
            per_paper_notes=per_paper,
            cross_paper_notes=cross_paper,
        )

    async def _payload(self, step: Step) -> StepPayload:
        match step.phase:
            case "search":
                return await self._search_payload()
            case "review":
                return await self._review_payload(step)
            case "low_confidence":
                return LowConfidencePayload(
                    papers=await self._review.batch(None, "auto_low", _BATCH_SIZE)
                )
            case "synthesis":
                return SynthesisPayload(note_density=await self._notes.density())
            case "done":
                return await self._done_payload()
            case _:
                return EmptyPayload()

    async def _search_payload(self) -> SearchPayload:
        criteria = await self._reviews.latest_criteria()
        return {"criteria": criteria["criteria_text"] if criteria else None}

    async def _review_payload(self, step: Step) -> ReviewPayload:
        criteria = await self._reviews.latest_criteria()
        summary = await self._reviews.load_summary()
        brief: SummaryBrief | None = (
            {
                "text": summary["summary"],
                "topics": [c["topic"] for c in summary["clusters"]],
                "stale": summary["stale"],
            }
            if summary
            else None
        )
        payload: ReviewPayload = {
            "criteria": criteria["criteria_text"] if criteria else None,
            "summary": brief,
        }
        if not step.needs_summary:
            payload["batch"] = await self._review.batch("unreviewed", None, _BATCH_SIZE)
        return payload

    async def _done_payload(self) -> DonePayload:
        outline = await self._section_service.outline_inputs()
        metadata = await self._project.load_metadata()
        project: ProjectBrief = {}
        if "language" in metadata:
            project["language"] = metadata["language"]
        if "standard" in metadata:
            project["standard"] = metadata["standard"]
        if "discipline" in metadata:
            project["discipline"] = metadata["discipline"]
        if "target_pages" in metadata:
            project["target_pages"] = metadata["target_pages"]
        if "target_words" in metadata:
            project["target_words"] = metadata["target_words"]
        return {**outline, "gaps": await self._synthesis.find_gaps(None), "project": project}
