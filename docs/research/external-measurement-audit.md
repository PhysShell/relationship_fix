# External Measurement & Calibration Audit — TRACK 1, первый заход

Дата: 2026-09-16. Статус: **research-only**. Pilot A и Pilot B не тронуты, замороженный спайк не тронут.

Рамка: [measurement-strategy.md](measurement-strategy.md). Назначение — не «найти ещё 47 датасетов», а по каждому слою ответить на десять вопросов и **сделать реальный adapter/probe**, а не census.

Артефакт кода: `research/python/external/kummerfeld_probe.py` + тесты.

---

## 0. Что сделано в этом заходе и что нет

| Датасет | 10 вопросов | Adapter/probe |
|---|---|---|
| **Kummerfeld / IRC-disentanglement** | **да, по первоисточнику** | **да** — probe на L1.5 |
| **Molweni** | **да, по первоисточнику** | нет |
| **STAC** | **частично** — числа из первоисточников Molweni + STAC-описаний; лицензия **не проверена** | нет |
| TIAGE · EPITOME · Perceived Empathy · NOESIS-II | **не аудированы** | нет |
| RESCUE | аудирован ранее, [dyadic-state-model.md](dyadic-state-model.md) §0 | нет |

Честно: это **три из восьми**. Остальные не «пропущены», а не сделаны — и это записано, чтобы не выглядеть полным census'ом.

---

## 1. Ledger

### Kummerfeld et al. 2019 — IRC disentanglement

[ACL P19-1374](https://aclanthology.org/P19-1374/) · [репозиторий](https://github.com/jkkummerfeld/irc-disentanglement)

| # | Вопрос | Ответ |
|---|---|---|
| 1 | Есть ли human-labelled reference data? | **Да.** 77 563 сообщения: 74 963 `#Ubuntu` IRC + 2 600 `#Linux` IRC |
| 2 | Что именно размечали? | Дословно: «link each message to the **one or more** messages it is a response to. If a message started a new conversation it was **linked to itself**» |
| 3 | Кто размечал | Обученные аннотаторы; гайдлайны выработаны **тремя раундами пилотной разметки с разбором всех расхождений** |
| 4 | IAA | **Cohen κ = 0.71 (train), 0.72 (dev), 0.74 (test), 0.72 (Channel Two)**. Первый датасет в этой области с **адъюдикацией** расхождений |
| 5 | Observation unit | сообщение; ребро между сообщениями |
| 6 | Raw text | да, IRC-логи публичны |
| 7 | Лицензия | репозиторий доступен; **точные условия не перечитаны в этой сессии** → `unknown` |
| 8 | Совпадение конструкта | **очень близко к нашему P1** и к `L1.5 explicit_reply` |
| 9 | Adapter сейчас? | **сделан**, §2 |
| 10 | Остаточный gap | их аннотация — про **структуру**, не про тему/негатив/смягчение. P2/P3/P4 не закрываются |

### Molweni

[arXiv:2004.05080](https://arxiv.org/abs/2004.05080) · [HIT-SCIR/Molweni](https://github.com/HIT-SCIR/Molweni)

| # | Вопрос | Ответ |
|---|---|---|
| 1 | Reference data | 10 000 диалогов, 88 303 реплики, **78 245 размеченных discourse relations** (Ubuntu Chat Corpus) |
| 2 | Что размечали | discourse dependency в модифицированном SDRT-стиле: **ссылка** + **тип отношения** из 16 |
| 3 | Кто | **10 аннотаторов**, студенты-бакалавры CS, **неносители английского** с сертификатом |
| 4 | IAA | **Fleiss κ = 0.91 для ссылок**, **0.56 для ссылок+типов** |
| 5 | Unit | реплика; DAG над репликами |
| 6 | Raw text | да |
| 7 | Лицензия | GitHub-релиз; условия **не перечитаны** → `unknown` |
| 8 | Совпадение | ссылки ≈ наш P1; типы отношений ≈ наш L2.5 `InteractionRelation` |
| 9 | Adapter | **не сделан** |
| 10 | Gap | инвентарь их отношений заточен под technical support, не под пару: `Acknowledgement` есть (3.2%), softening/negativity нет |

**16 отношений с долями:** Comment 31.7 · Clarification question 24.0 · Question-answer pair 20.1 · Continuation 6.7 · **Acknowledgement 3.2** · Q-Elab 3.0 · Result 2.6 · Elaboration 2.2 · Explanation 1.6 · Correction 1.2 · Contrast 1.2 · Conditional 1.0 · Background 0.4 · Narration 0.3 · Alternation 0.2 · Parallel 0.2.

Четыре верхних дают **80%+**; четыре нижних — менее 1% каждое. Авторы сами пишут, что «need to consider merging some rare relation types».

### STAC

[STAC corpus](https://www.irit.fr/STAC/corpus.html) · [Asher et al., описание корпуса](https://www.cs.brandeis.edu/~cs140b/CS140b_docs/AnnotationPapers/STAC_corpus_Dialog.pdf)

Multi-party чат в «Settlers of Catan», SDRT, ~10K EDU и отношений в 1091 диалоге. **κ ≈ 0.72 для attachment**; Molweni цитирует **0.58 для link+relation** в STAC. Лицензия **не проверена** → `unknown`.

---

## 2. Три сходящихся результата, которые меняют планирование

### 2.1 Связь и тип связи — задачи разной трудности, и это воспроизводится

| Уровень | Корпус | κ |
|---|---|---|
| attachment / link, **без якоря** | Kummerfeld | **0.71–0.74** |
| attachment | STAC | **≈0.72** |
| link, **с якорем** (готовые reply-to уже были) | Molweni | **0.91** |
| link **+ тип отношения** | Molweni | **0.56** |
| link **+ тип отношения** | STAC | **0.58** |

> **RESEARCH FINDING R-X1.** Три независимых корпуса дают один и тот же разрыв: **структуру отклика люди видят согласованно (κ ≈ 0.72), тип отношения — нет (κ ≈ 0.56–0.58)**. Это **внешний предответ на Pilot B**: его P1 скорее всего сядет около 0.7, а типизация отношений — около 0.56.
>
> Для нас это значит: `responds_to` — рабочий эмпирический примитив; богатый инвентарь `InteractionRelation` — нет, и `PCA→4 фактора` из couple-coding ([couple-coding-systems.md](couple-coding-systems.md) §3/R-B4) указывает в ту же сторону. Держать пять отношений вместо восьми было правильно; расширять их не следует.

### 2.2 Якорение всплыло в третий раз

Molweni объясняет свои 0.91 дословно: «because the Ubuntu dataset **initially contains the response-to relations**, and annotators **adopt most of the links**».

> **RESEARCH FINDING R-X2.** Это третий независимый случай после IDCS-CMC (master-коды, ICC .87→.51) и RESCUE-Bench (LLM-предразметка, IAA не сообщён). **Высокий κ при наличии предзаполненных меток не сопоставим с κ при разметке с нуля** — и разрыв 0.91 против 0.71–0.74 на одной и той же задаче даёт первую численную оценку размера эффекта: **≈0.2 κ**.
>
> Прямое следствие: `blind_rules` Pilot A и раздельные presentation-слои Pilot B — не бюрократия, а единственное, что отделяет наши будущие числа от чужих завышенных.

### 2.3 Krippendorff α к сегментации неприменим — и это сказано прямо

Kummerfeld, сноска 6, дословно: «Metrics such as Cohen's κ and Krippendorff's α **are not applicable to conversations** because there is no clear mapping from one set of conversations to another». И далее: «a single link can merge two conversations, meaning a **single disagreement in links can cause a major difference** in conversations».

> **RESEARCH FINDING R-X3.** Это ровно та неаддитивность, из-за которой мы ввели cluster bootstrap и раздельный strict/tolerant отчёт для P5. Внешнее подтверждение: наш выбор метрик для границ был верным, а позиционная α — действительно нижняя оценка, а не «просто консервативная».

---

## 3. Первый probe: наш L1.5 против reference-схемы

`research/python/external/kummerfeld_probe.py`. Спайк **заморожен** и probe его не чинит: тест `test_probe_does_not_mutate_the_frozen_spike` пинит набор полей `MessageNode`.

### Вердикт: **L1.5 НЕ lossless** относительно разметки, которую люди реально делали

| Что теряется | Почему |
|---|---|
| **множественные антецеденты** | `MessageNode.reply_to` — одно значение (`str \| None`), а гайдлайн разрешает «one **or more** messages it is a response to». Каждая вторая и далее ссылка **молча отбрасывается** |
| **начало треда** | self-link означает «начинает новый разговор». У нас нет третьего значения: `reply_to=None` читается как «нет reply-метаданных», а это **другое утверждение** |
| **cross-turn ссылка** | выразима, но любой потребитель с fallback на смежность разрешит её неверно — ровно тот дефект, который мы уже ловили у себя в repair-оценщике |

Потери **не взаимоисключающи**: одна аннотация может теряться двумя способами сразу. Поэтому отчёт — **список потерь, а не процент**: проценты позволили бы представлению, теряющему критический конструкт, выглядеть «на 97% в порядке».

> **RESEARCH FINDING R-X4 → candidate change (НЕ внедрено, спайк заморожен).**
> `MessageNode.reply_to: str | None` → `reply_to: tuple[str, ...]` плюс отдельный явный признак `thread_start`.
> **Обоснование:** это не гипотетическая нужда. Это то, что люди уже размечали в корпусе на 77 563 сообщения, и наша структура этого не принимает.
> **Критерий фальсификации:** если на реальном материале доля сообщений с >1 антецедентом ниже ~2% и доля thread-openers восстановима из сегментации, одиночного `reply_to` достаточно и изменение не нужно. Это **измеримо на данных Kummerfeld** и должно быть измерено до внедрения.

---

## 4. Что этот заход НЕ установил

1. **Лицензии.** Ни для Kummerfeld, ни для Molweni, ни для STAC не перечитаны условия → все три `unknown`. До любого ingestion это блокер.
2. **TIAGE, EPITOME, Perceived Empathy, NOESIS-II** не аудированы вовсе.
3. **Домен.** Все три разобранных корпуса — **technical support и настольная игра**. Ни один не является парой в конфликте. Переносимость κ на наш материал **не установлена**.
4. **Язык.** Все три англоязычные; Molweni размечали неносители. Для RU-материала — ничего.
5. **Ни одного recipient-rated датасета** пока не тронуто, то есть TRACK 4 (PerceivedImpact) — самый важный по [measurement-strategy.md](measurement-strategy.md) §4 — ещё не начат.

---

## 5. Что из этого следует для решения о пилотах

| Вопрос | Текущий ответ |
|---|---|
| Закрывает ли внешнее P1 (`responds_to`)? | **Частично.** κ ≈ 0.72 известен, но на technical-support-чате. Для нашего материала — нет |
| Закрывает ли внешнее P2 (тема)? | **Нет.** TIAGE не аудирован |
| Закрывает ли внешнее типизацию отношений? | **Скорее закрывает негативно**: κ ≈ 0.56–0.58 воспроизводимо низкий |
| Закрывает ли внешнее P3/P4 (негатив, смягчение)? | **Нет.** Ни один из разобранных инвентарей их не содержит |
| Закрывает ли внешнее P5 (границы)? | **Нет**, и Kummerfeld прямо говорит, что стандартные метрики согласия сюда не применимы |

Pilot B остаётся **contingency**, и его наиболее вероятная будущая роль сузилась: не «проверить все пять примитивов», а **P3/P4/P5 на нашем материале**, потому что P1 и типизация уже имеют внешние численные ориентиры.
