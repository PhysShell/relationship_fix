# annotation-pilot-v0.1 — BUILT 2026-09-08 · sealed · NOT issued

Статус: research artifact собран по [cutover contract A–I](../../../docs/pilot-v0.1-cutover-contract.md), запечатан и **принят фасилитатором 2026-09-08** (A–I closed). **Не выдан** (issuance J — отдельное «го»), **web cutover не сделан** (annotation-web и `Catalog.hs` по-прежнему показывают старое; отдельная приёмка), **human naturalness evidence: none**.

Идентичность пакета: `sha256(items.jsonl) = c100db894cef93cdc7b9dd69860dc805e1acdeabf7b8a58fd6dd9a651d8271d9`; полный список — `CHECKSUMS.sha256` (после seal любое изменение = новая версия пакета; `metrics.materialize verify` это обнаруживает).

## Как собран

Ничего не набиралось руками. `build-spec.json` (sha-pinned входы) → `metrics.materialize build` → exact accepted→built equality gate (`verify`) → `metrics.validate_items` (структура, lineage в соседний frozen `v0`, manifest↔ontology) → `metrics.presentation` (новые seeds, opaque ids заново) → `metrics.materialize dogfood` → `seal`.

- Источник текстов carried_over: frozen [`v0`](../v0/README.md) (`items.jsonl` sha `9d1a2690…`), побайтно, с `parent_item_version` + content hash.
- Источник текстов revision/replacement: **только** accepted candidates из [`naturalness-ab/v0-flagged-donor/candidates.json`](../naturalness-ab/v0-flagged-donor/candidates.json) (sha `df3eb3eb…`, 13/13 facilitator verdicts). `verify` сравнивает авторов, тексты и target по порядку; расхождение в одну запятую — build fails.
- Инвариант authoring изменён до сборки (commit `1c7c25f`): `parent = null ⇒ revision_reason = null, accepted_via ∈ {original, facilitator}`.

## Состав: 40 items, те же страты (20 challenge + 20 natural), ru 30 / en 10

| Вид | Сколько | authoring |
|---|---|---|
| carried_over | 31 | `origin: unrecorded`, `accepted_via: carried_over`, `parent_item_version` → v0 + hash, `revision_reason: null` |
| revision | 7 — pc-06, pc-09, pc-12, pc-13, pc-16, pc-17, pn-10 | `origin: llm_assisted`, `revision_reason: naturalness`, `accepted_via: facilitator`, parent → v0 + hash, `provenance` (method external_dialogue_seeded, RESD MIT, structure only), `note` с candidate id и причиной; у pc-17 — `caveat` V7/V5 |
| replacement | 2 — **pc-21** (заменяет pc-02), **pc-22** (заменяет pc-05) | `origin: llm_assisted`, `revision_reason: null`, `accepted_via: facilitator`, `parent_item_version: null`, `design_intent` (facilitator-only), `provenance`; чем что заменено — только `pilot-manifest.json → replaces` (package-level), retired ids pc-02/pc-05 в пакете отсутствуют и никогда не переиспользуются |

Presentation-слои: `presentation/annotator-1.jsonl` (sha `3847d6572b8e…`), `presentation/annotator-2.jsonl` (sha `221a8a7f4af0…`) — v1-проекция без `authoring`, opaque ids от seeds `rf-pilot-v0.1/annotator-N/2026-09-08`, mapping в `presentation-map/` (facilitator-only).

## Что здесь НЕ лежит

- **dg-\*** — dogfood, другая поверхность и другой storage contract: `form/dogfood-v7-items.yaml` (sha `f73347e5f573…`, `dogfood_id: annotation-ux-v7`, derived from frozen v6 `4b2cd0bf…`) + `form/dogfood-v7-provenance.json` (old hash → accepted candidate → result hash для всех шести: dg-10 заменяет dg-04, dg-11 заменяет dg-09, dg-05/dg-06 revisions, dg-07/dg-08 carried over). `Catalog.hs` **не переключён** — web cutover; там же понадобятся EN-переводы новых текстов. В v7 yaml изменены только строки `dogfood_id`, `item_id`, `text` и добавлен блок `lineage`; остальное побайтно как в v6 — включая блок `presentation` с фактами Tally v6, который перепишется при web cutover, когда поверхностью станет annotation-web.
- **generation 1** (`naturalness-ab/v0-flagged`, LLM minimal edits): не принята и не отвергнута — вход для человеческого A/B, которого не было; в v0.1 не попадает.
- Ответы: `responses/` пуст; eligibility не заполнен.

## До issuance (J) — не сделано, не начинать без «го»

1. `eligibility.json` заполняется фасилитатором до выдачи (`has_not_seen_items` — реальный критерий; contamination ledger).
2. Инструкция разметчика: [`docs/pilot-v0.1-instructions.md`](../../../docs/pilot-v0.1-instructions.md) (написана 2026-09-08; описывает необязательный канал `feedback` с флагами `unnatural_example | insufficient_context | wording_or_translation | other` и правило meaningful_feedback = хотя бы один флаг ИЛИ непустая заметка). Hash на момент написания: `9b53f79d91d951885a66d923056392a005665ab0865962a50bad8f822f0f4f57` — привязывающим считается hash, записанный в issuance record в момент выдачи. **Erratum к sealed manifest:** поле `pilot-manifest.json → instructions` указывает на `docs/pilot-v0-instructions.md` (документ пакета v0, без `feedback`); manifest запечатан и не правится, поэтому при issuance инструкцией пакета является v0.1-документ, и это фиксируется в issuance record, а не в manifest.
3. Issuance record: sha256 именно того файла, который уходит каждому псевдониму (протокол 2026-09-08); после выдачи `--force` запрещён процедурой.
4. Web cutover — отдельная приёмка: реестр статусов пакетов, `v0` не выдаётся runtime'ом, token-bound renderer/collector именно этого пакета, pc-08 в glossary `Domain.hs`, `Catalog.hs` на v7.

## Проверить самому

Из `research/python`:

```
uv run python -m metrics.materialize verify --pilot-dir ../../data/pilot/v0.1
uv run python -m metrics.validate_items --pilot-dir ../../data/pilot/v0.1 --ontology ../../data/ontology/behavior-v0.1.json
```

Из каталога пакета (записи в `CHECKSUMS.sha256` относительны к нему):

```
cd data/pilot/v0.1 && sha256sum -c CHECKSUMS.sha256
```

Этот README не входит в `CHECKSUMS.sha256` (seal покрывает build-spec, items, strata, manifest, eligibility, presentation/, presentation-map/, form/), поэтому правки здесь seal не ломают; всё, что в списке, — не редактируется.
