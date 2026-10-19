from typing import Any

from snowcite.domain.phases import Step, WorkflowState, decide
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

    async def next_step(self) -> dict[str, Any]:
        root = find_project_root()
        if root is None:
            step = decide(WorkflowState())
            return _result(step, {}, {"project_active": False})

        step = decide(await self._read_state())
        payload = await self._payload(step)

        progress = await self._review.progress()
        context = {
            "project_active": True,
            "counts": progress["counts"],
            "targets": progress["targets"],
            "warnings": progress["warnings"],
            "last_actions": await self._reviews.recent_history(5),
        }
        return _result(step, payload, context)

    # ─── State ──────────────────────────────────────────────────────────

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

    # ─── Payloads ───────────────────────────────────────────────────────

    async def _payload(self, step: Step) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        match step.phase:
            case "search":
                criteria = await self._reviews.latest_criteria()
                payload = {"criteria": criteria["criteria_text"] if criteria else None}
            case "review":
                payload = await self._review_payload(step)
            case "low_confidence":
                payload = {
                    "papers": await self._review.list_papers(
                        None, None, None, None, None, None, "auto_low", False, _BATCH_SIZE, 0
                    )
                }
            case "synthesis":
                payload = {"note_density": await self._notes.density()}
            case "done":
                payload = await self._section_service.outline_inputs()
                payload["gaps"] = await self._synthesis.find_gaps(None)
                meta = await self._project.load_metadata()
                keys = ("language", "standard", "discipline", "target_pages", "target_words")
                payload["project"] = {k: meta[k] for k in keys if k in meta}
        return payload

    async def _review_payload(self, step: Step) -> dict[str, Any]:
        criteria = await self._reviews.latest_criteria()
        summary = await self._reviews.load_summary()
        payload: dict[str, Any] = {
            "criteria": criteria["criteria_text"] if criteria else None,
            "summary": (
                {
                    "text": summary["summary"],
                    "topics": [c.get("topic") for c in summary["clusters"]],
                    "stale": summary["stale"],
                }
                if summary
                else None
            ),
        }
        if not step.needs_summary:
            payload["batch"] = await self._review.list_papers(
                "unreviewed", None, None, None, None, None, None, False, _BATCH_SIZE, 0
            )
        return payload


def _result(step: Step, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": step.phase,
        "why": step.why,
        "do": step.do,
        "payload": payload,
        **context,
    }
