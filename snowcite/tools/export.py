"""Export the approved bibliography.

- `export_bibtex` — `.bib` from the current approved set
- `export_ris` — RIS flavored for Mendeley / EndNote import
"""

from pathlib import Path
from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.bibliography import build_bibtex_document
from snowcite.domain.models import ApprovedPaper
from snowcite.storage.projects import require_project_root


def _default_output_path(name: str) -> Path:
    return require_project_root() / name


# ─── BibTeX ─────────────────────────────────────────────────────────────────


@mcp.tool()
async def export_bibtex(output_path: str | None = None) -> dict[str, Any]:
    """Write a .bib file for the approved set. Reuses per-paper bibtex when present."""
    papers = await container.papers.load_approved()
    path = Path(output_path) if output_path else _default_output_path("references.bib")
    path.write_text(build_bibtex_document(list(papers)) + "\n", encoding="utf-8")
    return {"path": str(path), "entries": len(papers)}


# ─── RIS ────────────────────────────────────────────────────────────────────

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
async def export_ris(output_path: str | None = None) -> dict[str, Any]:
    """Write a RIS file for Mendeley / EndNote import."""
    papers = await container.papers.load_approved()
    body = "\n\n".join(_ris_entry(p) for p in papers) + "\n"
    path = Path(output_path) if output_path else _default_output_path("references.ris")
    path.write_text(body, encoding="utf-8")
    return {"path": str(path), "entries": len(papers)}
