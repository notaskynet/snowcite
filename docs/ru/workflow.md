# Workflow

Сервер — это **рельсы**, процедура живёт в skills. `next_step()` — единственная точка входа: он выводит фазу из базы (флага нигде нет) и возвращает `phase`, `why`, упорядоченные действия `do` и `payload` с данными фазы, а также счётчики, цели, предупреждения и последние действия.

```
not_started → criteria → search → review ⇄ (сводка) → low_confidence → synthesis → done
```

## Ограничения, которые держит сервер

| Ограничение | Эффект |
|---|---|
| Сводка отсутствует или устарела | `review` не отдаёт пачку; первое действие — `review_summary(...)` |
| Есть неподтверждённые `auto_low` | `low_confidence` блокирует синтез и структуру |
| Approved / maybe без claim или finding | `review_batch` отклоняет решение (`errors` по индексу) |
| Межстатейная заметка без источников | `add_synthesis_note` отказывает |
| Секция без заметок для её области | правило skill, не сервера: пустые `notes` в `get_section_critique_inputs` значат «не писать» — добавьте статьи или сузьте область |

## Цикл ревью

1. Прочитать `payload.criteria` (защита от дрейфа) и сводку; сверить текст с живыми счётчиками.
2. Решить пачку самостоятельно с оценкой уверенности: уверенное совпадение → `auto_high`, склоняюсь → `auto_low`, пограничная → пользователю.
3. `review_batch([...])`: `{paper_id, status, reason, reviewed_by, notes}`. `reason` обязателен — это след PRISMA. Верные решения применяются, неверные возвращаются по индексу.
4. Пограничные статьи приходят к вам по одной, только факты, без рекомендации.
5. `review_summary(summary, clusters)` — до 500 слов, переписывается заново; кластеры берут категории из критериев.

Отмена — `undo_last_review_action`; перенос целого фильтра — `bulk_reclassify`; числа PRISMA — `get_prisma_counts`.

## Snowball

После первого прохода `snowball(paper_ids, "references" | "citations")` по одобренным статьям. Новые статьи попадают в `unreviewed` и делают сводку устаревшей. Решение всегда за вами, автоматически он не запускается.

## Синтез

По кластеру: `get_cluster_notes` → `add_synthesis_note(cluster, type, text, derived_from_note_ids)`; затем `find_gaps`. Типы: `gap`, `contradiction`, `consensus`, `open_question`.

## Секции

Секция — сущность с областью (`clusters`, `keywords`, `questions`), черновиком, статусом и счётчиками критики. По секции: `get_section_critique_inputs` → черновик → `record_section_critique` (стоп при нуле блокеров или после двух итераций) → `revise_section` → готово. `research_section` по запросу добавляет статьи под область; `gap_check` показывает предложения без ссылок; `rewrite_citations` переназначает `[N]`.

## Skills

| Плагин | Skills |
|---|---|
| `snowcite` | `workflow`, `search`, `review`, `synthesis`, `sections` |
| `academic-writing` | `academic-writing-ru`, `academic-critic`, `gost-report`, агент `academic-reviewer` |
