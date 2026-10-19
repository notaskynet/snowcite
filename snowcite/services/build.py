"""Build the document: render source + bibliography, compile, estimate length."""

import tempfile
from pathlib import Path
from typing import Any

from snowcite.domain.models import DocumentSection
from snowcite.domain.types import Backend
from snowcite.render.backends import backend_for_extension, get_backend
from snowcite.render.compiler import Compiler
from snowcite.storage.projects import require_project_root
from snowcite.storage.repositories import PaperRepository, ProjectRepository, SectionRepository


class BuildService:
    def __init__(
        self,
        papers: PaperRepository,
        sections: SectionRepository,
        project: ProjectRepository,
        compiler: Compiler | None = None,
    ) -> None:
        self._papers = papers
        self._sections = sections
        self._project = project
        self._compiler = compiler or Compiler()

    async def write_document(
        self,
        title: str,
        author: str,
        sections: list[DocumentSection] | None,
        backend: Backend,
        standard: str,
        language: str,
        output_dir: str | None,
    ) -> dict[str, str]:
        """Write `review.{tex,typ}` and its bibliography; sections default to the stored ones."""
        out = Path(output_dir) if output_dir else require_project_root()
        out.mkdir(parents=True, exist_ok=True)
        papers = await self._papers.load_approved()
        if sections is None:
            sections = await self._sections.load_document_sections()

        doc = get_backend(backend)
        doc_path = out / f"review{doc.extension}"
        bib_path = out / doc.bib_filename
        bib_path.write_text(doc.build_bibliography(papers), encoding="utf-8")
        doc_path.write_text(
            doc.render_document(title, author, sections, papers, standard, language),
            encoding="utf-8",
        )
        return {
            "doc_path": str(doc_path),
            "bib_path": str(bib_path),
            "backend": backend,
            "standard": standard,
        }

    async def compile_pdf(self, doc_path: str) -> dict[str, Any]:
        src = Path(doc_path).resolve()
        if not src.exists():
            return {"pdf_path": "", "success": False, "log": f"file not found: {doc_path}"}
        doc = backend_for_extension(src.suffix)
        if doc is None:
            return {
                "pdf_path": "",
                "success": False,
                "log": f"unknown source extension {src.suffix!r} (expected .tex or .typ)",
            }
        result = await self._compiler.compile(doc, src)
        pdf = src.with_suffix(".pdf")
        return {
            "pdf_path": str(pdf) if pdf.exists() else "",
            "success": result.success,
            "log": result.log,
            "backend": doc.name,
        }

    async def estimate_pages(
        self, backend: Backend | None, standard: str | None, language: str | None
    ) -> dict[str, Any]:
        """Render to a temp dir and count real PDF pages; never touches the project's files."""
        defaults = await self._project.defaults()
        resolved_backend: Backend = backend or defaults.get("backend") or "typst"
        resolved_standard = standard or defaults.get("standard") or "plain"
        resolved_language = language or defaults.get("language") or "en"

        sections = await self._sections.load_document_sections()
        if not sections:
            return {
                "pages": None,
                "words": 0,
                "sections_rendered": 0,
                "compile_success": False,
                "log": "no sections found — nothing to estimate",
            }
        total_words = sum(len(s["content"].split()) for s in sections)

        with tempfile.TemporaryDirectory(prefix="snowcite-estimate-") as tmp:
            wrote = await self.write_document(
                # The title doesn't affect the page count, so a draft preview needs no real one.
                "Draft preview",
                defaults.get("author") or "Author",
                sections,
                resolved_backend,
                resolved_standard,
                resolved_language,
                tmp,
            )
            compiled = await self.compile_pdf(wrote["doc_path"])
            if not compiled["success"]:
                return {
                    "pages": None,
                    "words": total_words,
                    "sections_rendered": len(sections),
                    "backend": resolved_backend,
                    "standard": resolved_standard,
                    "compile_success": False,
                    "log": compiled["log"][:4000],
                }
            pages = Compiler.page_count(Path(compiled["pdf_path"]).read_bytes())

        target_pages = defaults.get("target_pages")
        return {
            "pages": pages,
            "words": total_words,
            "words_per_page": round(total_words / pages, 1) if pages else None,
            "sections_rendered": len(sections),
            "backend": resolved_backend,
            "standard": resolved_standard,
            "target_pages": target_pages,
            "target_delta": (pages - target_pages) if (target_pages and pages) else None,
            "compile_success": True,
        }

    async def set_backend(
        self, new_backend: Backend, confirm_wipe_sections: bool
    ) -> dict[str, Any]:
        current = (await self._project.defaults()).get("backend")
        if current == new_backend:
            return {"changed": False, "backend": new_backend, "reason": "already set"}

        section_count = await self._sections.count_drafts()
        if section_count > 0 and not confirm_wipe_sections:
            return {
                "changed": False,
                "needs_wipe": section_count,
                "current_backend": current,
                "proposed_backend": new_backend,
                "message": (
                    f"{section_count} expanded section(s) exist in {current!r} "
                    f"syntax; switching to {new_backend!r} will make them "
                    f"uncompilable. Call again with confirm_wipe_sections=True "
                    f"to clear section drafts (outline + skeleton survive)."
                ),
            }
        await self._project.switch_backend(new_backend, wipe_sections=section_count > 0)
        return {
            "changed": True,
            "backend": new_backend,
            "previous": current,
            "sections_wiped": section_count,
        }
