# naturalness-ab-v0-flagged-donor — donor-grounded generation для 13 flagged items

Что это: вторая генерация кандидатов для тех же 13 items, что и [v0-flagged](../v0-flagged/README.md) (generation 1, LLM minimal edits). Отличие в методе: кандидат не «делается живее» с нуля, а строится на **скелете реального импровизированного диалога** из внешнего корпуса. Из донора берётся только структура взаимодействия (ходы, длины, маркеры, adjacency), текст не копируется. Это не generation 2 порядка работ: та зарезервирована для auditor-only находок слепого аудита.

Порядок, восстановимый из provenance каждого кандидата:

```
donor fragments (RESD, MIT) → interaction skeleton → target construct на скелет → candidate → V1–V10
```

## Что лежит

- [donor-report.md](donor-report.md) — какие корпуса проверены, лицензии по первичным источникам, tiers, кто отсеян и почему, цитаты использованных донорских реплик с идентификаторами, результат механической проверки на некопирование.
- `candidates.json` — 13 items, по одному кандидату на item: `donors_considered` (3–5 фрагментов с id и причиной), `skeleton`, `messages`, `inherited`, `changed`, `v1_v10`, `provenance`, `kind`.
- `ab-manifest.json` — чтобы `metrics.naturalness_ab check` (и `build`, если появятся люди) работали без изменений кода. Пакеты **не собраны**: человеческий A/B на этой генерации не запущен.

## Два вида кандидатов

- `kind: revision` — факты и сюжет сохранены, изменён регистр или контекстная реплика. При принятии — revision с `parent_item_version` (pc-06, pc-09, pc-12, pc-13, pc-16, pc-17, pn-10, dg-05, dg-06).
- `kind: replacement` — сюжет и факты новые (pc-02, pc-05, dg-04, dg-09). При сборке v0.1 это **новый original item** с явно унаследованным design intent; старый item получает retired status. Притворяться, что это revision, запрещено — lineage не должен врать.

Форма сохранена намеренно: число сообщений и последовательность авторов те же, что в оригинале, поэтому кандидаты проходят `check` и при необходимости встают в A/B пары с оригиналом.

## Что не сделано

- Ничего не принято. Это вход для veto-review по V1–V10 (только вето, не выбор по вкусу), затем ручной accept/reject с записанной причиной.
- Корпус, пакеты и generation 1 не тронуты.
- Спорные пункты V-оценки названы в самих кандидатах: pc-09 (V4, убран хвост-заверение), dg-09 (нет буквального «прости», ответственность есть), pn-10 (только лексика по правилу natural-страты).

## Provenance принятого кандидата (при сборке v0.1)

`authoring.origin` остаётся `llm_assisted`; способ пишется отдельно: `method: external_dialogue_seeded`, `source_kind`, `source_corpus`, `source_revision`, `source_ref` (id реплик), `source_license`, `source_text_copied: false`, `transformation: interaction_structure_only`. Это позволяет потом проверить на pilot, получают ли donor-grounded items меньше `unnatural_example`, чем handcrafted и чем minimal edits generation 1.

```
uv run python -m metrics.naturalness_ab check --ab-dir ../../data/pilot/naturalness-ab/v0-flagged-donor
```
