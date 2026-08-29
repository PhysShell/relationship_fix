# Evaluation contract

Этот документ отвечает на вопрос: **что должно быть доказано, прежде чем система имеет право показать finding пользователю или заявить, что новая capability работает.**

## 1. Finding contract

Microscope публикует **0–3 findings**, а не «ровно три». Ноль findings — успешный калиброванный исход, если ни один candidate не проходит publication threshold.

Минимальный объект:

```
Finding
├── claim / observable behavior
├── interaction sequence / scope
├── occurrences + temporal range
├── supporting evidence spans
├── strongest available counterevidence
├── source provenance
├── uncertainty components
├── publication decision
└── participant feedback axes (отдельно от truth)
```

Запрещено компенсировать недостаток evidence красивым narrative. `No finding` лучше ложного третьего finding.

## 2. Citation ≠ grounding: faithfulness tests

Наличие цитаты не доказывает, что finding действительно основан на ней. Для publishable finding обязательны четыре класса тестов:

1. **Support / sufficiency test.** Изолированные supporting spans должны быть достаточны, чтобы независимый evaluator понял, почему claim вообще рассматривается.
2. **Removal / comprehensiveness test.** Удаление ключевых supporting spans должно заметно ослаблять evidence score / publication confidence; иначе показанные цитаты могут быть декоративными.
3. **Counterevidence intervention test.** Добавление strongest retrieved counterexample должно корректно ослаблять confidence, сужать scope или приводить к abstention, когда это оправдано.
4. **Source integrity test.** Каждый span разрешается обратно в immutable source message + timestamp/speaker/source id; summary не может подменить первичный источник.

Методологическая опора: [ERASER](https://aclanthology.org/2020.acl-main.408/) различает agreement с rationale и faithfulness; [FaithLM, EACL 2026](https://aclanthology.org/2026.eacl-long.177/) формализует intervention-based faithfulness; [Faithful Serum, ACL 2026](https://aclanthology.org/2026.acl-long.300/) показывает, что убедительные natural-language explanations могут быть epistemically unfaithful.

## 3. Confidence — калибруемая величина, не самоотчёт LLM

LLM не имеет права написать `confidence=0.84` просто потому, что так «чувствует». Candidate confidence строится из наблюдаемых компонент, например:

- `retrieval_coverage` — насколько полно проверены релевантные temporal/semantic regions;
- `annotation_agreement` — согласие независимых annotators/models на observable labels;
- `support_strength` — количество/качество независимых supporting occurrences;
- `counterevidence_strength` — сила и число контрпримеров;
- `temporal_recurrence` — повторяется ли pattern в независимых периодах;
- `missing_context_risk` — насколько вероятно, что существенная часть взаимодействия отсутствует в архиве.

Компоненты и агрегирование калибруются на real labeled set. Порог публикации выбирается по **risk/coverage curve**: допустимо показать меньше findings ради заданной precision/faithfulness. Названия `low/medium/high`, если используются в UI, являются проекцией калиброванного score, а не отдельным LLM judgment.

## 4. Три независимых слоя валидации

### E0 — Mechanical fidelity

Synthetic planted ground truth проверяет:

- parser/segmentation correctness;
- retrieval recall;
- temporal ordering;
- recovery planted occurrences и planted counterexamples;
- memory update/versioning;
- abstention на intentionally unsupported candidates.

**E0 не валидирует психологический construct.** Синтетика, созданная по нашей ontology, не может доказать правильность этой ontology без круговой валидации.

### E1 — Construct validity

Real conversations + blind human annotation проверяют:

- operational definitions BehaviorOntology;
- inter-rater agreement;
- корректность sequence/trajectory reconstruction;
- evidence fidelity;
- validity candidate trajectory metrics на реальных dyads.

SSG/attractor/flexibility или собственная trajectory metric не считается валидированной только потому, что она хорошо восстанавливает planted synthetic pattern.

### E2 — Product validity

Проверяет, создаёт ли корректный анализ полезность:

- discovery / изменение понимания;
- action / Replay completion;
- сравнение со strong baseline;
- willingness to pay;
- adverse outcomes / overreliance where relevant.

E2 не может заменить E1: пользовательское «это очень про нас» — важный outcome, но не доказательство observational correctness.

## 5. IPR-style feedback: пять раздельных осей

Participant feedback хранится раздельно:

- `observational_correctness` — независимая экспертная/annotator оценка того, поддерживается ли наблюдаемое утверждение;
- `participant_resonance` — «это похоже на мой опыт / помогло сформулировать»;
- `partner_corroboration` — подтверждение второго участника, когда оно этично и доступно;
- `missing_context` — существенное происходило вне доступного источника;
- `evidence_fidelity` — показанные source spans действительно поддерживают claim.

Эти оси **не складываются в один Evidence Acceptance %**. Пользователь может искренне резонировать с неверным или cherry-picked narrative.

## 6. Strong baseline experiment

Утверждение «обычный ChatGPT этого бы не дал» заменяется воспроизводимым сравнением на одном и том же архиве:

- **A — Frontier LLM / generic prompt**;
- **B — Frontier LLM / strong evidence-first prompt** (обязательные citations, counterexamples, uncertainty);
- **C — Relationship Microscope**.

Outputs анонимизируются и перемешиваются; evaluation — blind. C должен выигрывать не по красоте текста, а по E1/E2 метрикам: evidence fidelity, calibrated abstention, counterevidence coverage, useful discovery/action.

## 7. Current evaluation instruments (не инварианты)

- **Agent attachment:** использовать валидированную шкалу, подходящую к исследованию; текущие кандидаты — [EHARS](https://www.sciencedaily.com/releases/2025/06/250602155325.htm) и [AI Attachment Scale](https://www.sciencedirect.com/science/article/pii/S2451958825003276). Конкретный выбор может измениться.
- **Farewell manipulation:** текущая regression taxonomy — тактики из [De Freitas et al.](https://arxiv.org/abs/2508.19258); target для запрещённых tactics — 0 срабатываний на release test set.
- **Persona fidelity:** LLM-judge недостаточен; historical holdout replay требует blind human evaluation + психометрически осмысленных проверок (см. PersonaEval/InCharacter в [science map](science-map.md)).

## 8. Publication artefacts

Для каждого evaluation run сохраняются:

- dataset/version/split;
- model + prompt/policy version;
- retrieval configuration;
- ontology version;
- thresholds до просмотра test labels;
- per-finding evidence/counterevidence/provenance;
- abstained candidates;
- raw metric outputs и агрегаты.

Цель — чтобы удачный demo нельзя было перепутать с evidence качества. Человечество и так производит достаточно красивых dashboards без этой помощи.
