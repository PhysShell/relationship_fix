# DyadicState: минимальная фальсифицируемая модель состояния

Дата: 2026-09-16. Статус: **research-only**. Pilot v0.1 не тронут, ответы не открывались, BehaviorOntology v0.1 не изменена. Код — исследовательский спайк по ADR-0001 §Python (роль 1), не production engine.

Companion: [relational-event-graph.md](relational-event-graph.md) · [episode-segmentation.md](episode-segmentation.md) · [intervention-interface.md](intervention-interface.md) · [couple-coding-systems.md](couple-coding-systems.md) · [ontology-crosswalk.md](ontology-crosswalk.md).

Артефакты: `research/python/dyadic/` · `data/research/dyadic-spike/episodes.jsonl` (26 синтетических кейсов) · `data/research/dyadic-spike/trace.json`.

---

## 0. Research inventory — только то, что нужно для этого вопроса

Полные разборы уже сделаны в [couple-coding-systems.md](couple-coding-systems.md) и [invalidation-review.md](invalidation-review.md); здесь — один вопрос: **какие конструкты требуют exchange/episode/longitudinal и как они связываются во времени?**

### Новый первоисточник: RESCUE-Bench

Hu, Xiao, Tang, Duan, Zhang, He, Zhang, Wang, Hoorn и др., *RESCUE-Bench: Towards Relation-Aware Multi-Party Emotional Support Conversation Systems*, [arXiv:2609.09657](https://arxiv.org/abs/2609.09657) (09.09.2026, HK PolyU и соавторы).

| Поле | Значение |
|---|---|
| existence_verified | yes |
| primary_source_verified | **yes** — HTML статьи прочитан целиком, включая Appendix D (таблицы меток) и G.2 (единица аннотации) |
| raw_data_available | **no** — исходное видео не перераспределяется |
| annotations_available | **unknown** — заявлен релиз через GitHub/HF под **research-only лицензией с контролируемым доступом**; не проверялось |
| license_verified | **no для датасета.** Бейдж CC BY 4.0 на arXiv относится к **статье**. Та же ловушка, что уже задокументирована для BenSyc в [external-corpus-license-matrix.md](external-corpus-license-matrix.md) |

**Состав:** 191 сэмпл (174 couple, 17 family), 7 079 turns, 1 064.8 минут видео. Источник — **публичные документальные видео-интервью пар и семей с YouTube-каналов Couple Therapy и Family Therapy**.

**Couple relation patterns (Table 7, дословно):**

| Метка | Operational meaning | Основание |
|---|---|---|
| `pursue_withdraw` | один партнёр давит/добивается вовлечения, другой «avoids, shuts down, minimizes, or disengages» | EFT |
| `attack_attack` | «Both partners criticize, blame, defend, or counterattack, leading to mutual escalation» | EFT; Gottman |
| `withdraw_withdraw` | «Both partners avoid emotional engagement, show low responsiveness, or mutually disengage» | EFT; Gottman |
| `repair_softening` | «Defensiveness decreases and the interaction begins to show vulnerability, apology, validation, emotional openness, or reconnection» | EFT; Gottman |
| `constructive_alignment` | «Partners move toward shared understanding, cooperation, or joint problem solving» | EFT; IBCT |
| `mixed_transition` | «Multiple relational signals coexist, or the interaction is clearly shifting between two relation patterns» | EFT; IBCT |

**Схема аннотации (Figure 11, дословно из примера):**

```
"relation_cycle_state":         "pursue_withdraw",
"relation_cycle_reason":        "Mia presses for contact, while Josh lowers engagement…",
"relation_cycle_evidence_rows": [18, 19, 20]
```

> **RESEARCH FINDING R-S1 — состояние ссылается на evidence, а не заменяет его.** Независимая работа пришла к той же структуре, которую мы проектируем: состояние несёт **обоснование** и **список строк-доказательств**. Это внешнее подтверждение того, что L4 обязан указывать вниз на L3/L1, а не быть свободным текстом.

**Транзиции (Figure 3, row-normalized, self-transitions исключены):** «relation change is **highly nonlinear**. Negative cycles such as pursue-withdraw and attack-attack **do not usually move directly into stable coordination**; instead, **repair softening often serves as an intermediate state before constructive alignment**. Meanwhile, pursue-withdraw **frequently reappears** after withdraw-withdraw, repair softening, and mixed transition, suggesting that it functions as a **recurring attractor**».

> **RESEARCH FINDING R-S2 — repair это состояние, а не акт.** Эмпирически repair_softening занимает позицию **промежуточного состояния** на пути к constructive_alignment. Это прямой внешний аргумент за расщепление `B.REPAIR_ATTEMPT` ([ontology-crosswalk.md](ontology-crosswalk.md) §4/Q5) и за то, что «успешность repair» принадлежит переходу, а не метке.

> **RESEARCH FINDING R-S3 — единица аннотации там тоже не реплика.** G.2, дословно: «A new row is created when there is a change in **speaker, addressee, interactional function, emotional meaning, or salient nonverbal behavior**». Из пяти критериев **три — суждение аннотатора, а один требует видео**. Ни один не разрешим детерминированным правилом по текстовому логу. Отсюда наш deterministic baseline в [episode-segmentation.md](episode-segmentation.md) — сознательно более слабый.

**Чего RESCUE-Bench НЕ даёт, и это надо держать на виду:**

1. **IAA не сообщён вообще.** Метки получены **LLM-предразметкой**, которую затем **верифицировали три PhD-аннотатора**. Верификация черновика — не независимое кодирование. После находки про anchoring collapse в IDCS-CMC (ICC .87→.51 при снятии якоря, [couple-coding-systems.md](couple-coding-systems.md) §1.4) это **самая слабая из возможных процедур**: LLM-черновик является якорем ещё более сильным, чем master-коды.
2. **Мультимодальность.** Паттерны опираются в том числе на «salient nonverbal behavior». Та же проблема канала, что у WITHDRAWAL.
3. **Присутствует терапевт.** «Intervention timing» = должен ли **терапевт** вмешаться. Как и ProMediConv (юридическая медиация с медиатором), это **third-party-present** сеттинг. Оба наших внешних подтверждения intervention-интерфейса приходят из ситуаций, где третья сторона легитимно присутствует в разговоре. У пары наедине её нет.
4. **Источник — документальные YouTube-видео терапии**, то есть отобранный, смонтированный и согласованный на трансляцию материал.

**Вывод инвентаризации:** RESCUE-Bench пригоден как **архитектурное** свидетельство (состояние↔evidence, нелинейность переходов, необходимость метки для неоднозначности) и **непригоден** как источник валидированных меток или reliability-ориентиров.

---

## 1. Четыре уровня и почему они не схлопываются

```
L1 Evidence             message_id, author, timestamp, дословный span, порядок
L2 BehaviorObservation  локально наблюдаемое поведение + его evidence
L3 RelationalEvent      несколько наблюдений, связанных во времени
L4 StateHypothesis      конкурирующая гипотеза о разворачивающемся паттерне
```

Граница между уровнями — **не слои реализации, а разные истинностные условия**:

| Уровень | Что делает утверждение истинным | Кто может его опровергнуть |
|---|---|---|
| L1 | байты источника | сверка с источником |
| L2 | наличие поведения в предъявленной единице | другой аннотатор на той же единице |
| L3 | порядок и авторство наблюдений | пересегментация или пропущенное наблюдение |
| L4 | повторяемость через **разные** эпизоды | counterevidence или исчезновение опоры |

Схлопывание любых двух уровней уничтожает возможность опровержения на нижнем. Именно поэтому `DyadicState` не собирается как сумма labels: IDCS-CMC определяет escalation через **последовательность** — «consecutive chains … **unrelated** positive behaviors do **not** constitute a snowball effect».

---

## 2. Главное правило: state ≠ diagnosis

`DyadicState` описывает **наблюдаемую траекторию взаимодействия**. Он **не кодирует**: attachment style, личность, нарциссизм, совместимость, «здоровье отношений», «абьюзер», вероятность расставания.

Это не новое правило, а применение существующих: инвариант 7 (observable behavior предпочтительнее identity/diagnosis), инвариант 10 (engine не приписывает недоступные внутренние состояния), safety-policy §3 (no breakup probability / relationship-future score), §12 (capability gating, не диагноз).

**Структурная реализация, а не обещание в прозе:**

- `StateHypothesis.pattern` — строка из закрытого списка паттернов **взаимодействия**; ни один не является свойством человека;
- `participants` — роли в паттерне, а не характеристики (`pursue_withdraw:a+b` означает «a добивается, b не подхватывает **в этих эпизодах**», и обратное направление — отдельная гипотеза с отдельным id);
- **нет ни одного скалярного поля confidence.** Есть `ConfidenceComponents` с именованными счётчиками. Скаляр — это ровно тот объект, который превращается в relationship score;
- тест `test_context_exposes_no_score_and_no_person_attributes` проверяет, что в `InterventionContext.uncertainty` не появляются строки `score`, `health`, `compatibility`, `personality`, `breakup`.

### Coercive control моделируется как накопление, а не как ярлык

```
observed events (across distinct episodes)
    → accumulation
    → capability gate
    → suppression of the symmetric-advice class
```

`SafetyAccumulator` структурно **отделён** от паттернов: он не конкурирует с ними и его нельзя «перевесить» позитивным паттерном. Гейт требует `≥3 различных эпизодов` **и** `≥4 событий` — единичное неоднозначное сообщение открыть его не может (тест `test_single_ambiguous_message_does_not_open_gate`, плюс кейс `safety-single-01` в корпусе). Шесть событий внутри одного эпизода гейт **не** открывают: тест проверяет и это.

Выход — не вердикт, а строка: «capability gate: when open, symmetric couples advice and joint mediation are suppressed. **NOT a determination about any person**». Тест `test_gate_is_a_capability_statement_not_a_verdict` запрещает слову «abuser» появляться в выводе.

---

## 3. Нет единого DyadicState — есть набор конкурирующих гипотез (Q4)

**Это центральное проектное решение, и оно фальсифицируемо.**

Единая переменная состояния невозможна по трём независимым причинам:

1. **К скаляру нельзя приложить counterevidence.** Требование «уметь добавить evidence_against и понизить уверенность» логически требует объекта с собственным ledger'ом. У `state = "attack_attack"` нет места для контрдовода.
2. **Сам внешний прецедент завёл escape hatch.** RESCUE-Bench понадобилась метка `mixed_transition` — «multiple relational signals coexist». Это признание, что однозначное состояние теряет информацию. Мы не добавляем escape hatch, а делаем множественность **нормальной формой**.
3. **Спайк показывает это эмпирически.** В трейсе одновременно живы `attack_attack` (recurring), `repair_softening` (recurring), `constructive_alignment` и `mixed_transition`. Единая переменная была бы вынуждена выбрать одно — и была бы неправа.

Порядок в `competing()` детерминирован (по support_count, затем по id), чтобы трейсы можно было диффать между прогонами.

---

## 4. Absence ≠ counterevidence (Q6 частично, и главный урок WITHDRAWAL)

`EvidenceStatus` различает **пять** состояний:

| Статус | Смысл | Что делает с гипотезой |
|---|---|---|
| `SUPPORTING` | наблюдали, поддерживает | +support, +эпизод, +coverage |
| `COUNTER` | наблюдали, противоречит | +counter, +coverage, **не удаляет support** |
| `ABSENT` | **искали в наблюдаемом окне, не нашли** | только **−coverage** |
| `INSUFFICIENT_OBSERVATION` | **не могли смотреть** (окно обрезано, нет timestamps) | только −coverage |
| `NOT_APPLICABLE` | слот неприменим к этой единице | **ничего** |

Словарь намеренно повторяет уже существующее различение в `metrics.agreement`, где `not_applicable` («не искали») отделён от `underpowered_not_estimable` («искали, мало нашли»). Один и тот же принцип, два слоя.

### Почему это здесь несущая конструкция

Отсутствие сообщений в окне **не является** наблюдаемым withdrawal. Три независимые системы определяют withdrawal через невербальный канал ([couple-coding-systems.md](couple-coding-systems.md) §4/R-B7), а IDCS-CMC прямо запрещает: «A delay in response during CMC **should not automatically be assumed to be withdrawal**».

**Наблюдаемое различение, которое мы вводим:**

```
non-uptake WITH presence   партнёр продолжает писать, но НЕ по поднятой теме
                           → наблюдаемо в тексте       → SUPPORTING

silence                    партнёр перестал писать вообще
                           → НЕ наблюдаемо в тексте    → ABSENT
```

Это, возможно, самый полезный результат этого спайка: **половина pursue-withdraw наблюдаема текстом, половина — нет**, и граница проходит не по паттерну, а по тому, остался ли уходящий партнёр присутствующим.

В трейсе: `pursue_withdraw` имеет `observation_coverage = 0.4444` при 5 незаполненных слотах и постоянном `unobserved_slots: ["withdrawer_internal_disengagement"]`. Три silence-only кейса дали `status: absent` и **пустой** `counterevidence` — тест `test_silence_only_cases_never_confirm_pursue_withdraw` проверяет это end-to-end.

---

## 5. Transition model (Q6 — когда состояние исчезает)

```
State(t) + new event/evidence → State(t+1)
```

Статус выводится **явными правилами** (`derive_status`), не самоотчётом модели:

```
support_count == 0                      → CANDIDATE
counter_count > support_count           → WEAKENED      ← проверяется ПЕРЕД повторяемостью
episodes_since_support >= 3             → WEAKENED
distinct_episodes >= 2                  → RECURRING
support_count >= 2                      → SUPPORTED
иначе                                   → CANDIDATE
```

Порядок проверок значим: counterevidence проверяется **раньше** повторяемости, иначе паттерн смог бы «перевесить» противоречащие наблюдения простым повторением (тест `test_repetition_cannot_outvote_contradiction_ordering`).

**Decay измеряется в наблюдаемых эпизодах, не в wall-clock.** Иначе «он не писал три дня» само станет доказательством — ровно та ошибка, которую запрещает §4. `_episodes_since` считает эпизоды, прошедшие с последней поддержки.

**Retirement — смена статуса, не удаление.** `retire()` сохраняет весь ledger; инвариант 8 требует, чтобы findings оставались проверяемыми, включая отозванные.

**Запрещённая архитектура** `latest LLM summary = current truth` исключена структурно: в ledger нет пути записи, принимающего свободный текст. Единственный вход — `RelationalEvent` с типизированным статусом и ссылками на наблюдения.

---

## 6. Три worked examples (из реального трейса, не придуманные)

### A — escalation (`esc-01`)

```
a: «Ты опять не закрыл счета за месяц.»       → PRESSURE_FOR_CHANGE
b: «Я работал. У тебя вечно претензии.»        → BLAME_CRITICISM
a: «С тобой всегда так, на тебя нельзя…»       → BLAME_CRITICISM
```

События из трейса:

```
attack_attack      supporting     obs=[o1,o2,o3]
pursue_withdraw    insufficient   obs=[o1,o3]        ← a дважды давит, но реакция b
                                                       НЕ является наблюдаемым non-uptake
```

Гипотеза после эпизода: `attack_attack` → `CANDIDATE` (один эпизод — не паттерн).
Contraindications: `no_recurring_pattern__single_episode_is_not_a_pattern`.

> Обратите внимание: модель **одновременно** открыла вторую гипотезу и честно пометила её как непроверяемую, вместо того чтобы либо проигнорировать, либо подтвердить.

### B — repair (`rep-02`)

```
a: «Ты меня не слушаешь вообще.»                        → BLAME_CRITICISM
b: «Я слышу, что тебе обидно. Давай переформулирую.»    → VALIDATION
a: «Да, давай попробуем ещё раз.»                       → AGREEMENT
b: «Договорились, сделаем вместе в выходные.»           → JOINT_PLAN
```

```
repair_softening        supporting    ← softening + отсутствие последующего негатива партнёра
constructive_alignment  supporting    ← обе стороны дали aligning-ход
mixed_transition        supporting    ← негатив и softening сосуществуют
```

Три гипотезы живы **одновременно**, и это правильно: RESCUE-Bench эмпирически показывает, что repair_softening — промежуточное состояние **перед** constructive_alignment, а не альтернатива ему.

### C — ambiguous (`amb-01`) и провалившийся repair (`rep-fail-01`)

```
a: «Ты опять со своими шуточками…»          → BLAME_CRITICISM
b: «Ладно, прости. Но ты тоже хороша.»       → APOLOGY + DEFENSIVENESS
a: «Проехали.»
```

```
attack_attack      supporting    obs=[o1,o3]
repair_softening   supporting    obs=[o2]
mixed_transition   supporting    obs=[o1,o2,o3]
```

**Одно и то же локальное поведение питает три гипотезы сразу.** Единая переменная состояния обязана была бы выбрать — и любой выбор был бы потерей.

Контрастный кейс `rep-fail-01` («Извини конечно, но это ты всё начала»):

```
attack_attack      supporting
repair_softening   COUNTER        ← извинение было, но партнёр продолжил негатив
mixed_transition   supporting
```

Тот же поверхностный ход (`APOLOGY`) даёт **supporting** в одном случае и **counter** в другом, и различает их **последующее поведение партнёра**, а не тон извинения. Это и есть ответ на Q7.

---

## 7. Ответы на Q1–Q10

**Q1 — что остаётся BehaviorObservation.** Всё, чьё истинностное условие содержится в предъявленной единице: blame/criticism (генерализующая форма), apology, taking_responsibility, validation, topic_shift, neutral_request, on_topic_reply, defensiveness, off_topic_message. Плюс наблюдаемые safety-релевантные ходы (monitoring, isolation pressure) — как наблюдения, **никогда** не как свойство человека.

**Q2 — что живёт только на Episode level.** Всё, что определено через **отношение между ходами**: escalation/de-escalation, non-uptake (нужна поднятая тема), repair как процесс, avoidance (нужен предшествующий вопрос), повторение требования.

**Q3 — что требует longitudinal.** Повторяемость как таковая (`RECURRING` по определению требует ≥2 различных эпизодов), pursue-withdraw как **паттерн** (а не как единичная асимметрия), накопление coercive control, staleness/decay. Ни одно из них не может быть утверждено по одному эпизоду.

**Q4 — нужен ли единый DyadicState.** **Нет.** Набор конкурирующих гипотез. Обоснование — §3, подтверждено трейсом.

**Q5 — как представлять competing interpretations.** Каждая гипотеза — самостоятельный объект с `evidence_for`, `evidence_against`, `unobserved_slots`, `supporting_episodes` и статусом. Они не нормализуются в распределение вероятностей: нормализация заставила бы их конкурировать за общую массу, а `attack_attack` и `repair_softening` **не** взаимоисключающи.

**Q6 — когда состояние исчезает.** Не по времени, а по **наблюдаемым эпизодам без поддержки** (≥3 → WEAKENED). Явный `retire()` сохраняет запись. См. §5.

**Q7 — repair attempt vs repair transition.** `repair_attempt` — L2-наблюдение (произошло или нет, решается по реплике). **Repair transition** — свойство L3/L4: попытка + отсутствие продолжения негатива партнёром + сдвиг статуса гипотезы. В коде это буквально разные объекты: `APOLOGY` — observation, `repair_softening` со статусом `SUPPORTING` vs `COUNTER` — event. Внешнее подтверждение: RESCUE-Bench размещает repair_softening как **состояние**, промежуточное к constructive_alignment.

**Q8 — можно ли моделировать pursue-withdraw text-only без запрещённого вывода.** **Наполовину, и эта половина именно та, которую можно назвать.** Pursue-сторона наблюдаема (повторное поднятие темы, нарастающее давление — лексически видимо). Withdraw-сторона наблюдаема **только** как non-uptake-with-presence. Чистое молчание → `ABSENT`, и гипотеза не может достичь `RECURRING` на таком материале. Слот `withdrawer_internal_disengagement` объявлен ненаблюдаемым **в схеме**, а не обнаруживается в рантайме.

**Q9 — минимальная сегментация для MVP.** Временной разрыв + жёсткий cap на длину. Чередование говорящих **не** является границей. См. [episode-segmentation.md](episode-segmentation.md).

**Q10 — интерфейс для InterventionOntology.** См. [intervention-interface.md](intervention-interface.md).

---

## 8. Что спайк опроверг и что оказалось лишним

**Опровергнуто в ходе работы:**

1. **«Повторяемость можно вывести из first_seen/last_supported».** Нельзя. Первая реализация выводила `distinct_episodes` из множества трёх полей и **упиралась в 3**: паттерн из двадцати эпизодов был неотличим от паттерна из трёх. Обнаружено чтением трейса, а не тестом. Исправлено явным `supporting_episodes`; регрессионный тест `test_distinct_episodes_counts_every_supporting_episode`.
2. **«Производные поля переживут сериализацию сами».** Нет. `dataclasses.asdict` рекурсивно разворачивает вложенные dataclass'ы **до** того, как срабатывает hook, и `observation_coverage` молча исчезал из трейса — то есть читатель трейса не мог отличить «не смогли посмотреть» от «посмотрели и не нашли». Ровно та путаница, против которой построена вся модель, и она возникла внутри неё самой из-за детали сериализации.
3. **«Chronemics даст withdrawal».** Нет: см. §4.

**Оказалось лишним / отложено:**

- **Graph DB.** Не нужна. Рёбра между событиями (`EventEdge`) в спайке вообще не понадобились для трёх worked examples: связность оказалась выразима через `source_observations` и порядок. Тип оставлен в модели как объявление намерения, но **не используется** — и это честнее, чем поставить Neo4j под три ребра.
- **Вероятности.** Нормализованное распределение по паттернам было бы неверным (§Q5).
- **Отдельный тип для turn.** Между utterance и exchange не обнаружилось работы, которую делал бы `turn`.
- **Ребро `INTERRUPTS`.** В тексте прерывание не наблюдаемо так, как в речи.

---

## 9. Falsification criteria

Модель неверна, если выполняется хоть одно:

| # | Критерий | Как проверить |
|---|---|---|
| F1 | Существует конструкт, который нужен продукту и **не** выражается ни на одном из четырёх уровней | перечислить его и показать, куда он не помещается |
| F2 | Два независимых человека, размечающих **эпизоды** (не реплики) на relation pattern, дают α < 0.4 | эксперимент из [next-research-design.md](next-research-design.md), паттерн-разметка на отдельном наборе обменов |
| F3 | `non-uptake with presence` **не** различается разметчиками надёжнее, чем silence | тот же эксперимент, две подгруппы items |
| F4 | Набор конкурирующих гипотез на реальных данных вырождается: всегда ровно одна живая | прогон на реальном корпусе; если так — единая переменная была бы достаточна |
| F5 | Правило decay (3 эпизода) даёт осцилляцию на реальных данных так же, как на синтетике | в текущем трейсе **21 транзиция на 27 эпизодов** — гипотезы колеблются weakened↔recurring. На синтетике это артефакт редких кейсов, но на реальных данных это стало бы дефектом |
| F6 | Safety-гейт срабатывает на материале без coercive control | прогон на нейтральном корпусе; ожидаемое число срабатываний — ноль |
| F7 | Детерминированная сегментация даёт эпизоды, на которых паттерны не собираются, а семантическая — даёт | сравнение baseline vs LLM-сегментация на одном материале |

> **F5 уже наполовину сработал.** 21 транзиция на 27 эпизодов — это много. На синтетическом корпусе, где кейсы намеренно разнородны, осцилляция ожидаема; но если то же соотношение появится на реальном материале, правило staleness придётся делать гистерезисным (разные пороги на вход и на выход из `WEAKENED`). **Это записано как известный дефект, а не как свойство.**
