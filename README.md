# relationship_fix — Relationship Engine (research)

Статус: **research → этап 0–2 roadmap'а**. В репозитории: research-фундамент (docs/) + первый исполняемый каркас на .NET 10 — BehaviorOntology v0.1, data contract с property-тестами и уродливый vertical slice.

## Концепция

Проект начинался как две отдельные идеи:

1. **Breakup / Relationship Lab** — анализ архива переписки с бывшим партнёром: эпизоды → повторяющиеся паттерны → evidence → counterfactual practice → (позже) controlled persona simulation с exit trajectory;
2. **Couples intimacy program** — приватное состояние каждого партнёра + consent-aware mutual matching + совместные/приватные задания + adaptive progression.

После landscape-ресерча обе идеи сошлись в общий фундамент:

> **Auditable longitudinal dyadic experimentation engine.**
>
> Система формулирует проверяемые гипотезы о повторяющихся взаимодействиях двух людей, активно ищет подтверждающие и опровергающие наблюдения, умеет abstain, принимает human correction и — только после этого — связывает гипотезу с интервенцией и её наблюдаемым outcome.

Это **differentiation hypothesis**, а не утверждение о «незанятой территории». Рынок быстро дрейфует в сторону framework-based relationship analysis; поэтому moat нельзя привязывать к одной feature вроде chat import, mutual matching или даже наличия цитат.

Целевая цепочка:

```
hypothesis
    ↓
supporting evidence
    ↓
active counterevidence search
    ↓
uncertainty / abstention
    ↓
human correction
    ↓
intervention
    ↓
observed outcome
    ↓
model update
```

Один engine, две product surfaces:

```
                Relationship Engine
                        │
        ┌───────────────┴───────────────┐
        │                               │
  Ex / retrospective              Existing couple
  (test bench, первый MVP)        (долгосрочный бизнес)
        │                               │
  Relationship Microscope         detect → explain →
  retrospective, replay,          private reflection →
  learning for next               shared handoff →
  relationship                    micro-intervention →
                                  measure → learn
```

Первый MVP — **Relationship Microscope**: chat export → **0–3 publishable evidence-grounded findings** → IPR-style feedback → Replay одного эпизода. Ноль findings является корректным калиброванным результатом, если evidence threshold не пройден. Подробно: [roadmap](docs/research/roadmap-microscope.md).

## Карта документов

| Документ | Что внутри |
|---|---|
| [docs/research/landscape-2026-08.md](docs/research/landscape-2026-08.md) | Конкурентная карта, верифицированные соседи, два фантомных кластера и differentiation hypothesis |
| [docs/research/science-map.md](docs/research/science-map.md) | Научная карта по слоям engine: observation, dynamics, memory, evidence, faithfulness, intervention, safety/regulatory |
| [docs/research/invariants.md](docs/research/invariants.md) | Только свойства системы, которые не должны дрейфовать вместе с текущими экспериментами |
| [docs/research/safety-policy.md](docs/research/safety-policy.md) | Запрещённые действия и capability gating, включая coercion/IPV и simulator mode |
| [docs/research/evaluation-contract.md](docs/research/evaluation-contract.md) | Finding contract, faithfulness, calibrated confidence, E0/E1/E2, IPR-оси, baseline A/B/C |
| [docs/research/research-hypotheses.md](docs/research/research-hypotheses.md) | Что пока только проверяется и может быть опровергнуто |
| [docs/research/roadmap-microscope.md](docs/research/roadmap-microscope.md) | Этапы MVP, real-data gates, Living Couple Sanity Set, data governance и WTP |

## Ключевые развилки, уже решённые

- LLM — не source of truth: generative слой отделён от trusted state, provenance и policy.
- `SOURCE_MEMORY` ≠ `USER_ASSERTED` ≠ `SIMULATED_MEMORY`; синтетика никогда автоматически не становится историческим фактом.
- Observable behavior предпочтительнее diagnosis labels.
- Citation сама по себе не является grounding: publishable finding обязан проходить faithfulness checks из [evaluation contract](docs/research/evaluation-contract.md).
- Confidence не является самооценкой LLM; это калибруемая величина с risk/coverage gate.
- IPR-style feedback пользователя измеряет субъективное соответствие и missing context, но не превращается автоматически в ground truth.
- Persona simulator — последний по порядку, а не первый; recovery value проверяется до realism.
- Breakup-surface не оптимизируется на бесконечный retention; monetization не должна поощрять rumination.

## Engineering

```
src/
  RelationshipFix.Domain          типы (Thinktecture VO/SmartEnum/Union + NodaTime): онтология,
                                  evidence spans, source messages, finding decisions
  RelationshipFix.DataContracts   канонический JSON (ADR-0002), wire DTO, явный маппинг,
                                  code-point утилиты, JSONL
  RelationshipFix.Evaluation      ontology loader/validator, slice pipeline, provenance (ADR-0003)
  RelationshipFix.AI.Abstractions IModelClient / capabilities (provider-free)
  RelationshipFix.AI.Anthropic    минимальный адаптер официального SDK
  RelationshipFix.Cli             relationship-fix slice | validate-ontology
tests/
  Architecture.Tests              границы ADR-0001 как падающие тесты (ArchUnitNET + reflection)
  DataContracts.Tests             FsCheck property-тесты Unicode-спанов + golden fixtures + roundtrip
  E2E.Tests                       vertical slice сквозняком на repo-fixture
data/
  ontology/behavior-v0.1.json     6 draft-лейблов с двуязычными примерами (machine-readable constraints)
  fixtures/slice-001/             входной fixture (ru/en, эмодзи, все timestamp-резолюции)
  contracts/                      golden wire fixtures (замороженные байты контракта)
docs/adr/                         ADR-0001 (пакеты/границы), ADR-0002 (data contract), ADR-0003 (run provenance)
docs/annotation-protocol-v0.md    протокол разметки: α per label, challenge/natural страты, abstention
docs/pilot-v0-instructions.md     инструкция разметчика micro-pilot
data/pilot/v0/                    annotation-pilot-v0: 40 items (20 challenge + 20 natural, слепые страты),
                                  manifest (5 active labels + B.WITHDRAWAL deferred/not_applicable), responses/
research/python/                  uv-проект (stdlib-only): agreement (α, CI, positive agreement, confusion pairs,
                                  estimability), validate_items; гейтящие числа — только отсюда
```

Запуск (нужен .NET 10 SDK):

```bash
dotnet test --solution RelationshipFix.slnx          # 32 теста: architecture + contracts + e2e
dotnet run --project src/RelationshipFix.Cli -- \
  slice --messages data/fixtures/slice-001/messages.jsonl \
        --ontology data/ontology/behavior-v0.1.json --out runs/demo-001
dotnet run --project src/RelationshipFix.Cli -- validate-ontology data/ontology/behavior-v0.1.json
```

Slice — детерминированный rule-stub (не LLM и не «анализ отношений»): его работа — прогнать весь контракт данных: решения `assigned` / `none_observed` / `abstained(reason)`, evidence-спаны в code points c sha256-проверкой источника, манифест запуска с git/ontology/dataset-хэшами. Аннотации пишутся в `rf.annotation.v2`: цель — union (utterance по message_id | turn/exchange/episode через provenance-aware DerivedUnitRef с segmentation_version и hash'ем состава); v1 заморожен и мигрируется (ADR-0002 §4.1).

## Сборка через Nix

Второй, независимый способ собрать annotation-web. Stack остаётся тем, что гоняет CI; Nix добавлен как воспроизводимая сборка из чистого checkout, без Stack.

```
nix flake check
nix build .#annotation-web
./result/bin/annotation-web
```

`nix build` собирает пакет и **прогоняет его тесты внутри сборки** (19 примеров). Полученный `result/bin/annotation-web` — тот же самый Yesod-сервер, а не отдельная сборка приложения: против него проходит весь обход инструмента, от выбора языка до `submission.json`.

`flake.nix` берёт дефолтный `haskellPackages`, а не `haskell.packages.ghc9103`, хотя на текущем пине это один и тот же компилятор. Только дефолтный набор покрыт `cache.nixos.org`, и разница — минуты против часов. Если он когда-нибудь перестанет быть GHC 9.10, это скажет не комментарий, а `base >=4.20 && <4.21` в `.cabal`.

Вход `nixpkgs` записан как `git+https://…`, а не привычным `github:`-сокращением: последнее резолвится через `api.github.com`, который доступен не в каждом окружении, где этот репозиторий собирается. На фиксацию ревизии в `flake.lock` это не влияет.

### Два резолвера дают разные планы, и оба собираются

| пакет | Stack (LTS 24.57) | Nix (nixpkgs 0968519e) |
|---|---|---|
| yesod | 1.6.2.3 | 1.6.2.1 |
| yesod-form | 1.7.11 | 1.7.9.2 |
| yesod-persistent | 1.6.0.9 | 1.6.0.8 |
| aeson | 2.2.5.1 | 2.2.4.1 |
| yesod-core | 1.6.29.1 | 1.6.29.1 |
| persistent | 2.17.1.0 | 2.17.1.0 |
| persistent-sqlite | 2.13.3.1 | 2.13.3.1 |
| warp | 3.4.9 | 3.4.9 |

Компилятор в обоих случаях GHC 9.10.3. Планы расходятся по нескольким пакетам, тесты проходят в обоих — то есть код инструмента не привязан к одному резолверу зависимостей. `text` и `time` в таблице отсутствуют, потому что это boot-библиотеки GHC; `hspec` и `yesod-test` — потому что они не входят в runtime-замыкание собранного пакета.

### Замыкание, которое придётся уменьшить до деплоя

```
nix path-info -rSh .#annotation-web
```

даёт **387 путей и 4.3 GiB**. Причина не в приложении: nixpkgs линкует Haskell динамически, и все библиотеки остаются runtime-ссылками. Для `nix copy` на маленький VPS это неприменимо.

Штатное лекарство — `pkgs.haskell.lib.justStaticExecutables`. Замерено на этом же пакете: **28 путей и 81.6 MiB**, тот же бинарь. В текущий флейк оно намеренно не внесено: первый Nix-коммит ограничен воспроизводимой сборкой, а выбор формы артефакта относится к шагу деплоя.

Для сравнения, Stack-бинарь — 42 МБ, динамически слинкован с `libc`, `libgmp`, `libz` **хоста**, то есть за пределами конкретной машины ничего не гарантирует. Nix-замыкание самодостаточно, включая glibc.

## Главные нерешённые вопросы

Открытые вопросы вынесены в [research hypotheses](docs/research/research-hypotheses.md): recovery vs attachment у симуляции, перенос deliberate practice на пары, construct validity trajectory-метрик, реальная добавочная ценность Microscope против сильного LLM-baseline и generalization с ex-архивов на живые пары.
