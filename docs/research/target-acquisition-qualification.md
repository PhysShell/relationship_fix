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

### 1. Coverage / completeness

| свойство | статус | claim | primary evidence | consequence · adapter | что закроет |
|---|---|---|---|---|---|
| `coverage.export_scope`<br>Что вообще входит в экспорт? | **QUALIFIED** | Пользователь выбирает чаты; экспорт одного чата дополнительно ограничивается диапазоном дат.<br>_ограничения:_ границы диапазона задаёт человек в момент экспорта | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_settings.h:88-89 — `TimeId singlePeerFrom` / `singlePeerTill` · telegram.org/blog/export-and-more — «export some (or all) of your chats» | Содержимое файла — функция выбора пользователя, а не истории.<br>**adapter:** Адаптер обязан получать окно извне и не выводить его из файла. | Экспорт одного чата с заданным диапазоном + экспорт без него. |
| `coverage.window_provenance`<br>Означает ли period_end реальное покрытие? | **UNAVAILABLE** | Нет. Экспорт не записывает запрошенный диапазон.<br>_ограничения:_ первое и последнее сообщение файла не доказывают ничего | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp — объект чата пишет `name`/`type`/`id`/`messages`; полей диапазона нет ни одного · telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_settings.h:88-89 — диапазон существует, но в вывод не попадает | `reentry_burden_H` требует общего окна; вывести его из файла нельзя — только из протокола (даты зачисления).<br>**adapter:** Отказ выводить period_start/period_end из содержимого; окно — обязательный аргумент, как сейчас в `extract()`. | Два экспорта одного чата с разными диапазонами — файлы обязаны быть неразличимы по метаданным покрытия. |
| `coverage.completeness`<br>Можно ли доказать, что в окне нет пропусков? | UNKNOWN | Не установлено.<br>_ограничения:_ официальный текст говорит о удобстве доступа к старым сообщениям, а не о гарантии полноты | telegram.org/blog/export-and-more — о полноте не сказано ничего | — | Два экспорта одного чата и окна: посимвольный diff множества id. |

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
| `events.edited`<br>Видны ли правки и меняют ли они время события? | **QUALIFIED** | `edited`/`edited_unixtime` присутствуют только у правленых; `date` остаётся исходным временем отправки.<br>_ограничения:_ исходный текст и его длина невосстановимы | telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp:1568-1571 — `if (message.edited) { pushBare("edited", ...); }}`, отдельно от `date` на строке 1552 | Топология и латентности не искажаются правкой; `char_count` — величина ПОСЛЕ правки, и `LengthSemantics` обязана это сказать.<br>**adapter:** Считать `edited` как диагностику; длину помечать post-edit. | Фикстура с правленым сообщением: латентность не меняется. |
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

## 3. Вердикт

```
21 свойство:  8 QUALIFIED · 2 PARTIAL · 9 UNKNOWN · 2 UNAVAILABLE
              0 понижено из PARTIAL (то есть оба PARTIAL несут контракт)
```

**Две UNAVAILABLE — самые содержательные строки этого документа.**

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

Двенадцать допущений заведены в `telegram_desktop.ASSUMPTIONS`. Открыты четыре:

| допущение | где сделано | упирается в | что сломается |
|---|---|---|---|
| `ties_resolvable` | сортировка `(timestamp, message_id)` | `ordering.tie_semantics` | передачи хода внутри секунды считаются неверно — **число**, а не только латентность |
| `stream_order_is_chronological` | нормализация | `ordering.exported_position` | порядок приходится строить целиком из timestamp, включая его ties |
| `duplicates_can_occur` | `DuplicateConflict` | `ordering.multi_device` | механизм конфликтов не получает входных данных |
| `no_silent_gaps` | все агрегаты | `coverage.completeness` | пропуск в окне неотличим от молчания |

**Ни одно из четырёх не закрывается документацией.** Все четыре закрываются
реальным экспортом, и это следующий шаг, а не следующая формула.

## 5. Что дальше, по порядку

```
official/export documentation     ✔ сделано — источники прочитаны в оригинале
        ↓
actual export                     ← БЛОКИРУЮЩИЙ ШАГ: нужен реальный файл
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
