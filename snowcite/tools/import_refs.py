import re
from pathlib import Path

import httpx
from pydantic import ValidationError

from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.dedup import normalize_doi
from snowcite.domain.models import Paper
from snowcite.domain.records import ErrorResult
from snowcite.domain.results import ImportResult
from snowcite.logging import log
from snowcite.settings import settings
from snowcite.sources._http import http_get


_OPENALEX_BASE = "https://api.openalex.org"
_SS_BASE = "https://api.semanticscholar.org/graph/v1"


def _ss_headers() -> dict[str, str]:
    if settings.semantic_scholar_api_key:
        return {"x-api-key": settings.semantic_scholar_api_key}
    return {}


# ─── BibTeX parsing ─────────────────────────────────────────────────────────

# A BibTeX entry looks like `@type{key, field = {value}, ...}`. We split on
# `@` at the start of a line so entries can span multiple lines freely.
_ENTRY_SPLIT_RE = re.compile(r"(?m)^@")
_HEAD_RE = re.compile(r"^(?P<type>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s]+)\s*,", re.DOTALL)


def _strip_braces(value: str) -> str:
    """Remove matching {}/"" wrappers and leftover whitespace/newlines."""
    min_wrapped_len = 2  # one opening + one closing char
    v = value.strip().rstrip(",").strip()
    while len(v) >= min_wrapped_len and (
        (v[0] == "{" and v[-1] == "}") or (v[0] == '"' and v[-1] == '"')
    ):
        v = v[1:-1].strip()
    return re.sub(r"\s+", " ", v)


def _parse_bibtex_fields(body: str) -> dict[str, str]:  # noqa: PLR0912
    """Very small BibTeX field parser — balances braces, handles quoted values.

    Not a full grammar; skips `@string`/`@comment` pseudo-entries by virtue of
    being called only on `@article`/`@misc`/etc. bodies. The branch count here
    is inherent to the state machine (brace / quote / bareword / separator).
    """
    fields: dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        # Find next field name.
        m = re.match(r"\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[i:])
        if not m:
            break
        name = m.group(1).lower()
        i += m.end()
        # Parse value: either {...} with nesting, "..." or barewords.
        if i >= n:
            break
        if body[i] == "{":
            depth = 0
            start = i
            while i < n:
                if body[i] == "{":
                    depth += 1
                elif body[i] == "}":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            fields[name] = _strip_braces(body[start:i])
        elif body[i] == '"':
            start = i + 1
            i += 1
            while i < n and body[i] != '"':
                i += 1
            fields[name] = _strip_braces(body[start:i])
            if i < n:
                i += 1  # consume closing quote
        else:
            start = i
            while i < n and body[i] not in (",", "}"):
                i += 1
            fields[name] = _strip_braces(body[start:i])
        # Skip trailing comma.
        while i < n and body[i] in (",", " ", "\n", "\t"):
            i += 1
    return fields


def _authors_from_bibtex(raw: str) -> list[str]:
    """Split `A and B and C` into a list. Last-first form is preserved as-is."""
    if not raw:
        return []
    return [a.strip() for a in re.split(r"\s+and\s+", raw) if a.strip()]


def parse_bibtex(text: str) -> list[Paper]:
    """Parse a BibTeX file and return Paper objects with `source="crossref"`.

    Records without a DOI get a synthetic `source_id` from the cite key so they
    still persist; otherwise the DOI is authoritative.
    """
    papers: list[Paper] = []
    chunks = _ENTRY_SPLIT_RE.split(text)
    for chunk in chunks:
        if not chunk.strip():
            continue
        head = _HEAD_RE.match(chunk)
        if not head:
            continue
        entry_type = head.group("type").lower()
        if entry_type in ("string", "comment", "preamble"):
            continue
        cite_key = head.group("key")
        # Find the balanced closing brace for the entry body.
        body_start = head.end()
        depth = 1
        i = body_start
        while i < len(chunk) and depth > 0:
            if chunk[i] == "{":
                depth += 1
            elif chunk[i] == "}":
                depth -= 1
            i += 1
        body = chunk[body_start : i - 1]

        fields = _parse_bibtex_fields(body)
        doi = normalize_doi(fields.get("doi"))
        try:
            p = Paper(
                source="crossref",  # generic "not from a snowcite search" bucket
                source_id=doi or f"bibtex:{cite_key}",
                doi=doi,
                title=fields.get("title", "").strip(),
                authors=_authors_from_bibtex(fields.get("author", "")),
                year=int(fields["year"]) if fields.get("year", "").isdigit() else None,
                venue=fields.get("journal")
                or fields.get("booktitle")
                or fields.get("howpublished"),
                abstract=fields.get("abstract"),
                metadata={"import_source": "bibtex", "cite_key": cite_key, "type": entry_type},
            )
            papers.append(p)
        except (ValidationError, ValueError, KeyError) as e:
            log.warning("bibtex: skipping entry %r: %s", cite_key, e)
    return papers


# ─── RIS parsing ────────────────────────────────────────────────────────────

# RIS records are line-oriented: `XX  - value`. Records end with `ER  -` (no value).
_RIS_LINE_RE = re.compile(r"^([A-Z][A-Z0-9])  -\s*(.*)$")


def _first(record: dict[str, list[str]], *tags: str) -> str | None:
    """First value of the first tag that is present in a parsed RIS record."""
    for tag in tags:
        if record.get(tag):
            return record[tag][0]
    return None


def parse_ris(text: str) -> list[Paper]:
    papers: list[Paper] = []
    current: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = _RIS_LINE_RE.match(line)
        if not m:
            continue
        tag, value = m.group(1), m.group(2).strip()
        if tag == "ER":
            if current:
                paper = _ris_to_paper(current)
                if paper is not None:
                    papers.append(paper)
            current = {}
            continue
        current.setdefault(tag, []).append(value)
    return papers


def _ris_to_paper(record: dict[str, list[str]]) -> Paper | None:
    """Map a parsed RIS record → Paper. Returns None on unusable records."""
    # Title: TI is primary; T1 is an alias for journal articles.
    title = (record.get("TI") or record.get("T1") or [""])[0]
    if not title.strip():
        return None
    # Authors live under AU / A1 (multiple lines allowed).
    authors = []
    for tag in ("AU", "A1", "A2", "A3"):
        authors.extend(record.get(tag, []))
    # DOI under DO; year under PY / Y1 (may include month, take the first 4 digits).
    doi = normalize_doi(_first(record, "DO"))
    year_raw = (record.get("PY") or record.get("Y1") or [""])[0]
    year_match = re.match(r"\d{4}", year_raw)
    year = int(year_match.group(0)) if year_match else None
    venue = _first(record, "JO", "JF", "T2", "BT")
    abstract = _first(record, "AB", "N2")
    try:
        return Paper(
            source="crossref",
            source_id=doi or f"ris:{title[:60]}",
            doi=doi,
            title=title.strip(),
            authors=[a.strip() for a in authors if a.strip()],
            year=year,
            venue=venue,
            abstract=abstract,
            metadata={"import_source": "ris"},
        )
    except (ValidationError, ValueError, KeyError) as e:
        log.warning("ris: skipping record with title %r: %s", title[:40], e)
        return None


# ─── Enrichment ─────────────────────────────────────────────────────────────


async def _openalex_abstract_by_doi(doi: str) -> str | None:
    """One DOI → one abstract via OpenAlex `/works/doi:...`."""
    try:
        resp = await http_get("openalex", f"{_OPENALEX_BASE}/works/doi:{doi}", timeout=10.0)
        if resp.status_code != httpx.codes.OK:
            return None
        inv = resp.json().get("abstract_inverted_index")
    except httpx.HTTPError:
        return None
    if not inv:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions) or None


async def _ss_abstract_by_doi(doi: str) -> str | None:
    try:
        resp = await http_get(
            "semantic_scholar",
            f"{_SS_BASE}/paper/DOI:{doi}",
            params={"fields": "abstract"},
            headers=_ss_headers(),
            timeout=10.0,
        )
        if resp.status_code != httpx.codes.OK:
            return None
        return resp.json().get("abstract")
    except httpx.HTTPError:
        return None


async def _enrich_abstracts(papers: list[Paper]) -> list[Paper]:
    """For papers with a DOI and no abstract, try OpenAlex then Semantic Scholar."""
    enriched: list[Paper] = []
    for p in papers:
        if p.abstract or not p.doi:
            enriched.append(p)
            continue
        abs_text = await _openalex_abstract_by_doi(p.doi) or await _ss_abstract_by_doi(p.doi)
        if abs_text:
            enriched.append(p.model_copy(update={"abstract": abs_text}))
        else:
            enriched.append(p)
    return enriched


# ─── Public MCP tools ───────────────────────────────────────────────────────


async def _import_core(papers: list[Paper], enrich: bool) -> ImportResult:
    if enrich:
        papers = await _enrich_abstracts(papers)
    persisted = await container.papers.persist(papers)
    no_abstract = sum(1 for p in papers if not p.abstract)
    return {
        "parsed": len(papers),
        "saved": persisted["saved"],
        "duplicates": persisted["duplicates"],
        "new_ids": persisted["new_ids"],
        "without_abstract": no_abstract,
        "note": (
            "Papers without abstracts still land in `unreviewed` but will be sparse "
            "during review. Fetch a full snowball via `snowball([new_id], ...)` or "
            "re-run the source search to enrich."
        )
        if no_abstract
        else None,
    }


@mcp.tool()
async def import_refs(file_path: str, enrich_abstracts: bool = True) -> ImportResult | ErrorResult:
    """Import papers from a BibTeX (`.bib`) or RIS (`.ris`) reference-manager export.

    DOI dedup applies. If `enrich_abstracts=True` (default), papers without an abstract
    get one fetched from OpenAlex or Semantic Scholar by DOI; skip it when offline or
    when you want the import to stay fast — a snowball enriches later. Returns
    `{parsed, saved, duplicates, new_ids, without_abstract, note}`.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        return {"error": f"file not found: {file_path}"}
    suffix = path.suffix.lower()
    if suffix not in (".bib", ".ris"):
        return {"error": f"unsupported extension {suffix!r}: expected .bib or .ris"}
    text = path.read_text(encoding="utf-8")
    papers = parse_bibtex(text) if suffix == ".bib" else parse_ris(text)
    return await _import_core(papers, enrich_abstracts)
