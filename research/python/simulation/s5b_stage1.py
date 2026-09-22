"""S5b, этап 1: популяционная поверхность измеримости.

ВОССТАНОВЛЕНО ИЗ НЕОТСЛЕЖИВАЕМОГО ИСТОЧНИКА. Первый прогон этапа 1 шёл из
`/tmp/claude-0/s5b/stage1.py` — кода, которого не было в репозитории. Он
сохранён по дайджесту `a48c59db31f0e15b` вместе с выходом, и этот модуль
обязан воспроизводить его ПОБИТОВО при `M = 4000`.

ЧЕГО ЗДЕСЬ НЕТ, И ЭТО НЕ УПУЩЕНИЕ, А ГРАНИЦА. Объявленная в prereg лестница
`4000 -> 16000 -> 64000` и статус `MC_PRECISION_INSUFFICIENT` НЕ реализованы,
потому что prereg замораживает лестницу и правило остановки, но НЕ
определяет, чем именно оценивать MCSE конца `λ∓`. Реализовать здесь
произвольную формулу SE и назвать это «исполнением замороженного правила»
означало бы дописать в prereg недостающую статистическую спецификацию задним
числом. До амендмента модуль считает ровно один уровень `M` и ничего не
утверждает о точности.

Поэтому его выход — EQUIVALENCE ORACLE, а не научный результат S5b.
"""

from __future__ import annotations

import json
import random
import sys
import time

from coarsening.bounded import (achievable_frontier, generalized_inverse,
                                hull_of, to_bins)
from coarsening.inversion import Piece
from coarsening.paired import Stream
from simulation import s5b_prereg as P
from simulation.process import DyadParameters, generate_dyad

DAY = 86400.0
LONGEST = P.LONGEST_DURATION_DAYS

#: 13 = R0 один раз плюс R1-R4 по три множителя (MAGNITUDE_NOT_APPLICABLE_TO).
REGIMES = [("R0", 1.0)] + [(regime, magnitude)
                           for regime in ("R1", "R2", "R3", "R4")
                           for magnitude in P.EFFECT_MAGNITUDE_MULTIPLIERS]


#: НАЙДЕНО ПОЗЖЕ И НЕ ИСПРАВЛЕНО ЗДЕСЬ НАМЕРЕННО. `effect` ниже НЕВЕРНА для
#: R4, и модуль сохраняет её такой, какой она была в первом прогоне: он
#: объявлен equivalence oracle, то есть записью того, ЧТО БЫЛО ПОСЧИТАНО, а
#: не того, что следовало. Исправление живёт в `s5b_escalation.regime_effect`,
#: расхождение описано в `R4_SEMANTICS_MISMATCH`.
#:
#: Область действия оракула — ВЫЧИСЛЕНИЕ, а не семантика режимов. Золотой
#: дайджест доказывает «новый слой считает то же, что старый», и ничего не
#: говорит о том, прав ли старый.
LEGACY_EFFECT_IS_WRONG_FOR_R4 = True


def effect(regime: str, magnitude: float) -> tuple[float, float]:
    """Логарифмическая шкала prereg §3. ДЛЯ R4 НЕВЕРНА — см. выше."""
    base = {"R0": (0.0, 1.0), "R1": (0.40, 1.0), "R2": (0.0, 0.75),
            "R3": (0.40, 0.75), "R4": (0.20, 0.87)}[regime]
    return base[0] * magnitude, base[1] ** magnitude


def arm_endpoints(seed: str, *, rate: float, shift: float, ratio: float,
                  c_rate: float, c_shift: float,
                  periods: int = P.MEASUREMENT_MC_START_PERIODS_PER_ARM
                  ) -> dict[tuple, float]:
    """Все 36 сочетаний (Δ, дни, H) x 2 направления из ОДНОГО набора потоков.

    Сид периода — `f"{seed}:{i}"`, то есть функция ТОЛЬКО научных координат и
    индекса. Ни worker, ни shard, ни порядок исполнения в него не входят.
    """
    params = DyadParameters(
        opportunity_rate_per_day=rate * ratio * c_rate,
        timestamp_resolution_seconds=1.0,
        latency_log_mean=DyadParameters().latency_log_mean + shift + c_shift)
    store: dict[tuple, list] = {}
    for index in range(periods):
        messages = generate_dyad(random.Random(f"{seed}:{index}"), params,
                                 days=LONGEST)
        if not messages:
            continue
        stream = Stream(tuple(m.local_time for m in messages),
                        tuple(0 if m.actor == "partner" else 1 for m in messages),
                        tuple(m.message_id for m in messages))
        for delta in P.ACQUISITION_RESOLUTIONS_SECONDS:
            full = to_bins(stream, 1, delta=delta)
            for days in P.OBSERVATION_DAYS:
                window = days * DAY
                prefix = [b for b in full if b.start < window]   # вложенный префикс
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
                        store.setdefault((delta, days, horizon, maximise), []).append(
                            tuple(Piece(float(n), b) for n, b in hull))

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
        # НАРУЖУ: нижний конец руки вниз, верхний вверх
        out[key] = bracket.high if maximise else bracket.low
    return out


def encode(ends: dict[tuple, float]) -> dict[str, float]:
    """Ключ (Δ, дни, H, направление) -> строка. Формат первого прогона."""
    return {f"{k[0]}|{k[1]}|{k[2]}|{int(k[3])}": v for k, v in ends.items()}


def arm_tag(rate: float, c_rate: float, regime: str, magnitude: float) -> str:
    """Стабильная научная идентичность руки. Основа сида."""
    return f"r{rate}:c{c_rate}:{regime}:m{magnitude}"


def main(rate: float, out=sys.stdout) -> None:
    for c_rate, c_shift in P.C_REACTIVITY_POINTS:
        for regime, magnitude in REGIMES:
            shift, ratio = effect(regime, magnitude)
            tag = arm_tag(rate, c_rate, regime, magnitude)
            started = time.perf_counter()
            ends = arm_endpoints(tag, rate=rate, shift=shift, ratio=ratio,
                                 c_rate=c_rate, c_shift=c_shift)
            print(json.dumps({
                "arm": tag, "rate": rate, "c_rate": c_rate, "c_shift": c_shift,
                "regime": regime, "magnitude": magnitude,
                "periods": P.MEASUREMENT_MC_START_PERIODS_PER_ARM,
                "seconds": round(time.perf_counter() - started, 1),
                "ends": encode(ends)}), file=out, flush=True)


if __name__ == "__main__":
    main(float(sys.argv[1]))
