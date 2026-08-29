# relationship_fix — Relationship Engine (research)

Статус: **research**. Кода пока нет — здесь фиксируется продуктовый и научный ресерч.

## Концепция (после трёх итераций)

Проект начинался как две отдельные идеи:

1. **Breakup / Relationship Lab** — анализ архива переписки с бывшим партнёром: эпизоды → повторяющиеся паттерны → evidence → counterfactual practice → (позже) controlled persona simulation с exit trajectory;
2. **Couples intimacy program** — приватное состояние каждого партнёра + consent-aware mutual matching + совместные/приватные задания + adaptive progression.

После landscape-ресерча (август 2026) обе идеи сошлись в одну:

> **Evidence-grounded model of dyadic interaction + relationship experimentation.**
>
> Система строит проверяемую модель взаимодействия двух людей (какие взаимодействия повторяются, когда возникают, как развиваются, что их обрывает — с указанием конкретных наблюдений под каждым выводом) и экспериментально выясняет, что помогает именно этой паре.

Причина слияния: оба исходных «вау-механизма» уже commoditized (см. [landscape](docs/research/landscape-2026-08.md)) — secret mutual matching, chat-import-анализ и ex-симуляция существуют как категории приложений. Незанятая территория — evidence-дисциплина и experimentation loop.

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

Первый MVP — **Relationship Microscope**: chat export → ровно 3 evidence-grounded findings → IPR-коррекция пользователем → Replay одного эпизода. Подробно: [roadmap](docs/research/roadmap-microscope.md).

## Карта документов

| Документ | Что внутри |
|---|---|
| [docs/research/landscape-2026-08.md](docs/research/landscape-2026-08.md) | Конкурентная карта со статусами верификации и «что утащить» из каждого продукта |
| [docs/research/science-map.md](docs/research/science-map.md) | Научная карта по слоям engine: источник → что взять → оговорки |
| [docs/research/invariants.md](docs/research/invariants.md) | 27 архитектурных и продуктовых инвариантов |
| [docs/research/roadmap-microscope.md](docs/research/roadmap-microscope.md) | Этапы 0–5 MVP, метрики, consent-протокол, открытые вопросы |

## Ключевые развилки, уже решённые

- LLM — не source of truth: persona/style/generation отделены от trusted state (память, provenance, cooldown, safety).
- SOURCE_MEMORY ≠ SIMULATED_MEMORY; синтетика никогда автоматически не становится «воспоминанием».
- Observable behavior вместо диагнозов; каждый значимый вывод несёт evidence + confidence; система умеет говорить «недостаточно данных».
- Persona simulator — последний по порядку, а не первый: и по продуктовому риску, и по регуляторике (companion-chatbot законы уже действуют).
- Retention не является автоматической метрикой успеха; у breakup-режима должен быть exit trajectory.

## Главные нерешённые вопросы

1. Помогает ли персонализированная симуляция двигаться дальше — или создаёт более качественный объект привязанности? (может убить breakup-simulator)
2. Даёт ли deliberate practice на собственных реальных эпизодах больший skill transfer, чем generic relationship education? (может самостоятельно оправдать весь продукт; RCT-база существует только для тренировки терапевтов — перенос на пары не доказан)
3. Проходит ли evidence-grounded анализ порог «этого я сам не видел, но evidence подтверждает» + готовность платить? (проверяется этапом 5 roadmap)
