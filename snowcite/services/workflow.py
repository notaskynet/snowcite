"""`next_step`: the single entry point that says where the project is and what to do.

Phase and gates come from `domain.phases.decide`; this service reads the
project, builds the phase payload (so the agent needs no extra reads), and adds
the numbers every caller wants (counts, targets, warnings, recent actions).
"""

from typing import Any

from snowcite.domain import rules
from snowcite.domain.phases import Step, WorkflowState, decide
from snowcite.services.review import ReviewService
from snowcite.services.sections import SectionService
from snowcite.services.synthesis import SynthesisService
from snowcite.storage.projects import find_project_root
from snowcite.storage.repositories import (
    NoteRepository,
    ProjectRepository,
    ReviewRepository,
    SectionRepository,
)


_BATCH_SIZE = 20
_PDF_NAME = "review.pdf"


class WorkflowService:
    def __init__(
        self,
        reviews: ReviewRepository,
        notes: NoteRepository,
        sections: SectionRepository,
        project: ProjectRepository,
        review_service: ReviewService,
        section_service: SectionService,
        synthesis: SynthesisService,
    ) -> None:
        self._reviews = reviews
        self._notes = notes
        self._sections = sections
        self._project = project
        self._review = review_service
        self._section_service = section_service
        self._synthesis = synthesis

    async def next_step(self) -> dict[str, Any]:
        root = find_project_root()
        if root is None:
            step = decide(WorkflowState())
            return _result(step, {}, {"project_active": False})

        state, next_section = await self._read_state(root)
        step = decide(state)
        payload: dict[str, Any] = {}
        if step.phase == "writing" and next_section is not None:
            step, payload = await self._writing(next_section)
        else:
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

    async def _read_state(self, root: Any) -> tuple[WorkflowState, dict[str, Any] | None]:
        counts = await self._reviews.live_counts()
        summary = await self._reviews.load_summary()
        per_paper, cross_paper = await self._notes.scope_counts()
        sections = await self._sections.progress_counts()
        next_section = await self._sections.next_unfinished()

        pdf = root / _PDF_NAME
        edited = await self._sections.last_edit_epoch()
        document_current = pdf.exists() and (edited is None or pdf.stat().st_mtime >= edited)

        state = WorkflowState(
            project_active=True,
            has_criteria=await self._reviews.latest_criteria() is not None,
            papers_total=counts["total"],
            unreviewed=counts["unreviewed"],
            approved=counts["approved"],
            auto_low=await self._reviews.count_auto_low(),
            summary_current=bool(summary and not summary["stale"]),
            per_paper_notes=per_paper,
            cross_paper_notes=cross_paper,
            sections_total=sections["total"],
            has_unfinished_section=next_section is not None,
            document_current=document_current,
        )
        return state, next_section

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
                payload = {"papers": await self._review.low_confidence(None, _BATCH_SIZE)}
            case "synthesis":
                payload = {"note_density": await self._notes.density()}
            case "outline":
                payload = await self._section_service.outline_inputs()
                payload["gaps"] = await self._synthesis.find_gaps(None)
            case "build":
                meta = await self._project.load_metadata()
                keys = ("author", "backend", "standard", "language", "target_pages")
                payload = {"metadata": {k: meta[k] for k in keys if k in meta}}
            case "done":
                payload = {"pdf": _PDF_NAME}
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
            payload["batch"] = await self._review.unreviewed(_BATCH_SIZE, None, None, None, False)
        return payload

    async def _writing(self, section: dict[str, Any]) -> tuple[Step, dict[str, Any]]:
        action = rules.next_section_action(section)
        inputs = await self._section_service.critique_inputs(section["id"])
        progress = await self._sections.progress_counts()
        payload = {"section": section, "action": action, "sections": progress}

        sid = section["id"]
        if action == "draft" and not inputs["notes"]:
            return (
                Step(
                    "writing",
                    f"Section {section['title']!r} has no notes for its clusters.",
                    [
                        "Do not draft without notes: review more papers into this scope, "
                        "or narrow it with update_section(scope=...) — ask the user",
                    ],
                ),
                payload,
            )
        do = {
            "draft": [
                f"get_section_critique_inputs({sid}) and draft only from its notes and papers",
                f"update_section({sid}, draft=..., status='drafting')",
            ],
            "critique": [
                f"get_section_critique_inputs({sid}); critique as a strict academic reviewer",
                f"record_section_critique({sid}, issues=[{{severity, type, text, suggested_action}}])",
            ],
            "revise": [
                "Address the blockers (cite missing notes, resolve contradictions, drop overclaims)",
                f"revise_section({sid}, new_draft=...)",
            ],
            "finish": [
                "No blockers remain or the iteration cap is reached: "
                "surface residual issues to the user",
                f"update_section({sid}, status='done')",
            ],
        }[action]
        why = f"Section {section['title']!r}: next action is {action}."
        return Step("writing", why, do), payload


def _result(step: Step, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": step.phase,
        "why": step.why,
        "do": step.do,
        "payload": payload,
        **context,
    }
