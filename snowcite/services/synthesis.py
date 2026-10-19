from snowcite.domain import rules
from snowcite.domain.records import ErrorResult
from snowcite.domain.results import (
    ClusterNotes,
    CrossNote,
    GapFinding,
    GapsResult,
    NoteBrief,
    PaperNotes,
    SynthesisAdded,
)
from snowcite.domain.types import CROSS_PAPER_NOTE_TYPES
from snowcite.storage.repositories import NoteRepository, ReviewRepository


class SynthesisService:
    def __init__(self, notes: NoteRepository, reviews: ReviewRepository) -> None:
        self._notes = notes
        self._reviews = reviews

    async def cluster_notes(self, cluster: str) -> ClusterNotes:
        """Per-paper notes grouped by paper + cross-paper notes with their sources."""
        rows, links = await self._notes.cluster_view(cluster)

        derived: dict[int, list[int]] = {}
        for link in links:
            if link["kind"] == "derived_from":
                derived.setdefault(link["from_note_id"], []).append(link["to_note_id"])

        by_paper: dict[int, PaperNotes] = {}
        cross: list[CrossNote] = []
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["type"]] = counts.get(r["type"], 0) + 1
            brief: NoteBrief = {"id": r["id"], "type": r["type"], "text": r["text"]}
            if r["paper_id"] is None:
                cross.append({**brief, "derived_from": derived.get(r["id"], [])})
            else:
                bucket = by_paper.setdefault(
                    r["paper_id"],
                    {
                        "paper_id": r["paper_id"],
                        "title": r["title"],
                        "year": r["year"],
                        "notes": [],
                    },
                )
                bucket["notes"].append(brief)

        return {
            "cluster": cluster,
            "papers": list(by_paper.values()),
            "cross_paper": cross,
            "counts": counts,
        }

    async def add_synthesis(
        self, cluster: str, note_type: str, text: str, derived_from_note_ids: list[int]
    ) -> SynthesisAdded | ErrorResult:
        sources = await self._notes.paper_ids_of(derived_from_note_ids)
        error = rules.validate_synthesis(note_type, text, derived_from_note_ids, sources)
        if error:
            return {"error": error}
        new_id = await self._notes.add_synthesis(
            cluster, note_type, text.strip(), derived_from_note_ids
        )
        return {"id": new_id, "links": len(derived_from_note_ids)}

    async def find_gaps(self, cluster: str | None) -> GapsResult:
        by_cluster, anchored = await self._notes.ids_by_cluster_and_type(cluster)

        findings: list[GapFinding] = []
        for name, types in sorted(by_cluster.items()):
            flags, per_paper_n, unanchored = rules.cluster_gap_flags(types, anchored)
            if flags:
                findings.append(
                    {
                        "cluster": name,
                        "flags": flags,
                        "per_paper_notes": per_paper_n,
                        "cross_paper_notes": sum(
                            len(ids) for t, ids in types.items() if t in CROSS_PAPER_NOTE_TYPES
                        ),
                        "unanchored_contradiction_ids": unanchored,
                    }
                )

        unknown: list[str] = []
        if cluster is None and by_cluster:
            topics = await self._reviews.summary_topics()
            if topics is not None:
                unknown = sorted(set(by_cluster) - topics)

        return {
            "findings": findings,
            "unknown_clusters_in_summary": unknown,
            "total_clusters_with_notes": len(by_cluster),
        }
