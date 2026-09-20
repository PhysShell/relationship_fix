"""Слой эскалации этапа 1: вложенная лестница по ACTIVE-амендменту (ред. 4).

ЧТО ЭТОТ МОДУЛЬ ДОБАВЛЯЕТ К ВОССТАНОВЛЕННОМУ RUNNER'У. `s5b_stage1` считает
ровно один уровень `M` и про точность НЕ утверждает ничего — таким он и
задумывался, пока амендмента не было. Теперь амендмент active, и здесь
появляется то, чего там сознательно не было:

    tau = min{ M из (4000, 16000, 64000) : r_M <= z · 0.1 · GATE_MARGIN · δ }
    tau = inf  ->  MC_PRECISION_INSUFFICIENT  ->  NOT_EVALUATED_MC_PRECISION

ЭСТИМАНД НЕ МЕНЯЕТСЯ. Точки — те же корни обобщённой инверсии, что считал
runner; `roots_from` обязан воспроизводить `arm_endpoints` до последнего
знака, и это проверяется золотым дайджестом, снятым ДО рефакторинга.

ВЛОЖЕННОСТЬ — СТРОГИЙ ПРЕФИКС. Сид периода есть `f"{tag}:{i}"`, функция
ТОЛЬКО научных координат и индекса. Поэтому `accumulate(tag, 0, 16000)` и
`accumulate(tag, 0, 4000)` + `accumulate(tag, 4000, 16000)` дают побитово
одно и то же, а shard, worker, порядок исполнения и их количество в поток
не входят. Это же свойство и делает возможным шардинг диапазонами.

ДВЕ ЯЧЕЙКИ `H = 300` НЕ ПРОПУСКАЮТСЯ. Futility-правила в `2224eb8` нет, а
пилотный прогноз им не является: прогноз остаётся в провенансе как
`MC_PRECISION_PREDICTED_INSUFFICIENT` и НИКОГДА не управляет ходом
вычисления. Лестница исполняется честно до `64000`, и если точность не
достигнута — это предусмотренный исход, а не отсутствие исхода.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from coarsening.bounded import (achievable_frontier, generalized_inverse,
                                hull_of, to_bins)
from coarsening.inversion import Piece, acceptance_set, convex_hull_interval
from coarsening.paired import Stream
from simulation import s5b_precision as PR
from simulation import s5b_prereg as P
from simulation.process import DyadParameters, generate_dyad

DAY = 86400.0

#: Горизонты, пропускаемые по прогнозу. ПУСТО, и это решение, а не недосмотр.
SKIPPED_HORIZONS: tuple[float, ...] = ()

#: Прогноз — провенанс, не управление. Константа объявлена, чтобы её можно
#: было диверсировать: ниже по файлу `PREDICTED_INSUFFICIENT` не встречается
#: ни в одной ветке, и тест это проверяет разбором исходника.
PREDICTED_NEVER_DRIVES_CONTROL_FLOW = True

#: ПРОБЕЛ СПЕЦИФИКАЦИИ, НАЙДЕННЫЙ ЗДЕСЬ И НЕ ЗАКРЫТЫЙ ДОГАДКОЙ.
CONTROL_ARM_IS_UNSPECIFIED = (
    "prereg объявляет объект гейта измерения как [λ⁻_T − λ⁺_K, λ⁺_T − λ⁻_K], "
    "но не определяет, какая рука сетки есть K: ни одной строки о паре "
    "(T, K) в 2224eb8 нет, и восстановленный runner пары не строит")
CONTROL_ARM_READING = (
    "естественное чтение: K — рука того же (rate, c_rate) с регимом R0, то "
    "есть отличающаяся от T ТОЛЬКО эффектом лечения; c-реактивность есть "
    "свойство популяции и присутствует в обеих. Чтение НЕ принято за "
    "спецификацию: контраст здесь не считается")


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Один конец одной ячейки на одном просмотре."""

    key: tuple                 # (delta, days, horizon, maximise)
    delta_fraction: float
    point: float
    low: float
    high: float
    radius: float
    status: PR.PrecisionStatus
    look: int | None


def _params(rate: float, shift: float, ratio: float, c_rate: float,
            c_shift: float) -> DyadParameters:
    return DyadParameters(
        opportunity_rate_per_day=rate * ratio * c_rate,
        timestamp_resolution_seconds=1.0,
        latency_log_mean=DyadParameters().latency_log_mean + shift + c_shift)


def accumulate(tag: str, start: int, stop: int, *, rate: float, shift: float,
               ratio: float, c_rate: float, c_shift: float,
               store: dict | None = None) -> dict[tuple, list]:
    """Периоды `start..stop-1` в общий склад. Дописывает, не пересоздаёт.

    Порядок ключей и порядок периодов внутри ключа определяются ТОЛЬКО
    индексом `i`, поэтому склад, собранный по кускам, побитово совпадает со
    складом, собранным целиком.
    """
    params = _params(rate, shift, ratio, c_rate, c_shift)
    store = {} if store is None else store
    for index in range(start, stop):
        messages = generate_dyad(random.Random(f"{tag}:{index}"), params,
                                 days=P.LONGEST_DURATION_DAYS)
        if not messages:
            continue
        stream = Stream(tuple(m.local_time for m in messages),
                        tuple(0 if m.actor == "partner" else 1 for m in messages),
                        tuple(m.message_id for m in messages))
        for delta in P.ACQUISITION_RESOLUTIONS_SECONDS:
            full = to_bins(stream, 1, delta=delta)
            for days in P.OBSERVATION_DAYS:
                window = days * DAY
                prefix = [b for b in full if b.start < window]
                if not prefix:
                    continue
                for horizon in P.HORIZONS_SECONDS:
                    cut = P.initiation_cutoff(window, horizon)
                    kw = dict(horizon=horizon, window_end=window, delta=delta,
                              time_layer=False, initiation_end=cut)
                    for maximise in (False, True):
                        hull = hull_of(
                            achievable_frontier(prefix, maximise=maximise, **kw),
                            upper=maximise)
                        store.setdefault(
                            (delta, days, horizon, maximise), []).append(
                                tuple(Piece(float(n), b) for n, b in hull))
    return store


def roots_from(store: dict[tuple, list]) -> dict[tuple, float]:
    """Точки — ровно те же корни, что считал восстановленный runner."""
    out: dict[tuple, float] = {}
    for key, pieces in store.items():
        maximise = key[3]
        picked = max if maximise else min
        horizon = key[2]

        def total(lam: float, pieces=pieces, picked=picked) -> float:
            return sum(picked(p.b - lam * p.n for p in q) for q in pieces)

        if total(0.0) <= 0.0:
            out[key] = 0.0
            continue
        bracket = generalized_inverse(total, 0.0, horizon + 1e-9, tolerance=1e-4)
        out[key] = bracket.high if maximise else bracket.low
    return out


def endpoints_from(store: dict[tuple, list], *, look: int,
                   z: float = PR.Z_PER_COMPARISON
                   ) -> dict[tuple, Endpoint]:
    """Все концы склада на просмотре `look`, по одному на долю δ.

    δ есть доля ГОРИЗОНТА, поэтому один ключ порождает столько концов,
    сколько объявлено долей: цель по точности у них разная.
    """
    roots = roots_from(store)
    out: dict[tuple, Endpoint] = {}
    for key, pieces in store.items():
        horizon, maximise = key[2], key[3]
        components = acceptance_set(pieces, z=z, lo=0.0, hi=horizon,
                                    maximise=maximise)
        span = convex_hull_interval(components)
        low, high = span if span else (0.0, horizon)
        point = roots[key]
        radius = PR.radius(components, point)
        for fraction in P.DELTA_FRACTIONS_OF_HORIZON:
            delta = fraction * horizon
            precise = PR.is_precise(radius, delta, z=z)
            out[(key, fraction)] = Endpoint(
                key=key, delta_fraction=fraction, point=point,
                low=low, high=high, radius=radius,
                status=(PR.PrecisionStatus.ACHIEVED if precise
                        else PR.PrecisionStatus.INSUFFICIENT),
                look=look if precise else None)
    return out


def run_arm(tag: str, *, rate: float, shift: float, ratio: float,
            c_rate: float, c_shift: float, ladder=PR.LOOKS,
            z: float = PR.Z_PER_COMPARISON) -> dict[tuple, Endpoint]:
    """Честная лестница. Останавливается, когда ВСЕ концы руки точны.

    Периоды общие для всех концов, поэтому рука идёт до максимума из их
    требований. Ни один горизонт не пропускается — см. `SKIPPED_HORIZONS`.
    """
    store: dict[tuple, list] = {}
    settled: dict[tuple, Endpoint] = {}
    drawn = 0
    for size in ladder:
        store = accumulate(tag, drawn, size, rate=rate, shift=shift,
                           ratio=ratio, c_rate=c_rate, c_shift=c_shift,
                           store=store)
        drawn = size
        current = endpoints_from(store, look=size, z=z)
        for name, endpoint in current.items():
            if name in settled:
                continue
            if endpoint.status is PR.PrecisionStatus.ACHIEVED:
                settled[name] = endpoint
        if len(settled) == len(current):
            break
    for name, endpoint in current.items():
        settled.setdefault(name, endpoint)
    return settled


# ---------------------------------------------------------------------------
# PROVENANCE: прогноз живёт ТОЛЬКО здесь и ни на что не влияет
# ---------------------------------------------------------------------------

def predicted_note(tag: str, key: tuple, fraction: float) -> str:
    """Диагностическая пометка пилота. Вердиктом не является.

    Возвращает строку для провенанса. Ни одна ветка управления её не
    читает: лестница исполняется независимо от того, что предсказал пилот.
    """
    return (f"{tag}|{key}|{fraction}: "
            f"{PR.PrecisionStatus.PREDICTED_INSUFFICIENT.value}")


def cell_is_evaluable(statuses) -> bool:
    """Ячейка оценима, только когда ТОЧНЫ ВСЕ ЧЕТЫРЕ конца.

    Четыре — это λ⁻ и λ⁺ у treated и control. Ни три, ни пять: длина
    проверяется отдельно, потому что `all([])` истинно, а пустая ячейка
    вердикта не заслуживает.
    """
    statuses = list(statuses)
    return (len(statuses) == 4
            and all(s is PR.PrecisionStatus.ACHIEVED for s in statuses))


def cell_status(statuses):
    """`None`, если ячейка оценима; иначе статус ПОВЕРХНОСТИ."""
    if cell_is_evaluable(statuses):
        return None
    return PR.NOT_EVALUATED_MC_PRECISION
