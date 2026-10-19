"""Document backends: how a section list becomes source, a bibliography and a PDF."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from snowcite.domain.models import ApprovedPaper, DocumentSection
from snowcite.domain.types import Backend
from snowcite.render.bibliography import (
    build_bibtex_document,
    build_cite_key_map,
    generate_hayagriva,
    rewrite_cite_refs,
)
from snowcite.render.templates import render_template


class DocumentBackend(ABC):
    name: Backend
    extension: str
    bib_filename: str

    @abstractmethod
    def render_sections(self, sections: list[DocumentSection]) -> str:
        """Section bodies joined with this backend's heading syntax."""

    @abstractmethod
    def template_variables(
        self, title: str, author: str, body: str, standard: str, language: str
    ) -> dict[str, Any]:
        """Variables the `{backend}/{standard}` template expects."""

    @abstractmethod
    def build_bibliography(self, papers: list[ApprovedPaper]) -> str: ...

    @abstractmethod
    def compile_command(self, src: Path) -> list[str]: ...

    def render_document(
        self,
        title: str,
        author: str,
        sections: list[DocumentSection],
        papers: list[ApprovedPaper],
        standard: str,
        language: str,
    ) -> str:
        # Stored sections cite papers as `[N]` (the id Claude sees in tool output);
        # rewrite to this backend's cite syntax using the keys the bibliography publishes.
        id_to_key = build_cite_key_map(list(papers))
        rewritten: list[DocumentSection] = [
            {"title": s["title"], "content": rewrite_cite_refs(s["content"], id_to_key, self.name)}
            for s in sections
        ]
        variables = self.template_variables(
            title, author, self.render_sections(rewritten), standard, language
        )
        return render_template(self.name, standard, variables)


class LatexBackend(DocumentBackend):
    name = "latex"
    extension = ".tex"
    bib_filename = "references.bib"

    _BABEL: ClassVar[dict[str, str]] = {"ru": "russian,english", "en": "english"}

    def render_sections(self, sections: list[DocumentSection]) -> str:
        return "\n\n".join(f"\\section{{{s['title']}}}\n{s['content']}" for s in sections)

    def template_variables(
        self, title: str, author: str, body: str, standard: str, language: str
    ) -> dict[str, Any]:
        return {
            "title": title,
            "author": author,
            "sections": body,
            "babel_langs": self._BABEL.get(language, "english"),
            "bib_style": "numeric" if standard == "plain" else "gost-numeric",
        }

    def build_bibliography(self, papers: list[ApprovedPaper]) -> str:
        return build_bibtex_document(list(papers))

    def compile_command(self, src: Path) -> list[str]:
        return ["tectonic", str(src)]


class TypstBackend(DocumentBackend):
    name = "typst"
    extension = ".typ"
    bib_filename = "references.yml"

    _CSL: ClassVar[dict[str, str]] = {"plain": "ieee", "gost": "gost-r-705-2008-numeric"}

    def render_sections(self, sections: list[DocumentSection]) -> str:
        return "\n\n".join(f"= {s['title']}\n\n{s['content']}" for s in sections)

    def template_variables(
        self, title: str, author: str, body: str, standard: str, language: str
    ) -> dict[str, Any]:
        return {
            "title": title,
            "author": author,
            "sections": body,
            "lang": language,
            "csl_style": self._CSL.get(standard, "ieee"),
        }

    def build_bibliography(self, papers: list[ApprovedPaper]) -> str:
        return generate_hayagriva(list(papers))

    def compile_command(self, src: Path) -> list[str]:
        return ["typst", "compile", str(src)]


_BACKENDS: dict[str, DocumentBackend] = {b.name: b for b in (TypstBackend(), LatexBackend())}


def get_backend(name: str) -> DocumentBackend:
    return _BACKENDS[name]


def backend_for_extension(extension: str) -> DocumentBackend | None:
    return next((b for b in _BACKENDS.values() if b.extension == extension), None)
