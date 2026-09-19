"""Парное измерение: те же сообщения, два знаменателя часов.

Реализация ЛИНЕЙНАЯ, а замороженный движок — нет: `find_opportunities`
берёт срез `stream[end + 1:]` на каждой возможности, то есть копирует хвост,
и на чате в 152 281 сообщение это часы. Поэтому здесь своя реализация, и
именно поэтому в `tests/test_coarsening.py` стоит property-тест на ПОБУКВЕННОЕ
совпадение с замороженным движком на случайных потоках.

Эквивалентность не «похоже работает», а доказуема: внутренний `while`
замороженного кода расширяет серию, пока следующий не участник, поэтому если
`end + 1 < n`, то `stream[end + 1]` — УЖЕ участник, и генератор
`next(m for m in stream[end+1:] if m.actor == participant)` выдаёт ровно его.
Срез там ищет то, что лежит на первой же позиции.

Движок при этом НЕ ТРОНУТ: заморозка запрещает менять его, а не считать
быстрее рядом, доказав равенство.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .prereg import (
    HORIZONS_HOURS, OBSERVED_RESOLUTION_SECONDS, REFERENCE_RESOLUTION_SECONDS,
    coarsen,
)


@dataclass(frozen=True, slots=True)
class Stream:
    """Поток одной диады: параллельные списки, отсортированные по sort_key.

    `keys` — произвольный tie-break, ровно как `message_id` в замороженной
    модели. Он НЕ несёт хронологии, и его произвольность — предмет измерения
    (§7 prereg), а не деталь реализации.
    """

    stamps: tuple[float, ...]
    actors: tuple[int, ...]
    keys: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.stamps)

    @property
    def actor_ids(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.actors)))


def order(stamps, actors, keys) -> Stream:
    """Сортировка по (метка, произвольный ключ) — то же, что `sort_key`."""
    rows = sorted(zip(stamps, keys, actors), key=lambda r: (r[0], r[1]))
    return Stream(tuple(r[0] for r in rows), tuple(r[2] for r in rows),
                  tuple(r[1] for r in rows))


def apply_operator(stream: Stream, delta: float, phase: float = 0.0) -> Stream:
    """C_{Δ,φ} ко всем меткам, затем пересортировка по (новая метка, ключ).

    Пересортировка обязательна и содержательна: наблюдатель A внутри корзины
    порядка не знает, поэтому порядок в ней задаётся произвольным ключом. Если
    оставить исходный порядок, мы бы подарили грубому наблюдателю знание,
    которого у него нет, и цена огрубления вышла бы нулевой по построению.
    """
    return order([coarsen(t, delta, phase) for t in stream.stamps],
                 stream.actors, stream.keys)


def ambiguous_stamps(stream: Stream) -> set[float]:
    """Метки, чью группу делят РАЗНЫЕ актёры. Тождественно замороженной."""
    seen: dict[float, int] = {}
    bad: set[float] = set()
    for stamp, actor in zip(stream.stamps, stream.actors):
        first = seen.get(stamp)
        if first is None:
            seen[stamp] = actor
        elif first != actor:
            bad.add(stamp)
    return bad


def tie_load(stream: Stream) -> tuple[int, int, int]:
    """(различных меток, из них многоакторных, сообщений в многоакторных).

    Первое число нужно, чтобы доля меток и доля ВОЗМОЖНОСТЕЙ не перепутались:
    это разные величины, и вторая заметно больше первой, потому что одна
    возможность касается до трёх меток и возможности гуще там, где гуще
    столкновения. Проект уже носит цифру «каждая шестая передача хода» —
    рядом с ней обязана стоять та, из которой она получена.
    """
    distinct = len(set(stream.stamps))
    bad = ambiguous_stamps(stream)
    if not bad:
        return distinct, 0, 0
    return distinct, len(bad), sum(1 for s in stream.stamps if s in bad)


def run_index(stream: Stream) -> list[int]:
    """Номер максимальной серии одного актёра для каждого сообщения."""
    out: list[int] = []
    current = -1
    previous = None
    for actor in stream.actors:
        if actor != previous:
            current += 1
            previous = actor
        out.append(current)
    return out


@dataclass(frozen=True, slots=True)
class Opportunity:
    opened_at: float
    run_end_at: float
    reply_at: float | None
    ambiguous: bool


def opportunities(stream: Stream, participant: int) -> list[Opportunity]:
    """Линейный эквивалент `extractor.extract.find_opportunities`."""
    bad = ambiguous_stamps(stream)
    stamps, actors = stream.stamps, stream.actors
    total = len(stamps)
    out: list[Opportunity] = []
    index = 0
    while index < total:
        if actors[index] == participant:
            index += 1
            continue
        if index > 0 and actors[index - 1] != participant:
            index += 1
            continue                          # внутри уже открытой серии
        end = index
        while end + 1 < total and actors[end + 1] != participant:
            end += 1
        reply = stamps[end + 1] if end + 1 < total else None
        touched = {stamps[index], stamps[end]}
        if reply is not None:
            touched.add(reply)
        out.append(Opportunity(stamps[index], stamps[end], reply,
                               bool(touched & bad)))
        index = end + 1
    return out


def rmtr(chances: list[Opportunity], horizon_hours: float,
         window_end: float) -> tuple[int, float | None]:
    """(N, Σ min(T, H) / N) по горизонту. Несостоявшийся возврат вносит H."""
    seconds = horizon_hours * 3600.0
    eligible = [o for o in chances if o.opened_at + seconds <= window_end]
    if not eligible:
        return 0, None
    total = sum(seconds if o.reply_at is None
                else min(o.reply_at - o.opened_at, seconds) for o in eligible)
    return len(eligible), total / len(eligible)


# ---------------------------------------------------------------------------
# Предикторы. Все ОКОННО-СВОБОДНЫЕ — см. prereg §6.
# ---------------------------------------------------------------------------

def local_density(stream: Stream) -> dict[str, float]:
    stamps = stream.stamps
    total = len(stamps)
    if total < 2:
        return {"messages_per_occupied_minute": float(total),
                "median_inter_event_gap_seconds": float("nan"),
                "p90_local_count_in_60s": float(total)}
    occupied = len({coarsen(t, 60.0) for t in stamps})
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    counts = []
    right = 0
    for left, start in enumerate(stamps):
        if right < left:
            right = left
        while right + 1 < total and stamps[right + 1] < start + 60.0:
            right += 1
        counts.append(right - left + 1)
    counts.sort()
    return {
        "messages_per_occupied_minute": total / occupied,
        "median_inter_event_gap_seconds": statistics.median(gaps),
        "p90_local_count_in_60s": float(counts[int(0.9 * (total - 1))]),
    }


# ---------------------------------------------------------------------------
# Одна рука и одна пара рук
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Arm:
    resolution_seconds: float
    phase_seconds: float
    messages: int
    distinct_stamps: int
    cross_actor_tie_groups: int
    messages_in_cross_actor_ties: int
    runs: int
    #: по обеим ролям, сложено
    opportunities: int
    opportunities_ambiguous: int
    #: N и RMTR по горизонтам, на выживших после STRICT
    rmtr_by_horizon: tuple[tuple[float, int, float | None], ...]

    @property
    def opportunities_strict(self) -> int:
        return self.opportunities - self.opportunities_ambiguous

    @property
    def strict_loss_share(self) -> float:
        if not self.opportunities:
            return 0.0
        return self.opportunities_ambiguous / self.opportunities

    @property
    def tied_stamp_share(self) -> float:
        """ДРУГАЯ величина, чем `strict_loss_share`. Не складывать и не путать."""
        if not self.distinct_stamps:
            return 0.0
        return self.cross_actor_tie_groups / self.distinct_stamps


def measure(stream: Stream, window_end: float,
            *, resolution: float, phase: float) -> tuple[Arm, list[int]]:
    """Одна рука. Возвращает также номера серий — для счёта склеек."""
    distinct, groups, tied = tie_load(stream)
    runs = run_index(stream)
    per_role = {a: opportunities(stream, a) for a in stream.actor_ids}
    survivors = [o for chances in per_role.values() for o in chances
                 if not o.ambiguous]
    rows = []
    for hours in HORIZONS_HOURS:
        count, value = rmtr(survivors, hours, window_end)
        rows.append((hours, count, value))
    total = sum(len(c) for c in per_role.values())
    flagged = sum(1 for c in per_role.values() for o in c if o.ambiguous)
    return Arm(resolution, phase, len(stream), distinct, groups, tied,
               (runs[-1] + 1) if runs else 0, total, flagged, tuple(rows)), runs


@dataclass(frozen=True, slots=True)
class Paired:
    """Одна диада, две руки и то, что между ними."""

    dyad: str
    reference: Arm
    observed: Arm
    #: сколько РАЗНЫХ опорных серий склеилось внутри наблюдённых
    merged_run_events: int
    predictors: dict[str, float]

    @property
    def added_strict_loss(self) -> float:
        """Добавочная потеря, а не потеря относительно совершенной меры."""
        return self.observed.strict_loss_share - self.reference.strict_loss_share

    @property
    def run_reduction(self) -> int:
        return self.reference.runs - self.observed.runs


def pair(dyad: str, stream: Stream, *, phase: float = 0.0) -> Paired:
    """Опорная рука, огрублённая рука и парные разности.

    Окно eligibility ОДНО на обе руки (prereg §4): иначе часть разницы
    оказалась бы разницей окон, а не разницей часов.
    """
    observed_stream = apply_operator(stream, OBSERVED_RESOLUTION_SECONDS, phase)
    window_end = max(stream.stamps[-1], observed_stream.stamps[-1]) if stream else 0.0
    reference, fine_runs = measure(
        stream, window_end, resolution=REFERENCE_RESOLUTION_SECONDS, phase=0.0)
    observed, _ = measure(
        observed_stream, window_end,
        resolution=OBSERVED_RESOLUTION_SECONDS, phase=phase)

    fine_of_key = dict(zip(stream.keys, fine_runs))
    merged = 0
    seen: set[int] = set()
    previous_run = None
    for key, run in zip(observed_stream.keys, run_index(observed_stream)):
        if run != previous_run:
            merged += max(0, len(seen) - 1)
            seen = set()
            previous_run = run
        seen.add(fine_of_key[key])
    merged += max(0, len(seen) - 1)

    return Paired(dyad, reference, observed, merged, local_density(stream))


# ---------------------------------------------------------------------------
# Передаточная функция часов: то, ради чего всё и затевалось
# ---------------------------------------------------------------------------

def transfer_rows(stream: Stream, phase: float = 0.0,
                  delta: float = OBSERVED_RESOLUTION_SECONDS):
    """(сколько сообщений было в этой корзине, стала ли возможность неоднозначной).

    Предиктор берётся из ОПОРНОГО потока и равен числу сообщений, попавших в
    ту же корзину, — то есть буквально тому, что и вызывает столкновение. Он
    локален и окна наблюдения не требует, поэтому отказанный Q1a через него
    не проходит.

    Результат пулится по диадам и даёт эмпирическое P(ambiguous | occupancy):
    не «магическая доля ties», а измеренный оператор деградации, зависящий от
    структуры потока.
    """
    occupancy: dict[float, int] = {}
    for stamp in stream.stamps:
        binned = coarsen(stamp, delta, phase)
        occupancy[binned] = occupancy.get(binned, 0) + 1
    observed = apply_operator(stream, delta, phase)
    rows = []
    for actor in observed.actor_ids:
        for chance in opportunities(observed, actor):
            rows.append((occupancy.get(chance.opened_at, 0), chance.ambiguous))
    return rows


def discard_profile(stream: Stream, phase: float = 0.0,
                    delta: float = OBSERVED_RESOLUTION_SECONDS):
    """Латентности ВЫБРОШЕННЫХ и ОСТАВЛЕННЫХ возможностей грубой руки.

    STRICT выбрасывает неоднозначные возможности. Если выброшенные системно
    быстрее оставшихся, то это не потеря мощности, а ОТБОР ПО ИСХОДУ: метрика
    считается на подвыборке, смещённой в сторону медленных возвратов. Разница
    между «шумно» и «смещено» стоит того, чтобы её померить, а не вывести.
    """
    observed = apply_operator(stream, delta, phase)
    dropped: list[float] = []
    kept: list[float] = []
    for actor in observed.actor_ids:
        for chance in opportunities(observed, actor):
            if chance.reply_at is None:
                continue
            latency = chance.reply_at - chance.opened_at
            (dropped if chance.ambiguous else kept).append(latency)
    return dropped, kept
