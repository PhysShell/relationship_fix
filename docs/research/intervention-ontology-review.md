# InterventionOntology: минимальный защитимый скелет

Дата: 2026-09-16. Статус: **research-only**. Ни одного intervention-label не создано. Здесь проверяется **архитектура**, а не строится taxonomy.

Companion: [couple-coding-systems.md](couple-coding-systems.md) · [ontology-crosswalk.md](ontology-crosswalk.md) · [next-research-design.md](next-research-design.md).

---

## 0. Ledger источников

| Артефакт | existence_verified | primary_source_verified | raw_data_available | annotations_available | license_verified |
|---|---|---|---|---|---|
| **ProMediConv** — Wei, Li, Liu, Zhang, Wang, Deng, «Benchmarking Proactive Conversational Agents in Legal Dispute Mediation», [arXiv:2609.11101](https://arxiv.org/abs/2609.11101) (10.09.2026) | yes | yes (abs + html прочитаны) | заявлен релиз: [github.com/ZsWei66/ProMediConv_repo](https://github.com/ZsWei66/ProMediConv_repo) — **репозиторий в этой сессии не открывался** → `unknown` | **unknown** (заявлены utterance-level аннотации; не проверено) | **unknown** — на arXiv-странице бейдж CC BY 4.0, но это **лицензия статьи**, не датасета (ровно та ловушка, что уже задокументирована для BenSyc в [external-corpus-license-matrix.md](external-corpus-license-matrix.md)) |
| **Cho, Zachry & McDonald**, «A Framework for AI-Supported Mediation in Community-based Online Collaboration», [arXiv:2509.10015](https://arxiv.org/abs/2509.10015) | yes | **partial** — только abstract | n/a (концептуальная работа) | n/a | n/a |
| **ESConv** (Liu et al., ACL 2021) | yes | yes (по предыдущей работе репозитория) | yes | yes | **RESEARCH_ONLY_OR_RESTRICTED** — см. [external-corpus-license-matrix.md](external-corpus-license-matrix.md) |
| «Beyond mediation: an evolutionary benchmark…», Frontiers in AI 2026 / [PMC13149239](https://pmc.ncbi.nlm.nih.gov/articles/PMC13149239/) | yes | **no** — только поисковая выдача | n/a (agent-based симуляция) | n/a | n/a |

**Честная оценка стрима F: он самый слабый по глубине источников.** Один первоисточник прочитан как следует (ProMediConv), остальное — abstract-уровень. Выводы ниже — **архитектурные**, а не эмпирические, и так и помечены.

---

## 1. Проверяемая архитектура

```
BehaviorOntology   = что произошло между людьми        (наблюдение)
DyadicState        = какой паттерн/состояние разворачивается (вывод над наблюдением)
InterventionOntology = что система может сделать дальше  (действие)
Outcome            = что изменилось после вмешательства  (измерение)
```

### Подтверждение 1 (внешнее, ML): ProMediConv строит ровно это разделение

ProMediConv моделирует медиацию как «proactive, multi-stage, **party-aware** dialogue process» и разносит по **двум независимым слоям аннотации на уровне реплики**:

- **Behavioral Pattern (BP) state — состояние стороны**, 4 значения:
  `Denial` («parties completely deny the existence of their own responsibilities or issues») → `Partial Acceptance` («acknowledge some facts partially but refuse to assume full responsibility») → `Negotiation` («begin to accept mediation and engage in disputes over details») → `Resolution` («explicitly accept the formal resolution»). Привязано к Transtheoretical Model.
- **Mediation strategy — ход медиатора**, 11 значений (Understanding the Situation, Perspective-Taking, Early Detection and Prevention, Strategic Ambiguity, Recognition and Motivation, Grasping the Principal Contradiction, Reaching a Mediation Agreement и др.).
- **Outcome-метрика MAD** (Mean Attribute Difference) — «average shift in each party's behavioral state across dialogue turns», то есть **эффект измеряется как сдвиг состояния стороны**, а не как «хороший ответ».

Данные: 972 реальных дела из изданных сборников по медиации, китайский язык, OCR, анонимизация; 8 опытных медиаторов размечали состояния завершения, **87% inter-annotator agreement**.

> **RESEARCH FINDING R-F1.** Независимая ML-работа, пришедшая из другой области (юридическая медиация), сошлась на **той же трёхслойной структуре**: состояние стороны ≠ ход системы ≠ эффект. Это повышает доверие к нашей архитектуре.
> **Оговорки, которые нельзя терять:** (a) 87% — это **сырое процентное согласие, не скорректированное на случайность**; при 4 несбалансированных классах это слабая цифра, и в нашем репозитории она бы не прошла собственный gate; (b) медиаторы — **эксперты**, не обычные люди; (c) домен — юридический спор с **третьей стороной-медиатором**, а не пара наедине; (d) данные — **изданные книги**, то есть уже отредактированные и отобранные тексты, а не сырой лог.

### Подтверждение 2 (внутреннее, из стрима A): диадические коды надёжнее индивидуальных

IDCS-CMC: `Positive Escalation` ICC **.83**, `Negative Escalation` **.74** — **выше**, чем `Withdrawal` .52 и `Dominance` .30. При этом escalation-коды требуют **больше** вывода, не меньше.

> **RESEARCH FINDING R-F2.** Уровень паттерна может оказаться **надёжнее** уровня индивидуального поведения, даже когда паттерн «сложнее».
> Правдоподобная причина: escalation определён через **отношение между ходами** («consecutive chains … unrelated positive behaviors do **not** constitute a snowball»), а это структурный признак, наблюдаемый в последовательности. Withdrawal определён через **отсутствие**, которое не наблюдаемо нигде.
> **Следствие:** не надо считать, что DyadicState обязан ждать «пока BehaviorOntology устаканится». Возможно, часть паттернов кодируется независимо и легче.
> **falsification:** прямой тест — разметить те же обмены на escalation-паттерн (два аннотатора, бинарно: «негативная цепочка есть / нет») и сравнить alpha с per-label alpha. Если паттерн даёт α выше, чем медиана по labels, — R-F2 подтверждён для нашего носителя.
> **Это можно сделать, не трогая sealed pilot** — на отдельном наборе обменов.

### Что архитектура запрещает

- **Intervention-метки не могут входить в BehaviorOntology.** ProMediConv держит ход медиатора в отдельном пространстве от состояния сторон — и это при том, что медиатор в его данных является участником диалога.
- **Outcome не может быть свойством intervention-метки.** MAD вычисляется **после** по сдвигу состояния. У нас уже есть правильный прецедент: `B.REPAIR_ATTEMPT` кодирует попытку, успех отнесён к `T.*`. Тот же принцип должен применяться к вмешательствам.
- **DyadicState не должен собираться как сумма labels.** Escalation определён через *последовательность*, а не через количество негативных реплик.

---

## 2. Минимальный скелет

Принцип: **каждое измерение существует только если у него есть определённый источник истины и оно может оказаться ложным.** Всё, что не проходит этот фильтр, вынесено в §3.

```
InterventionRecord
├── trigger
│   ├── dyadic_state_observed     : ссылка на DyadicState (что вызвало)
│   └── evidence_span             : обязательно, как и у B.*
├── decision
│   ├── act                       : {intervene, hold}         ← «hold» ЯВНАЯ запись
│   └── timing                    : {in_situ, post_hoc, scheduled}
├── target                        : {partner_a, partner_b, dyad, none}
├── strategy                      : один узкий словарь (см. ниже)
├── contraindication_check
│   └── blocked_by                : [] | [safety, escalation_risk, insufficient_evidence, …]
├── expected_effect               : предсказание ДО (фальсифицируемо)
└── outcome
    ├── observed_effect           : сдвиг DyadicState после (аналог MAD)
    ├── user_response             : {accepted, ignored, rejected, corrected}
    └── transfer_observed         : применил ли пользователь это в реальном обмене
```

**Пять измерений, которые обязаны быть в v1:**

| Измерение | Почему обязательно | Источник истины |
|---|---|---|
| `act: {intervene, hold}` | Без явной записи «решили не вмешиваться» **невозможно измерить unnecessary и missed intervention** — обе категории исчезают из данных. Это самая частая ошибка проектирования такого слоя | лог системы |
| `timing` | ProMediConv-находка про «pre-emptive repair» (стрим A, §5: самые эффективные repair — в первые 3 минуты) означает, что **время не параметр, а часть конструкта** | лог системы |
| `target` | «party-aware» в ProMediConv — не украшение: вмешательство, адресованное не тому партнёру, — отдельный класс отказа | лог системы |
| `strategy` | минимальный различитель того, *что именно* было сделано | лог системы |
| `outcome.observed_effect` | без него слой не обучаем и не фальсифицируем | **сдвиг DyadicState**, не self-report |

**Словарь strategy для v1 — намеренно короткий (5 значений):**

`reflect` (отразить наблюдаемое без оценки) · `reframe` (предложить другую рамку) · `slow_down` (предложить паузу/замедление) · `surface_perspective` (сделать видимой позицию другой стороны) · `none`.

Обоснование краткости — прямое из стрима A: PCA по **31 item** CIRS+SSIRS даёт **4 фактора**. Одиннадцать стратегий ProMediConv заточены под юридическую медиацию с третьей стороной и **не переносятся** на пару. Начинать надо с числа, которое можно оценить на реальных данных.

---

## 3. Измерения, которые НЕ идут в v1 — и почему

Это не отбрасывание. Это перенос в слой, где у них есть носитель истины.

| Кандидат из задачи | Куда | Почему не в v1 |
|---|---|---|
| **unnecessary intervention** | **вычислимо**, не измерение | = `act=intervene` ∧ `observed_effect ≈ 0` ∧ `user_response ∈ {ignored, rejected}`. Как отдельное поле — это оценка, замаскированная под наблюдение |
| **missed intervention** | **вычислимо** | = `act=hold` ∧ последующая негативная эскалация. Требует **обязательной записи hold** — см. §2 |
| **superficial resolution** | **DyadicState, не Intervention** | Это свойство состояния пары («согласились, чтобы прекратить разговор»), а не свойство хода системы. Прямая аналогия: наш `B.REPAIR_ATTEMPT` исключает «уступку под давлением без признания» |
| **user agency** | **инвариант/политика, не метка** | Агентность нельзя разметить постфактум — её либо обеспечивает дизайн, либо нет. Метка создала бы иллюзию измеримости |
| **AI-reliance pressure** | **отдельное longitudinal-измерение** | Это свойство **траектории использования** (распределение обращений, зависимость от системы), а не одного вмешательства. Уже существует в [research-hypotheses.md](research-hypotheses.md) как H1-риск (agent attachment) — там ему и место |
| **transfer back to human interaction** | **в v1, но как `outcome.transfer_observed`** | Наблюдаемо: применил ли пользователь предложенное в реальном обмене. Единственное из «мягких» измерений с определённым источником истины |
| **expected_effect** | **в v1** | Дёшево, и превращает каждое вмешательство в фальсифицируемое предсказание. Без него слой накапливает логи, а не знание |

> **RESEARCH FINDING R-F3 — главная ошибка проектирования, которую тут легко совершить.** Половина предложенных в задаче измерений (`unnecessary`, `missed`, `superficial resolution`) — это **оценочные суждения об исходе**, а не свойства вмешательства. Если они станут полями, кто-то будет их размечать вручную — и слой превратится в скрытую систему оценки без определённого носителя истины.
> Правильно: их **вычислять** из `act` × `observed_effect` × `user_response`. Это делает их фальсифицируемыми и снимает необходимость в разметчике.

---

## 4. Что связывает InterventionOntology с результатами стримов A–D

| Находка | Следствие для intervention-слоя |
|---|---|
| Withdrawal ненаблюдаем в тексте (ICC .52; латентность запрещена как признак; конфаунд с dominance) | **Ни одно вмешательство v1 не может триггериться по withdrawal.** Это самый естественный триггер («партнёр замолчал — вмешайся»), и он опирается на самый ненадёжный сигнал во всей разобранной литературе. Из-за конфаунда с dominance система рискует «помогать» тому, кто осуществляет контроль |
| Escalation-коды надёжнее индивидуальных (.83/.74 vs .52/.30) | **Первый триггер должен быть диадическим** (негативная эскалационная цепочка), а не индивидуальным поведением |
| perceived invalidation неопределим по тексту (R-C2: мост не построен даже в литературе) | Система **не может говорить** «партнёр почувствовал X». Допустимо: «здесь есть ход, который часто воспринимается как…». Формулировка вмешательства — часть его безопасности |
| «Pre-emptive repair» эффективнее (первые 3 минуты) | `timing` — первоклассное измерение; поздние вмешательства ожидаемо слабее и их нельзя сравнивать с ранними напрямую |
| 31 item → 4 фактора | Начинать с 5 стратегий, а не с 11+ |

---

## 5. Negative findings этого стрима

- **Не найден** benchmark relation-aware intervention **для романтических пар**, разделяющий timing/target/strategy/outcome. ProMediConv — юридическая медиация с третьей стороной; ESConv — helper↔seeker, не диада с историей.
- **Не найден** ни один источник, где эффект вмешательства в паре измерялся бы **сдвигом наблюдаемого диадического состояния**. MAD — ближайший аналог, но на другом домене.
- **Не подтверждено**, что 11 стратегий ProMediConv переносятся на пары. Половина («Combining Law with Morality», «Mobilizing Multiple Forces for Assistance», «Reaching a Mediation Agreement») институционально специфичны.
- **Не подтверждено**, что датасет ProMediConv доступен и под какой лицензией — репозиторий не открывался, arXiv-бейдж относится к статье.
- **Не найдено** валидированного инструмента для «AI-reliance pressure» в контексте отношений. Оставлено как гипотеза H1, не как измерение.
