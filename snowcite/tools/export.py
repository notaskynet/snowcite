"""Export the approved bibliography as BibTeX or RIS."""

from pathlib import Path
from typing import Any, Literal

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.bibliography import build_bibtex_document, build_cite_key_map
from snowcite.domain.models import ApprovedPaper
from snowcite.storage.projects import require_project_root


def _default_output_path(name: str) -> Path:
    return require_project_root() / name


# Minimal RIS entries — TY + TI + AU + PY + JO + DO + AB + ER. Most reference
# managers (Mendeley, EndNote, Zotero) accept this subset for import.


def _ris_entry(paper: ApprovedPaper) -> str:
    lines = [f"TY  - {'GEN' if paper['source'] == 'arxiv' else 'JOUR'}"]
    lines.append(f"TI  - {paper['title']}")
    for a in paper["authors"]:
        lines.append(f"AU  - {a}")
    if paper["year"]:
        lines.append(f"PY  - {paper['year']}")
    if paper["venue"]:
        lines.append(f"JO  - {paper['venue']}")
    if paper["doi"]:
        lines.append(f"DO  - {paper['doi']}")
    if paper["abstract"]:
        lines.append(f"AB  - {paper['abstract']}")
    lines.append("ER  - ")
    return "\n".join(lines)


@mcp.tool()
async def export_bibliography(
    format: Literal["bibtex", "ris"] = "bibtex",  # noqa: A002 — natural parameter name
    output_path: str | None = None,
) -> dict[str, Any]:
    """Write the approved set as `references.bib` (BibTeX) or `references.ris` (RIS).

    BibTeX reuses a paper's own bibtex when present. `keys` maps snowcite paper ids
    (the `[N]` in drafts) to the BibTeX cite keys. RIS is for Mendeley / EndNote /
    Zotero import. Default location is the project root.
    """
    papers = await container.papers.load_approved()
    if format == "bibtex":
        body = build_bibtex_document(list(papers)) + "\n"
        default_name = "references.bib"
    else:
        body = "\n\n".join(_ris_entry(p) for p in papers) + "\n"
        default_name = "references.ris"
    path = Path(output_path) if output_path else _default_output_path(default_name)
    path.write_text(body, encoding="utf-8")
    return {
        "path": str(path),
        "format": format,
        # snowcite ids -> BibTeX keys, so `[N]` citations in drafts can be rewritten
        # to \cite{key} / @key in whatever format the document is written in.
        "keys": {str(pid): key for pid, key in build_cite_key_map(list(papers)).items()},
        "entries": len(papers),
    }
