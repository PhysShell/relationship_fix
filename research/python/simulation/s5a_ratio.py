"""S5a-RATIO — квалификация машинерии НОВОГО первичного эстиманда.

БЛОКИРУЮЩИЙ амендмент к S5a (prereg S5b §4b). Исторический S5a квалифицировал
person-period-weighted RMTR; связка «ΣB/ΣN + арм-Динкельбах + инверсия теста»
такой квалификации не получала НИ ОДНОЙ, и наследовать её нельзя.

Здесь НЕ измеряется ничего про людей. Проверяется только машинерия, на том же
замороженном DGP.

ЧТЕНИЕ СПЕЦИФИКАЦИИ, СДЕЛАННОЕ ЗДЕСЬ И ОБЪЯВЛЕННОЕ ВСЛУХ. Prereg фиксирует
«отдельный интервал на каждый конец контраста, затем внешнее объединение» и
приводит Бонферрони для ДВУХ концов. Концов теперь четыре — λ∓ у каждой из
двух рук, — поэтому уровень на конец берётся 1 − α/4, и объединение границ
даёт совместное покрытие не хуже 1 − α. Это прочтение КОНСЕРВАТИВНО
(расширяет), но это именно прочтение, а не буква prereg, и потому вынесено
сюда, а не спрятано в код.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from statistics import NormalDist

from coarsening.bounded import Bin, achievable_frontier, hull_of, to_bins
from coarsening.inversion import Piece, acceptance_set, convex_hull_interval
from coarsening.paired import Stream
from simulation.process import DAY, DyadParameters, generate_dyad

#: Четыре конца -> уровень на конец по Бонферрони.
ENDPOINTS = 4
ALPHA = 0.05
Z_ENDPOINT = NormalDist().inv_cdf(1.0 - ALPHA / (2 * ENDPOINTS))


@dataclass(frozen=True, slots=True)
class Arm:
    """Руки хранятся оболочками: ψ(λ) = экстремум по (N, B)."""

    lower: tuple[tuple[Piece, ...], ...]
    upper: tuple[tuple[Piece, ...], ...]
    zero_incidence: int
    periods: int


def build_arm(seed: str, dyads: int, *, days: float, rate: float,
              resolution: float, horizon: float,
              latency_shift: float = 0.0, rate_ratio: float = 1.0,
              missing: float = 0.0, rng: random.Random | None = None) -> Arm:
    """Рука -> оболочки достижимых (N, B) на период."""
    rng = rng or random.Random(seed)
    params = DyadParameters(
        opportunity_rate_per_day=rate * rate_ratio,
        timestamp_resolution_seconds=resolution,
        latency_log_mean=DyadParameters().latency_log_mean + latency_shift)
    window = days * DAY
    lower, upper, empty = [], [], 0
    for index in range(dyads):
        messages = generate_dyad(random.Random(f"{seed}:{index}"), params, days=days)
        if missing:
            messages = [m for m in messages if rng.random() >= missing]
        if not messages:
            empty += 1
            continue
        stream = Stream(tuple(m.local_time for m in messages),
                        tuple(0 if m.actor == "partner" else 1 for m in messages),
                        tuple(m.message_id for m in messages))
        bins = to_bins(stream, 1, delta=resolution)
        kw = dict(horizon=horizon, window_end=window, delta=resolution,
                  time_layer=False)
        low = hull_of(achievable_frontier(bins, maximise=False, **kw))
        high = hull_of(achievable_frontier(bins, maximise=True, **kw), upper=True)
        if max(n for n, _ in low) == 0:
            empty += 1
        lower.append(tuple(Piece(float(n), b) for n, b in low))
        upper.append(tuple(Piece(float(n), b) for n, b in high))
    return Arm(tuple(lower), tuple(upper), empty, len(lower))


def arm_point(pieces, *, maximise: bool) -> float:
    """Точечная граница руки: ноль Σψ(λ), то есть ΣB/ΣN на экстремуме."""
    from coarsening.bounded import generalized_inverse
    picked = max if maximise else min
    total = lambda lam: sum(picked(p.b - lam * p.n for p in q) for q in pieces)
    if total(0.0) <= 0.0:
        return 0.0
    bracket = generalized_inverse(total, 0.0, HORIZON_CAP + 1e-9, tolerance=1e-6)
    return (bracket.low + bracket.high) / 2.0


HORIZON_CAP = 3600.0


def endpoint_set(pieces, *, maximise: bool, horizon: float):
    """ПОЛНОЕ множество принятия для одного конца одной руки."""
    return acceptance_set(pieces, z=Z_ENDPOINT, lo=0.0, hi=horizon,
                          maximise=maximise)


def contrast_interval(treated: Arm, control: Arm, *, horizon: float):
    """Внешняя оболочка контраста по четырём концам.

    Нижний конец контраста = λ⁻T − λ⁺K, верхний = λ⁺T − λ⁻K. Берём
    оболочки множеств принятия и комбинируем наружу.
    """
    sets = {
        ("T", "low"): endpoint_set(treated.lower, maximise=False, horizon=horizon),
        ("T", "high"): endpoint_set(treated.upper, maximise=True, horizon=horizon),
        ("K", "low"): endpoint_set(control.lower, maximise=False, horizon=horizon),
        ("K", "high"): endpoint_set(control.upper, maximise=True, horizon=horizon),
    }
    hulls = {key: convex_hull_interval(value) for key, value in sets.items()}
    if any(h is None for h in hulls.values()):
        return None, sets
    low = hulls[("T", "low")][0] - hulls[("K", "high")][1]
    high = hulls[("T", "high")][1] - hulls[("K", "low")][0]
    return (low, high), sets


def identified_contrast(treated: Arm, control: Arm) -> tuple[float, float]:
    """Популяционный/выборочный ИДЕНТИФИЦИРОВАННЫЙ интервал контраста."""
    t_low = arm_point(treated.lower, maximise=False)
    t_high = arm_point(treated.upper, maximise=True)
    k_low = arm_point(control.lower, maximise=False)
    k_high = arm_point(control.upper, maximise=True)
    return (t_low - k_high, t_high - k_low)
