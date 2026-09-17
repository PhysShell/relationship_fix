# Target Acquisition Qualification v0 — Telegram Desktop JSON

Статус: **открыт**. Ни одной строки адаптера не написано и не будет написано,
пока свойства, от которых он зависит, не получат статус или явно записанный отказ.

Это тот же ledger-приём, что в `reactivity-power-design.md` §6.1.2 для корпусов,
но вопрос другой. Там: что гарантирует опубликованный датасет. Здесь: **что
реально отдаёт устройство, на котором побежит пилот**.

## 0. Почему один target, а не матрица

Из двух треков §6.1.1 Telegram Desktop — единственный, который в принципе может
удовлетворить экстрактор: он отдаёт `id`, абсолютный timestamp, маркер правки и
различение message/service. WhatsApp-текстовый экспорт уже известен по корпусу
Seufert — ни идентификаторов, ни разрешения лучше минуты. Если не проходит
Telegram, plain-text не пройдёт тем более, и матрица на девять мессенджеров была
бы девятью копиями одного вердикта.

**Допущение, названное потому, что перевернуть его может только заказчик:**
пилот идёт этим путём. Если он пойдёт через WhatsApp, этот ledger — не
неправильный, а неправильный **первым**.

## 1. Правила ledger'а

Пять полей на свойство плюс `claim_scope`, и три механических правила, живущих в
`extractor/adapters/acquisition.py`, а не в памяти:

```
QUALIFIED     без primary evidence           → отказ конструктора
claim_scope = PHYSICAL_CHRONOLOGY
              при статусе ниже QUALIFIED     → отказ конструктора
PARTIAL       без downstream consequence
              или без adapter behavior       → effective_status = UNKNOWN
UNAVAILABLE   без записанного отказа         → отказ конструктора
```

`claim_scope` появился из истории с `EXPORTED_POSITION`: «источник даёт порядок»
эволюционирует в «мы знаем истинную хронологию Вселенной» за один абзац. Три
уровня — `artifact` (верно про файл), `device_state` (верно про то, что хранило
устройство), `physical` (верно про то, что произошло). Третий уровень требует
QUALIFIED, механически.

`PARTIAL` не является вежливым синонимом «ну вроде нормально». Если downstream
contract сформулировать нельзя, `effective_status` сам съезжает в `UNKNOWN` —
не молча: `demoted` это сообщает, и тест `test_no_partial_survived_without_a_contract`
падает, если кто-то напишет оптимистичный ярлык без содержания.

## 2. Ledger

Источники прочитаны напрямую, а не через пересказ. Это существенно: первая же
попытка получить ответ «через резюме» дала утверждение, что строка `date` — это
UTC. Открытие `SerializeDate` показало обратное.

```
WRITER    telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp
SETTINGS  telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_settings.h
OFFSETS   core.telegram.org/api/offsets
BLOG      telegram.org/blog/export-and-more
```

### 1. Coverage / completeness / provenance

| свойство | статус | claim | primary evidence | consequence · adapter | что закроет |
|---|---|---|---|---|---|
| `coverage.export_scope`<br>Что вообще входит в экспорт? | **QUALIFIED** | Пользователь выбирает чаты; экспорт одного чата дополнительно ограничивается диапазоном дат.<br>_ограничения:_ границы диапазона задаёт человек в момент экспорта · настройка существует — её соблюдение отдельный вопрос, см. `coverage.requested_range_honored` | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_settings.h:88-89 — `TimeId singlePeerFrom` / `singlePeerTill` · telegram.org/blog/export-and-more — «export some (or all) of your chats» | Содержимое файла — функция выбора пользователя, а не истории.<br>**adapter:** Адаптер обязан получать окно извне и не выводить его из файла. | Экспорт одного чата с заданным диапазоном + экспорт без него. |
| `coverage.window_provenance`<br>Означает ли period_end реальное покрытие? | **UNAVAILABLE** | Нет. Экспорт не записывает запрошенный диапазон.<br>_ограничения:_ первое и последнее сообщение файла не доказывают ничего | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp — объект чата пишет `name`/`type`/`id`/`messages`; полей диапазона нет ни одного · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_settings.h:88-89 — диапазон существует, но в вывод не попадает | `reentry_burden_H` требует общего окна; вывести его из файла нельзя — только из протокола (даты зачисления).<br>**adapter:** Отказ выводить period_start/period_end из содержимого; окно — обязательный аргумент, как сейчас в `extract()`. | Два экспорта одного чата с разными диапазонами — файлы обязаны быть неразличимы по метаданным покрытия. |
| `coverage.completeness`<br>Можно ли доказать, что в окне нет пропусков? | **UNAVAILABLE** | Нет, и это не «не установлено»: молчаливое усечение экспорта наблюдалось.<br>_ограничения:_ #31328 — про private supergroups с отключённой пересылкой; для диадического чата тот же потолок НЕ показан · один контрпример опровергает гарантию, но не измеряет частоту | tdesktop#31328 (2026-09-16, v7.2.8, OPEN) — ровно 10000 сообщений, JSON и HTML · tdesktop#27183 (2023-12-03, v4.12.2, closed as NOT PLANNED) — последний выбранный день отсутствует · telegram.org/blog/export-and-more — о полноте не сказано ничего | Гарантии полноты нет ни при каком чтении файла. Пропуск в окне неотличим от молчания, а молчание у нас вносит полный H — то есть усечение экспорта выглядит как медленный ответ.<br>**adapter:** Никогда не выводить покрытие из содержимого. Помечать экспорт подозрительным при круглом числе сообщений (10000) и при совпадении первого сообщения с началом окна; отказ, а не тихая обработка. | Два экспорта одного чата и окна: diff множества id (частота, не гарантия). |
| `coverage.requested_range_honored`<br>Соблюдается ли выбранный диапазон дат? | **UNAVAILABLE** | Не надёжно. Подтверждены отказы обоих краёв в разных версиях.<br>_ограничения:_ #5854 закрыт, #27183 закрыт как not planned, #30412 и #31082 закрыты как duplicate — то есть класс признан, а не опровергнут · наблюдалось на 1.6.2 (2019), 4.12.2 (2023), 6.6.2 и 7.0.6 (2026) — семь лет одного и того же симптома | tdesktop#5854 (2019-03-27, v1.6.2, closed) — «ALL the messages are exported» · tdesktop#27183 (2023-12-03, v4.12.2, closed as NOT PLANNED) — последний выбранный день отсутствует · tdesktop#30412 (2026-03-07, v6.6.2, closed as duplicate) — «It exports whole channels messages from oldest message» · tdesktop#31082 (2026-07-30, v7.0.6, closed as duplicate) — «The exported JSON file contains messages from the entire history, including messages sent before the selected start date» · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_api_wrap.cpp:2282-2290 — механизм: `MTPmessages_GetHistory` уходит с `offset_date = 0`, а в ветке `messages.Search` `min_date`/`max_date` передаются как `MTP_int(0)`. Диапазон в запрос НЕ входит вообще — он применяется на клиенте позже, и именно поэтому ломается | UI-диапазон не является утверждением о покрытии — ни слева (могут прийти все сообщения), ни справа (может пропасть последний день). Окно `reentry_burden_H` берётся ТОЛЬКО из протокола, и это теперь не осторожность, а следствие.<br>**adapter:** Игнорировать диапазон экспорта как источник окна; отбор по периоду делает `extract()` из протокольных границ, как сейчас. | Экспорт с заданным диапазоном: есть ли сообщения вне его. |
| `provenance.producer_version`<br>Известно ли, какая версия клиента произвела файл? | **UNAVAILABLE** | Из файла — нет. Поля версии в выводе не существует.<br>_ограничения:_ а семантика между версиями наблюдаемо меняется — #30647 | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp — в выводе только свободные строки `about`, поля версии нет · tdesktop#30647 (2026-05-03, v6.7.8, result.json attached) | Все статусы этого ledger'а версионно-зависимы, а файл не говорит, к какой версии относится. «Telegram Desktop JSON» — недостаточное имя источника; нужны `producer_version` и платформа.<br>**adapter:** Версия и платформа собираются ВНЕ файла, в момент acquisition, и входят в provenance наравне с согласием. Файл без версии — незаявленная семантика; адаптер обязан это пометить, а не додумать. | Экспорты с двух разных версий: различимы ли они по содержимому вообще. |
| `format.strict_json`<br>Гарантированно ли валиден выходной JSON? | **UNAVAILABLE** | Нет, и это не «не установлено»: существуют конкретные невалидные выгрузки, два независимых класса.<br>_ограничения:_ #27571 закрыт как not planned — то есть класс признан и не чинится · существование валидных файлов ничего не гарантирует о формате | tdesktop#24961 (2022-08-20, v4.1.1, closed) — «Export chat history» outputs illegal JSON with custom emojis: значение без кавычек там, где JSON требует строку · tdesktop#27571 (2024-03-12, v4.15.1, closed as NOT PLANNED) — `\x01` внутри строки; jq: «parse error: Invalid escape at line 2415365, column 47» · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp — вывод строится в значительной части вручную (`SerializeString`/`SerializeObject`/`SerializeArray`, склейка байтовых блоков), а не исключительно структурным JSON-builder'ом · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:2793 — Qt-классы JSON в файле есть, но `QJsonDocument::fromJson` стоит на пути ЧТЕНИЯ стороннего файла в `other_data`, а не на пути записи сообщений | Полагаться на валидность нельзя — это знание, а не пробел. Гарантия при этом и не нужна: допущение снято поведением.<br>**adapter:** Строгий разбор; отказ разбора = отказ acquisition, без починки «почти JSON» на лету. | `tools/export_scan.py` по публичным файлам: доля невалидных. Статус уже UNAVAILABLE, замер нужен для частоты, не для вердикта. |

### 2. Ordering

| свойство | статус | claim | primary evidence | consequence · adapter | что закроет |
|---|---|---|---|---|---|
| `ordering.timestamp`<br>Есть ли абсолютная временная метка? | **QUALIFIED** | `date_unixtime` — секунды эпохи, отдельным полем у каждого сообщения. | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1553 — `{ "date_unixtime", SerializeDateRaw(message.date) }` · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:82-84 — `SerializeDateRaw` = `QString::number(date)` | Порядок и длительности строятся на этом поле.<br>**adapter:** `ordering_evidence = TIMESTAMP`; читать только `date_unixtime`. | Реальный экспорт: доля сообщений без поля (ожидается 0). |
| `ordering.resolution`<br>Какое разрешение? | **PARTIAL** | Секунда: `TimeId` — целые секунды, миллисекунд в экспорте нет.<br>_ограничения:_ cross-actor ties внутри одной секунды возможны | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:77-84 — `SerializeDate(TimeId)`/`SerializeDateRaw(TimeId)` | Длительности пригодны (горизонты 6/12/24 ч против секунды); ties не могут устанавливать топологию — один перевёрнутый tie превращает одну передачу хода в две, и вторая вносит полный H.<br>**adapter:** Топология допустима, только пока доля неоднозначных cross-actor ties измерена и мала; иначе — тот же отказ, что у Seufert. | Реальный экспорт: доля соседних cross-actor пар с равным `date_unixtime`. |
| `ordering.exported_position`<br>Какой порядок у элементов массива `messages`? | **QUALIFIED** | Возрастающий `id`. Не «хронологический» — именно id, и это установлено кодом, а не наблюдением.<br>_ограничения:_ порядок по id равен хронологическому только если id монотонен по времени — а это отдельный вопрос, см. `ordering.tie_semantics` | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_api_wrap.cpp:2216-2218 — `requestChatMessages(split, largestIdPlusOne, -kMessagesSliceLimit, kMessagesSliceLimit)`: `offset_id` = курсор, `add_offset = -100`, `limit = 100` — постраничный обход ВПЕРЁД по id · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/data/export_data_types.cpp:3470-3473 — `ParseMessagesSlice` идёт по входному вектору С КОНЦА: `for (auto i = list.size(); i != 0;) {{ list[--i] }}`, то есть разворачивает убывающий ответ сервера в возрастающий · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_api_wrap.cpp:2806 — `largestIdPlusOne = slice.list.back().id + 1`: курсор берёт ПОСЛЕДНИЙ элемент развёрнутого среза, что подтверждает возрастание · core.telegram.org/api/offsets — «typically ... descending object ID values» на стороне API | `ordering = TOTAL`, и позиция — осмысленное свидетельство: она детерминирована и означает id-порядок. Но выдавать её за хронологию нельзя, пока не закрыт id↔время.<br>**adapter:** `ordering_evidence` объявляется как id-порядок, а не как хронология; адаптер не пересортировывает файл молча. | Публичный `result.json`: монотонность `id` по позиции и доля пар, где `date_unixtime` убывает при возрастании `id`. |
| `ordering.tie_semantics`<br>Что разрешает равенство секунд? | UNKNOWN | Позиция в файле, то есть возрастающий `id`. Остаётся ровно один открытый вопрос: монотонен ли `id` по времени.<br>_ограничения:_ два неизвестных схлопнулись в одно: вопрос о ties — это вопрос об id↔времени и ничего сверх · tdesktop#30421 (локальные id дают временно неверный визуальный порядок в живом клиенте) — НЕ evidence: экспорт видит финализированные серверные id. Но хорошее предупреждение против тезиса «id по определению есть время» | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/data/export_data_types.cpp:3470-3473 и telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_api_wrap.cpp:2216 — внутри секунды порядок задаёт id, потому что весь файл задаёт id · core.telegram.org/api/offsets — «typically» гарантией монотонности не является | — | `tools/export_scan.py` по публичным файлам: пара, где `id` растёт, а `date_unixtime` падает. ОДИН такой случай закрывает вопрос отрицательно; отсутствие на конечной выборке даёт максимум PARTIAL с долей. |
| `ordering.multi_device`<br>Могут ли в файле оказаться две копии одного сообщения? | **QUALIFIED** | Этот путь экспорта дублей по `id` не производит: срезы не перекрываются, а мигрированная история сдвинута в непересекающийся диапазон.<br>_ограничения:_ утверждение о пути экспорта, а не о мире: два РАЗНЫХ файла по-прежнему могут содержать один и тот же id | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_api_wrap.cpp:2806 — курсор `largestIdPlusOne = back().id + 1` строго проходит за уже взятый максимум, поэтому срезы дизъюнктны · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/data/export_data_types.cpp:3478-3486 + :30 — `AdjustMigrateMessageIds` прибавляет `kMigratedMessagesIdShift = -1'000'000'000`, то есть уводит id мигрированной истории в ОТРИЦАТЕЛЬНЫЙ диапазон — механизм существует именно затем, чтобы склейка двух историй не сталкивалась по id | `DuplicateConflict` и `DeletionStateConflict` на этом пути входных данных не получают. Это не повод их удалять — они написаны под multi-device источники, которых здесь нет.<br>**adapter:** Дедупликация остаётся включённой и обязана срабатывать НОЛЬ раз; ненулевой счётчик на этом источнике — сигнал, а не рутина. | Публичный `result.json`: повторяющиеся `id`; ожидается 0. |

### 3. Identity

| свойство | статус | claim | primary evidence | consequence · adapter | что закроет |
|---|---|---|---|---|---|
| `identity.message_id`<br>Есть ли стабильный идентификатор сообщения? | **QUALIFIED** | `id` — целое число, у каждого сообщения, включая service. | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1545 — `{ "id", NumberToString(message.id) }` | `message_identity = SOURCE_STABLE_ID`; дедупликация по id в принципе выразима. И `id` здесь ЧИСЛО, включая отрицательные у мигрированной истории.<br>**adapter:** Никогда не синтезировать id. И не передавать его голой десятичной строкой: `sort_key = (timestamp, message_id)` в `model.py` сравнивает строки, где «10» < «9». Адаптер обязан дать ключ с сохранением числового порядка (zero-pad со смещением под отрицательные) — иначе разрешение ties будет лексикографическим, то есть случайным. | Реальный экспорт: уникальность id внутри чата. |
| `identity.id_stability`<br>Стабилен ли id между экспортами? | UNKNOWN | Не установлено.<br>_ограничения:_ cross-export reconciliation на этом и держится | telegram.org/blog/export-and-more — о стабильности не сказано ничего | — | Два экспорта одного чата: совпадение множества id. |
| `identity.actor`<br>Однозначно ли атрибутируется отправитель? | **QUALIFIED** | `from_id` — типизированный идентификатор (`userN`/`chatN`/`channelN`); у service-сообщений роль играет `actor`.<br>_ограничения:_ `from` — отображаемое имя и может совпадать у разных людей | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1605-1630 — `pushFrom("from")` / `pushFrom("actor")` · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1817-1818 — `"from"` и `"from_id"` | Актор берётся из `from_id`, никогда из `from`.<br>**adapter:** `verify_dyad_membership` по `from_id`. | Реальный экспорт: число различных `from_id` в диадическом чате. |

### 4. Event semantics

| свойство | статус | claim | primary evidence | consequence · adapter | что закроет |
|---|---|---|---|---|---|
| `events.type`<br>Отличимы ли служебные события от сообщений? | **QUALIFIED** | `type` = `"service"` или `"message"`, оба в одном массиве `messages`. | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1547-1551 — `SerializeString(!v::is_null(message.action.content) ? "service" : "message")` | Service-события не открывают и не закрывают opportunity.<br>**adapter:** Исключать `type != "message"` из топологии, считая исключённые. | Фикстура со звонком/сменой фото: топология не меняется. |
| `events.deleted`<br>Видны ли удалённые сообщения? | **UNAVAILABLE** | Нет. Понятия удаления в экспорте не существует.<br>_ограничения:_ удалённый ответ делает отвеченную возможность неотвеченной, и отличить это от настоящего молчания нельзя | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp — подстрока `deleted` не встречается ни разу | `DeletionStateConflict` и `deleted_dropped` на этом пути недостижимы; контракт — current-state reconstruction, уже названный так в §6.1.<br>**adapter:** `deleted=False` для всех записей и явный флаг «источник не сообщает об удалениях», чтобы ноль не читался как «удалений не было». | Не строится из файла: нужен протокол (две выгрузки с интервалом). |
| `events.edited`<br>Видны ли правки и меняют ли они время события? | **PARTIAL** | Поля присутствуют, но НЕ означают «контент был отредактирован»: в 6.7.8 реакция создаёт `edited` у неправленого сообщения и затирает время настоящей правки. `date` при этом остаётся исходным временем отправки.<br>_ограничения:_ исходный текст и его длина невосстановимы · `edited_unixtime` может быть временем РЕАКЦИИ, а не правки · наблюдалось на 6.7.8; на какие версии распространяется — открыто | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1568-1571 — `if (message.edited) { pushBare("edited", ...); }}`, отдельно от `date` на строке 1552 · tdesktop#30647 (2026-05-03, v6.7.8, result.json attached) — «an edited field appears in result.json for the message to which the reaction was set, but the edit action is not performed» | Топология и латентности не затронуты: `date` реакция не трогает. Но `edited` пригоден только как «сообщение трогали после отправки», а `edited_unixtime` — не событие и не время правки. `char_count` — величина ПОСЛЕ правки, и `LengthSemantics` обязана это сказать.<br>**adapter:** `edited` читается как touched-after-send, никогда как edit-флаг; `edited_unixtime` не попадает во временную шкалу ни под каким видом. | Публичный result.json из #30647: сообщение с реакцией и без правки. |
| `events.reactions`<br>Являются ли реакции событиями? | **QUALIFIED** | `reactions` — массив внутри сообщения, а не отдельное сообщение.<br>_ограничения:_ время реакции в этом представлении не привязано к шкале так же, как время сообщения | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:2422 — `pushBare("reactions", SerializeArray(...))` | Реакция не закрывает opportunity — что содержательно спорно (человек ответил ❤️), но обязано быть решением, а не побочным эффектом формата.<br>**adapter:** Реакции игнорируются; политика записана и подлежит пересмотру отдельным решением, не молча. | Фикстура: сообщение с реакцией не порождает opportunity. |
| `events.media_only`<br>Что такое длина у сообщения без текста? | **PARTIAL** | Медиа-поля отдельны от `text`; текст может быть пуст.<br>_ограничения:_ `text` бывает массивом сущностей, а не строкой | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1552-1553 и media-поля (`photo`, `file`, `media_type`) в том же объекте | Топология не зависит от длины; `own_total_chars` зависит, поэтому политика длины обязана быть объявлена.<br>**adapter:** `LengthSemantics` объявляется явно; медиа без текста даёт 0 символов и считается отдельно. | Фикстура: фото без подписи, фото с подписью, текст с сущностями. |
| `events.own_other_device`<br>Видны ли собственные сообщения, отправленные с другого устройства? | UNKNOWN | Не установлено.<br>_ограничения:_ правдоподобно, что история серверная и потому полная — правдоподобие не является свидетельством | telegram.org/blog/export-and-more — о независимости выгрузки от устройства не сказано ничего | — | Отправить с телефона, выгрузить с десктопа, проверить наличие. |

### 5. Time semantics

| свойство | статус | claim | primary evidence | consequence · adapter | что закроет |
|---|---|---|---|---|---|
| `time.instant`<br>Абсолютный ли это момент? | **QUALIFIED** | `date_unixtime` — секунды от эпохи, то есть instant, а не настенные часы. | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:82-84 — сырое число секунд | Ни timezone, ни DST не влияют на порядок и длительности.<br>**adapter:** `utc_offset_minutes = 0`, `local_time = date_unixtime`. | Фикстура через переход DST: длительности не прыгают на час. |
| `time.local_string`<br>Что означает строка `date`? | **UNAVAILABLE** | Настенные часы машины экспорта, без указания смещения. Восстановить пояс из файла нельзя. Утверждение «`date` — это UTC» ОПРОВЕРГНУТО измерением.<br>_ограничения:_ один файл, одна машина: измерение опровергает прочтение «это UTC», но не доказывает поведение всех сборок · −5 ч — пояс того, кто экспортировал, и в файле это не написано | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:77-80 — `QDateTime::fromSecsSinceEpoch(date).toString(Qt::ISODate)` без указания time-spec · doc.qt.io/qt-6/qdatetime.html — «default time representation is local time» · ИЗМЕРЕНО на публичном экспорте `organicdesign/4qx-holarchy@4403e55` (sha256 bbe61b1c…): `date` минус `date_unixtime` = −18000 с ровно, на всех 127 сообщениях; суффикса смещения в строке нет ни у одного | Строка `date` непригодна как время события: смещение из файла не выводится, а разница с абсолютным моментом достигает часов. Контракт был написан устойчивым к обоим ответам заранее — и именно поэтому измерение ничего не сломало.<br>**adapter:** `date` не парсится никогда; событие берётся из `date_unixtime`. Наличие поля `date` не даёт права на `LocalDateTime`-семантику. | Закрыто. Дальнейшие файлы могут только уточнить разброс смещений. |
| `time.server_or_client`<br>Это время сервера или часы отправителя? | UNKNOWN | Не установлено.<br>_ограничения:_ MaiChat пришлось объявлять `SERVER_RECEIVE` именно здесь | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1552 — пишется `message.date`, происхождение которого в этом файле не определяется | — | core.telegram.org: семантика `message.date` в схеме API. |
| `time.clock_corrections`<br>Возможны ли ретроспективные правки времени или перестановки? | UNKNOWN | Не установлено. | telegram.org/blog/export-and-more — не упоминается | — | Два экспорта одного окна: сравнение `date_unixtime` по id. |

## 2a. Верифицированный корпус дефектов

Интернет-pass сделан **до** просьбы о живом экспорте, и он окупился: два статуса
изменились, один добавился. Каждый багрепорт открыт и прочитан — ниже только то,
что подтвердилось.

| источник | версия · дата · статус | что подтверждено | во что превратилось |
|---|---|---|---|
| [tdesktop#30647](https://github.com/telegramdesktop/tdesktop/issues/30647) | 6.7.8 · 2026-05-03 · приложен `result.json` | «an edited field appears in result.json for the message to which the reaction was set, but the edit action is not performed on the message»; при настоящей правке реакция затирает её время | `events.edited` **QUALIFIED → PARTIAL** |
| [tdesktop#5854](https://github.com/telegramdesktop/tdesktop/issues/5854) | 1.6.2 · 2019-03-27 · closed | выбран диапазон «от даты» — «ALL the messages are exported». Это корректность вывода, не производительность | `coverage.requested_range_honored` **UNAVAILABLE** |
| [tdesktop#27183](https://github.com/telegramdesktop/tdesktop/issues/27183) | 4.12.2 · 2023-12-03 · **closed as not planned** | выбран `…-11-30`, «the last day included is 2023-11-29» — правый край короче запрошенного | тот же статус, второй край |
| [tdesktop#31328](https://github.com/telegramdesktop/tdesktop/issues/31328) | 7.2.8 · 2026-09-16 · **открыт** | «exactly 10000 most recent messages», в `result.json` **и** в `messages*.html` | `coverage.completeness` **UNKNOWN → UNAVAILABLE** |

**Один контрпример сильнее ста страниц «обычно всё работает»** — и здесь он есть.
`coverage.completeness` перестало быть «не установлено» и стало «гарантии нет, вот
наблюдение». Честная оговорка записана в самом ledger'е: #31328 про private
supergroups с отключённой пересылкой, для диадического чата тот же потолок **не**
показан. Контрпример опровергает гарантию, но не измеряет частоту.

**И отсюда же — `provenance.producer_version`.** Раз семантика наблюдаемо меняется
между версиями, имя источника «Telegram Desktop JSON» недостаточно. А поля версии
в выводе нет вообще: писатель эмитит только свободные строки `about`. Значит версия
и платформа собираются **вне файла**, в момент acquisition, и входят в provenance
наравне с согласием. Файл без версии — незаявленная семантика.

### Заявлено, но НЕ подтверждено

Проверять чужие находки — то же правило, что проверять свои. Эти утверждения
прозвучали, но первоисточником в этом проходе не закрыты, поэтому в evidence
не входят и статусов не двигают:

| утверждение | состояние |
|---|---|
| ~~7.0.6 игнорирует начальную дату~~ | **ПОДТВЕРЖДЕНО, моя ошибка.** [#31082](https://github.com/telegramdesktop/tdesktop/issues/31082) (30.07.2026, 7.0.6, closed as duplicate): «The exported JSON file contains messages from the entire history, including messages sent before the selected start date». Это содержимое, а не скорость. Я нашёл соседний PR#30727 про производительность и, не найдя прямого репорта, объявил утверждение непроверенным вместо того, чтобы искать дальше. Отсутствие находки — не опровержение |
| ~~6.6.2 — повтор того же класса~~ | **ПОДТВЕРЖДЕНО.** [#30412](https://github.com/telegramdesktop/tdesktop/issues/30412) (07.03.2026, 6.6.2, closed as duplicate): «It exports whole channels messages from oldest message» |
| 5.5.5 — реакции не экспортировались вовсе | UNVERIFIED. В текущем писателе `reactions` есть (строка 2422); отсутствие в 5.5.5 не проверено |
| ~~4.1.1 — custom emoji ломали quoting~~ | **ПОДТВЕРЖДЕНО.** [#24961](https://github.com/telegramdesktop/tdesktop/issues/24961) (20.08.2022, 4.1.1): значение без кавычек там, где JSON требует строку |
| 5.9.0 — два ключа `"text"` | UNVERIFIED, номер не проверен. Но статус свойства это уже не двигает |
| HTML терял старые сообщения там, где JSON не терял | UNVERIFIED как отдельный кейс; #31328 показывает обратную симметрию — потолок виден в обоих форматах |

## 2b. History-fetch: цепочка прослежена до конца

Вопрос был «хронологичен ли порядок `messages[]`». Ответ по коду: **порядок — возрастающий `id`**, и это совсем не то же самое.

| этап | что делает код | источник |
|---|---|---|
| запрос | `offset_id = largestIdPlusOne`, `add_offset = -100`, `limit = 100` — постраничный обход **вперёд** по id | `export_api_wrap.cpp:2216-2218` |
| ответ API | убывающий id (reverse chronological) | `core.telegram.org/api/offsets` — «typically» |
| **transform** | `ParseMessagesSlice` идёт по вектору **с конца**: `for (auto i = list.size(); i != 0;) { list[--i] }` — разворот в возрастающий | `export_data_types.cpp:3470-3473` |
| dedup | отсутствует — и не нужен: курсор `largestIdPlusOne = back().id + 1` строго проходит за взятый максимум, срезы дизъюнктны | `export_api_wrap.cpp:2806` |
| **date filtering** | **в запрос не входит вообще**: `offset_date = 0`, а в ветке `messages.Search` — `min_date`/`max_date` как `MTP_int(0)`. Диапазон применяется на клиенте позже | `export_api_wrap.cpp:2282-2290` |
| merge splits | мигрированная история сдвигается на `kMigratedMessagesIdShift = -1'000'000'000`, то есть в отрицательный диапазон | `export_data_types.cpp:3478-3486` |
| writer | `handleSlice` дописывает срез в порядке среза | `export_api_wrap.cpp:2810-2812` |

Ваше предупреждение «не путать API semantics с export semantics» оказалось точным дважды. Наивный вывод «API отдаёт reverse chronological, значит файл тоже» был бы **перевёрнут**: клиент разворачивает. А правильный вывод «файл в возрастающем порядке» всё равно не означает «хронологический» — он означает **id-порядок**.

**Что это закрыло.** `ordering.exported_position` → **QUALIFIED**: порядок детерминирован и означает возрастающий `id`. `ordering.multi_device` → **QUALIFIED**: этот путь дублей по id не производит, и механизм сдвига мигрированных id существует именно затем, чтобы склейка двух историй не сталкивалась. `duplicates_can_occur` закрыто — с оговоркой, что дедупликация остаётся включённой и обязана срабатывать **ноль раз**: ненулевой счётчик на этом источнике сигнал, а не рутина.

**И два неизвестных схлопнулись в одно.** Внутри секунды порядок задаёт id, потому что id задаёт весь файл. Значит вопрос о ties — это ровно вопрос «монотонен ли `id` по времени», и ничего сверх. Его закрывает **одна пара** в любом публичном `result.json`: `id` растёт, а `date_unixtime` падает — и ответ отрицательный.

**Побочная находка, конкретная.** `id` здесь число, включая отрицательные у мигрированной истории. А `sort_key = (timestamp, message_id)` в `extractor/model.py` сравнивает **строки**, где «10» < «9». Передать телеграмный id голой десятичной строкой значит превратить разрешение ties в лексикографический шум. Требование записано в adapter behavior свойства `identity.message_id`.

## 2c. Валидность JSON: опровергнута, а не неизвестна

Два независимых класса невалидного вывода, оба подтверждены по первоисточнику:

| источник | что именно |
|---|---|
| [#24961](https://github.com/telegramdesktop/tdesktop/issues/24961) · 4.1.1 · 2022 | custom emoji → значение **без кавычек** там, где JSON требует строку |
| [#27571](https://github.com/telegramdesktop/tdesktop/issues/27571) · 4.15.1 · 2024 · **closed as not planned** | `\x01` внутри строки; `jq`: «parse error: Invalid escape at line 2415365, column 47» |

Поэтому `format.strict_json` — не `UNKNOWN`, а **UNAVAILABLE**. Это лучше незнания:
мы знаем, что полагаться на валидность нельзя. Допущение `input_is_valid_json` при
этом остаётся снятым через `eliminated_by_refusal` — строгий разбор, отказ при ошибке.
Свойство опровергнуто, допущение устранено, дыры нет.

## 2d. Сканер публичных экспортов

`tools/export_scan.py` — **не адаптер**: он не производит `RawMessage`, ничего не
подаёт вниз и живёт вне `extractor/`. Он отвечает на вопросы **о файле**.

Смысл — закрыть последнее допущение по многим публичным файлам, не заводя вторую
коллекцию чужой переписки. Человечество и так справляется с этой задачей без нас.
Что сканер сохраняет: метка источника · sha256 · размер · счётчики · кортежи
инверсий `(позиция, id₁, t₁, id₂, t₂)`. Чего не сохраняет: текст, сущности, имена,
`from`/`from_id`, id и имя чата, пути к медиа, реакции, цели ответов. В `ScanResult`
**нет поля, способного их удержать** — та же гарантия, что у типов экстрактора, и
она проверяется тестом, который скармливает сканеру чат из сплошного текста и ищет
его в сериализованном результате.

Ключевое по вашей подсказке: искать **не ties**. После history-fetch сильнейший
контрпример — это

```
id₁ < id₂   но   time₁ > time₂
```

на любом расстоянии. Часы врозь — контрпример **сильнее**, а не слабее. Сканер
считает `chronology_counterexamples` именно так, а `equal_timestamp_pairs` ведёт
отдельно, потому что равные секунды контрпримером не являются.

Вердикт сканера намеренно трёхзначный и не умеет говорить `QUALIFIED`:
`REFUSED` (не разобрался), `REFUTED` (найден контрпример), либо
`no inversion observed in N entries` — формулировка, из которой `QUALIFIED`
не выводится ни при каком N.

### Корпус: две строки, обе не по целевому типу

`telegram_desktop.CORPUS` — строки доказательств, не файлы. Каждая несёт URL, префикс
sha256, размер, тип чата, счётчики; ни текста, ни имён, ни id чата.

| источник | тип чата | записей | id↑/time↓ | равные метки (cross-actor) | что это квалифицирует |
|---|---|---|---|---|---|
| [organicdesign/4qx-holarchy@4403e55](https://code.organicdesign.nz/organicdesign/4qx-holarchy/src/commit/4403e558490bcf5c436cf85895b52ebe22e5b35a/OpenClaw/Discussion/epic4-constitutional-substrate/telegram-export.json) · `bbe61b1c…` · 362 830 Б | `private_group` | 127 | **0** | 4 (**0**) | поведение **экспортёра** |
| [innerdvations/telegram-chat-parser@main](https://raw.githubusercontent.com/innerdvations/telegram-chat-parser/main/tests/data/saved.json) · `c3c55650…` · 7 064 Б | `saved_messages` | 21 | 0 | 0 | работоспособность **инструмента** |

Ваша оговорка про `private_group` оказалась даже важнее, чем выглядела, и она теперь
механическая: `CorpusRow.qualifies_target_type` истинно только для `personal_chat`, и
сейчас таких строк **ноль**. Заодно тип вскрыл вторую подмену: файл, взятый в прошлом
проходе, — это `saved_messages`, то есть заметки себе, а не разговор вообще.

**354 KiB — это 127 сообщений, а не 8000.** Байты в этом файле ушли в длинные тексты.
Хороший урок про то, что размер файла — не размер выборки; 148 записей суммарно не
лицензируют даже скромный `PARTIAL`.

Контрпримера не нашлось. Это ровно `no inversion observed`, и `ties_resolvable`
остаётся открытым.

### Зато нашлось другое: `date` — это НЕ UTC, и теперь это измерено

На том же файле, все 127 сообщений:

```
date (ISO)  −  date_unixtime  =  −18000 с  ровно, без единого исключения
суффикс смещения в строке     =  отсутствует у всех
```

То есть строка `date` — настенные часы машины экспорта (здесь UTC−5), а смещение в
файле не записано и восстановлению не подлежит. Прочтение «`date` — это UTC», которое
мне в первом проходе подсунуло резюме документации, **опровергнуто измерением**.
`time.local_string` уходит из `UNKNOWN` в **UNAVAILABLE**.

И вот тут окупилась осторожность: контракт «никогда не парсить `date`, читать только
`date_unixtime`» был написан **до** того, как ответ стал известен, именно потому, что
устойчив к обоим исходам. Измерение не сломало ничего — оно закрыло строку.

## 3. Вердикт

```
24 свойства:  9 QUALIFIED · 3 PARTIAL · 5 UNKNOWN · 7 UNAVAILABLE
              0 понижено из PARTIAL (то есть все три PARTIAL несут контракт)
```

**Пять UNAVAILABLE — самые содержательные строки этого документа**, и четыре из
пяти лежат в coverage/provenance. Это не совпадение: экстрактор мы били месяц,
а вопрос «а покрывает ли файл то, что мы думаем» задали впервые.

`coverage.window_provenance`. Экспорт **не записывает запрошенный диапазон дат**:
`singlePeerFrom`/`singlePeerTill` существуют в настройках и не попадают в вывод;
объект чата пишет `name`, `type`, `id`, `messages` и больше ничего. Значит первая
и последняя строка файла не доказывают покрытия. А `reentry_burden_H` требует
**общего окна** — величина, которую мы неделю назад назвали и защитили тестами,
опирается на то, чего источник не сообщает. Окно обязано приходить из протокола
(даты зачисления), и адаптер обязан отказываться выводить его из содержимого.

`events.deleted`. Подстрока `deleted` не встречается в писателе экспорта **ни
разу**. Понятия удалённого сообщения в формате нет. Следствие: `DeletionStateConflict`
и `deleted_dropped` на этом пути недостижимы, а удалённый ответ превращает
отвеченную возможность в неотвеченную, и отличить это от настоящего молчания
нельзя. Контракт вырождается ровно в тот `current-state reconstruction`, который
§6.1 уже назвал честно. И `deleted_dropped = 0` обязан сопровождаться флагом
«источник не сообщает об удалениях» — иначе ноль прочитается как «удалений не
было», то есть отсутствие снова станет свидетельством.

## 4. Критерий завершения TRACK

Не «мы поняли формат». Для **каждого** допущения экстрактора известно, каким
наблюдаемым свойством target'а оно обеспечивается — либо почему feature
отказывается работать. `UNAVAILABLE` закрывает допущение: «источник этого не даёт,
и вот что перестаёт работать» — это ответ. `UNKNOWN` не закрывает: это состояние,
в котором экстрактор продолжает допускать, а никто не проверял.

Допущение перестаёт быть дырой тремя путями, а не двумя: (1) его поддерживает
наблюдаемое свойство; (2) источник его не даёт, и следствие записано (`UNAVAILABLE`);
(3) экстрактор его больше не делает — `eliminated_by_refusal`. Третий путь добавлен
для `input_is_valid_json`: строгий разбор с отказом снимает допущение целиком, поэтому
`format.strict_json` может остаться `UNKNOWN` навсегда и не блокировать заморозку.
Недоказанная гарантия и ненужная гарантия — разные состояния, и дыра только первое.

Четырнадцать допущений заведены в `telegram_desktop.ASSUMPTIONS`. Интернет-pass закрыл
два (`no_silent_gaps`, `semantics_stable_across_versions`), history-fetch закрыл ещё два
(`stream_order_is_chronological`, `duplicates_can_occur`), fail-closed снял один
(`input_is_valid_json`). **Открыто одно:**

| допущение | где сделано | упирается в | что сломается |
|---|---|---|---|
| `ties_resolvable` | сортировка `(timestamp, message_id)` | `ordering.tie_semantics` | передачи хода внутри секунды считаются неверно — **число** передач, а не только латентность |

И это уже не программа исследований, а один эмпирический вопрос: монотонен ли `id`
по времени. Один контрпример в любом публичном `result.json` закрывает его
отрицательно; отсутствие контрпримера на конечной выборке — не доказательство, и
тогда статус останется `PARTIAL` с измеренной долей, а не `QUALIFIED`.

## 5. Что дальше, по порядку

```
official/export documentation     ✔ источники прочитаны в оригинале
        ↓
public bug corpus                 ✔ 6 багрепортов проверены; 2 статуса изменены,
                                    3 свойства добавлены
        ↓
tdesktop history-fetch source     ✔ цепочка прослежена; 2 свойства QUALIFIED,
                                    2 допущения закрыты, 1 вопрос сведён к одному
        ↓
public result.json attachments    ← ИДЁТ: 2 файла, 148 записей, 0 контрпримеров,
                                    0 строк целевого типа `personal_chat`.
                                    Побочно закрыл `time.local_string`
        ↓
actual export                     только для того, что осталось незакрытым
        ↓
adversarial fixtures              правка · service-событие · реакция ·
                                  медиа без подписи · DST-переход ·
                                  два экспорта одного окна
        ↓
SourceSemantics                   декларация адаптера, механически проверяемая
        ↓
qualification verdict             и только теперь — первая строка адаптера
```

Пока реального экспорта нет, `instrumentation qualification` запускать
бессмысленно: он будет чрезвычайно тщательно измерять то, чего источник,
возможно, вообще не гарантирует. Человечество называет это telemetry.

## 6. Журнал поправок

| дата | что изменено | почему |
|---|---|---|
| 2026-09-17 | Ledger заведён; 21 свойство по пяти разделам; `claim_scope` и механическое понижение `PARTIAL` без контракта; 12 допущений экстрактора сопоставлены со свойствами | Пятое человеческое состояние «ну вроде WhatsApp обычно делает так» уже стоило проекту `user_count` как фильтра членства в диаде. Два `UNAVAILABLE` найдены по первоисточникам: экспорт не записывает свой диапазон дат, и понятия удаления в формате нет вовсе |
| 2026-09-17 | Интернет-pass до просьбы о личном экспорте: 4 багрепорта проверены по первоисточнику. `events.edited` **QUALIFIED → PARTIAL** (#30647: реакция создаёт и затирает `edited`); `coverage.completeness` **UNKNOWN → UNAVAILABLE** (#31328: ровно 10000 сообщений, JSON и HTML); добавлены `coverage.requested_range_honored` (#5854, #27183), `provenance.producer_version` и `format.strict_json`; заведён список UNVERIFIED | Заявленный баг 7.0.6 при проверке оказался другим классом — полный обход истории с клиентской фильтрацией это производительность, а не лишние сообщения в выводе; «медленно, но правильно» и «быстро, но неверно» дают противоположные контракты. Диапазонный класс подтверждают #5854 и #27183, а не 7.0.6 |
| 2026-09-17 | Две поправки заказчика внесены: #31082 (7.0.6) и #30412 (6.6.2) подтверждены как отказ по СОДЕРЖИМОМУ — мой предыдущий вывод «это только производительность» был ошибкой поиска, а не факта; формулировка про сериализатор смягчена до «в значительной части вручную». History-fetch прослежен: `ordering.exported_position` и `ordering.multi_device` → QUALIFIED, добавлен третий путь закрытия допущения (`eliminated_by_refusal`) | Экспорт идёт возрастающим `id`: сервер отдаёт убывающий, `ParseMessagesSlice` разворачивает, курсор `back().id + 1` подтверждает. Значит «файл в хронологии» — не то же, что «файл в id-порядке», и вопрос о ties свёлся ровно к монотонности id по времени. Диапазон дат в запрос не входит вообще — отсюда семь лет одного и того же бага |
| 2026-09-17 | `format.strict_json` **UNKNOWN → UNAVAILABLE** по двум подтверждённым классам невалидного вывода (#24961, #27571); добавлен `tools/export_scan.py` — сканер публичных экспортов, сохраняющий только метаданные и кортежи инверсий; #30421 внесён как явно **не**-evidence | Опровергнутая гарантия лучше неизвестной: мы знаем, что полагаться на валидность нельзя, и допущение всё равно снято fail-closed разбором. Искать надо не ties, а любую пару id↑/time↓ — часы врозь делают контрпример сильнее. Живой клиент (#30421) показывает временно неверный порядок по локальным id, но экспорт видит финализированные серверные — это предупреждение против тезиса «id по определению есть время», а не улика против файла |
| 2026-09-17 | Прогнан публичный экспорт `4qx-holarchy@4403e55` (127 записей, `private_group`): контрпримера id↑/time↓ нет. Заведён `CORPUS` со строками доказательств и механическим `qualifies_target_type`; сканер считает cross-actor ties и тип чата. `time.local_string` **UNKNOWN → UNAVAILABLE** по измерению | 354 KiB оказались 127 сообщениями — размер файла не размер выборки. Тип чата вскрыл, что ни один из двух файлов не `personal_chat`, а один вообще `saved_messages`. И на том же файле `date` − `date_unixtime` = −18000 с на всех сообщениях без суффикса смещения: строка — настенные часы машины экспорта, а не UTC |
