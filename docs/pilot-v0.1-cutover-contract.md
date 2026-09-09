# Cutover contract: annotation-pilot-v0.1 (materialization) — DECIDED 2026-09-08 · A–I EXECUTED · web cutover EXECUTED 2026-09-08 · J blocked

Статус: решения по развилкам закрыты фасилитатором **до** сборки; три открытых пункта закрыты 2026-09-08 (ниже); GO получен на A–I (research artifact), **не** на web cutover и **не** на issuance. Пакет собран и запечатан: [data/pilot/v0.1](../data/pilot/v0.1/README.md). Порядок соблюдён: сначала механизм (commit `1c7c25f`: инвариант, build/verify/seal, dogfood sidecar, тесты), затем пакет. Вход сборки: [naturalness-ab/v0-flagged-donor/candidates.json](../data/pilot/naturalness-ab/v0-flagged-donor/candidates.json) (13/13 accepted, `facilitator_review.at_build`) и frozen [v0](../data/pilot/v0/README.md).

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
| A | package-level replacement/retirement mapping в manifest v0.1 (`replaces`) | каждая запись: old резолвится в frozen v0 (или dogfood sidecar), new существует в v0.1, у new `parent_item_version = null`; ни один retired id не присутствует в v0.1 | **выполнено**: `metrics.materialize` build/verify |
| B | fresh IDs для replacement; no ID reuse | множество ids v0.1 ∩ retired ids = ∅; правило — следующий свободный номер в той же серии: pc-02→pc-21, pc-05→pc-22, dg-04→dg-10, dg-09→dg-11; message ids `pc-21-m1…` | **решено 2026-09-08**; `verify` проверяет |
| C | design intent facilitator-only | лежит в `authoring` (или в manifest) — никогда в stimulus-ключах; `stimulus_only` + `assert_no_canonical_leak` | уже enforced |
| D | dogfood provenance через sidecar/manifest, не fake v2 lineage | sidecar с тройками old hash (по pinned snapshot) → candidate id → yaml item/hash | **выполнено**: `metrics.materialize dogfood` → `form/dogfood-v7-provenance.json` |
| E | accepted candidate — source of truth для materialized text | materialize читает `candidates[].messages` accepted-кандидатов и `at_build`; carried_over items читаются из frozen v0 | **выполнено** |
| F | exact accepted→built equality — gate | после материализации: для каждого accepted — `(author, text)` по порядку и target index равны candidates.json; для carried_over — content hash равен v0; любое расхождение = build fails | **выполнено**: `verify` (тест: одна точка «по дороге» ловится) |
| G | presentation не содержит authoring/provenance metadata | `assert_no_canonical_leak`; presentation регенерируется из v0.1, seeds v0.1 свои | уже enforced |
| H | v0 остаётся frozen и non-issuable | `data/pilot/v0/README.md`; реестр статусов пакетов и отказ runtime'а выдавать v0 — web cutover, отдельная приёмка | частично (docs); runtime — web cutover |
| I | v0.1 получает один финальный manifest + package hash | `validate_items` проходит; hash считается один раз после E/F; никаких правок после hash | **выполнено**: `seal` → `CHECKSUMS.sha256`; `sha256(items.jsonl)` в README пакета |
| J | pilot issuance только после I | issuance record с sha256 именно выданного файла per pseudonym (протокол 2026-09-08) | **не начато** — нет GO |

## Build ≠ web cutover — две приёмки, даже в одном PR

Сначала доказуемо: v0.1 как immutable research artifact собран правильно (A–I). Потом annotation-web получает обязанность тупо показать именно этот artifact (token-bound renderer/collector, реестр статусов, `v0` не выдаётся runtime'ом, pc-08 в glossary `Domain.hs` перефразирован). Иначе при проблеме непонятно, сломан корпус или дверь, через которую его показывают.

## Что materialize пишет в `authoring` (из `at_build`)

- revision (7 в pilot-пакете: pc-06, pc-09, pc-12, pc-13, pc-16, pc-17, pn-10; плюс dg-05, dg-06 в dogfood): `origin: llm_assisted`, `revision_reason: naturalness`, `accepted_via: facilitator`, `parent_item_version` = тройка из `at_build`, пересчитанная из frozen v0 той же функцией, что использует `validate_items` (расхождение с `at_build` = build fails).
- replacement (2 в pilot-пакете: pc-21 ← pc-02, pc-22 ← pc-05; плюс dg-10 ← dg-04, dg-11 ← dg-09 в dogfood): **решено 2026-09-08 — расширить инвариант**, не писать `accepted_via: original`: `origin: llm_assisted`, `revision_reason: null`, `accepted_via: facilitator`, `parent_item_version: null`. Инвариант теперь `parent = null ⇒ revision_reason = null и accepted_via ∈ {original, facilitator}`; для этих items materialization gate дополнительно требует запись в package-level `replaces`. Локальный authoring честно говорит, как item принят; manifest честно говорит, что он заменяет — два понятия не живут в одном поле.
- carried_over (31 в pilot-пакете; 27 в первой оценке считали вместе с четырьмя dogfood, которые не в pilot-пакете; плюс dg-07, dg-08 в dogfood): **решено — `origin: unrecorded`**, `accepted_via: carried_over`, `revision_reason: null`, parent = frozen v0 + hash; валидатор требует exact content equality.
- provenance способа авторинга (`method: external_dialogue_seeded`, `source_corpus`, `source_revision`, `source_ref`, `source_license`, `source_text_copied: false`): `authoring_issues` проверяет только свои четыре поля и `note`, лишние ключи в `authoring` не отвергает — можно класть `authoring.provenance` без изменения кода; валидировать его — cutover code (или позже). Нужно для pilot-кросс-таба `unnatural_example` × способ авторинга (exploratory).

## Дополнительные развилки — закрыты как следствия принятых инвариантов (2026-09-08)

- **Dogfood yaml — новая версия, не правка in place** (решено): v6 frozen и hash-pinned; изменения materialized как `data/pilot/v0.1/form/dogfood-v7-items.yaml` (`dogfood_id: annotation-ux-v7`, блок `lineage` с `replaces`), только строки `item_id`/`text` изменены, остальное побайтно; sidecar `dogfood-v7-provenance.json`. `Catalog.hs` на v7 — web cutover, не эта приёмка (там же EN-переводы новых текстов).
- **strata.json v0.1** — свой файл: replacement ids заменяют retired в той же страте; `verify` сравнивает с source strata под id-mapping, покрытие проверяет `validate_items`. Выполнено.
- **`replaces` для dg-*** — в sidecar dogfood, не в pilot manifest: dg-items не в pilot package.
- **Что *не* в v0.1:** dg-* (dogfood, отдельная поверхность), а также ничего из generation 1 (`v0-flagged`, LLM minimal edits): та генерация не принята и не отвергнута — она осталась входом для человеческого A/B, которого нет; в v0.1 попадают только accepted donor candidates и carried_over v0.
- **Ontology pin:** manifest v0.1 указывает на ту же `behavior-v0.1` с актуальным sha256 (v0.2-candidate не активируется этой сборкой).
- **Presentation v0.1:** новые seeds `rf-pilot-v0.1/annotator-N/2026-09-08`, opaque ids заново; никакого переиспользования presentation v0. Выполнено.

## Что явно не делается при сборке

- Никаких правок текста «по дороге» — ни запятой. Исправление = новый accepted candidate с verdict'ом, не build-time edit.
- Никакой активации `behavior-v0.2-candidate`.
- Никакого web cutover в той же приёмке (см. выше).
- Никакой выдачи (issuance) до I.

## Статус выполнения 2026-09-08

A ✓ · B ✓ · C ✓ · D ✓ · E ✓ · F ✓ · G ✓ · H ✓ (docs; runtime-отказ выдавать v0 — web cutover) · I ✓ (`CHECKSUMS.sha256`) · **J — BLOCKED, нет GO**. Приёмка фасилитатора 2026-09-08: v0.1 artifact ACCEPTED / SEALED, A–I CLOSED, web cutover NOT STARTED. Build ≠ web cutover соблюдено: annotation-web не тронут.

## Issuance prep (J) — 2026-09-08, sealed package не тронут

J блокируют три конкретные вещи, не исследования naturalness:

1. **Инструкция v0.1** — [pilot-v0.1-instructions.md](pilot-v0.1-instructions.md) написана; v0-инструкция не менялась. Hash на момент написания `9b53f79d91d951885a66d923056392a005665ab0865962a50bad8f822f0f4f57`; привязывающий hash — тот, что записан в issuance record при выдаче (до выдачи документ ещё может правиться, после — только новая версия).
2. **Канал `feedback`** описан в инструкции как независимый от решения: `{"flags": [...], "note": "..."}`, допустимые флаги ровно `unnatural_example`, `insufficient_context`, `wording_or_translation`, `other` (= `metrics.agreement.FEEDBACK_FLAGS` = `annotation-web Feedback.hs`). Правило **meaningful_feedback = хотя бы один флаг ИЛИ непустая заметка**; пустое раскрытие блока — не сигнал. Разметчик не пишет JSON руками: renderer/collector материализует canonical response; если канал предлагался, `feedback` пишется для каждого item (пустой = «канал был, отзыва нет»), чтобы отчёт различал «не собирали» и «собирали, ноль».
3. **Hash-pinned issuance record**: sha256 инструкции + sha256 выданного presentation-файла + псевдоним + дата, до отправки; после — `--force` запрещён процедурно.

Erratum к sealed manifest: `pilot-manifest.json → instructions` называет v0-документ; manifest не правится, инструкция пакета при issuance — v0.1-документ по issuance record (README пакета). README пакета не входит в seal; команда проверки checksum там исправлена (относительные пути от каталога пакета).

Следующий большой gate — **web cutover** (отдельная приёмка): token-bound exact-packet renderer/collector, runtime-отказ выдавать v0, `Catalog.hs` на v7 с EN-переводами новых текстов, pc-08 в glossary. Только затем issuance J и pilot.

## Web cutover — выполнено 2026-09-08 (отдельная приёмка; GO от 2026-09-08)

Authority один: issuance record (`rf.issuance-record.v1`: package_id, items_sha256, checksums_sha256, presentation sha256, instructions sha256, ontology sha256, псевдоним, issued_at, token_sha256). Sealed manifest говорит, что запечатано в research artifact; issuance record говорит, что конкретно увидел конкретный человек; web следует record'у и никогда не выбирает между v0/v0.1 instruction path. Erratum к `manifest.instructions` тем самым закрыт архитектурно, не правкой seal.

Pilot renderer не получает stimuli из `Catalog.hs` вообще: sealed presentation packet → token/session binding → dumb renderer → collector. `Catalog.hs` — dogfood surface (v7 отдельной миграцией, см. ниже).

| # | Gate | Как обеспечено | Доказательство |
|---|---|---|---|
| 1 | Package registry / status | `data/pilot/package-registry.json`: v0 `frozen_non_issuable`, v0.1 `issuable` + pin на sha256 `CHECKSUMS.sha256`; unknown/unsealed/frozen → сервер не стартует (`Registry.loadBindings`) | тесты loader: frozen, unknown, unsealed, pin mismatch |
| 2 | Token-bound exact packet | `GET /t/<token>` → sha256 токена → запись → session с `pilot_binding` (все hash'и); токен не хранится; запись, изменившаяся после старта сессии, отвергается (`bindingUnchanged`) | тесты: unknown token 404; hash mismatch presentation/instructions; duplicate token |
| 3 | Renderer тупой | `pilotStimulus`: сообщения packet-строки в её порядке, её target; ни randomization, ни rewriting, ни translation, ни lookup через Catalog; сервер вообще не читает `items.jsonl` и `presentation-map/` (фикстура без них) | «renders each item as the packet has it»; annotator-2 в своём порядке; real package: тексты первой/последней строки |
| 4 | Collector связан с packet identity | ответы по (session, opaque item id); сессия ↔ одна запись; другой токен — другая сессия; экспорт требует все N ровно по одному разу | «keeps two tokens' sessions apart»; «refuses to export an incomplete session and says which items»; 40/40 на real package |
| 5 | Feedback semantics | канал показан на каждом item пилота; canonical export несёт `"feedback": {"flags": [], "note": ""}` для каждого item; «не открывал» и «открыл пусто» экспортируются одинаково пусто; флаг/заметка — как введены | «exports one canonical line per item … empty meaning empty»; dogfood hs-v1 (канал не собирался) — поля нет |
| 6 | Canonical IDs не текут | процесс не держит canonical ids; presentation row с `authoring`/не-v1 схемой отвергается при загрузке; HTML не печатает даже opaque id | `PacketNotStimulus`; `bodyNotContains id`; real package: `pc-*`/`pn-*` отсутствуют на страницах |
| 7 | Quote = exact substring | `checkEvidenceText`: без trim/normalize; хранится как введено | «stores a quote exactly as typed and rejects one that is not a span»; Domain: trailing space → not a span |
| 8 | Instructions binding | `/instructions` отдаёт байты документа из record'а (hash проверен при старте), hash на intro-странице; `manifest.instructions` не читается | «serves the instruction document byte for byte»; loader: изменённый документ → refusal |
| 9 | Catalog v7 отдельно | `Catalog.hs` = dogfood-v7 (dg-10, dg-11, revisions dg-05/dg-06), EN presentations помечены `llm_translation_2026-09-08` (target) / `prototype_mt_v1` (context); pilot validity не зависит | `research/python/tests/test_catalog_dogfood.py`: тексты Catalog == v7 yaml |
| 10 | pc-08 glossary | пример B.AVOIDANCE_TOPIC_SHIFT в `Domain.hs` заменён (счёт за электричество / соседи завели собаку); онтология не тронута | проверка n-gram против v0.1 items: совпадений нет |
| 11 | End-to-end | token → intro (hash инструкции) → item 0/39 (точные тексты) → assigned с точной цитатой, abstained, none_observed → 20 items → **рестарт** (второй процесс на той же БД, свежий клиент) → resume на `/item/20` → 40/40 → canonical export → hash'и packet/instruction/package равны sealed | `PilotSpec.realPackageSpec` на реальном `data/pilot/v0.1` |
| 12 | Issuance не автоматическая | web ничего не выдаёт; записи создаёт `metrics.issuance new` только при доказанной внешней eligibility-записи (`rf.annotator-eligibility.v1`, вне sealed package; sealed `eligibility.json` — null-шаблон, не operational state); каталог `issuance/` не существует | closure-repair 2026-09-09: раньше `new` читал sealed eligibility.json → любое заполнение ломало seal, незаполнение = отказ; исправлено без изменения сервера |

Не сделано намеренно: issuance record для реальных людей (J), eligibility, деплой релиза (flake.nix теперь кладёт registry, seal, presentation packets, инструкцию и онтологию в `$out/share/relationship-fix`; nix-сборка здесь не запускалась). Dogfood surface выключен по умолчанию (`RF_DOGFOOD_ENABLED=0`).

Статус: **v0.1 artifact ACCEPTED / SEALED · A–I CLOSED · issuance-prep ACCEPTED · web cutover EXECUTED (ждёт приёмки) · issuance J BLOCKED · human evidence NONE.**
