"""Checks and bulk edits over `[N]` citations in section drafts."""

from typing import Any

from snowcite.domain.citations import GAP_CHECK_MIN_WORDS, rewrite_cite_ids, uncited_sentences
from snowcite.storage.repositories import SectionRepository


class CitationService:
    def __init__(self, sections: SectionRepository) -> None:
        self._sections = sections

    async def gap_check(
        self, min_words: int = GAP_CHECK_MIN_WORDS, sections: list[str] | None = None
    ):
        """Uncited substantive sentences per section; a prompt for the author, not a lint."""
        gaps: list[dict[str, Any]] = []
        total = 0
        for section in await self._sections.drafts():
            if sections is not None and section["title"] not in sections:
                continue
            found = uncited_sentences(section["draft"], min_words)
            if found:
                gaps.append({"section": section["title"], "count": len(found), "sentences": found})
                total += len(found)
        return {"total_gaps": total, "min_words": min_words, "gaps": gaps}

    async def rewrite(self, mapping: dict[str, int], sections: list[str] | None) -> dict[str, Any]:
        """Remap paper ids in every draft (after dedup/merge/deletion renumbering)."""
        if not mapping:
            return {"modified": [], "refs_replaced": 0, "sections_scanned": 0}
        try:
            int_mapping = {int(k): int(v) for k, v in mapping.items()}
        except (TypeError, ValueError) as e:
            return {"error": f"mapping must be {{int: int}} (strings OK): {e}"}

        scanned = [
            s for s in await self._sections.drafts() if sections is None or s["title"] in sections
        ]
        modified: list[dict[str, Any]] = []
        total = 0
        for section in scanned:
            new_text, replaced = rewrite_cite_ids(section["draft"], int_mapping)
            if replaced == 0:
                continue
            await self._sections.update(section["id"], {"draft": new_text})
            total += replaced
            modified.append({"name": section["title"], "refs_replaced": replaced})
        return {"modified": modified, "refs_replaced": total, "sections_scanned": len(scanned)}
