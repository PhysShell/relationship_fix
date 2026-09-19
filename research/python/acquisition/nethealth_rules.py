"""Правила осмотра NetHealth, зафиксированные ДО чтения полного файла.

Существуют ровно затем, чтобы порог нельзя было выбрать по красивому пику.
Человеческий мозг удивительно быстро выясняет, что именно 0.6 является
философски верной границей, — ровно в тот момент, когда увидит размер выборки.

Ничего здесь не считает по данным. Только объявляет, что будет считаться и что
будет означать результат.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# --------------------------------------------------------------------------
# 1. Время: один источник истины
# --------------------------------------------------------------------------

#: Единственный источник времени для ЛЮБОГО downstream-расчёта.
TEMPORAL_SOURCE = "epochtime"

#: Пригодны только для криминалистической сверки и подтверждения часового пояса.
#: В построение меток времени не допускаются НИКОГДА.
#:
#: Причина не гигиеническая. `epochtime` — миллисекунды UTC, `date`/`time` —
#: местные настенные часы (разность −5.00 ч на январской выборке). Стоит
#: кому-нибудь «удобно» разобрать `date + time`, и вечерние пики уедут на пять
#: часов, а под летним временем — на четыре, то есть по-разному в разные месяцы.
#: Человечество очень любит второй источник истины, особенно когда первый уже
#: работает.
FORENSIC_ONLY_FIELDS = ("date", "time", "dayofweek")


class TemporalSourceError(ValueError):
    """Попытка построить метку времени из полей, которые для этого не годятся."""


def temporal_field(name: str) -> str:
    """Пропускает только `epochtime`. Вызывается адаптером на каждом поле."""
    if name in FORENSIC_ONLY_FIELDS:
        raise TemporalSourceError(
            f"{name!r} — местные настенные часы, а не ось времени; "
            f"единственный источник — {TEMPORAL_SOURCE!r}"
        )
    if name != TEMPORAL_SOURCE:
        raise TemporalSourceError(f"{name!r} не является источником времени")
    return name


# --------------------------------------------------------------------------
# 2. Дубликаты: лестница из трёх проб, а не один шаблон
# --------------------------------------------------------------------------

class DuplicateProbe(Enum):
    #: та же пара, та же метка, зеркальные ego/alter, противоположный outgoing
    D0_EXACT_MIRROR = "D0_exact_mirror"
    #: то же, но с допуском по времени: часы двух телефонов не совпадают
    D1_NEAR_MIRROR = "D1_near_mirror"
    #: избыток зеркальных близких пар над тем, что дала бы случайность
    D2_DISTRIBUTIONAL_EXCESS = "D2_distributional_excess"


#: Окно D1, зафиксированное ДО просмотра распределения.
#:
#: Обоснование, а не вкус: 94.3% записей округлены до секунды, поэтому одна и та
#: же отправка, записанная двумя телефонами, может разойтись на несколько секунд
#: чисто от округления и расхождения часов. Пять секунд покрывают это с запасом
#: и остаются много меньше типичной паузы между разными сообщениями.
DEDUP_NEAR_WINDOW_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class DuplicateEvidence:
    """Что нашли по каждой пробе. Числа — снаружи, толкование — здесь."""

    pairs_examined: int
    d0_exact: int
    d1_near: int
    #: сколько зеркальных близких пар ожидалось бы при независимости
    d2_expected_by_chance: float

    @property
    def d2_excess(self) -> float:
        return self.d1_near - self.d2_expected_by_chance


class DuplicateVerdict(Enum):
    #: дубли доказаны: их надо сводить, иначе плотность завышена
    PRESENT = "duplicates_present"
    #: сигнатуры не наблюдается — но это НЕ «двойное логирование невозможно»
    NO_SIGNATURE_OBSERVED = "no_signature_observed"
    #: данных не хватило, чтобы вопрос вообще был задан
    INSUFFICIENT = "insufficient"


def classify_duplicates(
    evidence: DuplicateEvidence,
    *,
    minimum_pairs: int = 1000,
    excess_ratio: float = 3.0,
) -> DuplicateVerdict:
    """Чистая функция. Отсутствие D0 ничего не доказывает — за тем и D1/D2.

    Формулировка исхода узкая намеренно: `NO_SIGNATURE_OBSERVED` означает, что
    мы не увидели следов, а не что двойное логирование невозможно. Второе из
    первого не следует и никогда не будет записано как вывод.
    """
    if evidence.pairs_examined < minimum_pairs:
        return DuplicateVerdict.INSUFFICIENT
    if evidence.d0_exact > 0:
        return DuplicateVerdict.PRESENT
    if evidence.d2_expected_by_chance > 0 and \
            evidence.d1_near >= excess_ratio * evidence.d2_expected_by_chance:
        return DuplicateVerdict.PRESENT
    return DuplicateVerdict.NO_SIGNATURE_OBSERVED


# --------------------------------------------------------------------------
# 3. Идентичность: вложенные режимы, primary — самый строгий выживший
# --------------------------------------------------------------------------

#: `alterconf` дискретна (.3 .4 .5 .6 .7 .95) и является ПОРЯДКОВОЙ шкалой,
#: хотя выглядит как вероятность. Порог выбираем мы, явно и заранее.
IDENTITY_REGIMES: tuple[tuple[str, float], ...] = (
    ("I0", 0.95),
    ("I1", 0.70),
    ("I2", 0.60),
)

#: Primary — самый строгий режим, который не уничтожает корпус. Порог «не
#: уничтожает» объявляется здесь, ДО того как станет виден размер выборки.
IDENTITY_MINIMUM_DYADS = 200


def primary_identity_regime(surviving_dyads: dict[str, int]) -> str | None:
    """Строжайший режим, оставляющий хотя бы `IDENTITY_MINIMUM_DYADS` пар."""
    for name, _ in IDENTITY_REGIMES:
        if surviving_dyads.get(name, 0) >= IDENTITY_MINIMUM_DYADS:
            return name
    return None


# --------------------------------------------------------------------------
# 4. Каналы: что primary, что sensitivity, что вон
# --------------------------------------------------------------------------

#: `eventtype='SMS'` смешивает iMessage и собственно SMS, а iMessage бывает
#: только на iPhone. Platform confounding сидит ВНУТРИ канала, который
#: планировался как чистый.
CHANNEL_PRIMARY = (("SMS", "SM"),)
CHANNEL_SENSITIVITY = (("SMS", "iM"), ("WhatsApp", "DM"))
#: Групповой чат — другая топология, а не шумная диада.
CHANNEL_EXCLUDED = (("WhatsApp", "GC"),)


def channel_role(eventtype: str, detail: str) -> str:
    key = (eventtype, detail)
    if key in CHANNEL_PRIMARY:
        return "primary"
    if key in CHANNEL_SENSITIVITY:
        return "sensitivity"
    if key in CHANNEL_EXCLUDED:
        return "excluded"
    return "unassigned"


# --------------------------------------------------------------------------
# 5. Разрешение: стратифицировать прежде, чем объявлять приговор
# --------------------------------------------------------------------------

#: По чему резать разрешение, прежде чем говорить «смешанное, Q3 закрыт».
#: Если `SM` окажется почти целиком секундным, Q3 для него определим честно на
#: родной секундной шкале, и общий приговор был бы преждевременным.
RESOLUTION_STRATA = ("eventtypedetail", "iphone", "outgoing", "insession")
