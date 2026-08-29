# relationship_fix — Relationship Engine (research)

Статус: **research**. Кода пока нет — здесь фиксируется продуктовый, научный, safety- и evaluation-фундамент.

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

## Главные нерешённые вопросы

Открытые вопросы вынесены в [research hypotheses](docs/research/research-hypotheses.md): recovery vs attachment у симуляции, перенос deliberate practice на пары, construct validity trajectory-метрик, реальная добавочная ценность Microscope против сильного LLM-baseline и generalization с ex-архивов на живые пары.
