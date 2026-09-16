# Couple coding systems: IDCS-CMC, CIRS/SSIRS и родственные системы

Дата: 2026-09-16. Статус: **research-only**. Документ ничего не меняет в `data/ontology/`, в sealed pilot `data/pilot/v0.1/` и в production code. Все предложения помечены как `RESEARCH FINDING → candidate change` и **не внедрены**.

Предшественник: [observational-coding-prior-art.md](observational-coding-prior-art.md). Тот документ фиксировал *происхождение* конструктов по вторичным описаниям. Этот — разбирает **первоисточники до уровня operational definitions, units и reliability** и там, где расходится с предшественником, расхождение отмечено явно.

Companion: [ontology-crosswalk.md](ontology-crosswalk.md) · [invalidation-review.md](invalidation-review.md) · [corpus-strategy.md](corpus-strategy.md) · [next-research-design.md](next-research-design.md) · [intervention-ontology-review.md](intervention-ontology-review.md).

---

## 0. Ledger первоисточников

Правило: «paper mentions data» ≠ «dataset available». Ниже — что реально удалось прочитать в этой сессии.

| Артефакт | existence_verified | primary_source_verified | raw_data_available | annotations_available | license_verified | Как проверено |
|---|---|---|---|---|---|---|
| **IDCS-CMC** (Rackets 2020, диссертация + **полный codebook в Appendix 3**) | yes | **yes — прочитаны все 175 стр.** | **no** (48 AIM-логов, UK IRB #09-0963-F4S / #61571, публикации данных нет) | no | yes (автор сохраняет copyright; UKnowledge — неисключительная лицензия на архивирование/доступ) | DOI 10.13023/etd.2020.440; PDF получен через CORE (uknowledge отдаёт 403 за Cloudflare) |
| **IDCS** (Kline et al. 2004, глава в Kerig & Baucom) | yes | **no — глава не читалась** | n/a | n/a | no | Известна только по цитированию внутри IDCS-CMC и по каталогу Routledge |
| **CIRS** (Heavey, Gill & Christensen 1996/1998) | yes | **partial** — manual **не опубликован**; дословные критерии 4 из 13 items получены из Appendix A диссертации Берклі | no | no | **no manual to license** | Berkeley eScholarship `qt1g37d6w6`, Appendix A; подтверждено формулировками в PMC3014221 |
| **SSIRS** (Jones & Christensen 1998) | yes | **no** — manual **не опубликован** (UCLA unpublished document); известны только агрегаты (18 items, 1–9) | no | no | no | PMC4306640 (references + methods) |
| **SPAFF** (Coan & Gottman, 2007) | yes | **partial** — дословные критерии **подмножества** negative-affect кодов (Appendix B той же диссертации); полный состав 20 кодов и определение `Stonewalling` — из вторичного описания; сам manual Gottman Institute **недоступен** | n/a | n/a | no | Berkeley `qt1g37d6w6` App. B; [Frontiers in Psychiatry 2023](https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2023.980739/full) |
| **Repair Attempts OCS** (Tabares, Driver & Gottman) | yes | **no — paywalled** (Taylor & Francis глава; статья 2015 IJST/JFP тоже paywalled) | no | no | no | Только каталожные страницы + вторичные пересказы |
| **UCLA/UW Couple Therapy Project** (134 пары, CIRS+SSIRS 33 dimensions) | yes | yes (methods прочитаны) | **no — «data cannot be released to the public»** | no | n/a | PMC5608311 |

**Главный негативный результат уровня источников:** канонические manual'ы CIRS и SSIRS — **неопубликованные внутренние документы UCLA**. Их нельзя ни купить, ни скачать. Всё, что доступно публично, — это item-описания, перепечатанные в приложениях чужих работ. Любая наша ссылка «adapted_from CIRS» опирается на **реконструкцию по вторичным перепечаткам**, а не на manual. Это надо писать прямо, а не прятать за красивой строкой `source_frameworks`.

Единственная система из перечисленных, чей **полный codebook реально доступен**, — IDCS-CMC (Appendix 3 диссертации). Это делает её не «дополнительным supplementary prior art», а **самым сильным доступным первоисточником для нашей задачи**.

---

## 1. IDCS-CMC (Rackets, 2020) — ближайший родственник и главный источник

### 1.1 Что это

Адаптация Interaction Dimensions Coding System (IDCS-PS; Kline et al., 2004; восходит к Julien, Markman & Van Widenfelt, 1986, University of Denver) к **текстовому чату реальных романтических пар**.

Данные: 48 пар (N=96), набор 2010–2012, юг США; средний возраст 27.78 (SD 7.61); 51% dating / 12% engaged / 38% married; 42% считали отношения distressed. Пары сидели в **разных комнатах** за терминалами AOL Instant Messenger и 15 минут обсуждали заранее выбранную ими **спорную тему** (FtF-условие — 10 минут, другая тема, порядок рандомизирован). Логи с timestamps сохранялись; видео CMC-условия не было. Кодировалось 43 лога.

Это **не** «датасет из интернета». Это лабораторный problem-solving task в тексте. Экологическая валидность ограничена ровно так же, как у любого лабораторного conflict task, плюс дополнительное ограничение — см. §1.5 «captive participation».

### 1.2 Структура: 9 индивидуальных + 5 диадических измерений

| Группа | Измерения | На чём основано |
|---|---|---|
| Affect codes (2) | Positive Affect, Negative Affect | только affect-cues (эмодзи, капс, растяжка букв, пунктуация) |
| Content codes (3) | Problem-Solving Skills, **Denial**, Dominance | только языковое содержание |
| Combined codes (4) | **Support/Validation**, **Conflict**, **Withdrawal**, Communication Skills | content + affect вместе |
| Dyadic codes (5) | Positive Escalation, Negative Escalation, Commitment, Future Satisfaction, Future Stability | вся интеракция как единица, оценка пары целиком |

### 1.3 Unit of analysis — **это самое важное для нас**

Процедура из manual (Appendix 3, «Procedure»):

1. Кодировщик берёт timestamps и делит весь лог на **3 равных временных сегмента**.
2. Читает **весь** лог целиком, делает заметки, **ничего не оценивает**.
3. Оценивает сегмент 1 по всем 9 измерениям для **каждого** партнёра (шкала 1–9), затем сегмент 2, затем сегмент 3.
4. Присваивает **overall rating** за всё взаимодействие по каждому измерению для каждого человека (обычно мода/среднее трёх, но кодировщику разрешено отступить).
5. Оценивает 5 диадических измерений, где **coding unit = вся интеракция**.

Для reliability и всех последующих анализов используется **только overall rating**; три сегментных оценки **выбрасываются**. Manual прямо говорит, зачем они нужны: это «anchor for themselves to remember the dynamics», механизм памяти кодировщика, а не данные.

Система явно самоопределяется как **global / macroanalytic**, в противопоставление microanalytic: «codes major dimensions of behavior over relatively long time periods … rather than small, specific pieces of behavior over short periods of time» (IDCS-CMC manual, Introduction).

> **RESEARCH FINDING R-A1.** Наш pilot кодирует **одну реплику** (`unit_of_analysis: "utterance"`, 40 items, target_message_id). IDCS-CMC — ближайшая существующая система для ровно нашего носителя (текстовый чат реальных пар) — **не кодирует ничего короче 5-минутного сегмента, и даже эти сегментные оценки выбрасывает**.
> Это не «мы взяли меньший unit». Это **другой класс измерения**: dimensional intensity целой интеракции vs binary presence одной реплики.
> **candidate change:** перестать описывать наши labels как «adapted_from IDCS-CMC» без явной пометки `unit_relation: "incompatible_granularity"`.
> **falsification:** если утверждаемый pilot-alpha ≥ 0.667 на utterance-уровне для ≥3 labels, granularity-претензия ослабевает для этих конкретных labels (но не для WITHDRAWAL — см. §1.5).

### 1.4 Reliability (Table 4.1, ICC, two-way mixed, consistency, average-measures)

| Измерение | 8 training logs | Первые 10 study logs | Итог 16 study logs |
|---|---|---|---|
| Positive Affect | .93 | .96 | **.91** |
| Negative Affect | .84 | .66 | **.60** |
| Problem Solving | .76 | .84 | **.81** |
| Denial | .76 | .79 | **.80** |
| **Dominance** | .69 | .50 | **.30** |
| **Support and Validation** | .86 | .74 | **.75** |
| Conflict | .82 | .88 | **.88** |
| **Withdrawal** | **.87** | **.51** | **.52** |
| Communication Skills | .89 | .86 | **.80** |
| Positive Escalation | .86 | .82 | .83 |
| Negative Escalation | .90 | .72 | .74 |
| Commitment / Satisfaction / Stability | .80 / .91 / .75 | .77 / .74 / .78 | .74 / .77 / .74 |
| **Average** | .83 | .79 | **.73** (.76 без Dominance) |

Пороги — Cicchetti (1994): <.40 poor, .40–.59 fair, .60–.74 good, .75–1.0 excellent.

Обучение: 4 кодировщика; 5 training logs → недостаточно (ICC 4 кодировщиков без master-кодов = **.79**, при том что *с* master-кодами = .85) → +3 лога → .83. Fully-crossed дизайн на 16 логах, остальные 24 распределены по одному кодировщику.

> **RESEARCH FINDING R-A2 — «anchoring collapse».** Withdrawal дал **.87 на training-логах и .51 сразу, как только исчезли групповое обсуждение и master-коды**. Это не шум: та же команда, то же обучение, тот же manual.
> Авторы сами наткнулись на этот механизм и на других измерениях: «master scores были consistently в середине», ICC с master-кодами .85 vs без них .79 — то есть **согласие частично производилось якорем, а не конструктом**.
> **Прямое следствие для нас:** любая цифра agreement, полученная после совместной калибровки на тех же/похожих items, **завышена**. Наш pilot строго blind (`blind_rules` в `pilot-manifest.json` запрещают обсуждение до заморозки обоих слоёв) — это правильно и должно остаться.

### 1.5 Withdrawal: разбор, ради которого всё затевалось

**Вопрос задачи:** низкая reliability withdrawal в тексте — случайность конкретной работы или более общая observability problem?

**Ответ: более общая observability problem. Четыре независимые причины, три из них структурные.**

**(1) Родительская система сама определяет withdrawal как преимущественно невербальный конструкт.**
Диссертация, гл. 3: «the definition in the IDCS manual states that withdrawal behavior **cannot be expressed through the content or language** used by participants and is instead typically communicated through nonverbal behaviors».
Списки cues это подтверждают. FtF affect-cues withdrawal: избегание зрительного контакта, тело отвёрнуто, физическая дистанция, барьер (скрещенные руки), fidgeting, «appears uncomfortable or bored». **Ни один из них не существует в тексте.** Текст не «хуже показывает» withdrawal — он лишён того канала, который для этого конструкта был основным.

**(2) Компенсирующая адаптация опирается на признаки, которые сами по себе неоднозначны.**
CMC-cues, добавленные в IDCS-CMC: сообщение из одной пунктуации («…», «??»), пустое сообщение, «idk» вместо «I don't know», «k» вместо «okay», «y» вместо «why?», манипуляции шрифтом/символами, создающие дистанцию.
Manual тут же ставит ограничение на chronemics: «**A delay in response during CMC should not automatically be assumed to be withdrawal** because a communicator could just be taking additional time to think, typing their message, or experiencing technological difficulties or other distractions.» И в разделе обсуждения: «there were instances when the coding team would **disagree about what the passage of time meant** or how to ascribe meaning to it».

> **RESEARCH FINDING R-A3 — латентность.** Наше operational definition `B.WITHDRAWAL` опирается на «латентность, падение длины, non-uptake», а positive-пример — «молчит 6 часов». Единственная существующая система для текстового чата пар **явно запрещает** выводить withdrawal из задержки и **эмпирически зафиксировала разногласия обученных кодировщиков именно по интерпретации времени**.
> **candidate change:** латентность понизить с признака-основания до **контекстного модификатора**, который не может один нести решение.
> **falsification:** если на размеченном exchange-корпусе латентность (нормированная на базовый темп пары) даёт предсказание withdrawal-меток с alpha, не падающим при её удалении, — ограничение избыточно.

**(3) Конструкт наблюдательно конфаундится с Dominance — в той же системе.**
Dominance cues включают дословно: «**Withholds contributions to conversations as a means of exerting control**». Contextual note к Dominance: «Withholding or delays in communicating could be considered dominance, but could also be an indication of someone thinking or typing out a longer message».
То есть **один и тот же наблюдаемый признак — молчание/сокращение вклада — в этой системе штатно принадлежит двум разным измерениям**, а различает их приписываемая функция (уход vs контроль), которая в тексте не наблюдаема.
Оба измерения — и есть ровно те два, что провалили reliability (Withdrawal .52, Dominance .30). Это **не совпадение, а ожидаемое следствие** общего наблюдаемого при ненаблюдаемой различающей функции. Диссертация сама рекомендует изучать связь dominance↔withdrawal как будущую работу.
Дополнительно: предыдущая работа по IDCS (Chartrand & Julien, 1994) уже признала Dominance проблемным и **перевела его в диадический код**.

**(4) «Captive participation» — лабораторный артефакт, который в нашу сторону работает наоборот.**
Диссертация, гл. 5: в лабораторном протоколе партнёр не может по-настоящему уйти — он социально обязан участвовать. Авторы вводят термин **«captive participation»**: вынужденное участие порождает «low participation responses or nonresponse responses (where the receiver acknowledges receipt of information but **stalls the feedback loop** by not contributing further)» и поведение, которое «served to **distract, deflect**, or **deflate or invalidate** the communication partner's opinion».

> **RESEARCH FINDING R-A4 — направление артефакта.** В лаборатории withdrawal **недонаблюдается** (уйти нельзя) и вырождается в минимальные отклики. В реальном мессенджере всё наоборот: уйти тривиально, зато **отсутствие ответа массово перегружено** (сон, работа, транспорт, разряженный телефон).
> Вывод: **ни одна из двух сред не даёт чистого withdrawal.** Лаборатория даёт суррогат, реальный чат даёт конфаунд. Это принципиальная граница, а не недоработка протокола.

**Промежуточный вердикт по WITHDRAWAL.**

| Утверждение | Вердикт |
|---|---|
| Низкая reliability — случайность одной работы | **Нет** |
| Withdrawal — невалидный конструкт | **Нет.** В FtF CIRS он даёт alpha .80 (§2.2); в SSIRS/CIRS PCA выделяется в отдельный фактор |
| Withdrawal надёжно кодируем на уровне utterance в тексте | **Нет.** Ни одна найденная система даже не пытается |
| Withdrawal кодируем на уровне exchange в тексте | **Не установлено.** Единственная попытка (global над 15 мин) дала .52; exchange-уровень не тестировал никто |
| Наш `deferred_until_exchange_segmentation` — правильное решение | **Да, и это самое сильное решение в v0.1** — но его обоснование надо переписать: дело не только в unit, а в **потере канала + конфаунде с Dominance** |
| Это специфично для IDCS-CMC | **Нет.** SPAFF `Stonewalling` и CIRS `Withdrawal` определяют конструкт через тот же невербальный канал — см. §4/R-B7 |

### 1.6 Support/Validation, Conflict, Denial — дословные ядра

**Support/Validation** (combined code): «positive listening skills and speaking skills that demonstrate support and understanding to the partner. Close synonyms … encouragement, acknowledgement, and acceptance.»
Content cues: выражает теплоту/заботу/сочувствие; делает позитивные или **нейтральные** атрибуции о поведении партнёра; **принимает атрибуции партнёра о собственном поведении**; суммирует/перефразирует высказывания партнёра; подбадривает; делает комплименты.
Context note (важно): «A lack of affect-based active listening **should not always be interpreted as a lack of support/validation**, as a listener may be providing the speaker space to type». И: реакции-символы («👍», «❤️», «!») засчитываются как cue.

> **RESEARCH FINDING R-A5.** IDCS-CMC `Support/Validation` **шире** нашей `B.VALIDATION` в трёх местах: (a) включает комплименты/поощрение без всякого признания переживания; (b) включает **принятие атрибуции партнёра о себе** (это у нас скорее в семье REPAIR_ATTEMPT); (c) засчитывает эмодзи-реакции.
> Наша `B.VALIDATION` требует именно **явного признания эмоции/позиции** и исключает «согласие с фактом без отклика на переживание».
> Это значит: наш label — **не** IDCS-CMC Support/Validation, а его **узкое подмножество**, при этом пересекающееся с IDCS-CMC `Communication Skills` («makes effort to validate the importance of partner's feedback», «summarizes partner's opinions, feelings, or decisions»).
> `Match` в crosswalk = **partial**, не strong.

**Conflict** (combined code): «an expressed struggle between two individuals with incompatible goals or opinions. The level of tension, hostility, disagreement, antagonism, or negative affect an individual displays can identify conflict.»
Content cues (дословно, сокращённо): судит и критикует партнёра; навязывает свою волю, контролирует; демонстрирует безразличие; **«Minimizes the value of partner's contributions»**; ригидность в готовности слушать; чаще не соглашается, чем соглашается; **negative mindreads**; **negative overgeneralizations** («You always say that!», «You never ask me how my day went»); антагонизирует сарказмом.

**Denial** (content code): «the active rejection of a problem's existence or of personal responsibility for the problem being discussed.»
Cues: оспаривание существования или **минимизация** проблемы; оправдания; признание проблемы с отказом от любой ответственности; признание проблемы с **полным перекладыванием вины на партнёра**; **«Blames partner for blowing the problem out of proportion»**; **«Claims partner is imagining or making up the problem»**.

> **RESEARCH FINDING R-A6 — где на самом деле живёт наш BLAME_CRITICISM.**
> В IDCS-CMC **нет** кода «Blame». Наши маркеры распределены по двум разным измерениям: генерализации и критика личности → `Conflict`; перекладывание вины и «ты придумываешь / раздуваешь» → `Denial`.
> «Опять ты со своими шуточками» и «Ты всегда обо всём забываешь» в IDCS-CMC подняли бы **Conflict**, а «это ты всё начала» — **Denial**.
> Значит наш `B.BLAME_CRITICISM` — **не адаптация одного внешнего конструкта**, а срез поперёк двух. Его настоящий однокоренной предок — CIRS `Blame` (§2.2), не IDCS-CMC.

> **RESEARCH FINDING R-A7 — invalidation уже присутствует, но как cues чужих кодов.**
> «Minimizes the value of partner's contributions» (Conflict), «Claims partner is imagining or making up the problem» (Denial), «Blames partner for blowing the problem out of proportion» (Denial) — это **ровно те поведения**, которые INV-01 предлагает выделить.
> Значит гипотеза INV-01 в формулировке «эти случаи выпадают между labels» **верна для нашей онтологии, но неверна как утверждение о поле**: поле их кодирует, просто не под именем «invalidation». Подробно — [invalidation-review.md](invalidation-review.md).

### 1.7 Что IDCS-CMC требует от кодировщика, а мы запрещаем

Manual, Introduction (дословно): «coders will also need to **utilize their own personal experience in relationships and using CMC** to help discern the meaning of patterns, behaviors, and dynamics. Coders will need to **make judgments on the meaning and the intention** of these behaviors. Thus, the role of the coders … is both that of a detector of information but also a **cultural informant**, such that **inference about others' intentions is necessary**.»

> **RESEARCH FINDING R-A8 — конфликт эпистемических режимов.** Наш протокол построен на «только наблюдаемое, никакого вывода о намерении». Единственная система для нашего носителя **строит себя на противоположном принципе** и достигает приемлемой reliability именно потому, что: (a) даёт кодировщику **всю** интеракцию, (b) использует **градуальную** шкалу интенсивности, (c) требует **недель обучения и еженедельных калибровок**.
> Мы убрали все три компенсатора и одновременно ужесточили запрет на вывод. Это не «более строгая наука» — это **другая и, вероятно, более сложная задача**.
> **candidate change:** переформулировать наш эпистемический принцип из «no intent inference» в «**intent inference must be licensed by text-visible evidence within the coded unit**». Это то, что мы фактически и требуем (evidence span), и это честнее.
> **falsification:** если в pilot-фидбеке аннотаторы систематически отмечают «понятно, что имелось в виду, но нет права так кодировать» — формулировка вредит.

---

## 2. CIRS — Couples Interaction Rating System

### 2.1 Статус источника

Heavey, C. L., Gill, D., & Christensen, A. (1996/1998). **Unpublished document, UCLA.** 13 items, шкала 1–9 («Not at All» → «A Lot»). Manual недоступен. Дословные критерии 4 демонд/уиздро-item'ов воспроизведены в Appendix A диссертации Berkeley (`qt1g37d6w6`) и согласуются с формулировками в PMC3014221 — это лучшее, что существует публично.

### 2.2 Дословные критерии (Appendix A, Berkeley)

Инструкция кодировщику: «assign points based on the **frequency, intensity, and context** of particular behaviors» — то есть явно **не** подсчёт.

| Item | Критерий (дословно) |
|---|---|
| **Blame** | «Blames, accuses, or criticizes partner. Uses critical sarcasm, character assassinations.» |
| **Pressure for Change** | «**Requests**, demands, nags, **manipulates, seduces**, or otherwise pressures for change in the partner. This pressure can be either **positive or negative** (critical or **complimenting and supportive**). This pressure can be **implicit as well as explicit**; it must carry in it an **implicit "should" statement**.» |
| **Withdrawal** | «Withdraws, becomes silent, refuses to discuss a particular topic, **looks away**, refuses to argue or fight about the issue, **does not actively defend self**, pulls back, retreats, disengages self from the discussion. **More passive than Avoidance.**» |
| **Avoidance** | «**Actively** avoids discussing the problem. Hesitates, changes topics, diverts attention, or delays discussion. **More active than Withdrawal.**» |

Unit: **весь конфликтный разговор** (15 минут), одна оценка на человека на разговор. Кодировщики смотрят запись целиком.
Reliability (Berkeley, longitudinal, 2 команды, ~4 недели обучения, 4–6 кодировщиков на интеракцию, 2–3 на каждого партнёра, усреднение): alpha **.90 Blame**, **.92 Pressure for Change**, **.80 Withdrawal**, **.83 Avoidance**, .82 Discussion.
Композиты: Demand = mean(Blame, Pressure); Withdraw = mean(Withdrawal, Avoidance).

### 2.3 Withdrawal vs Avoidance — source-grounded ответ

**Различающий критерий — не тема и не канал, а активность/пассивность ухода.**

| | Withdrawal | Avoidance |
|---|---|---|
| Ось | **пассивная** | **активная** |
| Что делает человек | замолкает, не защищается, откатывается, отказывается обсуждать | **делает ход**, уводящий разговор: медлит, меняет тему, отвлекает внимание, откладывает |
| Наблюдаемое в тексте | отсутствие/схлопывание вклада | **присутствует новая реплика с другим содержанием** |
| Наблюдаемо на utterance? | **Нет** — отсутствие не локализуется в реплике; нужен ≥ exchange | **Частично да** — сама уводящая реплика есть объект, но её квалификация требует **предшествующей** поднятой темы |
| Минимальный unit | **exchange минимум; реально episode** | **exchange** (adjacency pair: поднятая тема → ход) |

**Эмпирическое подтверждение, что это разные конструкты (Berkeley, 3 временные точки, ~125 пар):**
- Blame и Pressure коррелируют **сильно** (внутри Demand).
- Withdrawal и Avoidance коррелируют, но **слабее**, чем демонд-пара.
- **Avoidance отрицательно коррелирует с обоими демонд-поведениями** (больше требований → меньше avoidance).
- **Withdrawal с blame/pressure практически не связан.**
- Withdrawal мужа **положительно** связан с demand жены (классический demand-withdraw), а avoidance мужа — **отрицательно или незначимо**.

> **RESEARCH FINDING R-B1.** Withdrawal и Avoidance — **не две градации одного конструкта, а конструкты с разной номологической сетью**: один встроен в demand-withdraw цикл, второй — нет. Наш split на `B.WITHDRAWAL` / `B.AVOIDANCE_TOPIC_SHIFT` **подтверждён внешне и должен быть сохранён**.
> Но: наши границы проведены **не по той оси**. У нас различитель — «остался в разговоре vs ушёл». У CIRS — **passive vs active**. Наш `B.AVOIDANCE_TOPIC_SHIFT` («остаётся в разговоре, но уводит») ≈ CIRS Avoidance — здесь совпадение хорошее. А наш `B.WITHDRAWAL` тянет к себе и «резкое сокращение ответов» — что в CIRS пассивная сторона, ок, — но наш exclusion «явно объявленный таймаут → repair» в CIRS попал бы в **Avoidance** («delays discussion»).
> **candidate change:** перенести признак `passive/active` в схему labels явным полем, вместо того чтобы прятать его в прозе definition.

### 2.4 Pressure for Change vs Blame — и где мы разошлись с наукой

CIRS различает их так: **Blame атакует/оценивает; Pressure добивается изменения.** Это совпадает с нашим замыслом. Но дальше идут три существенных расхождения.

| Ось | CIRS Pressure for Change | Наш `B.PRESSURE_FOR_CHANGE` | Оценка |
|---|---|---|---|
| Ядро конструкта | **implicit "should" statement** — это *обязательный* критерий | «требует, настаивает или повторно добивается … **с нажимом**» — критерий *интенсивности* | **Разные конструкты.** Мы измеряем силу давления, CIRS — наличие нормативного требования |
| Валентность | **явно включает позитивное давление**: «complimenting and supportive», **«seduces»** | только негативно-нажимная форма | **Мы теряем целую половину конструкта** |
| Нейтральная просьба | **включена** («Requests…»), просто получает низкий балл (2–3), а не ноль | **явно исключена**: «однократная нейтральная просьба без нажима» → negative | **Прямое противоречие**. Наш пример «Можешь завтра забрать посылку?» = negative; для CIRS это request с implicit should, т.е. низкая, но **ненулевая** точка шкалы |
| Шкала | 1–9 интенсивность за всю интеракцию | binary presence на реплике | см. R-B2 |

> **RESEARCH FINDING R-B2 — бинаризация градуального конструкта.** CIRS достигает alpha .92 по Pressure for Change, **потому что кодировщик не обязан решать «есть или нет»** — он размещает наблюдение на шкале, и разница между 2 и 3 не ломает согласие.
> Мы требуем решить ровно тот вопрос, который CIRS обходит: **где на континууме находится порог присутствия**. Причём нижняя часть шкалы (просьба → просьба с нажимом) — это именно та зона, где конструкт наиболее плотный и наименее различимый.
> **Предсказание:** `B.PRESSURE_FOR_CHANGE` даст **худший** alpha среди четырёх «содержательных» активных labels, и его confusion пойдёт не в `B.BLAME_CRITICISM`, а в `none_observed`.
> **falsification:** если в pilot alpha(PRESSURE) ≥ alpha(BLAME) **и** доля confusion `PRESSURE ↔ none_observed` не превышает `PRESSURE ↔ BLAME`, предсказание опровергнуто.
> **Это проверяется на текущем pilot без единого изменения** — см. [next-research-design.md](next-research-design.md) §1.

> **RESEARCH FINDING R-B3.** Наш `B.BLAME_CRITICISM` **уже**, чем CIRS `Blame`: CIRS включает «criticizes partner» без требования генерализации, а мы требуем генерализацию или оценку личности и исключаем «жалобу на конкретный эпизод». В CIRS жалоба-с-критикой — это Blame низкой интенсивности.
> Итог: **и BLAME, и PRESSURE у нас сдвинуты в одну сторону — мы отрезали нижнюю треть обеих шкал.** Систематически, не случайно. Это делает оба label'а более редкими → prevalence-проблема (см. [next-research-design.md](next-research-design.md) §4, риск R5).

---

## 3. SSIRS и что происходит при факторизации

**SSIRS** (Jones & Christensen, 1998; unpublished, UCLA): 18 items, шкала 1–9 («none» → «a lot»), кодировщик «rate[s] one partner at a time» и учитывает «frequency, context, and intensity». Покрывает эмоциональные характеристики интеракции и тему разговора — то, чего нет в CIRS.

В исследованиях IBCT/TBCT (PMC4306640) CIRS и SSIRS применяются вместе; **principal components analysis по items обеих систем даёт четыре шкалы: negativity, positivity, withdrawal, problem solving.** Interobserver alpha: negativity .86–.95, positivity .81–.95.

В UCLA/UW Couple Therapy Project (PMC5608311): 134 пары, 3 сессии за 2 года, по два 10-минутных problem-solving разговора, **33 поведенческих измерения CIRS+SSIRS**, 1–9, 2–9 кодировщиков на сессию, средняя Krippendorff **α = 0.7528**.

> **RESEARCH FINDING R-B4 — 31 item схлопывается в 4 фактора.** Это, возможно, самое неприятное для нашей дорожной карты. Люди, у которых есть обученные кодировщики, полные записи и десятилетия итераций, при факторизации получают **negativity / positivity / withdrawal / problem-solving**. Blame и Pressure уходят в negativity. Withdrawal и Avoidance — в withdrawal.
> То есть **наши шесть labels с высокой вероятностью измеряют два-три измерения**, а не шесть. И, что хуже, именно три пары, которые мы объявили `confusable_with` (BLAME↔PRESSURE, VALIDATION↔REPAIR, WITHDRAWAL↔AVOIDANCE), — это ровно те пары, которые в литературе **сливаются при факторизации**.
> **candidate change:** добавить в анализ pilot **проверку размерности**, а не только per-label alpha: если BLAME и PRESSURE дают высокое взаимное согласие «хоть один из двух», но низкое согласие «который именно» — это негативность, а не два конструкта.
> **falsification:** alpha(union BLAME∪PRESSURE) ≈ alpha(BLAME) ≈ alpha(PRESSURE) опровергает слияние; alpha(union) существенно выше обоих — подтверждает.
> **Это тоже считается на текущем pilot без изменений.**

---

## 4. SPAFF — что там есть полезного и чего мы не заметили

Дословные критерии negative-affect кодов (Appendix B, Berkeley). SPAFF — «gestalt system … integrates non-verbal and physical cues, voice tone, and speech content». Для текста напрямую непригоден, но две вещи важны:

**Defensiveness:** «Communication of blamelessness or victimization via "yes, but…" statements, cross-complaining, excuses, negative mindreading, countercriticism, or **reflecting blame back onto partner**.»

> **RESEARCH FINDING R-B5.** Это **отдельный установленный конструкт**, а у нас он существует только как *exclusion criterion* внутри `B.REPAIR_ATTEMPT` («"извини, но…" с немедленной контратакой» → negative) и частично внутри `B.BLAME_CRITICISM`.
> Наш аннотатор, увидев «Извини конечно, но это ты всё начала», обязан выбрать: REPAIR (нет, исключено) → BLAME? → none_observed? Онтология не даёт ему правильного ящика, и два аннотатора, скорее всего, выберут разные.
> **candidate change:** `B.DEFENSIVENESS` — сильный кандидат в v1: он (a) имеет прямой prior art, (b) наблюдаем в тексте (в отличие от withdrawal — «yes, but», cross-complaint, countercriticism — это **лексически и структурно видимые** ходы), (c) закрывает известную дыру в наших exclusion-правилах, (d) частотен в конфликтных переписках.
> **falsification:** если в pilot-фидбеке и в confusion-матрице items с «извинение+контратака» **не** порождают повышенного разногласия — дыра теоретическая.

**Domineering:** «Trying to dominate partner via incessant speech, glowering, low balling, **invalidation**, patronizing, or lecturing.» — то есть **в SPAFF «invalidation» фигурирует как cue доминирования**, а не как самостоятельный код. Ещё один довод к §1.6/R-A7 и к [invalidation-review.md](invalidation-review.md).

**Полный состав SPAFF-20** (Coan & Gottman, 2007): 1 нейтральный код; 7 позитивных (affection, high validation, humor, interest, surprise/joy, low validation, tense humor); 12 негативных (contempt, belligerence, **criticism**, **stonewalling**, defensiveness, high domineering, low domineering, anger, sadness, whining, disgust, tension).

> **Поправка к этому же разбору.** Первоначальный вывод, что «кода `Criticism` в SPAFF нет», был **неверен** — он строился на Appendix B диссертации Berkeley, где приведено лишь **подмножество** кодов, использованное в той работе. SPAFF содержит и `Criticism`, и `Stonewalling`. Прежняя провенанс-ссылка на SPAFF `Criticism` в [observational-coding-prior-art.md](observational-coding-prior-art.md) **корректна** и исправления не требует.

**Stonewalling — четвёртый независимый источник по withdrawal.**
SPAFF кодирует «listener withdrawal» отдельным кодом `Stonewalling` (один из «четырёх всадников» Готтмана). Его операционализация: «the face typically appears **stiff or frozen**, the **jaw may be clenched** with obviously **flexed neck muscles**, and other times the face shows **no obvious signs of emotion** at all, deliberately arranged to appear emotionless».

> **RESEARCH FINDING R-B7 — сходимость трёх систем на одном ограничении.** Три независимые традиции определяют withdrawal через невербальный канал:
> - **IDCS**: «withdrawal … cannot be expressed through the content or language»;
> - **CIRS `Withdrawal`**: включает «**looks away**», «does not actively defend self»;
> - **SPAFF `Stonewalling`**: определён **целиком** через лицо и мышечное напряжение.
>
> Это уже не свойство одной работы и не артефакт одного носителя. **Withdrawal — конструкт, чья каноническая операционализация находится вне текста.** Наш `deferred_until_exchange_segmentation` правилен, но его формулировка недооценивает проблему: дело не в том, что нам нужна единица побольше, а в том, что **в тексте отсутствует канал, через который этот конструкт определяется во всех трёх родительских системах**.
> **falsification:** найти опубликованную систему, кодирующую withdrawal/stonewalling **только по тексту** с α ≥ 0.667 у независимых кодировщиков. В этой сессии такой не найдено.

**SPAFF как контрпример к «все couple-системы глобальные».**
SPAFF — **микроаналитическая**: непрерывный посекундный поток кодов, назначаемых в реальном времени с клавиатуры при просмотре видео; порог допуска кодировщика — windowed/free-marginal kappa ≥ 0.6, в цитируемой работе достигнуто >0.7.
То есть мелкая единица в этом поле **возможна** — но ценой (a) непрерывного потока вместо дискретных решений, (b) **аффективного**, а не содержательного объекта кодирования, (c) видео, (d) windowed-метрик согласия вместо поединичных. Ни одно из четырёх условий у нас не выполнимо, но сам факт важен: **наш utterance-уровень не является беспрецедентным по гранулярности — он беспрецедентен по сочетанию «мелкая единица + бинарное решение + только текст + необученные аннотаторы»**.

---

## 5. Repair Attempts — первоисточник недоступен, вывод условный

Repair Attempts Observational Coding System (Tabares, Driver & Gottman; глава в Kerig & Baucom, *Couple Observational Coding Systems*) и «Repair During Marital Conflict in Newlyweds» (2015) — **обе за paywall, прочитать не удалось**. Ниже — по вторичным описаниям, и это должно быть помечено как слабое звено.

По этим описаниям: критерий эффективности repair — (1) снижение негативного аффекта или (2) рост позитивного во время конфликта. Эффективные repair'ы — **аффективные** (общий юмор, привязанность, самораскрытие, выражение понимания и эмпатии, **принятие части ответственности**, «we're okay»), а не когнитивные (проблемо-решение, логика, убеждение). Отмечается «pre-emptive repair» в первые 3 минуты как наиболее эффективный.

> **RESEARCH FINDING R-B6 (условный, primary source unavailable).** Литература трактует repair как **семейство наблюдаемых примитивов + функциональный исход**, причём исход измеряется **изменением аффекта после**, то есть является свойством **перехода**, а не реплики.
> Наш `B.REPAIR_ATTEMPT` уже правильно отделяет попытку от успеха («Успешность repair — свойство ПЕРЕХОДА (T.*)»). Но он **лумпит примитивы**, и минимум один из них (`выражение понимания`) — это дословно наша же `B.VALIDATION`, отчего они и помечены `confusable_with` друг с другом.
> Ответ на Q5 — в [ontology-crosswalk.md](ontology-crosswalk.md) §5.

---

## 6. Сводка: что именно опровергнуто в нашем предыдущем документе

[observational-coding-prior-art.md](observational-coding-prior-art.md) утверждал:

| Прежнее утверждение | Статус после чтения первоисточников |
|---|---|
| `B.VALIDATION` ← IDCS-CMC `Support/Validation`, «CMC-focused adaptation» | **Уточнено.** Наш label — узкое подмножество; пересекается ещё и с `Communication Skills`. Match = partial |
| `B.BLAME_CRITICISM` ← CIRS `Blame`, «event-level adaptation»; SPAFF `Criticism` — supplementary | **Ссылка на SPAFF `Criticism` подтверждена** (SPAFF-20 содержит такой код). Уточнения: в IDCS-CMC blame распределён по `Conflict`+`Denial`, а наш label **уже**, чем CIRS `Blame` |
| `B.PRESSURE_FOR_CHANGE` ← CIRS `Pressure for Change`, «close adaptation» | **Неверно как «close».** Разошлись по ядру (implicit should vs нажим), по валентности (мы потеряли positive pressure) и по нижней границе (мы исключаем то, что CIRS включает) |
| «Withdrawal был проблематичен в той работе; это не доказывает невалидность» | **Верно, но недосказано.** Причина структурная: потеря невербального канала + штатный конфаунд с Dominance внутри самой системы + запрет выводить withdrawal из задержки |
| Withdrawal deferred «потому что unit mismatch» | **Обоснование надо усилить**: не только unit |
| «Более labels не автоматически лучше» (RMICS) | **Подтверждено и усилено**: PCA по 31 item CIRS+SSIRS даёт **4 фактора** |
| Про IDCS-CMC: «dissertation/manual copies may circulate» | **Устарело.** Полный manual — Appendix 3, публично доступен через CORE; DOI 10.13023/etd.2020.440 |

---

## 7. Источники

Первичные, прочитанные полностью:
- Rackets, M. S. (2020). *The Development of a Couple Observational Coding System for Computer-Mediated Communication.* Диссертация PhD, University of Kentucky. DOI [10.13023/etd.2020.440](https://doi.org/10.13023/etd.2020.440) · [запись](https://uknowledge.uky.edu/hes_etds/85/) · [PDF через CORE](https://core.ac.uk/download/363910481.pdf). **Appendix 3 = полный IDCS-CMC manual.**
- Berkeley eScholarship, *The Demand-Withdraw Communication Pattern in Middle-Aged and Older Couples* — [qt1g37d6w6](https://escholarship.org/content/qt1g37d6w6/qt1g37d6w6.pdf). **Appendix A = дословные критерии CIRS; Appendix B = дословные критерии SPAFF.**

Первичные, прочитанные частично (methods/results):
- [PMC3014221](https://pmc.ncbi.nlm.nih.gov/articles/PMC3014221/) — CIRS operationalization, reliability, процедура обучения кодировщиков.
- [PMC4306640](https://pmc.ncbi.nlm.nih.gov/articles/PMC4306640/) — CIRS+SSIRS, PCA → 4 шкалы; подтверждает **unpublished** статус обоих manual'ов.
- [PMC5608311](https://pmc.ncbi.nlm.nih.gov/articles/PMC5608311/) — UCLA/UW Couple Therapy Project: 33 измерения, α=0.7528, **запрет публикации данных**.

Недоступны (зафиксировано как ограничение, не реконструировано):
- CIRS manual (Heavey, Gill & Christensen, unpublished, UCLA).
- SSIRS manual (Jones & Christensen, unpublished, UCLA).
- Kline et al. (2004), глава IDCS в Kerig & Baucom.
- Tabares, Driver & Gottman, Repair Attempts OCS (Taylor & Francis, paywall).
