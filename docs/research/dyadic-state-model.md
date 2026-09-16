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
L1   Evidence / Message     message_id, author, timestamp, дословный span, порядок
L1.5 Conversation topology  кто на какое СООБЩЕНИЕ структурно ответил
L2   BehaviorObservation    локально наблюдаемое поведение + его evidence
L2.5 InteractionRelation    отношение L1.5, обогащённое наблюдениями на концах
L3   RelationalEvent        событие, собранное ИЗ ОТНОШЕНИЙ
L4   StateHypothesis        одновременная гипотеза о разворачивающемся паттерне
```

### L1.5 появился из selection bias, а не из аккуратности

Первая версия `InteractionRelation` строилась **между `BehaviorObservation`**, а `responds_to` определялся как «следующее **наблюдение** другого актора». Это не то же самое, что «следующая **реплика** другого актора»:

```
m1  A: обвинение        → observation BLAME
m2  B: «понял»          → НИКАКОГО observation
m3  B: меняет тему      → observation TOPIC_SHIFT
```

Для старого алгоритма `m3` становился ответом на `m1`, потому что `m2` **просто исчезал из топологии**. Хуже: несколько labels на одной реплике делали топологию зависимой от порядка перечисления наблюдений.

То есть bag of labels мы починили, а relation graph продолжал строиться **на отфильтрованном онтологией представлении разговора**:

```
raw conversation → оставили только интересные labeled behaviors
                 → из них восстановили структуру разговора      ← selection bias
```

Теперь наоборот:

```
raw conversation → MessageRelation между ВСЕМИ сообщениями
                 → BehaviorObservation привязаны к сообщениям
                 → InteractionRelation = MessageRelation + наблюдения на концах
```

`MessageNode` (`message_id`, `actor`, `order`, `timestamp`, `topic?`, `reply_to?`) и `MessageRelation` (`next_by_other_actor`, `explicit_reply_to`, `topic_continuity`, `topic_discontinuity`) считаются **до и независимо от разметки**. Ни одно interaction-отношение не существует без факта структуры разговора под ним: у `RelationEdge` есть поле `via_message_relation`, и тест требует, чтобы оно было заполнено.

> **Ирония, которую стоит записать.** Прошлая итерация отдельно отметила, что `turn`-слой «не делает никакой работы» и не нужен. Отдельный domain type `Turn`, возможно, действительно не нужен — но **raw message topology как слой оказалась несущей**. Архитектура мстит за самоуверенность быстрее, чем хотелось бы.

### L2.5 появился не из красоты, а из дефекта

Первая версия спайка собирала L3 **из совместной встречаемости labels внутри эпизода**: `attack_attack` возникал, если у обоих есть любой негатив где угодно в сорока сообщениях — **не требовалось, чтобы второй ход отвечал на первый**. То же с `constructive_alignment` и даже с `pursue_withdraw`, который связывал преследование и off-topic-ответ по принадлежности эпизоду, а не отношением «этот ответ не подхватил **именно эту** попытку вовлечения».

Это был bag of labels в пальто interaction model. Весь смысл L3 — `observations related through interaction`, а не `labels co-occurred somewhere`.

`InteractionRelation` — минимальный набор направленных отношений, каждое решаемое из **порядка, автора и записанной темы**:

| Отношение | Правило | Статус |
|---|---|---|
| `adjacent_cross_actor_turn` | следующий ход другого человека | детерминированное |
| `explicit_reply` | лог сам говорит, на что это ответ | детерминированное |
| `topic_continuity` / `topic_discontinuity` | та же / другая **записанная** тема | детерминированное по записи |
| `negative_response` | негативный ход рядом с негативным | детерминированное |
| `softening_response` | softening рядом с негативным | детерминированное |

### Чего в этом списке намеренно нет

**`RESPONDS_TO` больше не выводится из смежности.** «Следующая реплика другого человека» лицензирует ровно `adjacent_cross_actor_turn` — и не более. Она может быть ответом, а может быть новым сообщением, параллельной темой или реакцией на что-то гораздо более старое. Выводя `responds_to` из смежности, мы **утверждали ровно то, что хотим дать проверить людям**. Теперь это **эмпирическое** отношение для primitives-пилота, а детерминированно утверждается только `explicit_reply`, где так говорит сам лог.

```
L1.5 deterministic:   NEXT_BY_OTHER_ACTOR · EXPLICIT_REPLY_TO
L2.5 empirical:       RESPONDS_TO · CONTINUES_TOPIC · TOPIC_DISCONTINUITY
```

**`ESCALATES` сузился до `NEGATIVE_RESPONSE`.** Эскалация предполагает конфликт, **сохранённый или усиленный во времени**, чего одна смежная пара показать не может:

> A: «ты всё испортила»
> B: «мне тоже было неприятно, как ты себя повёл»

Это negative-negative по онтологии и **не обязательно** эскалация. Escalation остаётся L3-кандидатом, а не примитивом, который кого-то просят увидеть.

**`NON_UPTAKE`** — см. ниже.

### Примитива `non_uptake` больше нет

Он был определён как `responds_to + другая тема` и **трактовался в комментарии как «present but not engaging»**. Это разные утверждения:

> A: «Мне было обидно, что ты не пришёл.»
> B: «Понимаю. И хочу объяснить, почему вчера всё сорвалось.»

Тема сменилась — но ответ сначала **принял** её и затем расширил разговор. Одна реплика может отвечать сразу двум темам. А `topic` у нас вообще **supplied annotation**, то есть уже выход классификатора, а не сырое свойство сообщения.

Примитив теперь называется максимально тупо — **`topic_discontinuity`**, ровно то, что он измеряет. **Non-uptake доказывается на уровне события** и требует дополнительного наблюдаемого условия: тема разошлась **И** в отвечающем сообщении **нигде** нет uptake-наблюдения. Кейс выше даёт `VALIDATION` на `m2`, поэтому non-uptake не объявляется (`test_reply_that_takes_the_topic_up_and_widens_it_is_not_non_uptake`).

Иначе психологический вывод снова прятался бы внутри якобы детерминированного relation predicate — на этаж ниже, чем в прошлый раз.

`topic` **подаётся корпусом ровно как labels**. Тематическая связность не решается детерминированно из сырого текста, и делать вид, что решается, означало бы спрятать классификатор внутри предиката. Без темы отношения `continues_topic`/`non_uptake` просто не порождаются — модель молчит, а не угадывает (тест `test_missing_topic_yields_no_topic_relation`).

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

## 3. Одной mutually-exclusive categorical state недостаточно (Q4)

**Предыдущая формулировка «единый DyadicState невозможен» была сильнее доказанного.** Доказано другое, и только это: **одной взаимоисключающей категориальной метки состояния недостаточно**. Объект-снимок вполне нормален:

```
DyadicStateSnapshot {
    hypotheses[]          одновременные, не обязательно конкурирующие
    safety_state
    observation_context
}
```

Метод называется `concurrent()`, а не `competing()`, и это не косметика: `attack_attack` и `repair_softening` **сплошь и рядом держатся одновременно и ни за что не соперничают**. Настоящее соперничество — частный случай, а не общая форма; ровно это показывает §6.

Одной категориальной метки недостаточно по трём независимым причинам:

1. **К скаляру нельзя приложить counterevidence.** Требование «уметь добавить evidence_against и понизить уверенность» логически требует объекта с собственным ledger'ом. У `state = "attack_attack"` нет места для контрдовода.
2. **Сам внешний прецедент завёл escape hatch.** RESCUE-Bench понадобилась метка `mixed_transition` — «multiple relational signals coexist». Это признание, что однозначное состояние теряет информацию. Мы не добавляем escape hatch, а делаем множественность **нормальной формой**.
3. **Спайк показывает это эмпирически.** В трейсе одновременно живы `attack_attack`, `repair_softening`, `constructive_alignment` и `pursue_withdraw`. Одна категориальная метка была бы вынуждена выбрать одно — и была бы неправа.

### `mixed_transition` убран из таксономии гипотез

Прежняя версия торжественно отменяла escape hatch — и тут же селила его на соседнюю полку как третью peer-гипотезу с собственным ledger'ом. Теперь это **производное свойство**:

```
is_mixed_transition = (живёт установленная негативная гипотеза)
                      AND (живёт установленная softening-гипотеза)
```

Ни evidence ledger, ни статуса, ни старения. Считается только по гипотезам со статусом `SUPPORTED`/`RECURRING`: два одноэпизодных кандидата не делают снимок «смешанным», иначе свойство истинно с третьего эпизода навсегда и не значит ничего.

Порядок в `concurrent()` детерминирован (по support_count, затем по id), чтобы трейсы можно было диффать между прогонами.

---

## 4. Absence ≠ counterevidence (Q6 частично, и главный урок WITHDRAWAL)

`EvidenceStatus` различает **пять** состояний:

| Статус | Смысл | Что делает с гипотезой |
|---|---|---|
| `SUPPORTING` | наблюдали, поддерживает | +support, +эпизод |
| `COUNTER` | наблюдали, противоречит | +counter, **не удаляет support** |
| `OBSERVED_ABSENCE` | **окно было открыто, вещи там не было** | +observed_absence; **coverage не падает**; **является opportunity** |
| `RIGHT_CENSORED` | **запись кончилась раньше исхода** | −coverage; **не старит** |

> **`RIGHT_CENSORED` — структурная метадата доступности наблюдения, а не human-annotated interaction primitive.** Она выводится из L1/L1.5 (`trigger message + record ends`), и человеку в ней нечего согласованно видеть. Pilot B это проверил на себе: первая версия его корпуса содержала страту `right_censored`, где A и B оказались одним сообщением, и людям задавался вопрос «является ли B ответом на A?». Страта удалена как концепт ([interaction-primitives-v0-prereg.md](interaction-primitives-v0-prereg.md) §2). Сущность переезжала вниз по архитектуре трижды — психологический исход → evidence status → свойство доступности записи — и каждый переезд делал систему менее мистической.
| `INSUFFICIENT_OBSERVATION` | не могли смотреть (нет окна, нет timestamps) | −coverage; **не старит** |
| `NOT_APPLICABLE` | слот неприменим к этой единице | **ничего** |

### Censoring: «не ответил» и «запись кончилась» — разные факты

Прошлая версия объявляла repair без следующего наблюдения `ABSENT`. Но если лог просто оборвался сразу после «прости», мы **не знаем**, что партнёр не ответил — мы знаем только, что запись кончилась. Разница стала критичной ровно тогда, когда `ABSENT` начал старить гипотезу, а `INSUFFICIENT` — нет: слишком мощное различие для слишком неформального решения.

Теперь окно решается топологией, детерминированно:

| Что в топологии | Статус |
|---|---|
| есть следующее сообщение партнёра, и на нём есть наблюдение | классифицируем (support / counter) |
| есть следующее сообщение партнёра, но на нём **нет** ничего кодируемого | **`OBSERVED_ABSENCE`** — они ответили, отклика не было |
| следующего сообщения партнёра **нет** | **`RIGHT_CENSORED`** |

### Coverage считал `ABSENT` как «не смогли посмотреть»

Внутреннее противоречие прошлой версии: `ABSENT` документировался как «looked in an observable window, not found», а ledger инкрементировал ему `unobservable_slots` и **понижал** coverage. Если мы действительно посмотрели и убедились в отсутствии — наблюдение **было** доступно.

```
observable = observed_support + observed_counter + observed_absence
coverage   = observable / (observable + insufficient_observation)
```

`OBSERVED_ABSENCE` не является counterevidence — но и не является отсутствием возможности наблюдать.

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

В трейсе: `pursue_withdraw` имеет `observation_coverage = 0.50` (3 support + 2 counter наблюдаемых против 5 обрезанных) и постоянный `unobserved_slots: ["withdrawer_internal_disengagement"]`. Silence-only кейсы дают `right_censored` и **пустой** `counterevidence`.

### Тот же дефект жил внутри repair — и документация была лучше реализации

Первая версия спайка содержала буквально `if later_negative: COUNTER else: SUPPORTING`. То есть **«я сказал „прости“, и дальше ничего плохого не случилось» засчитывалось как поддержанный repair** — даже если партнёр вообще ничего не ответил. Ровно тот inference, от которого мы только что спасали WITHDRAWAL, живший в соседней функции.

Тезис `repair attempt != successful repair` был лучше документацией, чем кодом. Теперь:

| Ситуация | Статус |
|---|---|
| softening + **наблюдаемый** uptake/деэскалация партнёра | `SUPPORTING` |
| softening + возобновлённый негатив партнёра | `COUNTER` |
| softening + **партнёр не ответил вообще** | `ABSENT` |
| softening + ответ вне известных категорий | `INSUFFICIENT_OBSERVATION` |

`repair_softening` в трейсе: 6 support, 1 counter, 1 observed_absence, 14 обрезанных/вне frame, `observation_coverage = 0.3636`.

Показательно, что `observed_absence` у repair теперь **1**: после ужесточения coding-frame-правила почти все прежние «отсутствия» оказались случаями, где отклик просто **не был закодирован**, и мы не имели права называть это отсутствием. У `attack_attack` при этом 16 настоящих observed_absence — там отклики закодированы.

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

**Decay измеряется в eligible observation opportunities, не в прошедших эпизодах и не в wall-clock.**

Прежняя версия объявляла «decay в наблюдаемых эпизодах», но считала **любой** следующий эпизод. Получалась скрытая форма ровно запрещённого вывода:

```
не наблюдали  →  прошло три эпизода  →  гипотеза ослабла
```

Теперь эпизод старит гипотезу, **только если паттерн вообще мог в нём проявиться**: `observe_episode` принимает множество `opportunities`, и `_opportunities_since_support` считает лишь их. Спокойная неделя бытовой переписки гипотезу не ослабляет.

Политика по статусам объявлена явно константой `OBSERVED_ABSENCE_IS_AN_OPPORTUNITY = True`, а не выведена случайно:

| Статус | Старит? | Почему |
|---|---|---|
| `OBSERVED_ABSENCE` | **да** | отклик разрешён, в coding frame, исхода нет |
| `RIGHT_CENSORED` | **нет** | запись кончилась раньше исхода |
| `INSUFFICIENT_OBSERVATION` | **нет** | отклик вне coding frame — не знаем, проверяли ли |
| `NOT_APPLICABLE` | **нет** | слот неприменим |
| *(события нет вовсе)* | **нет** | отсутствие события — отсутствие информации |

### Канала `opportunities` больше нет вообще

Предыдущая версия считала возможности **отдельной функцией**, параллельно событиям. Это давало третий способ получить скрытое `absence → weakening`: ledger записывал эпизод в `opportunity_episodes`, даже если **ни одного события не возникло**, и через три таких эпизода ослаблял гипотезу. Тест это даже закреплял как ожидаемое поведение — с пустым списком событий.

Спрятанная предпосылка: «если отклик был доступен для наблюдения, но SUPPORTING-события не появилось, значит паттерна не было». Это верно **только** если coding frame был исчерпывающим относительно этого паттерна. А `BehaviorObservation` такого не утверждает: отсутствие `BLAME_CRITICISM` в списке может означать и «проверили, нет», и «такое здесь вообще не размечали».

Теперь **события — единственный вход ledger'а**, и ничто не выводится из их отсутствия. Каждый сработавший триггер обязан материализоваться в событие со статусом:

```
нет отклика вообще              → RIGHT_CENSORED
отклик вне coding frame         → INSUFFICIENT_OBSERVATION
отклик несёт unwanted           → COUNTER
отклик несёт wanted             → SUPPORTING
отклик закодирован, ни то ни сё → OBSERVED_ABSENCE
```

Третья ступень — та, ради которой всё это. `OBSERVED_ABSENCE` стал **редким и осмысленным**: он требует, чтобы отклик был *разрешён*, *попал в coding frame* и *не нёс исхода*.

Правило `absence ≠ counterevidence` перестало быть договорённостью между двумя функциями и стало **свойством метода `observe_episode`**.

Демонстрация в корпусе: `adv-frame-01` и `adv-frame-02` — **одни и те же сообщения**, различается только объявленный coding frame. Первый даёт `OBSERVED_ABSENCE`, второй — `INSUFFICIENT_OBSERVATION`.

> **Ограничение спайка, названное явно.** Если `coded_messages` не объявлен, код берёт прокси «сообщение закодировано, если на нём есть хоть одно наблюдение». Это **прокси, а не факт**; настоящий pipeline обязан объявлять coding frame отдельно, а не выводить его из наличия меток.

### Одна каноническая политика разрешения отклика

`build_topology()` знал сильный сигнал (`EXPLICIT_REPLY_TO`) и слабый (`NEXT_BY_OTHER_ACTOR`), но `repair_softening` разрешал отклик через функцию, которая брала **просто следующее сообщение другого человека** и `reply_to` не смотрела вовсе:

```
m1  A: «Прости за вчера»
m2  B: «Купи молоко»
m3  B: [explicit reply to m1] «Спасибо, я это ценю»
```

Топология знала `m1 → m3`, а repair-оценщик брал `m2`. **L1.5 была умнее, чем L3, и L3 ею не пользовалась.**

Теперь одна политика — `response_candidates()` возвращает **список** кандидатов с указанием основания, explicit-reply первым; `resolve_response()` берёт лучшего. Никаких вероятностей: только основание, чтобы вызывающий решал в открытую.

Эффект виден в числах: транзиций **9 на 40 эпизодов** против 21/27 в первой версии, 13/32 во второй и 8/37 в третьей. Тест `test_decay_needs_eligible_opportunities_not_elapsed_episodes` прогоняет шесть эпизодов без возможности — статус не меняется — и затем три реальные возможности без поддержки — статус падает.

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
attack_attack      supporting     ← негатив b ОТВЕЧАЕТ на негатив a (relation: escalates)
pursue_withdraw    insufficient   ← a дважды давит, но реакция b не является
                                     наблюдаемым non-uptake
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
repair_softening        supporting    ← softening + НАБЛЮДАЕМЫЙ uptake партнёра
constructive_alignment  supporting    ← aligning-ход ОТВЕЧАЕТ на aligning-ход
```

Две гипотезы живы **одновременно**, и это правильно: RESCUE-Bench эмпирически показывает, что repair_softening — промежуточное состояние **перед** constructive_alignment, а не альтернатива ему. `mixed_transition` здесь не появляется как третья сущность — он выводится из того, что обе живы.

### C — ambiguous (`amb-01`) и провалившийся repair (`rep-fail-01`)

```
a: «Ты опять со своими шуточками…»          → BLAME_CRITICISM
b: «Ладно, прости. Но ты тоже хороша.»       → APOLOGY + DEFENSIVENESS
a: «Проехали.»
```

```
repair_softening   absent        ← «прости» есть, но «Проехали» не является
                                   наблюдаемым uptake
```

Показательно: после ужесточения предикатов этот кейс **перестал** порождать `attack_attack`. Раньше он его порождал — потому что негатив a и защита b просто сосуществовали в эпизоде. Теперь требуется, чтобы один ход **отвечал** другому, и оказалось, что здесь такого отношения нет.

Это и есть разница между bag of labels и interaction model, измеренная на одном кейсе.

Контрастный кейс `rep-fail-01` («Извини конечно, но это ты всё начала»):

```
attack_attack      supporting
repair_softening   COUNTER        ← извинение было, но партнёр продолжил негатив
```

Тот же поверхностный ход (`APOLOGY`) даёт **supporting** в одном случае и **counter** в другом, и различает их **последующее поведение партнёра**, а не тон извинения. Это и есть ответ на Q7.

---

## 7. Ответы на Q1–Q10

**Q1 — что остаётся BehaviorObservation.** Всё, чьё истинностное условие содержится в предъявленной единице: blame/criticism (генерализующая форма), apology, taking_responsibility, validation, topic_shift, neutral_request, on_topic_reply, defensiveness, off_topic_message. Плюс наблюдаемые safety-релевантные ходы (monitoring, isolation pressure) — как наблюдения, **никогда** не как свойство человека.

**Q2 — что живёт только на Episode level.** Всё, что определено через **отношение между ходами**: escalation/de-escalation, non-uptake (нужна поднятая тема), repair как процесс, avoidance (нужен предшествующий вопрос), повторение требования.

**Q3 — что требует longitudinal.** Повторяемость как таковая (`RECURRING` по определению требует ≥2 различных эпизодов), pursue-withdraw как **паттерн** (а не как единичная асимметрия), накопление coercive control, staleness/decay. Ни одно из них не может быть утверждено по одному эпизоду.

**Q4 — нужен ли единый DyadicState.** Объект-снимок нужен; **одной взаимоисключающей категориальной метки внутри него — нет**. Набор **одновременных** (не обязательно конкурирующих) гипотез. Обоснование — §3.

**Q5 — как представлять concurrent interpretations.** Каждая гипотеза — самостоятельный объект с `evidence_for`, `evidence_against`, `unobserved_slots`, `supporting_episodes` и статусом. Они не нормализуются в распределение вероятностей: нормализация заставила бы их конкурировать за общую массу, а `attack_attack` и `repair_softening` **не** взаимоисключающи.

**Q6 — когда состояние исчезает.** Не по времени и не по числу прошедших эпизодов, а по **eligible observation opportunities без поддержки** (≥3 → WEAKENED). Явный `retire()` сохраняет запись. См. §5.

**Q7 — repair attempt vs repair transition.** `repair_attempt` — L2-наблюдение (произошло или нет, решается по реплике). **Repair transition** — свойство L3/L4: попытка + отсутствие продолжения негатива партнёром + сдвиг статуса гипотезы. В коде это буквально разные объекты: `APOLOGY` — observation, а `repair_softening` со статусом `SUPPORTING` / `COUNTER` / `ABSENT` — event, и различает их **наблюдаемый отклик партнёра**, а не сам факт извинения. Внешнее подтверждение: RESCUE-Bench размещает repair_softening как **состояние**, промежуточное к constructive_alignment.

**Q8 — можно ли моделировать pursue-withdraw text-only без запрещённого вывода.** **Наполовину, и эта половина именно та, которую можно назвать.** Pursue-сторона наблюдаема (повторное поднятие темы, нарастающее давление — лексически видимо). Withdraw-сторона наблюдаема **только** как non-uptake-with-presence. Чистое молчание → `ABSENT`, и гипотеза не может достичь `RECURRING` на таком материале. Слот `withdrawer_internal_disengagement` объявлен ненаблюдаемым **в схеме**, а не обнаруживается в рантайме.

**Q9 — минимальная сегментация для MVP.** Временной разрыв + жёсткий cap на длину. Чередование говорящих **не** является границей. См. [episode-segmentation.md](episode-segmentation.md).

**Q10 — интерфейс для InterventionOntology.** См. [intervention-interface.md](intervention-interface.md).

---

## 8. Что спайк опроверг и что оказалось лишним

**Опровергнуто в ходе работы:**

1. **«Повторяемость можно вывести из first_seen/last_supported».** Нельзя. Первая реализация выводила `distinct_episodes` из множества трёх полей и **упиралась в 3**: паттерн из двадцати эпизодов был неотличим от паттерна из трёх. Обнаружено чтением трейса, а не тестом. Исправлено явным `supporting_episodes`; регрессионный тест `test_distinct_episodes_counts_every_supporting_episode`.
2. **«Производные поля переживут сериализацию сами».** Нет. `dataclasses.asdict` рекурсивно разворачивает вложенные dataclass'ы **до** того, как срабатывает hook, и `observation_coverage` молча исчезал из трейса — то есть читатель трейса не мог отличить «не смогли посмотреть» от «посмотрели и не нашли». Ровно та путаница, против которой построена вся модель, и она возникла внутри неё самой из-за детали сериализации.
3. **«Chronemics даст withdrawal».** Нет: см. §4.
4. **«Тезис `repair attempt != successful repair` реализован».** Не был. Код делал `else: SUPPORTING`, то есть засчитывал молчание партнёра как успешный repair. Документ был честнее реализации — самый неприятный вид расхождения, потому что его не видно в прозе. См. §4.
5. **«Decay в наблюдаемых эпизодах».** Считались **все** эпизоды подряд, что давало скрытое «не наблюдали → ослабло». См. §5.
6. **«Мы отменили escape hatch».** `mixed_transition` был отменён как обязанность выбрать одну метку и тут же оставлен жить peer-гипотезой с собственным ledger'ом. См. §3.
7. **«L3 — interaction model».** Был bag of labels: `attack_attack` не требовал, чтобы один ход отвечал другому. См. §1.
8. **«Relation graph построен на разговоре».** Был построен на **отфильтрованном онтологией** представлении: топология шла по `BehaviorObservation`, неразмеченная реплика исчезала, несколько labels на одной реплике меняли форму графа. Selection bias на этаж ниже предыдущего. См. §1/L1.5.
9. **«`non_uptake` — детерминированный примитив».** Он был определён как «другая тема» и **трактовался** как «присутствует, но не вовлекается». Ответ может принять тему и расширить её. См. §1.
10. **«`ABSENT` понижает coverage».** Противоречие внутри одной строки документации: «looked in an observable window» и одновременно `unobservable_slots += 1`. Если мы посмотрели — наблюдение было доступно. См. §4.
11. **«Отсутствие следующего наблюдения = партнёр не ответил».** Нет: это может быть конец записи. Censoring выделен отдельно. См. §4.
12. **«Opportunity = в эпизоде был негатив».** Слишком широко: один негативный ход открывал окно сразу двум паттернам, включая тот, которому нужно повторное преследование.
13. **«Opportunities как отдельный канал безопасны».** Нет: они давали третий путь к `absence → weakening` — ledger старил гипотезу на эпизоде **без единого события**, молча предполагая, что coding frame исчерпывающий. Канал удалён целиком. См. §5.
14. **«Отсутствие метки = проверили и не нашли».** Не отличимо от «здесь не размечали». Введён coding frame; некодированный отклик — `INSUFFICIENT`, не `OBSERVED_ABSENCE`. **Мой собственный adversarial-кейс `adv-noncodable-01` был неправ** и переименован.
15. **«Одна response-resolution политика».** Их было две: топология знала `explicit_reply_to`, а repair-оценщик брал смежное сообщение. L1.5 была умнее L3, и L3 ею не пользовалась. См. §5.
16. **«`responds_to` — детерминированное отношение».** Нет: смежность лицензирует только `adjacent_cross_actor_turn`. `RESPONDS_TO` — эмпирическое отношение, которое должны проверить люди. См. §1.
17. **«`escalates` — примитив».** Одна смежная негативная пара не показывает конфликт во времени. Сужено до `NEGATIVE_RESPONSE`; escalation остаётся L3-кандидатом. См. §1.

**Оказалось лишним / отложено:**

- **Graph DB.** По-прежнему не нужна. Но прежний вывод «рёбра не понадобились» был неверен **уровнем**: не понадобились рёбра между **событиями** (`EventEdge` удалён), а вот рёбра между **наблюдениями** оказались недостающим этажом и теперь несущие (`RelationEdge`, §1). Хранилище от этого не меняется: это список рёбер внутри эпизода, а не граф, который нужно индексировать.
- **Вероятности.** Нормализованное распределение по паттернам было бы неверным (§Q5).
- **Отдельный domain type `Turn`.** По-прежнему не нужен как тип. Но вывод «между utterance и exchange нет работы» был **неверен**: работа есть, и её делает `MessageNode` — raw message topology. Слой понадобился, имя `Turn` — нет.
- **Ребро `INTERRUPTS`.** В тексте прерывание не наблюдаемо так, как в речи.

---

## 9. Falsification criteria — по трём уровням

Прежний список смешивал уровни, и F2 был из-за этого просто неверен: «два человека дали α < 0.4 по relation pattern ⇒ модель неверна». Нет. Плохой термометр не опровергает существование температуры. Плохая операционализация `pursue_withdraw` убивает **этот label**, а не архитектуру `Evidence → Observation → Relation → Event → Hypothesis`.

### A. Representation — опровергает архитектуру

| # | Критерий | Как проверить |
|---|---|---|
| A1 | Существует нужный продукту конструкт, не выражающийся ни на одном из шести уровней | назвать его и показать, куда он не помещается |
| A2 | Набор одновременных гипотез на реальных данных **всегда** вырождается ровно в одну | прогон на реальном корпусе; тогда одной категориальной метки было бы достаточно |
| A3 | Ledger теряет evidence, counterevidence или censoring при любом порядке входа | property-тесты на перестановках эпизодов |
| A4 | Различение `OBSERVED_ABSENCE` / `RIGHT_CENSORED` / `INSUFFICIENT` / `NOT_APPLICABLE` не даёт ни одного различного решения ни на одном реальном материале | если четыре статуса всегда ведут себя одинаково, они лишние |
| A5 | L1.5 не меняет ни одного решения относительно топологии по наблюдениям на реальных логах | тогда слой — лишняя сложность. На синтетике меняет: `adv-unlabelled-01` даёт 0 событий вместо ложной связи |

### B. Candidate pattern — опровергает конкретный label, не архитектуру

| # | Критерий | Что умирает |
|---|---|---|
| B1 | Два человека, размечающих **эпизоды** на `pursue_withdraw`, дают α < 0.4 | операционализация `pursue_withdraw`; архитектура не затронута |
| B2 | `non-uptake with presence` не различается разметчиками надёжнее, чем silence | ключевое различение §4 — **это уже серьёзнее**, оно несущее для pursue-withdraw |
| B3 | `repair_softening` и `constructive_alignment` не различаются людьми | их надо слить, как CIRS/SSIRS сливаются в 4 фактора |
| B4 | Ни один паттерн не достигает `RECURRING` на реальном материале за разумное окно | пороги повторяемости, не уровни |

### C. Segmentation — опровергает baseline, не архитектуру

| # | Критерий |
|---|---|
| C1 | Два человека не воспроизводят границы эпизода (α < 0.4) — тогда спор baseline vs LLM не имеет разрешения |
| C2 | Детерминированный baseline даёт эпизоды, на которых паттерны не собираются, а семантический даёт |
| C3 | Правило staleness даёт осцилляцию на реальных данных |

### D. Safety — отдельно, потому что цена ошибки другая

| # | Критерий |
|---|---|
| D1 | Гейт срабатывает на материале без coercive control (ожидаемое число — ноль) |
| D2 | Гейт **не** срабатывает там, где сработал бы обученный человек |

> **C3 частично сработал раньше и стал лучше.** Было 21 транзиция на 27 эпизодов; после перехода на opportunity-aware staleness — **13 на 32**. Осцилляция уменьшилась, но не исчезла. Если она сохранится на реальном материале, правило придётся делать гистерезисным (разные пороги на вход и выход из `WEAKENED`). Записано как **известный дефект**, не как свойство.

---

## 10. Спайк заморожен здесь

Архитектурное discovery закончено. Дальше — зона, где ещё тысячу строк Python написать быстрее, чем получить один факт о том, видят ли люди то, что мы моделируем.

Текущее состояние слоёв:

```
L1    Evidence / Message
L1.5  Conversation topology     ← детерминированно: next_by_other_actor, explicit_reply_to
L2    BehaviorObservation       ← pilot A уже проверяет это фоном
L2.5  InteractionRelation       ← pilot B должен проверить ЭТО
L3    RelationalEvent
L4    concurrent StateHypotheses
```

## 11. Следующий эксперимент: `interaction-primitives-v0`

**Отдельный эксперимент, не смешиваемый с текущими 40 items.**

```
pilot A (фоном):  могут ли люди применять behavior labels?
pilot B (далее):  могут ли люди согласованно видеть interaction structure?
```

Материал: 40–80 коротких цепочек сообщений, **не обязательно романтических** — здесь проверяется механика взаимодействия, а не психология пары. Никаких наших higher-order названий людям не показывается.

Вопросы задаются **независимо** и все с явным «недостаточно данных»:

| # | Вопрос | Ответы |
|---|---|---|
| 1 | Является ли сообщение B ответом на **конкретное** сообщение A? | yes / no / insufficient |
| 2 | Продолжает ли B ту же тему? | same / different / **mixed** / insufficient |
| 3 | Если A содержит негативный ход — продолжает ли ответ B негативный обмен? | yes / no / insufficient |
| 4 | Если A содержит попытку смягчения — подхватывает ли её B? | yes / no / insufficient |
| 5 | *(на длинных кусках)* Где кончается один эпизод и начинается другой? | границы |

**`topic` людям не назначается.** Сейчас в спайке это единственное значение на сообщение, но наш же adversarial-кейс показал, что сообщение бывает «продолжает старую тему **и** открывает новую». Поэтому вопрос 2 — **pairwise relation** (`same` / `different` / `mixed` / `uncertain`), и это избавляет проект от отдельной taxonomy тем, которая ему не нужна.

Что даёт результат:

- **agreement хороший** → higher-order паттерны строятся как **композиция валидированных примитивов**, а не как ещё один магический label;
- **agreement плохой** → мы узнаём, **на каком именно ребре** всё разваливается, вместо α=.42 на `pursue_withdraw` и полугода выяснений, почему.

Дизайн этого пилота — отдельный документ и отдельный prereg, по образцу [pilot-v0.1-analysis-prereg.md](pilot-v0.1-analysis-prereg.md).
