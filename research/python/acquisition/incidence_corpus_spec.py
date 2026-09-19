"""Чего именно мы ищем для S4-Q1 — после того, как NetHealth заморожен.

Passive-sensing исследования ломаются на одном и том же: человек и его телефон
СУТЬ прибор сбора, поэтому появляется неизвестная observability. CNS упёрся в
неё, NetHealth упёрся в неё же при куда большем богатстве данных.

Значит менять надо не датасет, а КЛАСС источника:

    сервер / оператор пишет все события
            ↓
    фиксированный интервал сбора
            ↓
    отправитель / получатель / метка времени

Тогда тишина хотя бы потенциально становится настоящей тишиной, а не «человек
не запустил бэкап».
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Без любого из этих пунктов корпус для Q1 не рассматривается вовсе.
MUST = (
    "server/operator-side acquisition",
    "explicit fixed collection interval",
    "event-level sender",
    "event-level receiver",
    "event timestamp",
    "explicit reusable licence",
    "no participant-device observability ambiguity",
)

#: Желательно, но отсутствие не дисквалифицирует.
NICE = (
    "messaging rather than calls",
    "dyadic/private rather than broadcast",
    "multi-week or longer",
    "no message content",
)


class Fit(Enum):
    CANDIDATE = "CANDIDATE"
    #: техника подходит, но право не выяснено
    LICENSE_PROVENANCE_OPEN = "LICENSE_PROVENANCE_OPEN"
    #: право в порядке, но данные не того разрешения/состава
    WRONG_GRANULARITY = "WRONG_GRANULARITY"
    #: популяция не та, каким бы чистым ни был захват
    POPULATION_UNSUITABLE = "POPULATION_UNSUITABLE"
    #: ЛИЦЕНЗИЯ ОТНОСИТСЯ К ДРУГОМУ АРТЕФАКТУ, чем тот, который нужен
    ARTIFACT_MISMATCH = "ARTIFACT_MISMATCH"
    #: годится как якорь здравого смысла, но не как цель калибровки
    STRESS_ANCHOR_ONLY = "STRESS_ANCHOR_ONLY"
    REFUSED = "REFUSED"


#: ПРАВИЛО, заработанное дважды подряд и стоившее бы дорого на третий раз.
#:
#: Лицензию проверять у ТОГО АРТЕФАКТА, который будешь читать, а не у
#: производной коллекции, зеркала или страницы проекта. Пойманные случаи:
#:
#:   Figshare-коллекция под CC BY 4.0, а сырые CDR под NDA и «по запросу»;
#:   Kaggle-зеркало объявляет CC BY 4.0 для корпуса, у источника которого
#:   лицензии нет вовсе.
#:
#: И зеркально: лицензию читать через API записи, а не по тому, как её
#: отрисовала страница — так дважды находилась лицензия там, где страница
#: показывала пустоту.
LICENCE_APPLIES_TO_THE_ARTIFACT_YOU_READ = True


#: ПОЧЕМУ мы упираемся в стену — это структурно, а не невезение.
#:
#:     приватная диадическая связь
#:   + псевдонимизированные реальные личности
#:   + точные метки времени
#:   + полный серверный/операторский захват
#:   + свободно распространяемая, коммерчески совместимая лицензия
#:
#: Первые четыре пункта делают данные очень чувствительными. Пятый требует от
#: владельца разрешить свободное дальнейшее использование. Операторы и
#: платформы обычно делают ровно наоборот: агрегаты, controlled access, NDA
#: или исследовательский DUA. Комбинация почти специально устроена так, чтобы
#: публично не существовать.
WALL_IS_STRUCTURAL = True


@dataclass(frozen=True, slots=True)
class Candidate:
    name: str
    fit: Fit
    evidence: str
    note: str = ""


CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        "Anonymised Phone Call Dataset for Anomaly Detection",
        Fit.POPULATION_UNSUITABLE,
        "Zenodo API, запись 13254389: access_right='open', "
        "license.id='cc-by-4.0'. Два окна сбора с явными границами: 24.07-"
        "21.10.2018 (89 суток, 83 366 367 записей) и 01-30.06.2019 (29 суток, "
        "32 879 670). Поля: A-Number, B-Number, timestamp, call result.",
        note="ВСЕ пункты MUST выполнены — это первый источник операторского "
             "класса с проверенной лицензией. Но состав популяции против нас: "
             "9 006 011 уникальных A-номеров против 2 387 932 B-номеров, а "
             "`call result` кодирует ЧЁРНЫЙ СПИСОК. Это набор для детекции "
             "аномалий, то есть трафик обогащён спамом и мошенничеством, а не "
             "выборка обычных диад. Для incidence обычных пар не годится, "
             "сколь угодно чистый захват. Плюс это ЗВОНКИ, а не сообщения: "
             "семантика возврата другая.",
    ),
    Candidate(
        "Communication with family and friends across the life course",
        Fit.WRONG_GRANULARITY,
        "CC BY 4.0, операторские CDR за 7 месяцев 2007 года, эгосети 3 340 868 "
        "человек, более 3 млрд звонков.",
        note="Право безупречно и захват операторский. Но опубликованы "
             "АГРЕГИРОВАННЫЕ помесячные ego-alter счётчики, без меток времени "
             "событий. Для Q1 в нашей постановке слишком грубо: incidence "
             "определена на окне и требует событий, а не месячных сумм.",
    ),
    Candidate(
        "Multiplexity is temporal (Aalto CDR)",
        Fit.ARTIFACT_MISMATCH,
        "Статья EPJ Data Science 2026; Figshare/Aalto-страница набора "
        "заявляет CC BY 4.0. Но Data Availability самой статьи говорит прямо: "
        "«the CDR dataset analysed during the current study is not publicly "
        "available due to a signed non-disclosure agreement, as it contains "
        "sensitive information of the subscribers» — выдаётся автором по "
        "запросу.",
        note="Чистейший случай LICENCE LOOKS GOOD -> WRONG ARTIFACT: лицензия "
             "относится к производной коллекции, а событийные CDR под NDA. "
             "Проверять лицензию надо у того артефакта, который будешь читать.",
    ),
    Candidate(
        "Republic of Letters (historical correspondence)",
        Fit.STRESS_ANCHOR_ONLY,
        "Более 150 000 писем с отправителем, получателем и датой. "
        "ЛИЦЕНЗИЯ МНОЙ НЕ ПОДТВЕРЖДЕНА: поиск не дал первичного указания на "
        "CC BY 4.0 у самой раздачи, только вторичные упоминания.",
        note="Очевидно НЕ современный messaging, НЕ калибровка латентности "
             "возврата и НЕ аналог Telegram: в XVII веке на push-уведомления "
             "за 43 секунды не отвечали. Но для узкого вопроса «как "
             "независимые человеческие часы порождают межпарную "
             "гетерогенность incidence» может служить якорем здравого смысла. "
             "Не ставить впереди нормальных цифровых логов.",
    ),
    Candidate(
        "CollegeMsg (SNAP / Opsahl)",
        Fit.LICENSE_PROVENANCE_OPEN,
        "59 835 приватных сообщений, 1 899 пользователей, 193 дня, "
        "SRC DST UNIXTS. SNAP лицензии не указывает.",
        note="Технически интересен и это СООБЩЕНИЯ, а не звонки. Тот же трюк "
             "с двух сторон: есть Kaggle-зеркало, объявляющее CC BY 4.0 и "
             "содержащее те самые 59 835 рёбер за 193 дня, и есть более "
             "поздняя Figshare-коллекция под CC BY 4.0, использующая "
             "CollegeMsg. Ни downstream-загрузчик, ни производная коллекция "
             "не выдают прав, которых нет у источника. SNAP лицензии не даёт "
             "— значит LICENSE_PROVENANCE_OPEN.",
    ),
)


#: РАЗБИЕНИЕ Q1: перестаём требовать от одного корпуса ответить на всё.
SUBQUESTIONS = {
    "Q1a_absolute_incidence_scale": (
        "Какова АБСОЛЮТНАЯ величина incidence?",
        "нужен coverage-полный операторский/платформенный лог"),
    "Q1b_incidence_shape_heterogeneity": (
        "Какова форма и межпарная гетерогенность incidence?",
        "терпит известные фиксированные окна наблюдения, даже если среда "
        "связи другая"),
    "Q1c_density_and_run_merging": (
        "Как плотность связана со слиянием серий?",
        "нужны событийные направленные метки времени; романтическая переписка "
        "не обязательна"),
}

#: STOP-RULE, объявленный заранее. После стольких серьёзных кандидатов (то есть
#: удовлетворяющих всем MUST на бумаге) поиск прекращается, и отсутствие
#: чистого Q1-корпуса становится ЗАДОКУМЕНТИРОВАННЫМ ОГРАНИЧЕНИЕМ, а не поводом
#: провести октябрь в DataCite. Поиск датасета не превращается в новый
#: исследовательский проект.
STOP_AFTER_SERIOUS_CANDIDATES = 6

#: Куда смотреть, вместо общего зоопарка поисковой выдачи.
SEARCH_CLASSES = (
    "Dataverse / ICPSR / Harvard с communication-event логами и CC0/CC BY",
    "операторские challenge-датасеты 2010-х — проверять release licence и "
    "гранулярность, а не статью",
    "platform-side онлайн-сообщества с приватными сообщениями и серверными "
    "метками времени; телефон не обязателен",
)


def by_fit(fit: Fit) -> tuple[Candidate, ...]:
    return tuple(c for c in CANDIDATES if c.fit is fit)


def serious_candidates_checked() -> int:
    """Кандидаты, дошедшие до реальной проверки, а не отсеянные по названию."""
    return len(CANDIDATES)
