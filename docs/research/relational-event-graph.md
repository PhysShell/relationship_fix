# RelationalEventGraph: минимальное представление

Дата: 2026-09-16. Статус: **research-only**. Реализация: `research/python/dyadic/model.py`.

Companion: [dyadic-state-model.md](dyadic-state-model.md) · [episode-segmentation.md](episode-segmentation.md).

---

## 0. Слово Graph здесь ничего не покупает

Сразу и прямо: **graph database не нужна, и по итогам спайка рёбра между событиями не понадобились вообще.**

Три worked examples из [dyadic-state-model.md](dyadic-state-model.md) §6 собрались полностью на `source_observations` + порядок сообщений. Тип `EventEdge` в модели объявлен, но **не используется ни одним кодовым путём**. Он оставлен как декларация намерения и как место, где будущая необходимость станет видна, а не как работающий механизм.

Правило, которое из этого следует: **immutable domain representation + JSON сначала.** Хранилище выбирается тогда, когда запрос, ради которого оно нужно, уже написан и медленно работает.

---

## 1. Уровни и типы

```
EvidenceSpan          L1  message_id + дословная цитата
BehaviorObservation   L2  label + actor + message_id + evidence (непустой!)
RelationalEvent       L3  несколько наблюдений, связанных во времени
StateHypothesis       L4  гипотеза с собственным ledger'ом
```

### EvidenceSpan

```python
EvidenceSpan(message_id, quote)
    .validate(message_text)   # quote обязан быть дословной подстрокой
```

Пересказ запрещён на уровне типа. Тест `test_evidence_must_be_verbatim`.

### BehaviorObservation

```python
BehaviorObservation(observation_id, label, actor, message_id, evidence)
```

`__post_init__` **бросает исключение** при пустом evidence: наблюдение без доказательства не является наблюдением. Это тот же контракт, что уже действует в pilot'е (`evidence_required: true` в онтологии, проверка «no quote for label» в `metrics.agreement.validate_responses`).

`label` — **непрозрачная строка**. Спайк намеренно не импортирует и не расширяет BehaviorOntology v0.1: она заморожена, а спайк не должен иметь возможности её задеть даже случайно.

### RelationalEvent

```python
RelationalEvent(
    event_id, event_type, participants, episode_id,
    source_observations,      # ссылки на L2
    supporting_evidence,      # ссылки на L1
    counterevidence,          # ссылки на L1
    status: EvidenceStatus,   # supporting | counter | absent | insufficient | not_applicable
    provenance,
)
```

Два решения стоит назвать явно:

1. **`counterevidence` живёт на событии, а не только на гипотезе.** Событие может быть хорошо обосновано локально и при этом работать **против** более крупного паттерна. Пример из трейса (`rep-fail-01`): извинение произошло — это факт; но как событие для `repair_softening` оно имеет статус `COUNTER`, потому что партнёр продолжил негатив.
2. **`status` — свойство события, а не гипотезы.** Одно и то же наблюдение (`APOLOGY`) даёт `SUPPORTING` в `rep-02` и `COUNTER` в `rep-fail-01`. Различает их **последующее поведение партнёра**, то есть позиция в последовательности, а не сам ход.

### EventRelation — объявлен, не используется

```
follows · responds_to · escalates · softens · repeats · contradicts · repairs · interrupts
```

Единственное требование ко всем восьми: **решаемость из порядка и типов событий, никогда из предполагаемого мотива.** `INTERRUPTS` уже сейчас выглядит непереносимым в текст: в речи прерывание наблюдаемо, в асинхронном чате — нет.

---

## 2. Провенанс и инварианты

| Инвариант репозитория | Как соблюдён |
|---|---|
| 1 — LLM не source of truth | в ledger нет пути записи, принимающего свободный текст; единственный вход — типизированный `RelationalEvent` |
| 3 — тип происхождения памяти сохраняется | `RelationalEvent.provenance` (в спайке всегда `deterministic_spike`) |
| 4 — generated events не становятся фактами | спайк не порождает сообщений; `messages` приходят только из корпуса |
| 7 — observable behavior > identity | `event_type` — тип **взаимодействия**; `participants` — роли, не характеристики |
| 8 — publishable finding проверяем | evidence обязателен на L2; `retire()` сохраняет запись, а не удаляет |
| 9 — abstention обязателен | `EvidenceStatus.ABSENT` / `INSUFFICIENT_OBSERVATION` — первоклассные значения |

---

## 3. Сериализация и идентичность

`to_jsonable` обходит поля dataclass'а **поверхностно** и рекурсирует сам. Это выглядит как лишняя работа вместо `dataclasses.asdict`, и причина конкретна: `asdict` **рекурсивно** разворачивает вложенные dataclass'ы **до** того, как срабатывает hook производных полей, из-за чего `observation_coverage` молча исчезал из трейса. Читатель такого трейса не мог отличить «не смогли посмотреть» от «посмотрели и не нашли» — ровно та путаница, против которой построена вся модель.

`content_hash` — sha256 канонического JSON (sorted keys, без пробелов). Используется для идентичности эпизода и для проверки детерминизма всего прогона (тест `test_same_corpus_produces_identical_trace`).

---

## 4. Что не построено и почему

| Не построено | Причина |
|---|---|
| Graph DB | рёбра не понадобились; см. §0 |
| Индексы, персистентность | нет запроса, который тормозит |
| Детекторы поведения | спайк проверяет **представление**, а не детекцию; корпус подаёт L2 напрямую, чтобы провал нельзя было списать на классификатор |
| C# domain types | это был бы шаг к production engine; сначала research design должен пережить фальсификацию |
| Слияние с BehaviorOntology v0.1 | она заморожена; кросвок — только в документах |
