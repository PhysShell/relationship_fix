"""Target acquisition qualification — Telegram Desktop JSON export.

NO ADAPTER CODE HERE. The rule from the corpus ledger holds for targets too:
not one line of adapter until the properties it depends on are qualified or
their refusal is written down. This file is the qualification, and it is data
so that a status cannot drift in prose.

Why this target first, and only this one: the pilot needs an acquisition path
that could in principle satisfy the extractor at all. Of the two candidates in
reactivity-power-design §6.1.1, Telegram Desktop is the only one that emits a
message id, an absolute timestamp, edit markers and a message/service
distinction. The WhatsApp text export is already known from the Seufert corpus
to carry neither ids nor better than minute resolution. If Telegram cannot
qualify, no plain-text export will, and a nine-messenger matrix would only be
nine copies of the same verdict.

ASSUMPTION, stated because it is the user's to overturn: the pilot runs on this
path. If it runs on WhatsApp instead, this ledger is the wrong one first, not
wrong.

Evidence is by file and line of the code that writes the export, read directly
rather than through a summary — the claim that `date` is UTC survives exactly
until someone opens `SerializeDate`.
"""

from __future__ import annotations

from .acquisition import Assumption, ClaimScope, Ledger, Property, Status

#: Primary sources, fetched and read 2026-09-17.
WRITER = "telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/output/export_output_json.cpp"
SETTINGS = "telegramdesktop/tdesktop@dev Telegram/SourceFiles/export/export_settings.h"
OFFSETS = "core.telegram.org/api/offsets"
BLOG = "telegram.org/blog/export-and-more"
#: Verified defect corpus — each opened and read, not taken from a summary.
I_EDITED = "tdesktop#30647 (2026-05-03, v6.7.8, result.json attached)"
I_RANGE = "tdesktop#5854 (2019-03-27, v1.6.2, closed) — «ALL the messages are exported»"
I_LASTDAY = "tdesktop#27183 (2023-12-03, v4.12.2, closed as NOT PLANNED) — последний выбранный день отсутствует"
I_CAP = "tdesktop#31328 (2026-09-16, v7.2.8, OPEN) — ровно 10000 сообщений, JSON и HTML"


def _p(**kw) -> Property:
    kw.setdefault("observed_limitations", ())
    return Property(**kw)


COVERAGE = (
    _p(
        key="coverage.export_scope",
        question="Что вообще входит в экспорт?",
        claim="Пользователь выбирает чаты; экспорт одного чата дополнительно "
              "ограничивается диапазоном дат.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{SETTINGS}:88-89 — `TimeId singlePeerFrom` / `singlePeerTill`",
                          f"{BLOG} — «export some (or all) of your chats»"),
        observed_limitations=("границы диапазона задаёт человек в момент экспорта",
                              "настройка существует — её соблюдение отдельный вопрос, "
                              "см. `coverage.requested_range_honored`"),
        downstream_consequence="Содержимое файла — функция выбора пользователя, а не истории.",
        adapter_behavior="Адаптер обязан получать окно извне и не выводить его из файла.",
        fixture_needed="Экспорт одного чата с заданным диапазоном + экспорт без него.",
    ),
    _p(
        key="coverage.window_provenance",
        question="Означает ли period_end реальное покрытие?",
        claim="Нет. Экспорт не записывает запрошенный диапазон.",
        status=Status.UNAVAILABLE,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER} — объект чата пишет `name`/`type`/`id`/`messages`; "
                          "полей диапазона нет ни одного",
                          f"{SETTINGS}:88-89 — диапазон существует, но в вывод не попадает"),
        observed_limitations=("первое и последнее сообщение файла не доказывают ничего",),
        downstream_consequence="`reentry_burden_H` требует общего окна; вывести его из файла "
                               "нельзя — только из протокола (даты зачисления).",
        adapter_behavior="Отказ выводить period_start/period_end из содержимого; окно — "
                         "обязательный аргумент, как сейчас в `extract()`.",
        fixture_needed="Два экспорта одного чата с разными диапазонами — файлы обязаны быть "
                       "неразличимы по метаданным покрытия.",
    ),
    _p(
        key="coverage.completeness",
        question="Можно ли доказать, что в окне нет пропусков?",
        claim="Нет, и это не «не установлено»: молчаливое усечение экспорта наблюдалось.",
        status=Status.UNAVAILABLE,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(I_CAP, I_LASTDAY, f"{BLOG} — о полноте не сказано ничего"),
        observed_limitations=("#31328 — про private supergroups с отключённой пересылкой; "
                              "для диадического чата тот же потолок НЕ показан",
                              "один контрпример опровергает гарантию, но не измеряет частоту"),
        downstream_consequence="Гарантии полноты нет ни при каком чтении файла. Пропуск в окне "
                               "неотличим от молчания, а молчание у нас вносит полный H — то есть "
                               "усечение экспорта выглядит как медленный ответ.",
        adapter_behavior="Никогда не выводить покрытие из содержимого. Помечать экспорт "
                         "подозрительным при круглом числе сообщений (10000) и при совпадении "
                         "первого сообщения с началом окна; отказ, а не тихая обработка.",
        fixture_needed="Два экспорта одного чата и окна: diff множества id (частота, не гарантия).",
    ),
    _p(
        key="coverage.requested_range_honored",
        question="Соблюдается ли выбранный диапазон дат?",
        claim="Не надёжно. Подтверждены отказы обоих краёв в разных версиях.",
        status=Status.UNAVAILABLE,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(I_RANGE, I_LASTDAY),
        observed_limitations=("#5854 закрыт, #27183 закрыт как not planned — то есть "
                              "не «починено», а «не будет»",
                              "поведение версионно и наблюдалось с 1.6.2 по 4.12.2"),
        downstream_consequence="UI-диапазон не является утверждением о покрытии — ни слева "
                               "(могут прийти все сообщения), ни справа (может пропасть "
                               "последний день). Окно `reentry_burden_H` берётся ТОЛЬКО из "
                               "протокола, и это теперь не осторожность, а следствие.",
        adapter_behavior="Игнорировать диапазон экспорта как источник окна; отбор по периоду "
                         "делает `extract()` из протокольных границ, как сейчас.",
        fixture_needed="Экспорт с заданным диапазоном: есть ли сообщения вне его.",
    ),
    _p(
        key="provenance.producer_version",
        question="Известно ли, какая версия клиента произвела файл?",
        claim="Из файла — нет. Поля версии в выводе не существует.",
        status=Status.UNAVAILABLE,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER} — в выводе только свободные строки `about`, поля версии нет",
                          I_EDITED),
        observed_limitations=("а семантика между версиями наблюдаемо меняется — #30647",),
        downstream_consequence="Все статусы этого ledger'а версионно-зависимы, а файл не говорит, "
                               "к какой версии относится. «Telegram Desktop JSON» — недостаточное "
                               "имя источника; нужны `producer_version` и платформа.",
        adapter_behavior="Версия и платформа собираются ВНЕ файла, в момент acquisition, и входят "
                         "в provenance наравне с согласием. Файл без версии — незаявленная "
                         "семантика; адаптер обязан это пометить, а не додумать.",
        fixture_needed="Экспорты с двух разных версий: различимы ли они по содержимому вообще.",
    ),
    _p(
        key="format.strict_json",
        question="Гарантированно ли валиден выходной JSON?",
        claim="Не установлено; гарантии в документации нет.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER} — сериализация ручная, через конкатенацию байтовых блоков, "
                          "а не через JSON-библиотеку",),
        observed_limitations=("ручной сериализатор — это класс, в котором ошибки квотирования "
                              "и дублирующиеся ключи возможны в принципе",),
        downstream_consequence="",
        adapter_behavior="Строгий разбор; отказ разбора = отказ acquisition, без починки "
                          "«почти JSON» на лету.",
        fixture_needed="Строгий разбор всех публичных result.json из багрепортов.",
    ),
)

ORDERING = (
    _p(
        key="ordering.timestamp",
        question="Есть ли абсолютная временная метка?",
        claim="`date_unixtime` — секунды эпохи, отдельным полем у каждого сообщения.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:1553 — `{{ \"date_unixtime\", SerializeDateRaw(message.date) }}`",
                          f"{WRITER}:82-84 — `SerializeDateRaw` = `QString::number(date)`"),
        downstream_consequence="Порядок и длительности строятся на этом поле.",
        adapter_behavior="`ordering_evidence = TIMESTAMP`; читать только `date_unixtime`.",
        fixture_needed="Реальный экспорт: доля сообщений без поля (ожидается 0).",
    ),
    _p(
        key="ordering.resolution",
        question="Какое разрешение?",
        claim="Секунда: `TimeId` — целые секунды, миллисекунд в экспорте нет.",
        status=Status.PARTIAL,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:77-84 — `SerializeDate(TimeId)`/`SerializeDateRaw(TimeId)`",),
        observed_limitations=("cross-actor ties внутри одной секунды возможны",),
        downstream_consequence="Длительности пригодны (горизонты 6/12/24 ч против секунды); "
                               "ties не могут устанавливать топологию — один перевёрнутый tie "
                               "превращает одну передачу хода в две, и вторая вносит полный H.",
        adapter_behavior="Топология допустима, только пока доля неоднозначных cross-actor ties "
                         "измерена и мала; иначе — тот же отказ, что у Seufert.",
        fixture_needed="Реальный экспорт: доля соседних cross-actor пар с равным "
                       "`date_unixtime`.",
    ),
    _p(
        key="ordering.exported_position",
        question="Хронологичен ли порядок элементов массива?",
        claim="Не установлено.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{BLOG} — о порядке не сказано ничего",),
        observed_limitations=("порядок записи задаёт обход истории в клиенте, а не контракт",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Реальный экспорт: монотонность `date_unixtime` по позиции.",
    ),
    _p(
        key="ordering.tie_semantics",
        question="Что разрешает равенство секунд?",
        claim="Не установлено.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{OFFSETS} — «typically, results are returned in reverse "
                          "chronological order with descending object ID values»; «typically» "
                          "гарантией не является",),
        observed_limitations=("порядок по id не объявлен эквивалентным хронологии",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Экспорт с известной реальной последовательностью внутри одной секунды.",
    ),
    _p(
        key="ordering.multi_device",
        question="Могут ли в файле оказаться две копии одного сообщения?",
        claim="Не установлено.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER} — писатель не содержит понятия «копия с другого устройства»",),
        observed_limitations=("отсутствие поля не доказывает отсутствие дублей",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Реальный экспорт: повторяющиеся `id` внутри одного чата.",
    ),
)

IDENTITY = (
    _p(
        key="identity.message_id",
        question="Есть ли стабильный идентификатор сообщения?",
        claim="`id` — целое число, у каждого сообщения, включая service.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:1545 — `{{ \"id\", NumberToString(message.id) }}`",),
        downstream_consequence="`message_identity = SOURCE_STABLE_ID`; дедупликация по id "
                               "в принципе выразима.",
        adapter_behavior="Никогда не синтезировать id и не использовать его как tie-break.",
        fixture_needed="Реальный экспорт: уникальность id внутри чата.",
    ),
    _p(
        key="identity.id_stability",
        question="Стабилен ли id между экспортами?",
        claim="Не установлено.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{BLOG} — о стабильности не сказано ничего",),
        observed_limitations=("cross-export reconciliation на этом и держится",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Два экспорта одного чата: совпадение множества id.",
    ),
    _p(
        key="identity.actor",
        question="Однозначно ли атрибутируется отправитель?",
        claim="`from_id` — типизированный идентификатор (`userN`/`chatN`/`channelN`); "
              "у service-сообщений роль играет `actor`.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:1605-1630 — `pushFrom(\"from\")` / `pushFrom(\"actor\")`",
                          f"{WRITER}:1817-1818 — `\"from\"` и `\"from_id\"`"),
        observed_limitations=("`from` — отображаемое имя и может совпадать у разных людей",),
        downstream_consequence="Актор берётся из `from_id`, никогда из `from`.",
        adapter_behavior="`verify_dyad_membership` по `from_id`.",
        fixture_needed="Реальный экспорт: число различных `from_id` в диадическом чате.",
    ),
)

EVENTS = (
    _p(
        key="events.type",
        question="Отличимы ли служебные события от сообщений?",
        claim="`type` = `\"service\"` или `\"message\"`, оба в одном массиве `messages`.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:1547-1551 — `SerializeString(!v::is_null("
                          "message.action.content) ? \"service\" : \"message\")`",),
        downstream_consequence="Service-события не открывают и не закрывают opportunity.",
        adapter_behavior="Исключать `type != \"message\"` из топологии, считая исключённые.",
        fixture_needed="Фикстура со звонком/сменой фото: топология не меняется.",
    ),
    _p(
        key="events.deleted",
        question="Видны ли удалённые сообщения?",
        claim="Нет. Понятия удаления в экспорте не существует.",
        status=Status.UNAVAILABLE,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER} — подстрока `deleted` не встречается ни разу",),
        observed_limitations=("удалённый ответ делает отвеченную возможность неотвеченной, "
                              "и отличить это от настоящего молчания нельзя",),
        downstream_consequence="`DeletionStateConflict` и `deleted_dropped` на этом пути "
                               "недостижимы; контракт — current-state reconstruction, уже "
                               "названный так в §6.1.",
        adapter_behavior="`deleted=False` для всех записей и явный флаг «источник не "
                         "сообщает об удалениях», чтобы ноль не читался как «удалений не было».",
        fixture_needed="Не строится из файла: нужен протокол (две выгрузки с интервалом).",
    ),
    _p(
        key="events.edited",
        question="Видны ли правки и меняют ли они время события?",
        claim="Поля присутствуют, но НЕ означают «контент был отредактирован»: в 6.7.8 "
              "реакция создаёт `edited` у неправленого сообщения и затирает время настоящей "
              "правки. `date` при этом остаётся исходным временем отправки.",
        status=Status.PARTIAL,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:1568-1571 — `if (message.edited) {{ pushBare(\"edited\", "
                          "...); }}`, отдельно от `date` на строке 1552",
                          I_EDITED + " — «an edited field appears in result.json for the message "
                          "to which the reaction was set, but the edit action is not performed»"),
        observed_limitations=("исходный текст и его длина невосстановимы",
                              "`edited_unixtime` может быть временем РЕАКЦИИ, а не правки",
                              "наблюдалось на 6.7.8; на какие версии распространяется — открыто"),
        downstream_consequence="Топология и латентности не затронуты: `date` реакция не трогает. "
                               "Но `edited` пригоден только как «сообщение трогали после отправки», "
                               "а `edited_unixtime` — не событие и не время правки. `char_count` — "
                               "величина ПОСЛЕ правки, и `LengthSemantics` обязана это сказать.",
        adapter_behavior="`edited` читается как touched-after-send, никогда как edit-флаг; "
                         "`edited_unixtime` не попадает во временную шкалу ни под каким видом.",
        fixture_needed="Публичный result.json из #30647: сообщение с реакцией и без правки.",
    ),
    _p(
        key="events.reactions",
        question="Являются ли реакции событиями?",
        claim="`reactions` — массив внутри сообщения, а не отдельное сообщение.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:2422 — `pushBare(\"reactions\", SerializeArray(...))`",),
        observed_limitations=("время реакции в этом представлении не привязано к шкале так же, "
                              "как время сообщения",),
        downstream_consequence="Реакция не закрывает opportunity — что содержательно спорно "
                               "(человек ответил ❤️), но обязано быть решением, а не побочным "
                               "эффектом формата.",
        adapter_behavior="Реакции игнорируются; политика записана и подлежит пересмотру "
                         "отдельным решением, не молча.",
        fixture_needed="Фикстура: сообщение с реакцией не порождает opportunity.",
    ),
    _p(
        key="events.media_only",
        question="Что такое длина у сообщения без текста?",
        claim="Медиа-поля отдельны от `text`; текст может быть пуст.",
        status=Status.PARTIAL,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:1552-1553 и media-поля (`photo`, `file`, `media_type`) "
                          "в том же объекте",),
        observed_limitations=("`text` бывает массивом сущностей, а не строкой",),
        downstream_consequence="Топология не зависит от длины; `own_total_chars` зависит, "
                               "поэтому политика длины обязана быть объявлена.",
        adapter_behavior="`LengthSemantics` объявляется явно; медиа без текста даёт 0 символов "
                         "и считается отдельно.",
        fixture_needed="Фикстура: фото без подписи, фото с подписью, текст с сущностями.",
    ),
    _p(
        key="events.own_other_device",
        question="Видны ли собственные сообщения, отправленные с другого устройства?",
        claim="Не установлено.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{BLOG} — о независимости выгрузки от устройства не сказано ничего",),
        observed_limitations=("правдоподобно, что история серверная и потому полная — "
                              "правдоподобие не является свидетельством",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Отправить с телефона, выгрузить с десктопа, проверить наличие.",
    ),
)

TIME = (
    _p(
        key="time.instant",
        question="Абсолютный ли это момент?",
        claim="`date_unixtime` — секунды от эпохи, то есть instant, а не настенные часы.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:82-84 — сырое число секунд",),
        downstream_consequence="Ни timezone, ни DST не влияют на порядок и длительности.",
        adapter_behavior="`utc_offset_minutes = 0`, `local_time = date_unixtime`.",
        fixture_needed="Фикстура через переход DST: длительности не прыгают на час.",
    ),
    _p(
        key="time.local_string",
        question="Что означает строка `date`?",
        claim="Производная от `QDateTime::fromSecsSinceEpoch(date)` без указания time-spec, "
              "то есть от представления по умолчанию, отформатированного `Qt::ISODate`. "
              "Есть ли в строке суффикс смещения — по документации Qt однозначно не "
              "устанавливается.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:77-80 — `QDateTime::fromSecsSinceEpoch(date)"
                          ".toString(Qt::ISODate)`",
                          "doc.qt.io/qt-6/qdatetime.html — «default time representation is "
                          "local time»; про суффикс смещения при LocalTime формулировка "
                          "прочитана неоднозначно"),
        observed_limitations=("зависит от версии Qt и от часового пояса машины экспорта",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Реальный экспорт с машины в известном не-UTC поясе: есть ли суффикс.",
    ),
    _p(
        key="time.server_or_client",
        question="Это время сервера или часы отправителя?",
        claim="Не установлено.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{WRITER}:1552 — пишется `message.date`, происхождение которого "
                          "в этом файле не определяется",),
        observed_limitations=("MaiChat пришлось объявлять `SERVER_RECEIVE` именно здесь",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="core.telegram.org: семантика `message.date` в схеме API.",
    ),
    _p(
        key="time.clock_corrections",
        question="Возможны ли ретроспективные правки времени или перестановки?",
        claim="Не установлено.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{BLOG} — не упоминается",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Два экспорта одного окна: сравнение `date_unixtime` по id.",
    ),
)

ASSUMPTIONS = (
    Assumption("event_time_is_instant", "RawMessage.timestamp", "time.instant",
               "без этого нельзя ни упорядочить, ни измерить длительность"),
    Assumption("resolution_fine_enough", "find_opportunities", "ordering.resolution",
               "топология недоступна; остаются только bounds по допустимым порядкам"),
    Assumption("ties_resolvable", "нормализация: сортировка (timestamp, message_id)",
               "ordering.tie_semantics",
               "передачи хода внутри секунды считаются неверно — и число, а не только латентность"),
    Assumption("stream_order_is_chronological", "нормализация", "ordering.exported_position",
               "порядок приходится строить целиком из timestamp, включая его ties"),
    Assumption("stable_identity", "dedup по message_id", "identity.message_id",
               "дедупликация невыразима"),
    Assumption("duplicates_can_occur", "DuplicateConflict", "ordering.multi_device",
               "механизм конфликтов не получает входных данных"),
    Assumption("deletion_observable", "DeletionStateConflict, deleted_dropped", "events.deleted",
               "контракт вырождается в current-state reconstruction, и это записано"),
    Assumption("actor_unambiguous", "verify_dyad_membership", "identity.actor",
               "принадлежность к диаде недоказуема"),
    Assumption("edit_preserves_event_time", "латентности", "events.edited",
               "латентность правленого сообщения становится неинтерпретируемой"),
    Assumption("service_events_separable", "find_opportunities", "events.type",
               "звонок или смена фото открывали бы возможность"),
    Assumption("window_from_protocol", "extract(period_start, period_end)",
               "coverage.window_provenance",
               "окно пришлось бы выводить из файла, а burden требует общего окна"),
    Assumption("no_silent_gaps", "все агрегаты", "coverage.completeness",
               "пропуск в окне неотличим от молчания — и усечение выглядит как медленный ответ"),
    Assumption("input_is_valid_json", "любой будущий adapt_file", "format.strict_json",
               "acquisition отказывает, а не чинит файл на лету"),
    Assumption("semantics_stable_across_versions", "весь этот ledger",
               "provenance.producer_version",
               "статусы применимы только к версии, которая их породила; версия собирается вне файла"),
)

LEDGER = Ledger(
    target="Telegram Desktop JSON export",
    acquisition_path="пользователь экспортирует один чат из десктоп-клиента",
    properties=COVERAGE + ORDERING + IDENTITY + EVENTS + TIME,
    assumptions=ASSUMPTIONS,
)
