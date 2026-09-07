# annotation-pilot-v0 — FROZEN, historical, not issued

Статус на 2026-09-07: **пакет заморожен как исторический артефакт и не выдаётся разметчикам.** Он не был выдан: `responses/` пуст, `eligibility.json` не заполнен, presentation-слои сгенерированы 2026-08-29 и никому не передавались.

Причина: naturalness gate ([docs/research/dialogue-naturalness-gate.md](../../../docs/research/dialogue-naturalness-gate.md), §7) нашёл у 13 из 46 единиц корпуса (9 из 40 здесь + 4 из 6 dogfood) терапевтический регистр, требования-регламенты, экспозицию для читателя или реплики, не читающиеся как ответ на предыдущую. Дефект концентрируется в challenge-страте (8 из 20) и dogfood (4 из 6); natural-страта чистая (1 из 20). Решение: не запускать pilot на этом наборе.

## Что это значит

- Ничего в этом каталоге не редактируется, кроме этого README. `items.jsonl`, `strata.json`, `pilot-manifest.json`, `presentation/`, `presentation-map/` остаются побайтно такими, какими были сгенерированы: это исходная точка lineage для следующего пакета.
- `responses/` остаётся пустым навсегда. Слои разметчиков для этого пакета не принимаются.
- Пакет по-прежнему обязан проходить `metrics.validate_items`: инструменты меняются, исторический артефакт — нет.

## Преемник

`annotation-pilot-v0.1` собирается после blinded human A/B по flagged items (`data/pilot/naturalness-ab/v0-flagged/`) как **новый immutable package**: свой `items.jsonl` в схеме `rf.pilot-item.v2` (с блоком `authoring`: origin, revision_reason, accepted_via, parent_item_version → сюда), свой hash, свой manifest, заново сгенерированные presentation-слои. Правила авторинга для него: [docs/item-authoring-v0.1.md](../../../docs/item-authoring-v0.1.md).

Порядок работ (решение 2026-09-07): freeze v0 → provenance-схема → чистка утечки примеров в v0.2-candidate → кандидаты minimal edit → human A/B → ручной accept/reject → сборка v0.1 → pilot → кросс-табы `unnatural_example` × disagreement → автоматизация только после достаточного числа adjudicated правок.
