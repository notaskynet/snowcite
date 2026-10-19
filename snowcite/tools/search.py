from snowcite.app import mcp
from snowcite.container import container
from snowcite.domain.records import ErrorResult, PaperDetails, PaperRecord
from snowcite.domain.results import ClusterError, SearchPreview, SearchSummary
from snowcite.domain.types import Direction, ReviewedBy, Source, Status


@mcp.tool()
async def search_papers(
    query: str,
    sources: list[Source] | None = None,
    limit: int = 20,
    year_from: int | None = None,
    year_to: int | None = None,
    auto_save: bool = True,
    abstract_max_chars: int = 0,
) -> SearchSummary | SearchPreview:
    """Search arXiv / Semantic Scholar / OpenAlex / Crossref / PubMed in parallel, dedup by DOI/title.

    By default (auto_save=True) persists new papers to the DB and returns a compact
    summary {saved, duplicates, new_ids, titles} — abstracts never enter the chat
    context, which keeps review sessions lean and avoids false-positive safety triggers
    when harmful-sounding abstracts accumulate. Sources default to a set chosen from
    the project's discipline.

    Set auto_save=False for preview mode; then the response includes the full paper list
    (with abstracts trimmed to abstract_max_chars; 0 drops the field entirely).

    A single source failure is logged and does not abort the search.
    """
    return await container.search.search(
        query, sources, limit, year_from, year_to, auto_save, abstract_max_chars
    )


@mcp.tool()
async def snowball(
    paper_ids: list[int],
    direction: Direction,
    limit: int = 20,
    auto_save: bool = True,
    abstract_max_chars: int = 0,
) -> SearchSummary | SearchPreview:
    """Fetch references or citations for several papers; by default persist the new ones.

    Uses the Semantic Scholar graph; arXiv / OpenAlex papers are resolved through their
    DOI. New papers land in `unreviewed` and mark the review summary stale. Returns
    `{saved, duplicates, new_ids, titles, errors?}` — `errors` lists papers that
    couldn't be resolved, by `paper_id`. With auto_save=False returns the merged paper
    list with abstracts trimmed to abstract_max_chars (0 = omitted).

    Snowball is the user's decision, never part of an automatic loop.
    """
    return await container.search.snowball(
        paper_ids, direction, limit, auto_save, abstract_max_chars
    )


@mcp.tool()
async def papers(
    status: Status | None = None,
    source: Source | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    search: str | None = None,
    cluster: str | None = None,
    reviewed_by: ReviewedBy | None = None,
    include_abstracts: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[PaperRecord] | ClusterError:
    """List saved papers with their review state. All filters are AND-joined.

    Compact records by default — title / year / venue / authors / doi / review fields,
    no abstract — to keep the context lean. Typical calls:
    - next review batch: `status="unreviewed"`
    - second pass over uncertain calls: `reviewed_by="auto_low"`
    - material for a section: `status="approved", cluster="...", include_abstracts=True`
    A `cluster` that isn't in the current review summary returns `[{error, available}]`.
    For one borderline paper use `paper(id)`.
    """
    return await container.review_service.list_papers(
        status,
        source,
        year_from,
        year_to,
        search,
        cluster,
        reviewed_by,
        include_abstracts,
        limit,
        offset,
    )


@mcp.tool()
async def paper(paper_id: int) -> PaperDetails | ErrorResult:
    """Full record for one paper: abstract, review state, stored citation-edge counts.

    Summarise the abstract in one or two neutral sentences for the user; don't paste it.
    """
    return await container.review_service.paper_details(paper_id)
