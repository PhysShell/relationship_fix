"""S3: сопоставление синтетического процесса с MaiChat по зарегистрированным вопросам.

Корпус здесь — КАЛИБРОВОЧНЫЙ, не validation set (prereg §0). Он уже
использовался, и теперь на него смотрят, чтобы оценить правдоподобие
генератора. Подтверждать на нём подстроенное запрещено бессрочно.

Ни одна строка замороженного экстрактора не трогается: топология берётся его же
публичными функциями (`normalize`, `find_opportunities`, `ambiguous_timestamps`,
`Opportunity.eligible_for`), потому что доля ВЫБРОШЕННЫХ возможностей по
горизонту из агрегата не восстанавливается — агрегат их уже не содержит.

Классы сравнимости объявлены в prereg §2 и здесь только исполняются. Величина,
помеченная NOT_COMPARABLE, всё равно считается и печатается — но вердикта не
получает. Иначе структурное несоответствие превращается в «расхождение», а
потом в повод подкрутить генератор под корпус, который на этот вопрос не
отвечает.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum

from extractor.extract import ambiguous_timestamps, find_opportunities, normalize
from extractor.model import RawMessage

#: Сетка квантилей из prereg §2.4. Хвосты, а не одна медиана.
QUANTILES = (0.50, 0.75, 0.90, 0.95)
#: Короткая часть сетки: там, где синхронная сессия ещё что-то говорит.
SHORT_GRID = (0.50, 0.75)


class Comparability(Enum):
    #: сравнимо на всей сетке
    FULL = "comparable"
    #: сравнимо только в короткой части; хвост подавлен синхронной сессией
    SHORT_RANGE = "short_range_only"
    #: структурное несоответствие запрещает сравнение вовсе
    NONE = "not_comparable"


class Verdict(Enum):
    IN_RANGE = "in_range"
    MARGINAL = "marginal"
    OUT_OF_RANGE = "out_of_range"
    NOT_COMPARABLE = "not_comparable"
    #: обе стороны не дали достаточно наблюдений, чтобы считать квантиль
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class Quantity:
    name: str
    comparability: Comparability
    why: str

    @property
    def verdict_grid(self) -> tuple[float, ...]:
        if self.comparability is Comparability.FULL:
            return QUANTILES
        if self.comparability is Comparability.SHORT_RANGE:
            return SHORT_GRID
        return ()


QUANTITIES = (
    Quantity("run_message_count", Comparability.FULL,
             "длина серии партнёра — внутрисессионная топология"),
    Quantity("run_span_seconds", Comparability.FULL,
             "протяжённость серии партнёра"),
    Quantity("reply_speed_seconds", Comparability.SHORT_RANGE,
             "последнее сообщение серии -> ответ; хвост подавлен синхронной сессией"),
    Quantity("run_start_to_reentry_seconds", Comparability.SHORT_RANGE,
             "начало серии -> ответ; то же ограничение"),
    Quantity("inter_opportunity_gap_seconds", Comparability.NONE,
             "сессия в минутах против периода в 14 суток: несравнимо по построению"),
    Quantity("messages_per_person_period", Comparability.NONE,
             "величина масштаба окна, а окна разные (prereg §1.2)"),
    Quantity("opportunities_per_person_period", Comparability.NONE,
             "то же; N на период несравним (prereg §1.2)"),
    Quantity("nonresponse_share", Comparability.NONE,
             "обе стороны сидят и разговаривают: молчание подавлено (prereg §1.3)"),
    Quantity("hour_of_day", Comparability.NONE,
             "час назначения сессии, а не ритм пары (prereg §1.3)"),
)

BY_NAME = {q.name: q for q in QUANTITIES}


# --------------------------------------------------------------------------
# Топология одного person-period, публичными функциями замороженного движка
# --------------------------------------------------------------------------

def coarsen(messages: Sequence[RawMessage], resolution_seconds: float) -> list[RawMessage]:
    """Огрубление часов до `resolution_seconds`, полом по оси СОБЫТИЯ.

    MaiChat отдаёт миллисекунды server-receive, Telegram — секунды часов
    отправителя. Доля ties в родном разрешении MaiChat к нашему вопросу
    отношения не имеет, поэтому она меряется и после огрубления (prereg §1.1).
    Пол берётся от `timestamp`, а не от `local_time`, чтобы смещение зоны не
    двигало сетку.
    """
    if resolution_seconds <= 0:
        return list(messages)
    out = []
    for m in messages:
        stamped = math.floor(m.timestamp / resolution_seconds) * resolution_seconds
        out.append(replace(m, local_time=stamped + m.utc_offset_minutes * 60.0))
    return out


@dataclass(frozen=True, slots=True)
class TiePressure:
    """Prereg §2.1: не одно число, а четыре — они про разное."""

    messages: int
    #: групп, где одну метку делит больше одного сообщения
    timestamp_groups: int
    #: из них групп, где в группе больше одного актёра — только они ломают топологию
    cross_actor_groups: int
    opportunities_in_period: int
    ambiguous_in_period: int
    #: H -> (чистых eligible, неоднозначных eligible)
    by_horizon: dict[float, tuple[int, int]]

    def cost(self, horizon_hours: float) -> float | None:
        clean, ambiguous = self.by_horizon[horizon_hours]
        total = clean + ambiguous
        return ambiguous / total if total else None

    def merged(self, other: TiePressure) -> TiePressure:
        return TiePressure(
            messages=self.messages + other.messages,
            timestamp_groups=self.timestamp_groups + other.timestamp_groups,
            cross_actor_groups=self.cross_actor_groups + other.cross_actor_groups,
            opportunities_in_period=self.opportunities_in_period + other.opportunities_in_period,
            ambiguous_in_period=self.ambiguous_in_period + other.ambiguous_in_period,
            by_horizon={
                h: (self.by_horizon[h][0] + other.by_horizon[h][0],
                    self.by_horizon[h][1] + other.by_horizon[h][1])
                for h in self.by_horizon
            },
        )


def _empty_pressure(horizons) -> TiePressure:
    return TiePressure(0, 0, 0, 0, 0, {h: (0, 0) for h in horizons})


@dataclass
class Sample:
    """Накопитель наблюдений по именам величин. Списки, не сводки."""

    values: dict[str, list[float]]
    pressure: TiePressure

    @classmethod
    def empty(cls, horizons) -> Sample:
        return cls({q.name: [] for q in QUANTITIES}, _empty_pressure(horizons))

    def absorb(self, other: Sample) -> None:
        for name, series in other.values.items():
            self.values[name].extend(series)
        self.pressure = self.pressure.merged(other.pressure)


def observe(
    raw: Sequence[RawMessage],
    participant: str,
    period_start: float,
    period_end: float,
    horizons: Sequence[float],
) -> Sample:
    """Один person-period -> наблюдения по всем зарегистрированным величинам."""
    sample = Sample.empty(horizons)
    stream, _, _, _ = normalize(list(raw))
    in_window = [m for m in stream if period_start <= m.timestamp < period_end]

    groups: dict[float, set[str]] = {}
    counts: dict[float, int] = {}
    for message in stream:
        groups.setdefault(message.timestamp, set()).add(message.actor)
        counts[message.timestamp] = counts.get(message.timestamp, 0) + 1
    shared = {stamp for stamp, n in counts.items() if n > 1}
    cross = ambiguous_timestamps(stream)

    opportunities = [o for o in find_opportunities(stream, participant)
                     if period_start <= o.opened_at < period_end]
    ambiguous = [o for o in opportunities if o.ambiguous_order]
    clean = [o for o in opportunities if not o.ambiguous_order]

    by_horizon = {}
    for hours in horizons:
        seconds = hours * 3600.0
        by_horizon[hours] = (
            sum(1 for o in clean if o.eligible_for(seconds, period_end)),
            sum(1 for o in ambiguous if o.eligible_for(seconds, period_end)),
        )

    sample.pressure = TiePressure(
        messages=len(in_window),
        timestamp_groups=len(shared),
        cross_actor_groups=len(cross),
        opportunities_in_period=len(opportunities),
        ambiguous_in_period=len(ambiguous),
        by_horizon=by_horizon,
    )

    v = sample.values
    replied = 0
    for opportunity in clean:
        v["run_message_count"].append(float(opportunity.run_message_count))
        v["run_span_seconds"].append(float(opportunity.run_span_seconds))
        latency = opportunity.latency_seconds
        if latency is not None:
            replied += 1
            v["run_start_to_reentry_seconds"].append(float(latency))
            speed = opportunity.reply_speed_seconds
            if speed is not None:
                v["reply_speed_seconds"].append(float(speed))
    for before, after in zip(clean, clean[1:]):
        v["inter_opportunity_gap_seconds"].append(float(after.opened_at - before.opened_at))

    v["messages_per_person_period"].append(float(len(in_window)))
    v["opportunities_per_person_period"].append(float(len(clean)))
    if clean:
        v["nonresponse_share"].append(1.0 - replied / len(clean))
    for message in in_window:
        v["hour_of_day"].append((message.timestamp % 86400.0) / 3600.0)
    return sample


# --------------------------------------------------------------------------
# Сравнение: квантили, log2-отношение, вердикт
# --------------------------------------------------------------------------

def quantile(series: Sequence[float], p: float) -> float | None:
    """Линейная интерполяция по порядковым статистикам; None, если мало данных."""
    ordered = sorted(series)
    if len(ordered) < 5:
        return None
    if p <= 0:
        return ordered[0]
    if p >= 1:
        return ordered[-1]
    position = p * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def classify_distance(distance: float | None, comparability: Comparability) -> Verdict:
    """Чистая функция. Пороги из prereg §3, назначены ДО просмотра.

    `D <= 1` — везде в пределах ×2, внутри уже моделируемого межпарного
    разброса. `D > 2` — дальше ×4, что меняет power landscape существенно,
    поскольку дисперсия входит в квадрате.
    """
    if comparability is Comparability.NONE:
        return Verdict.NOT_COMPARABLE
    if distance is None:
        return Verdict.INSUFFICIENT
    if distance <= 1.0:
        return Verdict.IN_RANGE
    if distance <= 2.0:
        return Verdict.MARGINAL
    return Verdict.OUT_OF_RANGE


@dataclass(frozen=True, slots=True)
class Comparison:
    quantity: Quantity
    synthetic: dict[float, float | None]
    corpus: dict[float, float | None]
    n_synthetic: int
    n_corpus: int
    distance: float | None
    verdict: Verdict

    def ratio(self, p: float) -> float | None:
        a, b = self.synthetic.get(p), self.corpus.get(p)
        if a is None or b is None or b == 0:
            return None
        return a / b


def compare(synthetic: Sample, corpus: Sample) -> list[Comparison]:
    out = []
    for quantity in QUANTITIES:
        mine = synthetic.values[quantity.name]
        theirs = corpus.values[quantity.name]
        grid_mine = {p: quantile(mine, p) for p in QUANTILES}
        grid_theirs = {p: quantile(theirs, p) for p in QUANTILES}
        ratios = []
        for p in quantity.verdict_grid:
            a, b = grid_mine[p], grid_theirs[p]
            if a is None or b is None or a <= 0 or b <= 0:
                ratios = []
                break
            ratios.append(abs(math.log2(a / b)))
        distance = max(ratios) if ratios else None
        out.append(Comparison(
            quantity=quantity,
            synthetic=grid_mine,
            corpus=grid_theirs,
            n_synthetic=len(mine),
            n_corpus=len(theirs),
            distance=distance,
            verdict=classify_distance(distance, quantity.comparability),
        ))
    return out


def total_variation(a: Sequence[float], b: Sequence[float], bins: int = 24) -> float | None:
    """Для распределений по часам суток: отношение квантилей тут бессмысленно."""
    if not a or not b:
        return None
    def histogram(series):
        counts = [0] * bins
        for value in series:
            counts[min(bins - 1, int(value / (24.0 / bins)))] += 1
        return [c / len(series) for c in counts]
    return 0.5 * sum(abs(x - y) for x, y in zip(histogram(a), histogram(b)))


def summarise(series: Sequence[float]) -> str:
    if not series:
        return "—"
    return (f"n={len(series)} mean={statistics.fmean(series):.1f} "
            + " ".join(f"p{int(p*100)}={quantile(series, p):.1f}"
                       for p in QUANTILES if quantile(series, p) is not None))
