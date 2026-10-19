"""Run a backend's compiler and inspect the resulting PDF."""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from snowcite.logging import log
from snowcite.render.backends import DocumentBackend


# PDF page count — read the `/Type /Pages ... /Count N` dict directly rather than
# pull in pypdf. The root Pages node's Count is the page total; if several Pages
# nodes exist (rare for our templates) take the max. Works for typst and tectonic.
_PDF_PAGES_COUNT_RE = re.compile(rb"/Type\s*/Pages\b[^>]{0,200}?/Count\s+(\d+)", re.DOTALL)


@dataclass
class CompileResult:
    returncode: int
    log: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class Compiler:
    def __init__(self, timeout_seconds: int = 300, max_log_bytes: int = 65_536) -> None:
        self._timeout = timeout_seconds
        # Cap captured stderr so a misbehaving typst/tectonic pass can't flood memory.
        self._max_log_bytes = max_log_bytes

    async def compile(self, backend: DocumentBackend, src: Path) -> CompileResult:
        """Compile `src` next to itself. stdout is discarded — the PDF goes to disk."""
        cmd = backend.compile_command(src)
        log.info("compiling %s with %s", src, cmd[0])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(src.parent),
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError:
            proc.kill()
            return CompileResult(-1, f"compile timed out after {self._timeout}s")

        data = stderr or b""
        if len(data) > self._max_log_bytes:
            data = data[: self._max_log_bytes] + b"\n... (truncated)"
        return CompileResult(proc.returncode or 0, data.decode(errors="replace"))

    @staticmethod
    def page_count(pdf_bytes: bytes) -> int:
        counts = [int(m) for m in _PDF_PAGES_COUNT_RE.findall(pdf_bytes)]
        if counts:
            return max(counts)
        # Fallback: count `/Type /Page` entries for PDFs that elide the Pages /Count.
        return len(re.findall(rb"/Type\s*/Page(?![s/\w])", pdf_bytes))
