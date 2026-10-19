# Installation

snowcite is a Python package that runs as an MCP server, plus two Claude Code plugins that carry the skills. You need:

- [uv](https://docs.astral.sh/uv/) (ships `uvx`) — runs the server on demand.
- [Claude Code](https://claude.com/claude-code) — the client.

## As plugins (recommended)

```bash
claude plugin marketplace add notaskynet/snowcite
claude plugin install snowcite@snowcite-plugins           # server + review skills
claude plugin install academic-writing@snowcite-plugins   # optional: RU style, critic, GOST
```

The `snowcite` plugin starts the server with `uvx snowcite` and asks for two optional settings: a Semantic Scholar API key and a contact email for OpenAlex / Crossref. The `academic-writing` plugin is independent — install it with or without snowcite.

## Server only

```bash
claude mcp add snowcite -- uvx snowcite

# with optional keys (higher rate limits)
claude mcp add snowcite \
  -e SNOWCITE_SEMANTIC_SCHOLAR_API_KEY=xxx \
  -e SNOWCITE_OPENALEX_EMAIL=you@example.com \
  -- uvx snowcite
```

Without the plugin you have the tools but not the skills; ask Claude to call `next_step()` and it will tell you what to do.

## Verify

Ask Claude: "run `check_environment`". The report lists which source APIs and keys are reachable. `error` entries are blockers; `warn` entries degrade one feature (a source down, a key missing).

## API keys

| Source | Without a key | With a key |
|---|---|---|
| Semantic Scholar (`SNOWCITE_SEMANTIC_SCHOLAR_API_KEY`) | 100 requests / 5 min | 100 requests / s — [request one](https://www.semanticscholar.org/product/api) |
| OpenAlex (`SNOWCITE_OPENALEX_EMAIL`) | common pool | polite pool with a stable limit |
| Crossref | reuses the OpenAlex email | — |
| arXiv, PubMed | no key | — |

## Development

```bash
git clone https://github.com/notaskynet/snowcite.git && cd snowcite
uv sync --group dev
uv run pytest && uv run ruff check
claude plugin validate .     # marketplace + both plugins
```
