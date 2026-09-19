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
    REFUSED = "REFUSED"


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
        "CollegeMsg (SNAP / Opsahl)",
        Fit.LICENSE_PROVENANCE_OPEN,
        "59 835 приватных сообщений, 1 899 пользователей, 193 дня, "
        "SRC DST UNIXTS. SNAP лицензии не указывает.",
        note="Технически интересен и это СООБЩЕНИЯ, а не звонки. Более поздний "
             "набор на Figshare под CC BY 4.0 использует CollegeMsg вместе с "
             "другими сетями, но это не даёт автоматического права "
             "перелицензировать исходный корпус: надо проверить, что именно "
             "лежит в той коллекции.",
    ),
)


def by_fit(fit: Fit) -> tuple[Candidate, ...]:
    return tuple(c for c in CANDIDATES if c.fit is fit)
