# Roadmap: Relationship Microscope (этапы 0–5) и дальше

Первый MVP — не breakup-app и не couples-app, а общий исследовательский инструмент: **Relationship Microscope**. Retrospective/ex данные — удобный test bench; existing couples остаются кандидатом на долгосрочный recurring business. Это рабочая стратегия, а не доказанный вывод.

Системные свойства: [invariants](invariants.md). Запрещённые действия: [safety policy](safety-policy.md). Что считается доказанным: [evaluation contract](evaluation-contract.md). Что пока только гипотеза: [research hypotheses](research-hypotheses.md).

## Форма MVP

Без mobile. Вход: длинный chat export (Telegram/WhatsApp) или несколько выбранных эпизодов. Выход: **0–3 publishable findings**.

```
Finding
├── observable behavior
├── interaction sequence / scope
├── occurrences + temporal range
├── supporting evidence spans
├── strongest counterevidence
├── provenance
├── calibrated uncertainty
└── IPR-style participant feedback (не ground truth)
```

Ноль findings — допустимый и желательный исход, если evidence threshold не пройден. Чего в MVP нет: relationship score, attachment diagnosis, personality type, «ваши отношения токсичны», breakup probability, AI-ex, dashboard ради dashboard и sentiment-графики как суррогат понимания.

После findings — одна функция сверх анализа: **Replay** одного эпизода (original → пауза перед выбранным transition → пользователь пишет альтернативу → 2–3 варианта системы → объяснение observable behavioral difference).

## Этап 0 — BehaviorOntology v0

Не обучать модель. Собрать 15–25 наблюдаемых действий на базе couple-литературы: CIRS (blame, pressure for change, withdrawal, avoidance…), SPAFF/SSIRS, BOLT-style multi-label, repair-категории.

Для каждого label:

- operational definition;
- inclusion/exclusion criteria;
- positive/negative examples;
- tricky/context-dependent cases;
- relation to соседним labels;
- human annotation guide.

Цель этапа — не «идеальная психология», а auditable vocabulary для E0/E1.

## Этап 1 — Synthetic corpus / E0 mechanical fidelity

Synthetic corpus строится в стиле LongMemEval: timestamped history с planted episodes, patterns, counterexamples, knowledge changes и unsupported candidates.

Обязательно включить не только конфликты:

- successful repair;
- boring normality;
- affection;
- playful insults / inside jokes;
- healthy disagreement;
- boundary respected;
- support offered;
- support declined without conflict.

Synthetic corpus проверяет **механику**: segmentation, retrieval recall, temporal ordering, counterexample recovery, provenance, abstention. Он **не валидирует construct** и не может доказать, что придуманная нами trajectory metric психологически значима.

## Этап 2 — Microscope alpha

Pipeline:

```
parser (готовый OSS)
  → episode segmentation
  → multi-label annotation candidates
  → pattern / trajectory candidates
  → active evidence + counterevidence retrieval
  → faithfulness checks
  → calibrated publication gate
  → 0–3 findings
```

Выход может быть HTML/локальным отчётом. Mobile здесь не нужен.

До UI-polish обязателен strong-baseline harness: один архив прогоняется через A/B/C из [evaluation contract](evaluation-contract.md).

## Этап 2.5 — Living Couple Sanity Set

До основного retrospective user study провести sanity check на **5–10 действующих парах**, включая довольные отношения и обычные неконфликтные периоды.

Цель не доказать effectiveness, а поймать distribution failure:

- benign sarcasm → false hostility;
- healthy pause → false withdrawal;
- playful insult → false contempt;
- disagreement → false pathology;
- отсутствие сообщений → ложная интерпретация намерений.

Если ontology/pipeline систематически патологизирует normality, Stage 5 не начинается до исправления.

## Этап 3 — IPR-style correction

Под finding и, выборочно, под episode-level hypothesis:

- именно так;
- частично;
- совсем не так;
- я воспринимал это иначе;
- важное происходило вне чата;
- свободный комментарий.

Этот feedback не является truth label сам по себе. Хранятся отдельные оси из evaluation contract: `participant_resonance`, `missing_context`, `partner_corroboration` (если этично/доступно), `observational_correctness`, `evidence_fidelity`.

Польза петли: меньше самоуверенности, richer context и будущий research dataset без подмены resonance на accuracy.

## Этап 4 — Replay

Один выбранный эпизод:

```
original interaction
       ↓
pause before transition
       ↓
user alternative
       ↓
2–3 candidate responses
       ↓
observable-behavior comparison
       ↓
(optional later) real-world practice
```

Для retrospective/ex surface Replay — deliberate-practice hypothesis для будущих отношений. Для living couples — потенциальная preparation/intervention capability, но перенос проверяется отдельно.

## Этап 5 — 10–20 real histories: E1 + E2

Почти вручную; качество и falsification важнее автоматизации.

### E1 — construct validity

- blind human annotation по BehaviorOntology;
- inter-rater agreement;
- evidence fidelity;
- trajectory reconstruction correctness;
- calibration / risk-coverage;
- false-positive audit на benign/ambiguous episodes.

### E2 — product validity

1. **Discovery:** пользователь может указать конкретный finding, который действительно изменил понимание, а не просто звучал умно.
2. **Participant resonance:** отдельно от correctness.
3. **Missing-context rate:** сигнал границ источника, не автоматический failure.
4. **Baseline win:** C (Microscope) сравнивается blind с A generic frontier LLM и B strong evidence-first prompt.
5. **Action:** пользователь завершил Replay / practice.
6. **Willingness to pay:** реальная one-shot оплата **полного Microscope report + Replay** после teaser/демонстрации ценности. Не продавать «ещё один анализ бывшего» как бесконечный rumination loop.

Гейт на следующий product phase: Microscope даёт измеримую добавочную ценность против B, publication calibration приемлема, Living Couple Sanity Set не показывает патологизации normality и WTP ненулевая.

## Data governance для донорских архивов

Research consent и legal/data-governance analysis — разные вещи.

### Research consent

- explicit informed consent донора;
- понятное описание обработки, рисков и deletion;
- отдельное согласие на исследовательское использование производных annotations, если оно вообще допускается;
- никакого обучения общей модели по умолчанию.

### Data-governance matrix

До Stage 5 для каждого режима заполняется матрица:

| Поле | Пример вопроса |
|---|---|
| mode | Microscope / Replay / coach / simulator |
| jurisdiction | где пользователь и где processing |
| data subject | донор / второй участник / третьи лица |
| data category | обычные данные / возможные special categories |
| processing location | local / server / vendor |
| legal basis | какая правовая база заявляется |
| Art. 9 condition | если обрабатываются special categories |
| Art. 14 transparency | что требуется, если данные получены не от самого data subject |
| retention | raw / derived / logs и сроки |
| deletion | как удаляется raw + derived + backups |

Для GDPR reference: [Regulation (EU) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng). Псевдонимизация и local-first уменьшают риск, но не превращают данные второго человека в «данные только пользователя».

## Regulatory boundary: SB 243 + EU transparency

[California SB 243, §22601(b)(2)(A)](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260SB243) исключает bot, **used only** для перечисленных утилитарных задач, включая “productivity and analysis related to source information”. Поэтому source-analysis Microscope имеет сильнейший аргумент на exclusion; расширение capability требует новой оценки.

```
Microscope/source analysis → strongest exclusion case
Replay                    → review boundary
persistent coach          → companion-like risk grows
persona simulator         → companion-like by design
```

[EU AI Act Article 50](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng) — общий transparency layer, а не только simulator gate.

Это research architecture, не юридическое заключение; перед реальным запуском legal basis и jurisdiction-specific obligations проверяются отдельно.

## После гейта: existing couples

```
Detect → Explain → Private reflection → Shared handoff
      → Micro-intervention → Measure outcome → Learn
```

- Product grammar: Observe → Understand → Respond (OurRelationship/IBCT).
- Private-per-partner spaces + explicit granular handoff; никаких auto-share private reflections.
- Mutual desire matching — commodity primitive, а не позиционирование.
- JITAI/MRT — кандидат-рамка для `micro-intervention → proximal outcome → update`.
- Proprietary dataset hypothesis: `context → dyadic state → hypothesis → evidence/counterevidence → human correction → intervention → outcome`.
- При coercion/IPV safety state совместная mediation-петля не запускается; см. [safety policy](safety-policy.md).
- Persona simulator — только после отдельного safety/compliance/recovery gate.

### Monetization split

- **Breakup/Microscope:** one-shot report/course-like package; exit-compatible.
- **Existing couples:** subscription потенциально легитимна, потому что ценность может продолжаться через новые contexts/interventions/outcomes; всё равно не оптимизировать engagement ценой wellbeing.

## Почему Microscope first

1. Secret matching и chat-import analysis уже commoditized по подтверждённому landscape.
2. Retrospective archive даёт длинную историю и одного доступного участника для test bench.
3. Source-information analysis имеет более чистую capability boundary, чем companion/persona mode.
4. Но retrospective data создаёт selection bias, поэтому Living Couple Sanity Set встроен **до** основного product gate.

Текущие спорные предположения не дублируются здесь: см. [research-hypotheses.md](research-hypotheses.md).
