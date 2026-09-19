"""Результат гейта приёма для Copenhagen Networks Study — как данные, а не проза.

Файл корпуса НЕ вендорится (гарнесс принимает путь). Здесь только то, что было
установлено при осмотре, и ссылки на то, чем установлено.

Итог: **корпус НЕ ДОПУЩЕН.** Одна блокирующая проверка провалена —
`coverage.semantics`. Гейт сработал так, как задуман: он остановил чтение до
того, как из неизвестного покрытия была бы посчитана incidence.
"""

from __future__ import annotations

from .admission import CORPORA, CheckVerdict

#: sha256 осмотренного файла. Любой другой файл — другой осмотр.
SMS_CSV_SHA256 = "2262320d1ec159d8efeaa86dc4ac295f4ad04f3b40fa1d7075ccacd5068f4803"
SMS_CSV_BYTES = 368_659
FIGSHARE_DOI = "10.6084/m9.figshare.7267433.v1"
PAPER_DOI = "10.1038/s41597-019-0325-x"

#: (ключ, вердикт, наблюдение)
FINDINGS: tuple[tuple[str, CheckVerdict, str], ...] = (
    ("licence.terms", CheckVerdict.PASSED,
     f"Figshare API запись 7267433: license.name=MIT, "
     f"url=opensource.org/licenses/MIT; DOI {FIGSHARE_DOI}. Статья — CC BY 4.0. "
     f"Использование разрешено."),
    ("licence.derivative_reach", CheckVerdict.PASSED,
     "MIT производное не ограничивает: генератор, откалиброванный на CNS, не "
     "утаскивается ни в non-commercial, ни в share-alike. Это, как выяснилось "
     "при осмотре ландшафта, редкость — и главное преимущество CNS перед более "
     "богатыми кандидатами."),
    ("licence.redistribution", CheckVerdict.PASSED,
     "MIT допускает распространение, но соглашение проекта не меняется: корпус "
     "остаётся вне репозитория, гарнесс принимает путь."),
    ("schema.fields", CheckVerdict.PASSED,
     "Ровно три столбца: timestamp, sender, recipient (sms.README). Table 3 "
     "статьи называет их user_a/user_b; смысл тот же."),
    ("schema.text_present", CheckVerdict.PASSED,
     "Столбца с текстом нет в файле; статья: «network of text messages (time of "
     "message, no content)». Файл и источник согласны."),
    ("schema.text_discarded", CheckVerdict.PASSED,
     "Отрезать нечего. Адаптер всё равно берёт три столбца по белому списку, а "
     "не отбрасывает лишние по чёрному."),
    ("time.resolution", CheckVerdict.PASSED,
     "Целые секунды: все значения целые, НОД = 1. Статья: «Timestamp in seconds "
     "from the beginning of the observation period»."),
    ("time.semantics", CheckVerdict.PASSED,
     "Секунды от начала наблюдения; запись — из метаданных SMS-лога телефона "
     "(Funf на выданном Nexus 4). Направление задано: «userA initiates the "
     "interaction and userB is the recipient». ОДНА запись на сообщение: "
     "двойного логирования обоими телефонами не видно — в гистограмме пауз "
     "между подряд идущими сообщениями одного направления нет всплеска на 0-1 с "
     "(21, 46, 107, 137, 153, ... — плавный подъём, а не пик). "
     "ОСТАЁТСЯ НЕИЗВЕСТНЫМ, чей аппарат дал метку; возможная примесь смещения "
     "порядка секунд ограничивает ТОЧНОСТЬ Q3 и записана как её лимит."),
    ("scale.counts", CheckVerdict.PASSED,
     "24 333 записи — совпадает со статьёй точно. Окно 28.0 суток (min 18, max "
     "2 418 982 с). 697 неупорядоченных пар. РАСХОЖДЕНИЕ: в файле 568 различных "
     "идентификаторов, статья пишет «577 total users». Записано как есть, не "
     "сглажено."),
    ("coverage.target_dyad_filtering", CheckVerdict.PASSED,
     "«non-participants were removed» — да, вырезаны. Для ОСТАВШЕЙСЯ пары "
     "participant-participant это НЕ пропуск: сообщения A с кем-то вне "
     "исследования в процесс пары A-B не входят по определению, ровно как "
     "target chat в Telegram не включает переписку с мамой. Прежняя редакция "
     "(коммит fe9eecc) путала усечение СЕТИ с дырой в окне ДИАДЫ и отказала "
     "корпусу по неверному основанию."),
    ("coverage.capture_window", CheckVerdict.FAILED,
     "НЕ установлено. Опубликованный срез делит ОБЩИЙ четырёхнедельный период "
     "на 8064 пятиминутных корзины — то есть окно одно на всех, а не на "
     "пользователя. Поздний вход, ранний выход и устройство, появившееся в "
     "середине, из sms.csv неразличимы. Availability 0.81 из статьи относится "
     "ЯВНО к Bluetooth («the quality (availability) of the Bluetooth data»), а "
     "не к SMS-логгеру, и переносить её нельзя."),
    ("identity.dyad", CheckVerdict.PASSED,
     "Целочисленные идентификаторы, отрицательных нет, самосообщений нет; "
     "статья: единый user id общий для всех каналов."),
    ("events.non_message", CheckVerdict.PASSED,
     "Только метаданные SMS-лога; столбца типа события нет, самосообщений нет."),
    ("direction.sender_receiver", CheckVerdict.PASSED,
     "Явно и в файле (sender/recipient), и в статье («userA initiates»). "
     "Перепутать нечего."),
    ("ethics.scope", CheckVerdict.PASSED,
     "Одобрено Danish Data Supervision Authority до сбора; информированное "
     "согласие; право на отзыв и удаление; релиз приведён в соответствие с GDPR "
     "и деидентифицирован. Запрета на объявленный в prereg анализ нет."),
)


def admission():
    """Гейт CNS с внесёнными наблюдениями."""
    result = CORPORA["CNS"][2]
    for key, verdict, finding in FINDINGS:
        result = result.resolve(key, verdict, finding)
    return result


#: Что именно разблокирует корпус. Названо заранее, чтобы «разблокируем как-нибудь»
#: не стало планом.
WHAT_WOULD_ADMIT = (
    "Построить окно наблюдения на пользователя из слоя Bluetooth "
    "(bt_symmetric.csv, скан раз в 5 минут): период, когда устройство вообще "
    "присутствовало в данных. Тогда incidence считается по НАБЛЮДЁННОМУ окну, а "
    "не по номинальным 28 суткам, и `coverage.semantics` получает ответ, "
    "измеренный, а не предположенный."
)
