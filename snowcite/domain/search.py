"""Search policy: which sources to query, how to merge their results. Pure."""

from typing import Any

from snowcite.domain.dedup import find_title_match, normalize_title
from snowcite.domain.models import Paper
from snowcite.domain.types import Source


# STEM disciplines get arXiv; everyone else gets universal sources only.
_STEM_DISCIPLINES = frozenset(
    {"cs", "computer_science", "physics", "math", "stats", "econ", "q-bio", "q-fin"}
)
_MEDICAL_DISCIPLINES = frozenset({"medicine", "biology", "psychiatry", "nursing", "pharmacy"})

# Universal sources run for every discipline.
_UNIVERSAL_SOURCES: list[Source] = ["semantic_scholar", "openalex", "crossref"]


def sources_for_discipline(discipline: str | None) -> list[Source]:
    """Pick a reasonable default set of sources based on the user's discipline."""
    base: list[Source] = list(_UNIVERSAL_SOURCES)
    if discipline is None:
        # Unknown — keep the pre-T7 default so existing behaviour holds.
        return ["arxiv", *base]
    d = discipline.lower()
    if d in _STEM_DISCIPLINES:
        base.insert(0, "arxiv")
    if d in _MEDICAL_DISCIPLINES:
        base.append("pubmed")
    return base


def truncate_abstract(abstract: str | None, max_chars: int) -> str | None:
    """Return abstract clipped to max_chars. max_chars=0 drops the field entirely."""
    if abstract is None or max_chars == 0:
        return None
    if len(abstract) <= max_chars:
        return abstract
    return abstract[: max_chars - 1].rstrip() + "…"


def compact_paper(p: Paper, abstract_max_chars: int) -> dict[str, Any]:
    """Paper → dict, respecting the abstract truncation policy."""
    data = p.model_dump()
    data["abstract"] = truncate_abstract(p.abstract, abstract_max_chars)
    return data


def _richness(p: Paper) -> int:
    """Score paper by populated key fields — used to pick the best of duplicates."""
    return sum(bool(x) for x in (p.doi, p.abstract, p.bibtex, p.venue, p.pdf_url))


def dedup_within_batch(papers: list[Paper]) -> list[Paper]:
    """Inter-source dedup: prefer the richer record on a DOI or title collision."""
    by_doi: dict[str, Paper] = {}
    no_doi: list[Paper] = []
    for p in papers:
        if p.doi:
            existing = by_doi.get(p.doi)
            if existing is None or _richness(p) > _richness(existing):
                by_doi[p.doi] = p
        else:
            no_doi.append(p)

    merged = list(by_doi.values())
    merged_norms = [normalize_title(p.title) for p in merged]
    for p in no_doi:
        norm = normalize_title(p.title)
        idx = find_title_match(norm, merged_norms)
        if idx is None:
            merged.append(p)
            merged_norms.append(norm)
        elif _richness(p) > _richness(merged[idx]):
            merged[idx] = p
            merged_norms[idx] = norm
    return merged
