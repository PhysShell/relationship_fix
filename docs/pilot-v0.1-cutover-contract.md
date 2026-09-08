# Cutover contract: annotation-pilot-v0.1 (materialization) — DECIDED 2026-09-08, build NOT started

Статус: решения по развилкам закрыты фасилитатором **до** сборки. Ни одного файла v0.1 не существует. Сборка начинается только по отдельному «го» и проверяется по этому документу пункт за пунктом. Вход сборки: [naturalness-ab/v0-flagged-donor/candidates.json](../data/pilot/naturalness-ab/v0-flagged-donor/candidates.json) (13/13 accepted, `facilitator_review.at_build`) и frozen [v0](../data/pilot/v0/README.md).

Зачем документ: четыре replacement, retirement, новые ids, lineage и dogfood/Catalog cutover дают достаточно мест, где можно очень аккуратно соврать самому себе. «Собрать как очевидно» не разрешено; архитектуру за фасилитатора агент не выбирает.

## Пять развилок — решено

1. **Retirement — свойство отношения между версиями пакета, не item'а.** В `rf.pilot-item.v2` ничего не добавляется. Manifest v0.1 получает package-level блок `replaces`: `old <package>/<item_id> → new <item_id>`. Иначе item-schema начнёт описывать жизненный цикл пакетов, а потом туда поселятся `deprecated_since`, `superseded_by`, `migration_reason` и небольшой Kubernetes.
2. **Четыре replacement получают новые ids; старые никогда не переиспользуются.** Mapping явный: `new_original_id ← inherits design intent from retired v0/item_id`. Это **не** parent lineage: у нового original `parent_item_version = null`, иначе новый сюжет снова называется revision.
3. **design_intent — facilitator/authoring metadata, никогда не проецируется в presentation.** Это объяснение, зачем item существует, а не материал для разметчика; связь живёт в manifest/authoring side. Уже обеспечено кодом: `stimulus_only` оставляет только stimulus-ключи, `assert_no_canonical_leak` отвергает любую строку с `authoring` или не-v1 схемой (тесты есть). Контракт требует, чтобы это осталось так.
4. **Dogfood lineage не изображать через `rf.pilot-item.v2`.** У dogfood другая поверхность и другой storage contract. Минимальный package-level provenance record (sidecar/manifest): `old dogfood id/hash → accepted donor candidate id → resulting yaml item/hash`. `dogfood-v*-items.yaml` и `Catalog.hs` остаются содержательными артефактами; пол-исследовательской схемы туда не внедряется ради симметрии.
5. **Ручная сверка accepted → v0.1 не единственный gate.** Build либо берёт текст непосредственно из accepted candidate, либо после материализации проверяет **exact equality** с `candidates.json`. Схема: accepted candidate → materialize → new package item → exact content comparison → manifest/hash. Не: человек copy/paste → человек внимательно проверил → наверное нормально.

## Контракт (проверяется при сборке, пункт за пунктом)

| # | Пункт | Как проверяется | Статус |
|---|---|---|---|
| A | package-level replacement/retirement mapping в manifest v0.1 (`replaces`) | каждая запись: old резолвится в frozen v0 (или dogfood sidecar), new существует в v0.1, у new `parent_item_version = null`; ни один retired id не присутствует в v0.1 | cutover code |
| B | fresh IDs для replacement; no ID reuse | множество ids v0.1 ∩ retired ids = ∅; предложение правила — следующий свободный номер в той же серии (`pc-21`, `pc-22`; `dg-10`, `dg-11`), решение фасилитатора до go | **открыто: правило нумерации** |
| C | design intent facilitator-only | лежит в `authoring` (или в manifest) — никогда в stimulus-ключах; `stimulus_only` + `assert_no_canonical_leak` | уже enforced |
| D | dogfood provenance через sidecar/manifest, не fake v2 lineage | sidecar с тройками old hash (по pinned snapshot) → candidate id → yaml item/hash | cutover code (sidecar), формат ниже |
| E | accepted candidate — source of truth для materialized text | materialize читает `candidates[].messages` accepted-кандидатов и `at_build`; carried_over items читаются из frozen v0 | cutover code |
| F | exact accepted→built equality — gate | после материализации: для каждого accepted — `(author, text)` по порядку и target index равны candidates.json; для carried_over — content hash равен v0; любое расхождение = build fails | cutover code |
| G | presentation не содержит authoring/provenance metadata | `assert_no_canonical_leak`; presentation регенерируется из v0.1, seeds v0.1 свои | уже enforced |
| H | v0 остаётся frozen и non-issuable | `data/pilot/v0/README.md`; реестр статусов пакетов и отказ runtime'а выдавать v0 — web cutover, отдельная приёмка | частично (docs); runtime — web cutover |
| I | v0.1 получает один финальный manifest + package hash | `validate_items` проходит; hash считается один раз после E/F; никаких правок после hash | cutover code |
| J | pilot issuance только после I | issuance record с sha256 именно выданного файла per pseudonym (протокол 2026-09-08) | протокол |

## Build ≠ web cutover — две приёмки, даже в одном PR

Сначала доказуемо: v0.1 как immutable research artifact собран правильно (A–I). Потом annotation-web получает обязанность тупо показать именно этот artifact (token-bound renderer/collector, реестр статусов, `v0` не выдаётся runtime'ом, pc-08 в glossary `Domain.hs` перефразирован). Иначе при проблеме непонятно, сломан корпус или дверь, через которую его показывают.

## Что materialize пишет в `authoring` (из `at_build`)

- revision (9): `origin: llm_assisted`, `revision_reason: naturalness`, `accepted_via: facilitator`, `parent_item_version` = тройка из `at_build` (content hash родителя посчитан из frozen v0 той же функцией, что использует `validate_items`).
- replacement (4): `origin: llm_assisted`, `revision_reason: null`, `accepted_via: original`?? — **нет**: `authoring_issues` требует `parent = null ⇒ accepted_via = original`. Развилка: (i) записывать `accepted_via: original` и держать факт facilitator acceptance в manifest `replaces` + `authoring.note`; (ii) расширить инвариант, чтобы `accepted_via: facilitator` допускался без parent. Вариант (i) не трогает код и не врёт: item действительно original для lineage, а способ принятия — package-level. **Открыто, решить до go.**
- carried_over (27 pilot items без правок): `origin: unrecorded` (текст v0 без записанной истории) или `human`? В v0 авторство не записано — честный вариант `unrecorded`, `accepted_via: carried_over`, `revision_reason: null`, parent = v0 с hash. **Открыто: `unrecorded` предлагается как единственный не-врущий вариант.**
- provenance способа авторинга (`method: external_dialogue_seeded`, `source_corpus`, `source_revision`, `source_ref`, `source_license`, `source_text_copied: false`): `authoring_issues` проверяет только свои четыре поля и `note`, лишние ключи в `authoring` не отвергает — можно класть `authoring.provenance` без изменения кода; валидировать его — cutover code (или позже). Нужно для pilot-кросс-таба `unnatural_example` × способ авторинга (exploratory).

## Дополнительные развилки, которые сборка вскроет (предложения checker'а, не решения)

- **Dogfood yaml — новая версия, не правка in place.** `form/dogfood-v6-items.yaml` захеширован (sha256 `4b2cd0bf…`) snapshot'ом аудита и манифестами A/B; правка in place инвалидирует pin (stale snapshot отказывает в сборке). Значит `dogfood-v7-items.yaml` + `Catalog.hs` на v7; v6 остаётся как frozen источник pin'ов. Для dg-04/dg-09 (replacement) в yaml тоже новые ids.
- **strata.json v0.1** — свой файл: replacement ids заменяют retired в той же страте; покрытие страт проверяет `validate_items`.
- **`replaces` для dg-*** — в sidecar dogfood, не в pilot manifest: dg-items не в pilot package.
- **Что *не* в v0.1:** dg-* (dogfood, отдельная поверхность), а также ничего из generation 1 (`v0-flagged`, LLM minimal edits): та генерация не принята и не отвергнута — она осталась входом для человеческого A/B, которого нет; в v0.1 попадают только accepted donor candidates и carried_over v0.
- **Ontology pin:** manifest v0.1 указывает на ту же `behavior-v0.1` с актуальным sha256 (v0.2-candidate не активируется этой сборкой).
- **Presentation v0.1:** новые seeds (`rf-pilot-v0.1/annotator-N/<date>`), opaque ids заново; никакого переиспользования presentation v0.

## Что явно не делается при сборке

- Никаких правок текста «по дороге» — ни запятой. Исправление = новый accepted candidate с verdict'ом, не build-time edit.
- Никакой активации `behavior-v0.2-candidate`.
- Никакого web cutover в той же приёмке (см. выше).
- Никакой выдачи (issuance) до I.
