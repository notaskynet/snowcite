# Установка

snowcite — Python-пакет, который работает как MCP-сервер, плюс два плагина Claude Code со skills. Нужны:

- [uv](https://docs.astral.sh/uv/) (в комплекте `uvx`) — запускает сервер по требованию.
- [Claude Code](https://claude.com/claude-code) — клиент.

## Как плагины (рекомендуется)

```bash
claude plugin marketplace add notaskynet/snowcite
claude plugin install snowcite@snowcite-plugins           # сервер + skills ревью
claude plugin install academic-writing@snowcite-plugins   # по желанию: научный русский, критик, ГОСТ
```

Плагин `snowcite` запускает сервер через `uvx snowcite` и спрашивает две необязательные настройки: ключ Semantic Scholar и контактный email для OpenAlex / Crossref. Плагин `academic-writing` независим — ставьте его с snowcite или без.

## Только сервер

```bash
claude mcp add snowcite -- uvx snowcite

# с необязательными ключами (выше лимиты)
claude mcp add snowcite \
  -e SNOWCITE_SEMANTIC_SCHOLAR_API_KEY=xxx \
  -e SNOWCITE_OPENALEX_EMAIL=you@example.com \
  -- uvx snowcite
```

Без плагина будут инструменты, но не skills; попросите Claude вызвать `next_step()`, и он подскажет, что делать.

## Проверка

Попросите Claude: «запусти `check_environment`». Отчёт покажет, какие API источников и ключи доступны. `error` — блокер, `warn` — деградирует одна функция (источник недоступен, нет ключа).

## API-ключи

| Источник | Без ключа | С ключом |
|---|---|---|
| Semantic Scholar (`SNOWCITE_SEMANTIC_SCHOLAR_API_KEY`) | 100 запросов / 5 мин | 100 запросов / с — [получить](https://www.semanticscholar.org/product/api) |
| OpenAlex (`SNOWCITE_OPENALEX_EMAIL`) | общий пул | polite pool со стабильным лимитом |
| Crossref | берёт email OpenAlex | — |
| arXiv, PubMed | ключ не нужен | — |

## Разработка

```bash
git clone https://github.com/notaskynet/snowcite.git && cd snowcite
uv sync --group dev
uv run pytest && uv run ruff check
claude plugin validate .     # маркетплейс и оба плагина
```
