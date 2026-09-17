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
| `coverage.requested_range_honored`<br>Соблюдается ли выбранный диапазон дат? | **UNAVAILABLE** | Не надёжно. Подтверждены отказы обоих краёв в разных версиях.<br>_ограничения:_ #5854 закрыт, #27183 закрыт как not planned — то есть не «починено», а «не будет» · поведение версионно и наблюдалось с 1.6.2 по 4.12.2 | tdesktop#5854 (2019-03-27, v1.6.2, closed) — «ALL the messages are exported» · tdesktop#27183 (2023-12-03, v4.12.2, closed as NOT PLANNED) — последний выбранный день отсутствует | UI-диапазон не является утверждением о покрытии — ни слева (могут прийти все сообщения), ни справа (может пропасть последний день). Окно `reentry_burden_H` берётся ТОЛЬКО из протокола, и это теперь не осторожность, а следствие.<br>**adapter:** Игнорировать диапазон экспорта как источник окна; отбор по периоду делает `extract()` из протокольных границ, как сейчас. | Экспорт с заданным диапазоном: есть ли сообщения вне его. |
| `provenance.producer_version`<br>Известно ли, какая версия клиента произвела файл? | **UNAVAILABLE** | Из файла — нет. Поля версии в выводе не существует.<br>_ограничения:_ а семантика между версиями наблюдаемо меняется — #30647 | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp — в выводе только свободные строки `about`, поля версии нет · tdesktop#30647 (2026-05-03, v6.7.8, result.json attached) | Все статусы этого ledger'а версионно-зависимы, а файл не говорит, к какой версии относится. «Telegram Desktop JSON» — недостаточное имя источника; нужны `producer_version` и платформа.<br>**adapter:** Версия и платформа собираются ВНЕ файла, в момент acquisition, и входят в provenance наравне с согласием. Файл без версии — незаявленная семантика; адаптер обязан это пометить, а не додумать. | Экспорты с двух разных версий: различимы ли они по содержимому вообще. |
| `format.strict_json`<br>Гарантированно ли валиден выходной JSON? | UNKNOWN | Не установлено; гарантии в документации нет.<br>_ограничения:_ ручной сериализатор — это класс, в котором ошибки квотирования и дублирующиеся ключи возможны в принципе | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp — сериализация ручная, через конкатенацию байтовых блоков, а не через JSON-библиотеку | —<br>**adapter:** Строгий разбор; отказ разбора = отказ acquisition, без починки «почти JSON» на лету. | Строгий разбор всех публичных result.json из багрепортов. |

### 2. Ordering

| свойство | статус | claim | primary evidence | consequence · adapter | что закроет |
|---|---|---|---|---|---|
| `ordering.timestamp`<br>Есть ли абсолютная временная метка? | **QUALIFIED** | `date_unixtime` — секунды эпохи, отдельным полем у каждого сообщения. | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1553 — `{ "date_unixtime", SerializeDateRaw(message.date) }` · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:82-84 — `SerializeDateRaw` = `QString::number(date)` | Порядок и длительности строятся на этом поле.<br>**adapter:** `ordering_evidence = TIMESTAMP`; читать только `date_unixtime`. | Реальный экспорт: доля сообщений без поля (ожидается 0). |
| `ordering.resolution`<br>Какое разрешение? | **PARTIAL** | Секунда: `TimeId` — целые секунды, миллисекунд в экспорте нет.<br>_ограничения:_ cross-actor ties внутри одной секунды возможны | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:77-84 — `SerializeDate(TimeId)`/`SerializeDateRaw(TimeId)` | Длительности пригодны (горизонты 6/12/24 ч против секунды); ties не могут устанавливать топологию — один перевёрнутый tie превращает одну передачу хода в две, и вторая вносит полный H.<br>**adapter:** Топология допустима, только пока доля неоднозначных cross-actor ties измерена и мала; иначе — тот же отказ, что у Seufert. | Реальный экспорт: доля соседних cross-actor пар с равным `date_unixtime`. |
| `ordering.exported_position`<br>Хронологичен ли порядок элементов массива? | UNKNOWN | Не установлено.<br>_ограничения:_ порядок записи задаёт обход истории в клиенте, а не контракт | telegram.org/blog/export-and-more — о порядке не сказано ничего | — | Реальный экспорт: монотонность `date_unixtime` по позиции. |
| `ordering.tie_semantics`<br>Что разрешает равенство секунд? | UNKNOWN | Не установлено.<br>_ограничения:_ порядок по id не объявлен эквивалентным хронологии | core.telegram.org/api/offsets — «typically, results are returned in reverse chronological order with descending object ID values»; «typically» гарантией не является | — | Экспорт с известной реальной последовательностью внутри одной секунды. |
| `ordering.multi_device`<br>Могут ли в файле оказаться две копии одного сообщения? | UNKNOWN | Не установлено.<br>_ограничения:_ отсутствие поля не доказывает отсутствие дублей | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp — писатель не содержит понятия «копия с другого устройства» | — | Реальный экспорт: повторяющиеся `id` внутри одного чата. |

### 3. Identity

| свойство | статус | claim | primary evidence | consequence · adapter | что закроет |
|---|---|---|---|---|---|
| `identity.message_id`<br>Есть ли стабильный идентификатор сообщения? | **QUALIFIED** | `id` — целое число, у каждого сообщения, включая service. | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1545 — `{ "id", NumberToString(message.id) }` | `message_identity = SOURCE_STABLE_ID`; дедупликация по id в принципе выразима.<br>**adapter:** Никогда не синтезировать id и не использовать его как tie-break. | Реальный экспорт: уникальность id внутри чата. |
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
| `time.local_string`<br>Что означает строка `date`? | UNKNOWN | Производная от `QDateTime::fromSecsSinceEpoch(date)` без указания time-spec, то есть от представления по умолчанию, отформатированного `Qt::ISODate`. Есть ли в строке суффикс смещения — по документации Qt однозначно не устанавливается.<br>_ограничения:_ зависит от версии Qt и от часового пояса машины экспорта | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:77-80 — `QDateTime::fromSecsSinceEpoch(date).toString(Qt::ISODate)` · doc.qt.io/qt-6/qdatetime.html — «default time representation is local time»; про суффикс смещения при LocalTime формулировка прочитана неоднозначно | — | Реальный экспорт с машины в известном не-UTC поясе: есть ли суффикс. |
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
| 7.0.6 (июль 2026) игнорирует выбранную начальную дату | **UNVERIFIED.** Найденное рядом — [PR#30727](https://github.com/telegramdesktop/tdesktop/pull/30727) и [#25139](https://github.com/telegramdesktop/tdesktop/issues/25139) — описывает полный обход истории с клиентской фильтрацией, то есть **производительность**, а не лишние сообщения в выводе. Это другой дефект, и смешивать их нельзя: «медленно, но правильно» и «быстро, но неверно» дают противоположные контракты. Подтверждает диапазонный класс **#5854**, а не 7.0.6 |
| 6.6.2 — повтор того же класса | UNVERIFIED, номер не найден |
| 5.5.5 — реакции не экспортировались вовсе | UNVERIFIED. В текущем писателе `reactions` есть (строка 2422); отсутствие в 5.5.5 не проверено |
| 4.1.1 — custom emoji ломали quoting; 5.9.0 — два ключа `"text"` | UNVERIFIED. Контракт строгого разбора от них не зависит и введён по другому основанию: сериализатор **ручной**, склейка байтовых блоков без JSON-библиотеки — класс, в котором такие ошибки возможны в принципе |
| HTML терял старые сообщения там, где JSON не терял | UNVERIFIED как отдельный кейс; #31328 показывает обратную симметрию — потолок виден в обоих форматах |

## 3. Вердикт

```
24 свойства:  7 QUALIFIED · 3 PARTIAL · 9 UNKNOWN · 5 UNAVAILABLE
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

Четырнадцать допущений заведены в `telegram_desktop.ASSUMPTIONS`. Интернет-pass
закрыл два — `no_silent_gaps` и `semantics_stable_across_versions` — причём закрыл
их в форме «источник этого не даёт, вот что перестаёт работать», а не «всё хорошо».
Открыты четыре:

| допущение | где сделано | упирается в | что сломается |
|---|---|---|---|
| `ties_resolvable` | сортировка `(timestamp, message_id)` | `ordering.tie_semantics` | передачи хода внутри секунды считаются неверно — **число**, а не только латентность |
| `stream_order_is_chronological` | нормализация | `ordering.exported_position` | порядок приходится строить целиком из timestamp, включая его ties |
| `duplicates_can_occur` | `DuplicateConflict` | `ordering.multi_device` | механизм конфликтов не получает входных данных |
| `input_is_valid_json` | любой будущий `adapt_file` | `format.strict_json` | acquisition обязан отказывать, а не чинить «почти JSON» |

**Три из четырёх, скорее всего, закрываются без личного экспорта.** Порядок, в
котором vector приходит в сериализатор, и судьба дубликатов — это код `tdesktop`
до `export_output_json.cpp`: history-fetch и pagination. Валидность JSON — строгий
разбор публичных `result.json` из багрепортов. Личный controlled export нужен только
для того, что после исходника и корпуса останется принципиально незакрытым.

## 5. Что дальше, по порядку

```
official/export documentation     ✔ сделано — источники прочитаны в оригинале
        ↓
public bug corpus                 ✔ сделано — 4 багрепорта проверены,
                                    2 статуса изменены, 1 свойство добавлено
        ↓
tdesktop history-fetch source     ← СЛЕДУЮЩЕЕ: порядок и дубликаты до сериализатора
        ↓
public result.json attachments    строгий разбор + первые фикстуры
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
