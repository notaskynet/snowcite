"""Document generation + PDF compilation.

Handles both LaTeX (via tectonic) and Typst (via the typst binary). Backend,
standard, and author can come from `project_metadata` once the user has
onboarded; callers also pass them explicitly for flexibility.
"""

from typing import Any

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.types import Backend


@mcp.tool()
async def write_document(
    title: str,
    author: str,
    sections: list[dict[str, str]] | None = None,
    backend: Backend = "typst",
    standard: str = "plain",
    language: str = "ru",
    output_dir: str | None = None,
) -> dict[str, str]:
    """Render a review document (LaTeX or Typst) + bibliography from approved papers.

    `sections`: optional list of `{"title", "content"}` — content must already be
      valid syntax for the chosen backend. Omit it to build from the project's
      stored sections (v0.3 drafts, or v0.2 section_content as a fallback).

    `backend`: "typst" (default) or "latex".
    `standard`: template to use — "plain" / "gost" / ... (see render/templates/{backend}/).
    `language`: ISO code; LaTeX routes it to babel, Typst to `set text(lang:)`.
    `output_dir`: default is the project root so `.snowcite/` stays for DB only.
    """
    return await container.build.write_document(
        title, author, sections, backend, standard, language, output_dir
    )


@mcp.tool()
async def compile_pdf(doc_path: str) -> dict[str, Any]:
    """Compile a LaTeX or Typst source to PDF.

    Backend is inferred from the file extension: `.tex` → tectonic,
    `.typ` → typst. PDF lands next to the source.
    """
    return await container.build.compile_pdf(doc_path)


@mcp.tool()
async def estimate_pages(
    backend: Backend | None = None,
    standard: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Render the current sections to PDF in a temp dir and return the page count.

    Lets Claude answer "how long is this in pages?" with a real number instead
    of guessing from word counts. Sections come from the stored drafts in
    document order; backend/standard/language default to what's in
    `project_metadata` and can be overridden here.

    Returns `{pages, words, words_per_page, sections_rendered, backend,
    standard, target_pages, target_delta, compile_success, log}`. If the
    compile fails, `pages` is `None` and `log` has the stderr excerpt.

    Does NOT touch the project's `review.{typ,tex}` / `review.pdf` — output
    lands in a temp dir and is cleaned up on return.
    """
    return await container.build.estimate_pages(backend, standard, language)


@mcp.tool()
async def set_backend(
    new_backend: Backend,
    confirm_wipe_sections: bool = False,
) -> dict[str, Any]:
    """Switch the project's document backend (`typst` ↔ `latex`).

    Existing section text is written in the source backend's syntax and
    won't compile under the new one — this tool refuses to switch unless the
    user has explicitly opted into wiping expanded sections.

    Flow:
    1. Call with `confirm_wipe_sections=False` (default) to see what would be
       lost. Returns a `needs_wipe` count; nothing is modified.
    2. If the user agrees, call again with `confirm_wipe_sections=True` to
       clear section text (v0.2 `section_content` rows and v0.3 `sections.draft`)
       and update `project_metadata.backend`. `outline` and `skeleton` are
       preserved — you re-expand sections under the new backend.
    """
    return await container.build.set_backend(new_backend, confirm_wipe_sections)
