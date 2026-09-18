"""Target acquisition qualification — Telegram API / TDLib (TDLIB-0).

NO ADAPTER CODE. Same rule as every source before it.

Why a second source ledger at all: `C_target` requires ZERO routine user actions
per period, and a watched export folder cannot deliver that — the person still
performs the export every period, which is the largest touchpoint in the whole
protocol. Reading `tdata` directly is worse: a reverse-engineered local store
that is not a reliable full history. The API is the only path where the routine
person-period is empty.

So this ledger exists to remove the largest part of `C`, not as architectural
entertainment.

STATUS: contract-only. Steps 2-6 of the spike (run a client, authorise an
account, fetch pages, look at raw fields) need a real Telegram account and have
NOT been done. Everything below is either read from the official contract or
marked UNKNOWN pending that run. A vendor's documentation sentence is evidence
about intent; it is not a measurement.
"""

from __future__ import annotations

from .acquisition import Assumption, ClaimScope, Ledger, Property, Status

#: Primary sources, fetched and read 2026-09-18.
MTPROTO = "core.telegram.org/method/messages.getHistory"
TDLIB_DOC = "core.telegram.org/tdlib/docs — td_api::getChatHistory"
TDLIB_LICENSE = "github.com/tdlib/td LICENSE_1_0.txt + README §License"
API_ID = "core.telegram.org/api/obtaining_api_id"
API_TOS = "core.telegram.org/api/terms — Telegram API Terms of Service"
CONTENT = "telegram.org/tos/content-licensing — Terms of Service for Content Licensing"


def _p(**kw) -> Property:
    kw.setdefault("observed_limitations", ())
    return Property(**kw)


LEGAL = (
    _p(
        key="legal.library_license",
        question="Можно ли встроить TDLib в наше приложение?",
        claim="Boost Software License 1.0 — пермиссивная, совместима с закрытой поставкой.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{TDLIB_LICENSE} — «TDLib is licensed under the terms of the "
                          "Boost Software License»; текст LICENSE_1_0.txt прочитан",),
        downstream_consequence="Библиотека может входить в продукт (в отличие от GPL-доноров "
                               "из DONOR-0, которым разрешён только oracle).",
        adapter_behavior="Версия TDLib входит в provenance машинно.",
        fixture_needed="Закрыто.",
    ),
    _p(
        key="legal.api_terms_app_scope",
        question="Является ли наше приложение адресатом этих условий?",
        claim="НЕ УСТАНОВЛЕНО, и прочтение скорее против нас. Условия написаны про "
              "«Telegram-like messaging applications» и «third-party client apps», а §1.3 "
              "требует, чтобы «all the basic features of the main Telegram apps function "
              "correctly» в вашем приложении. Исследовательский измеритель мессенджером не "
              "является и §1.3 выполнить не может по построению.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{API_TOS} — преамбула и §1.3 прочитаны дословно",
                          f"{API_ID} — «all third-party client apps must comply with the "
                          "API Terms of Service»"),
        observed_limitations=("вилка неприятна с обеих сторон: если мы НЕ client app, то "
                              "непонятно, что вообще разрешает нам доступ; если client app — "
                              "мы нарушаем §1.3",
                              "вывод юридический, а не технический: тестом не закрывается"),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Юридическая оценка или прямое разъяснение от Telegram. **Блокирует "
                       "реализацию**, а не откладывается на потом.",
    ),
    _p(
        key="legal.content_access_purpose",
        question="Разрешён ли доступ к контенту РАДИ ИЗМЕРЕНИЯ?",
        claim="НЕ УСТАНОВЛЕНО, и текст читается скорее против. Общий запрет: «Access to "
              "user-generated content for any purpose other than ordinary, legitimate, and "
              "intended use of the Telegram platform as its user is prohibited». Исключение "
              "перечислено закрытым списком — Client, Bot, Mini App — и лицензия дана «solely "
              "to the extent strictly required to operate the relevant service».",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{CONTENT} — обе цитаты прочитаны дословно",),
        observed_limitations=("исследовательский измеритель не входит в перечисление из трёх",
                              "даже внутри исключения чтение истории ради метрик трудно назвать "
                              "«strictly required to operate» клиент"),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Та же юридическая оценка. **Блокирует реализацию.**",
    ),
    _p(
        key="legal.ai_use",
        question="Могут ли данные из Telegram попасть в AI/ML-слой продукта?",
        claim="Нет по умолчанию. Запрет прямой и широкий: «prohibited from using, accessing "
              "or aggregating data obtained from the Telegram platform to train, fine-tune or "
              "otherwise engage in the development, enhancement or deployment of artificial "
              "intelligence, machine learning models and similar technologies».",
        status=Status.UNAVAILABLE,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{API_TOS} §1.5 — цитата выше",
                          f"{CONTENT} §«Large Language Models and AI» — шире: добавлены "
                          "«scraping, indexing, harvesting», «validate», «benchmarking»"),
        observed_limitations=("исключение существует, но требовательное: «all relevant users "
                              "individually provide explicit, informed, affirmative and "
                              "continued consent», строго ограниченное конкретным чатом, и "
                              "«consent obtained in one context is non-transferable»",
                              "«all relevant users» для диады означает ОБОИХ партнёров — то "
                              "самое согласие второго человека, которое prereg §3.1 уже "
                              "отметил как нерешённое"),
        downstream_consequence="Архитектурный firewall обязателен: данные, полученные из "
                               "Telegram, не входят в LLM/embeddings/ML ни в каком виде, "
                               "включая feasibility-спайк. Даже разведочный прогон не должен "
                               "случайно стать первым AI-путём.",
        adapter_behavior="Путь обрывается на детерминированных агрегатах. Пересечение границы "
                         "требует отдельно установленного основания, а не решения инженера.",
        fixture_needed="Закрыто как запрет. Открыть может только явное основание по исключению "
                       "о согласии — для ОБОИХ участников диады.",
    ),
    _p(
        key="legal.transparency_obligations",
        question="Что требуется от приложения, если путь окажется допустим?",
        claim="Перечислено явно: собственный `api_id`; пользователи должны знать, что "
              "приложение использует Telegram API, и это «must be featured prominently»; "
              "слово «Telegram» в названии запрещено (кроме «Unofficial»); официальный "
              "логотип использовать нельзя.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{API_TOS} §2.1–2.4 прочитаны дословно",),
        observed_limitations=("§4: при нарушении — уведомление, 10 дней на исправление, "
                              "затем отключение доступа и обращение в магазины приложений",),
        downstream_consequence="Требования известны и выполнимы; они НЕ решают вопрос "
                               "применимости из двух предыдущих строк.",
        adapter_behavior="Раскрытие факта использования Telegram API входит в onboarding — "
                         "то есть в `C`, и должно быть учтено в burden budget.",
        fixture_needed="Закрыто.",
    ),
    _p(
        key="legal.security_guidelines",
        question="Обязаны ли мы соблюдать Security Guidelines?",
        claim="Да, прямо: «All client apps must, therefore, guard their users' privacy with "
              "utmost care and comply with our Security Guidelines».",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{API_TOS} §1.1 прочитан дословно",),
        observed_limitations=("руководство писано про реализации MTProto; использование "
                              "официальной TDLib закрывает криптографическую часть, но не "
                              "снимает обязательство целиком",),
        downstream_consequence="Совместимо с нашей privacy boundary, которая уже строже: "
                               "наружу уходят только агрегаты из allowlist.",
        adapter_behavior="Соблюдение фиксируется в provenance этапа, а не подразумевается.",
        fixture_needed="Прочитать guidelines целиком при переходе к реализации.",
    ),
    _p(
        key="deployment.authorization_burden",
        question="Авторизация — разовая или повторяющаяся?",
        claim="Предположительно разовая: TDLib держит локальную базу и переиспользует "
              "авторизованное состояние. НЕ ПРОВЕРЕНО живым прогоном.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.DEVICE_STATE,
        primary_evidence=(f"{TDLIB_DOC} — модель authorization state документирована",),
        observed_limitations=("частота повторной авторизации, поведение при смене устройства "
                              "и при истечении сессии не измерены",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Спайк: авторизоваться, дождаться следующего периода, проверить, что "
                       "повторный запрос не требует человека. Это ПРЯМО определяет, "
                       "достижим ли `C_target`.",
    ),
)

ORDERING = (
    _p(
        key="ordering.contract",
        question="Какой порядок гарантирует источник?",
        claim="MTProto объявляет порядок ЯВНО — по дате, а не «typically»: "
              "«Results are ordered by date (descending)».",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{MTPROTO} — «Returns the message history in a peer. "
                          "Results are ordered by date (descending).»",),
        observed_limitations=("утверждение о выдаче метода, а не о физической хронологии",),
        downstream_consequence="Существенно сильнее, чем было у экспорта: там "
                               "`core.telegram.org/api/offsets` говорил лишь «typically ... "
                               "descending object ID values».",
        adapter_behavior="`ordering_evidence` объявляется как контракт метода, не как id-порядок.",
        fixture_needed="Спайк: монотонность `date` по страницам.",
    ),
    _p(
        key="ordering.tdlib_conflates_id_and_time",
        question="Утверждает ли TDLib, что id-порядок И ЕСТЬ хронология?",
        claim="Да, в одной скобке — и это ровно тот вопрос, который на экспортном пути "
              "остался UNAVAILABLE.",
        status=Status.UNKNOWN,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{TDLIB_DOC} — «The messages are returned in reverse chronological "
                          "order (i.e., in order of decreasing message_id)»",
                          f"{MTPROTO} — «ordered by date (descending)»"),
        observed_limitations=("ДВА документа вендора описывают порядок РАЗНО: один по дате, "
                              "другой по убыванию message_id, и TDLib приравнивает их через "
                              "«i.e.». Совпадают они только если id монотонен по времени — "
                              "то самое, что мы отказались предполагать",),
        downstream_consequence="",
        adapter_behavior="",
        fixture_needed="Спайк: на реальных страницах проверить, встречается ли пара, где "
                       "`message_id` растёт, а `date` падает. Плюс доля cross-actor пар с "
                       "равной секундой — вопрос `TiePolicy` никуда не делся.",
    ),
)

COVERAGE = (
    _p(
        key="coverage.window_query",
        question="Можно ли ЗАПРОСИТЬ ровно протокольное окно?",
        claim="Контракт для этого есть: `offset_date` («Only return messages sent before the "
              "specified date»), плюс `min_id`/`max_id` для границ по идентификатору.",
        status=Status.PARTIAL,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{MTPROTO} — таблица параметров прочитана: `offset_id`, "
                          "`offset_date`, `add_offset`, `limit`, `max_id`, `min_id`",),
        observed_limitations=("одна граница задаётся датой, другая — идентификатором; "
                              "симметричного диапазона по датам в методе нет",),
        downstream_consequence="Принципиально лучше экспорта, где запрошенный диапазон "
                               "**не соблюдался** семь лет (#5854 · #27183 · #30412 · #31082). "
                               "Окно всё равно остаётся протокольным: запрос — это удобство, "
                               "а не источник истины о покрытии.",
        adapter_behavior="Окно по-прежнему приходит из протокола; запрос лишь сужает объём. "
                         "Полученный интервал сверяется с запрошенным, расхождение — finding.",
        fixture_needed="Спайк: запросить известное окно, сравнить фактические границы.",
    ),
    _p(
        key="coverage.only_local_truncation",
        question="Может ли выдача оказаться усечённой локальным кэшем?",
        claim="TDLib имеет режим `only_local`, где метод работает офлайн по локальной базе.",
        status=Status.PARTIAL,
        claim_scope=ClaimScope.DEVICE_STATE,
        primary_evidence=(f"{TDLIB_DOC} — «This is an offline method if only_local is true»",),
        observed_limitations=("неизвестно, что возвращается при частично заполненной локальной "
                              "базе и отличима ли такая выдача от полной",),
        downstream_consequence="Новый механизм молчаливого усечения — того же класса, что "
                               "10000-сообщений у экспорта, но с другой причиной.",
        adapter_behavior="`only_local = false` всегда; флаг фиксируется в provenance; "
                         "локальная неполнота обязана давать finding, а не тихий результат.",
        fixture_needed="Спайк: сравнить выдачу при `only_local` true и false на одном чате.",
    ),
    _p(
        key="coverage.page_limit",
        question="Какими порциями приходит история?",
        claim="`limit` не больше 100; TDLib выбирает фактический размер сам.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{TDLIB_DOC} — «must be positive and can't be greater than 100. "
                          "For optimal performance, the number of returned messages is chosen "
                          "by TDLib»",),
        observed_limitations=("«выбирает сам» означает, что число возвращённых < limit НЕ "
                              "является признаком конца истории",),
        downstream_consequence="Пагинация обязана определять конец по курсору, а не по "
                               "короткой странице. Классическая ошибка на ровном месте.",
        adapter_behavior="Конец истории — только по исчерпанию курсора; короткая страница "
                         "продолжает обход.",
        fixture_needed="Спайк: доля страниц короче `limit` в середине истории.",
    ),
)

PROVENANCE = (
    _p(
        key="provenance.producer_under_our_control",
        question="Кто продюсер артефакта?",
        claim="Мы. Telegram Desktop из пути приёма исчезает целиком.",
        status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT,
        primary_evidence=(f"{TDLIB_LICENSE} — библиотека встраивается в наше приложение",),
        downstream_consequence="Исчезает самая мерзкая строка экспортного ledger'а: "
                               "`provenance.producer_version = UNAVAILABLE`. Версия нашего "
                               "приложения, версия TDLib, версия адаптера, слой API, время "
                               "приёма и границы запроса собираются машинно.",
        adapter_behavior="Вопрос о версии чужого GUI-клиента к человеку больше не задаётся "
                         "никогда — `C_target` §4 закрыт этим решением, а не автоматизацией "
                         "поля ввода.",
        fixture_needed="Закрыто конструкцией.",
    ),
)

ASSUMPTIONS = (
    Assumption("zero_routine_user_actions", "C_target §2C", "deployment.authorization_burden",
               "если авторизация повторяется каждый период, C_target недостижим и весь смысл "
               "перехода на этот источник исчезает"),
    Assumption("app_is_in_scope_of_the_terms", "весь acquisition path",
               "legal.api_terms_app_scope",
               "реализация не начинается; это не техническое ограничение и тестом не "
               "закрывается"),
    Assumption("measurement_purpose_is_licensed", "весь acquisition path",
               "legal.content_access_purpose",
               "реализация не начинается по той же причине"),
    Assumption("ai_layer_may_use_telegram_data", "будущий AI-слой Relationship Fix",
               "legal.ai_use",
               "AI-слой не питается данными из Telegram ни в каком виде — это установленный "
               "запрет, а не риск, и firewall обязателен уже на этапе спайка"),
    Assumption("order_is_chronological", "нормализация",
               "ordering.tdlib_conflates_id_and_time",
               "остаётся `TiePolicy.STRICT`: экстрактор уже не предполагает порядок внутри "
               "секунды, поэтому ядро не трогается ни при каком ответе",
               eliminated_by="Допущение снято конструкцией ещё на экспортном пути. Новый "
                             "источник его не возвращает: cross-actor-группы с одной секундой "
                             "помечаются неоднозначными независимо от того, что пишет вендор "
                             "в скобках."),
    Assumption("history_is_complete", "все агрегаты", "coverage.only_local_truncation",
               "локальная неполнота выглядит как молчание — тот же класс, что усечение "
               "экспорта на 10000"),
    Assumption("pagination_terminates_correctly", "будущий fetcher", "coverage.page_limit",
               "короткая страница принимается за конец истории и период обрезается молча"),
)

LEDGER = Ledger(
    target="Telegram API / TDLib",
    acquisition_path="локальный клиент в нашем приложении, разовая авторизация участника",
    properties=LEGAL + ORDERING + COVERAGE + PROVENANCE,
    assumptions=ASSUMPTIONS,
)
