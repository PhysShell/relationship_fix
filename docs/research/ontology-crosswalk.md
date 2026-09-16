# Ontology crosswalk: внешние конструкты → BehaviorOntology v0.1

Дата: 2026-09-16. Статус: **research-only**. `data/ontology/behavior-v0.1.json` не изменён, sealed pilot не тронут.

Цель таблицы — **не** показать, что у нас всё имеет аналог. Цель — показать, **где совпадает имя, но не совпадает операциональное определение**. `Match` присваивается по сопоставлению inclusion/exclusion-критериев и unit'а, а не по сходству названий.

Источники дословных определений и все обоснования: [couple-coding-systems.md](couple-coding-systems.md), [invalidation-review.md](invalidation-review.md).

---

## 1. Легенда

**Match:**
- `strong` — то же ядро конструкта, те же границы, различия только в форме записи решения;
- `partial` — общее ядро, но у одной стороны существенно шире/уже объём, либо иной различающий критерий;
- `weak` — пересекаются наблюдаемые cues, но конструкты разные;
- `none` — аналога нет.

**Unit mismatch** — расстояние между единицей внешней системы и нашей.

---

## 2. Обязательная таблица

| Our construct | External construct / system | Match | Unit mismatch | Important difference | Evidence |
|---|---|---|---|---|---|
| `B.BLAME_CRITICISM` | **CIRS `Blame`** — «Blames, accuses, or criticizes partner. Uses critical sarcasm, character assassinations» | **partial** | **высокий**: CIRS — 1–9 за весь 15-мин разговор, 2–3 кодировщика усредняются; у нас — binary на реплике | CIRS **не требует генерализации**. «Criticizes» достаточно. Мы требуем генерализацию/оценку личности и **исключаем жалобу на конкретный эпизод**, которая в CIRS = Blame низкой интенсивности. Мы отрезали нижнюю треть шкалы | Berkeley `qt1g37d6w6` Appendix A; [PMC3014221](https://pmc.ncbi.nlm.nih.gov/articles/PMC3014221/) |
| `B.BLAME_CRITICISM` | **IDCS-CMC `Conflict`** (content cues: judges/criticizes, negative overgeneralizations, negative mindreads, sarcasm) + **`Denial`** (entirely blaming partner) | **weak** | **высокий** | В IDCS-CMC кода «Blame» **нет вообще**: наши маркеры разложены по двум разным измерениям. Наш label — срез **поперёк** двух конструктов, а не адаптация одного | IDCS-CMC manual App. 3, Conflict / Denial |
| `B.BLAME_CRITICISM` | **SPAFF `Criticism`** (+ `Contempt`: sarcasm, mockery, insults) | **weak** | **критический**: SPAFF кодируется **посекундно**, непрерывным потоком, по видео | SPAFF-20 (Coan & Gottman, 2007) действительно содержит код `Criticism` — прежняя ссылка **верна**, вопреки первоначальному выводу этого разбора (Appendix B диссертации Berkeley приводит лишь подмножество кодов, использованное в той работе, а не весь SPAFF). Но эквивалентности нет: SPAFF интегрирует мимику, голос и содержание, а unit — секунда |
| `B.PRESSURE_FOR_CHANGE` | **CIRS `Pressure for Change`** — «Requests, demands, nags, manipulates, seduces, or otherwise pressures for change… can be positive or negative… must carry in it an implicit "should" statement» | **partial** (ближе к weak) | **высокий** | Три расхождения: (1) **ядро другое** — у CIRS критерий «implicit should», у нас «нажим»; (2) CIRS **включает позитивное давление** (комплиментами, «seduces») — мы его теряем целиком; (3) CIRS **включает простые requests** низким баллом, мы их **явно исключаем** («однократная нейтральная просьба» → negative) | Berkeley Appendix A |
| `B.VALIDATION` | **IDCS-CMC `Support/Validation`** — «positive listening skills and speaking skills that demonstrate support and understanding… synonyms: encouragement, acknowledgement, and acceptance» | **partial** | **высокий**: 1–9 за весь лог | IDCS-CMC **шире**: включает комплименты/поощрение без признания переживания, включает **принятие атрибуции партнёра о себе**, засчитывает эмодзи-реакции (👍/❤️). Мы требуем именно явное признание эмоции/позиции. Наш label — **узкое подмножество** | IDCS-CMC manual App. 3, Support/Validation |
| `B.VALIDATION` | **IDCS-CMC `Communication Skills`** (cues: «summarizes partner's opinions, feelings, or decisions», «makes effort to validate the importance of partner's feedback») | **weak** | высокий | Наш «перефразирование переживания партнёра» в IDCS-CMC попадает **сюда**, а не в Support/Validation. То есть наш единственный label расщеплён во внешней системе между двумя измерениями | IDCS-CMC manual App. 3 |
| `B.VALIDATION` | **VIBCS `Validation`** (clarification, relevant questions, articulating why the other's experience makes sense) | **partial** | **средний**: 30-сек клипы + global, шкала 1–7 | Ближайшее по духу. Но VIBCS явно включает **уточняющие вопросы** как валидацию — у нас вопросов нет вообще ни в одном label. ICC валидации **0.70** — самый низкий из пары, т.е. это трудная сторона даже для обученных | JSM 20(8):1103; Fruzzetti 2001 (unpublished) |
| `B.WITHDRAWAL` | **CIRS `Withdrawal`** — «Withdraws, becomes silent, refuses to discuss a particular topic, looks away, refuses to argue, does not actively defend self, pulls back, retreats, disengages. **More passive than Avoidance**» | **partial** | **критический**: CIRS = весь разговор; наши allowed_units [turn, exchange]; в pilot **deferred** | Различитель CIRS — **пассивность**, а не «ушёл vs остался». Часть cues невербальны («looks away»). Наш exclusion «объявленный таймаут → repair» в CIRS попал бы в **Avoidance** («delays discussion»), не в repair | Berkeley Appendix A |
| `B.WITHDRAWAL` | **IDCS-CMC `Withdrawal`** — «the avoidance of the interaction or of the problem discussion. The individual may evade the issue, retreat into a shell, back off…» | **partial** | **критический** | (a) IDCS-CMC Withdrawal **включает avoidance внутрь себя** — то есть внешняя система **не делает** наш split; (b) родительский manual утверждает, что withdrawal **не выражается содержанием/языком**; (c) **ICC .87→.51→.52** при снятии калибровочного якоря; (d) штатный конфаунд с `Dominance` («withholds contributions as a means of exerting control»), у которого ICC .30 | IDCS-CMC manual App. 3 + Table 4.1 + гл. 5 «Withdrawal» |
| `B.WITHDRAWAL` | **IDCS-CMC `Dominance`** (cue: «Withholds contributions to conversations as a means of exerting control») | **weak, но это конфаунд, а не поддержка** | — | Тот же наблюдаемый признак (молчание/схлопывание вклада) принадлежит **двум** измерениям; различает их ненаблюдаемая функция. Оба провалили reliability | IDCS-CMC manual App. 3, Dominance |
| `B.WITHDRAWAL` | **SPAFF `Stonewalling`** (listener withdrawal; один из «четырёх всадников») | **partial — и это сильнейший довод против текстовой наблюдаемости** | **критический**: посекундное кодирование по видео | Каноническая операционализация опирается на **лицо и тело**: «the face typically appears stiff or frozen, the jaw may be clenched with obviously flexed neck muscles… deliberately arranged to appear emotionless». В тексте не существует **ничего** из этого. Третий независимый источник (после IDCS и CIRS), определяющий withdrawal через невербальный канал | [Frontiers in Psychiatry 2023](https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2023.980739/full); Coan & Gottman 2007 |
| `B.AVOIDANCE_TOPIC_SHIFT` | **CIRS `Avoidance`** — «Actively avoids discussing the problem. Hesitates, changes topics, diverts attention, or delays discussion. **More active than Withdrawal**» | **strong** | **средний**: CIRS = весь разговор, но сам ход **локализуем** в репликах | Лучшее совпадение во всей таблице. Расхождение одно: CIRS включает «delays discussion» в Avoidance, а мы выносим объявленный перенос в exclusion. Внешне подтверждена и **дискриминантная валидность**: avoidance ↔ demand коррелирует **отрицательно**, withdrawal ↔ demand — около нуля | Berkeley Appendix A; Berkeley Results (корреляции T1–T3) |
| `B.REPAIR_ATTEMPT` | **Repair Attempts OCS** (Tabares, Driver & Gottman) | **partial, оценка условная** | **высокий** | **Первоисточник недоступен (paywall).** По вторичным описаниям: repair — семейство примитивов (общий юмор, привязанность, самораскрытие, выражение понимания/эмпатии, принятие ответственности, «we're okay») + **аффективный исход**. Мы лумпим примитивы в один label. Разделение «cognitive vs emotional repair» с разной эффективностью у нас отсутствует | Каталог T&F; вторичные пересказы — **помечено как слабое звено** |
| `B.REPAIR_ATTEMPT` | **SPAFF `Defensiveness`** — «blamelessness or victimization via "yes, but…", cross-complaining, excuses, negative mindreading, countercriticism, reflecting blame back» | **none → это дыра** | n/a | У нас это **только exclusion-критерий** внутри REPAIR («"извини, но…" с контратакой» → negative). Аннотатору некуда положить такое высказывание. Во внешней системе это **самостоятельный конструкт** | Berkeley Appendix B |
| `INV-01a` (observable invalidating behavior) | **VIBCS `Invalidation`** (inattentiveness, being judgmental, telling someone they should not feel a certain way, agreeing with self-invalidation) | **partial** | **средний**: 30-сек клипы + global, 1–7 | Кодируется **надёжнее валидации** (ICC **0.86** vs 0.70). Но: инструмент **неопубликован**, применялся только к видео/аудио, к тексту **никем не переносился**. Ключевая часть («agreeing with the other's self-invalidation») лексически невидима | JSM 20(8):1103 |
| `INV-01a` | **IDCS-CMC `Denial`** — «active rejection of a problem's existence or of personal responsibility», cues: minimizing, «blames partner for blowing the problem out of proportion», «claims partner is imagining or making up the problem» | **partial — и это лучший найденный кандидат** | **высокий** (1–9 за лог), но cues **чисто текстовые** | У нас **нет ничего похожего на `Denial`**. ICC **.76/.79/.80**, стабилен, **не потребовал модификации при переносе FtF→CMC** — единственный конструкт с таким свойством. Покрывает минимизацию и «ты преувеличиваешь/выдумываешь» | IDCS-CMC manual App. 3 + Table 4.1 + гл. 3 |
| `INV-01a` | **IDCS-CMC `Conflict`** (cue: «Minimizes the value of partner's contributions») / **SPAFF `Domineering`** (cue: «invalidation») | **weak** | — | Подтверждает: поле кодирует инвалидацию **как cue чужих кодов**, а не как самостоятельный код | IDCS-CMC App. 3; Berkeley App. B |
| `INV-01b` (perceived invalidation) | **PIES** (Zielinski & Veilleux, 2018) | **none — по построению** | **несоизмеримо**: self-report получателя | Операциональное определение поля **явно ставит восприятие получателя выше объективного поведения отвечающего**. Не может быть label'ом BehaviorOntology ни при каком unit'е | [PMC6212305](https://pmc.ncbi.nlm.nih.gov/articles/PMC6212305/) |
| *(нет у нас)* | **IDCS-CMC `Denial`** | **none** | — | См. выше — кандидат `B.DENIAL_MINIMIZATION` | |
| *(нет у нас)* | **SPAFF `Defensiveness`** | **none** | — | Кандидат `B.DEFENSIVENESS` | |
| *(нет у нас)* | **CIRS/IDCS `Discussion` / `Problem-Solving Skills`** (конструктивное участие; в CIRS **reverse-coded** в withdraw-композит) | **none** | — | У нас **нет ни одного позитивного конструкта, кроме VALIDATION и REPAIR**. В CIRS «engagement» — не отсутствие withdrawal, а **измеряемая величина**. Это даёт withdrawal-композиту третий индикатор, и, вероятно, поэтому CIRS Withdrawal даёт .80, а IDCS-CMC — .52 | Berkeley Appendix A; [PMC3014221](https://pmc.ncbi.nlm.nih.gov/articles/PMC3014221/) |
| *(нет у нас)* | **IDCS/IDCS-CMC `Positive Escalation` / `Negative Escalation`** (диадические: цепочка «позитив→позитив», «негатив→негатив») | **none** — это `T.*`/DyadicState, не BehaviorOntology | — | Подтверждает правильность нашего разделения `B.*` / `T.*`. ICC .83 / .74 — **выше, чем у Withdrawal**: диадический паттерн кодируется надёжнее, чем индивидуальный уход | IDCS-CMC manual App. 3, Dyadic Codes |

---

## 3. Minimum observation unit — отдельный deliverable

Оценка для каждого конструкта: какая **минимальная** единица наблюдения делает решение определённым. Основание — только то, что реально есть в источниках; там, где источников нет, стоит `не установлено`, а не догадка.

| Construct | Minimum unit | Основание |
|---|---|---|
| `B.BLAME_CRITICISM` (генерализующая форма) | **UTTERANCE** | Единственный конструкт, чьи inclusion-маркеры **полностью содержатся в реплике**: кванторы всегда/никогда, оценка личности. Внешние системы кодируют выше, но по *шкале интенсивности*, а не потому, что реплики не хватает |
| `B.BLAME_CRITICISM` (вина за конкретный эпизод) | **EXCHANGE** | Атрибуция вины требует знать, о каком событии речь и чья версия оспаривается. Наш собственный confusable-пример «ну ты дебил 😂❤️» разрешается **только** историей пары → фактически **LONGITUDINAL** |
| `B.PRESSURE_FOR_CHANGE` | **EXCHANGE** | Наш собственный inclusion-критерий содержит «**повторение** требования с эскалацией нажима» — повторение по определению не наблюдаемо в одной реплике. CIRS-критерий «implicit should» формально utterance-локален, но отличить его от нейтральной просьбы без истории темы нельзя |
| `B.VALIDATION` | **EXCHANGE** | Конструкт **реляционный по определению**: признание *чего-то, что партнёр выразил*. Без предшествующей реплики с переживанием «понимаю, звучит обидно» не квалифицируется. IDCS-CMC кодирует его как combined code над всем логом |
| `B.REPAIR_ATTEMPT` | **EXCHANGE** (попытка) / **EPISODE** (процесс) | «Прекращение негативной петли» требует наличия петли. Отличить извинение-repair от извинения-контратаки («извини, но…») можно внутри реплики; отличить repair от капитуляции («ладно, как скажешь») — нет |
| `B.AVOIDANCE_TOPIC_SHIFT` | **EXCHANGE** | Минимально — adjacency pair: поднятая тема → уводящий ход. Наш собственный ambiguous-пример это подтверждает: «Кстати, ты видела…» без предшествующего вопроса **неразрешим**. Ход **активен и локализуем**, поэтому exchange достаточно — episode не требуется |
| `B.WITHDRAWAL` | **EPISODE** (в тексте), и даже там **не установлено** | Отсутствие вклада не локализуется. Нужно: (a) активный конфликтный эпизод, (b) базовый темп пары, (c) исключение внешних причин молчания. Единственная попытка в CMC — global над 15 мин, **ICC .52**. Exchange-уровень **не тестировал никто**. Честный статус: **минимальная надёжная единица неизвестна и может не существовать для текста** |
| `INV-01a` предписание чувства («не надо так реагировать») | **UTTERANCE** | Ход содержится в реплике целиком |
| `INV-01a` минимизация | **UTTERANCE** | «Да ерунда», «раздуваешь» — самодостаточно |
| `INV-01a` смена темы после раскрытия | **EXCHANGE** | Нужно раскрытие перед ходом |
| `INV-01a` согласие с само-инвалидацией | **EXCHANGE** | Нужна само-инвалидирующая реплика партнёра |
| `INV-01b` perceived invalidation | **не unit-вопрос** | Истинностное условие — самоотчёт получателя. Никакая единица текста не делает его наблюдаемым |
| `B.DENIAL_MINIMIZATION` (кандидат) | **EXCHANGE** | Отрицание проблемы требует, чтобы проблема была поднята |
| `B.DEFENSIVENESS` (кандидат) | **EXCHANGE** | «Yes, but», cross-complaint, countercriticism — все определяются **относительно предыдущей реплики** |
| pursue–withdraw / demand–withdraw | **EPISODE** | В CIRS это **композит двух людей** (demand одного + withdraw другого) по целому разговору. Утверждать паттерн по одному обмену нельзя |
| escalation (positive / negative) | **EPISODE** | IDCS-CMC: «**consecutive** chains … unrelated positive behaviors do **not** constitute a snowball effect» — явное требование последовательности |
| coercive control | **LONGITUDINAL** | Ни одна из разобранных систем не кодирует это по одному разговору. Вне области наблюдательного кодирования интеракции |

### Прямое следствие для текущего pilot

Из пяти активных labels **pilot кодирует на utterance ровно один** (`B.BLAME_CRITICISM` в генерализующей форме), для которого utterance действительно достаточен.

Четыре остальных (`PRESSURE_FOR_CHANGE`, `VALIDATION`, `REPAIR_ATTEMPT`, `AVOIDANCE_TOPIC_SHIFT`) требуют минимум exchange.

**Смягчающее обстоятельство, и оно существенное:** items pilot'а — не одиночные реплики, а короткие обмены из 2–4 сообщений с `target_message_id`. То есть **контекст exchange фактически предъявлен**, хотя решение выносится о реплике.

> **RESEARCH FINDING R-D1.** Наш дизайн — не «utterance-only», а **«exchange-context, utterance-decision»**. Это принципиально лучше, чем чистый utterance, и это надо было называть правильно с самого начала: `unit_of_analysis: "utterance"` в манифесте **занижает** то, что реально сделано.
> Остаточный риск, который контекст **не** снимает: границы `B.PRESSURE_FOR_CHANGE` (нужно **повторение** через несколько ходов, а items коротки) и `B.REPAIR_ATTEMPT` (нужна установленная петля).
> **falsification:** если alpha для `AVOIDANCE_TOPIC_SHIFT` и `VALIDATION` (exchange-конструкты, но с предъявленным контекстом) окажется **не хуже**, чем для `BLAME_CRITICISM` (utterance-конструкт), — предъявление контекста работает, и unit-риск для них закрыт.
> **Это проверяется на текущем pilot без изменений.**

---

## 4. Ответы на Q1–Q5

### Q1 — какие labels имеют сильный prior art

| Label | Сила prior art | Комментарий |
|---|---|---|
| `B.AVOIDANCE_TOPIC_SHIFT` | **сильный** | CIRS `Avoidance` — совпадение по операциональному ядру; α .83 у обученных; **дискриминантная валидность подтверждена** отдельно от withdrawal |
| `B.BLAME_CRITICISM` | **сильный по конструкту, средний по границам** | CIRS `Blame` α .90 — самый надёжный конструкт во всей разобранной литературе. Но наши границы уже |
| `B.WITHDRAWAL` | **сильный в FtF (α .80), слабый в тексте (ICC .52)** | Валиден как конструкт, **структурно проблемен как измерение в тексте**: три независимые системы (IDCS, CIRS, SPAFF `Stonewalling`) определяют его через невербальный канал (R-B7) |
| `B.VALIDATION` | **средний** | Расщеплён между IDCS-CMC `Support/Validation` (ICC .75) и `Communication Skills`; VIBCS `Validation` ICC .70 — **самая низкая надёжность в паре с инвалидацией** |
| `B.PRESSURE_FOR_CHANGE` | **средний** | CIRS α .92, но **мы кодируем другой конструкт** (нажим вместо implicit should, без позитивного давления) |
| `B.REPAIR_ATTEMPT` | **слабый по нашей операционализации** | Первоисточник недоступен; во внешней литературе это **семейство**, а не один код |

### Q2 — какие выглядят operationally wrong / слишком широкими / слишком функциональными

1. **`B.REPAIR_ATTEMPT` — слишком функциональный.** Определён через *цель* («направленное на прекращение негативной петли»), т.е. через намерение. Объединяет извинение, юмор, предложение перезапуска — три поведения с разными маркерами. Inclusion-критерий «разряжающий юмор, адресованный напряжению (не партнёру)» требует от аннотатора решить, **на что направлен** юмор — это вывод о намерении, который наш же протокол запрещает.
2. **`B.PRESSURE_FOR_CHANGE` — operationally wrong относительно заявленного предка.** См. выше и R-B2. Плюс порог «нажим» — градуальный признак, бинаризованный в самой плотной зоне шкалы.
3. **`B.WITHDRAWAL` — правильно deferred, но обоснование неполно.** Проблема не только в unit'е: потерян несущий канал, есть штатный конфаунд с dominance, а опора на латентность **явно запрещена** единственной системой для нашего носителя.
4. **`B.VALIDATION` — слишком узкий там, где это не нужно, и слишком широкий там, где нужно.** Исключает вопросы (VIBCS их включает), но включает любое «явное признание эмоции», не отделяя настоящее признание от ритуального.
5. **`B.BLAME_CRITICISM` — систематически сдвинут вверх по интенсивности**, вместе с PRESSURE. Оба потеряют нижнюю часть распределения → редкость → prevalence-проблема.

### Q3 — какие требуют большего context unit

`B.WITHDRAWAL` (episode, и даже там не установлено) → `B.REPAIR_ATTEMPT` (exchange для попытки, episode для процесса) → `B.PRESSURE_FOR_CHANGE` (exchange, из-за требования повторения) → `B.VALIDATION`, `B.AVOIDANCE_TOPIC_SHIFT` (exchange, **но контекст уже предъявлен в items**).

### Q4 — стоит ли добавлять invalidation

**Нет** в виде label `INVALIDATION`. **Да** в виде более узкого, текстово-наблюдаемого `B.DENIAL_MINIMIZATION` — как кандидата, требующего фальсификации, а не как решённого вопроса. Полное обоснование и критерии — [invalidation-review.md](invalidation-review.md) §7.

### Q5 — разделять ли REPAIR_ATTEMPT

**Да.** Основания:

- внешняя литература трактует repair как **семейство примитивов + аффективный исход**, а не как один код;
- наш собственный `confusable_with: ["B.VALIDATION"]` — это признание того, что один из примитивов (**выражение понимания**) *дословно совпадает* с отдельным label'ом;
- функциональный признак («направлено на прекращение петли») невыводим из текста без вывода о намерении;
- SPAFF `Defensiveness` показывает, что «извинение с контратакой» — **самостоятельный конструкт**, а не просто exclusion.

> **candidate change (НЕ внедрено).** Разложить на наблюдаемые примитивы, а функцию repair перенести в производный слой:
>
> ```
> наблюдаемые примитивы (BehaviorOntology, каждый со своим alpha):
>     B.TAKING_RESPONSIBILITY   принятие части ответственности за конкретное
>     B.APOLOGY                 извинение (форма, без требования искренности)
>     B.VALIDATION              уже есть
>     B.SOFTENING               смягчение/деэскалирующий ход, юмор-разрядка
>     B.RESTART_PROPOSAL        явное предложение начать заново / остановиться
>
> производный слой (НЕ label):
>     T.REPAIR_PROCESS = композиция примитивов + наблюдаемый отклик партнёра
> ```
>
> `B.APOLOGY` намеренно отделён от `B.TAKING_RESPONSIBILITY`: это и делает «извини, но это ты начала» **представимым** (APOLOGY=yes, TAKING_RESPONSIBILITY=no, + кандидат `B.DEFENSIVENESS`), вместо того чтобы выбрасывать случай в `none_observed`.
>
> **Критерий фальсификации:** если в pilot `B.REPAIR_ATTEMPT` даст α ≥ 0.667 **и** доля его confusion с `B.VALIDATION` < 20% — лумпинг работает, разделение не оправдано, экономим 4 label'а.
> **Если α < 0.667 и confusion с VALIDATION высок** — разделение обосновано эмпирически, а не эстетически.
> **Это решается текущим pilot без изменений.** До его результатов не разделять.

---

## 5. Что из этого НЕ следует делать

- Не переписывать `B.PRESSURE_FOR_CHANGE` под CIRS. Если мы включим requests и позитивное давление, конструкт станет верным по отношению к CIRS и **бесполезным для продукта** (любая просьба = pressure). Расхождение с CIRS надо **задокументировать как осознанное**, а не устранить.
- Не добавлять `B.DENIAL_MINIMIZATION`, `B.DEFENSIVENESS` и разложение REPAIR до результатов pilot. Три новых label'а на непроверенной онтологии — это возврат к нулю, а не прогресс.
- Не менять `unit_of_analysis` в манифесте pilot. Он sealed. Уточнить наименование можно только в следующей версии.
- Не использовать ICC из IDCS-CMC/CIRS как ожидание для нашего pilot. Там обученные кодировщики, недели калибровки, градуальные шкалы и усреднение 2–6 оценок. Наши **два обычных человека с бинарными решениями** — другая задача; см. [next-research-design.md](next-research-design.md) §3.

---

## 6. Источники

Все дословные определения выше взяты из:

- Rackets, M. S. (2020), диссертация PhD, University of Kentucky, DOI [10.13023/etd.2020.440](https://doi.org/10.13023/etd.2020.440) — **Appendix 3 = полный IDCS-CMC manual** ([PDF](https://core.ac.uk/download/363910481.pdf))
- Berkeley eScholarship [qt1g37d6w6](https://escholarship.org/content/qt1g37d6w6/qt1g37d6w6.pdf) — **Appendix A = CIRS criteria**, **Appendix B = SPAFF criteria** (подмножество)
- [PMC3014221](https://pmc.ncbi.nlm.nih.gov/articles/PMC3014221/) — CIRS operationalization и reliability
- [PMC4306640](https://pmc.ncbi.nlm.nih.gov/articles/PMC4306640/) — CIRS+SSIRS, PCA → 4 шкалы; unpublished-статус manual'ов
- [PMC6212305](https://pmc.ncbi.nlm.nih.gov/articles/PMC6212305/) — PIES, операциональное определение emotion invalidation
- [PMC4477266](https://pmc.ncbi.nlm.nih.gov/articles/PMC4477266/) — validating pain communication; отсутствие работ, связывающих observer-coding и self-report
- Journal of Sexual Medicine 20(8):1103 — [применение VIBCS к парам](https://academic.oup.com/jsm/article/20/8/1103/7205210)
- [Frontiers in Psychiatry 2023;14:980739](https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2023.980739/full) — состав SPAFF-20, посекундное кодирование
