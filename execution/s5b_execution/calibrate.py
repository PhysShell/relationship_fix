"""Калибровка экономии деления ключей. ОДНО задание, ОДИН раннер.

Зачем именно так. `UNDIVIDED_SHARE` — единственный параметр, из-за
которого ступень 64000 не планируется: худший полный юнит весит 9.74 ч
против бюджета 2.5 ч и потолка задания 5.83 ч, значит деление
обязательно, а его экономия не измерена ни разу (на 4000 и 16000
`groups_needed = 1` у всех рук).

Единственное прежнее касание этой оси — дымовая проба, гонявшая одну
группу из двух. Её факт был ближе к «половина ключей стоит как все», чем
к модельным 0.525, но развести это с классом раннера нельзя: там
менялись одновременно ступень, доля ключей и раннер. Наблюдённый разброс
раннеров 1.96× БОЛЬШЕ разницы, которую ищем, поэтому сравнение вариантов
на разных раннерах не измеряет ничего.

Отсюда конструкция: все варианты одной руки идут ПОСЛЕДОВАТЕЛЬНО в одном
задании. Отношение времён тогда не содержит межраннерной дисперсии
вовсе, и одной руки достаточно.

Ступень 4000, а не 16000: `s` в модели не зависит от просмотра
(генерация — на период, работа по ключам — на период на ключ), а полный
свип на 4000 стоит около 2 ч против 8 ч на 16000. Предположение о
независимости от просмотра само НЕ проверено — подтверждение на 16000
требует отдельного решения.

Наука здесь не меняется: деление выражается юнитом с подмножеством
ключей, что `S.Unit` умеет с самого начала, а сборка идёт ЗАМОРОЖЕННЫМ
`S.merge`.
"""

from __future__ import annotations

import resource
import time

from simulation import s5b_shard as S

from .scheduler import FRACTIONS, KEYS, arms, key_slices

#: варианты деления, в этом порядке: сперва база, потом дробления
VARIANTS = (1, 2, 4)

#: Худший случай экономии: деление не экономит ничего (s = 1), и вариант
#: из g групп стоит g * T1. Охранник времени считает по нему, а не по
#: надежде: иначе таймаут задания стал бы суррогатом измерения.
WORST_CASE_COST_IS_G_TIMES_BASELINE = True

#: запас на выгрузку артефакта и постобработку задания
TAIL_SECONDS = 240.0


class CalibrationIncomplete(Exception):
    """Времени задания не хватает на следующий вариант. Это НЕ измерение."""


class SplitChangedTheScience(Exception):
    """Делёный прогон дал другой научный результат. Останов немедленный."""


def _usage() -> tuple[float, float]:
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime, r.ru_maxrss / 1024.0


def measure_group(unit, arm: dict) -> dict:
    """Один юнит: время стены, время ЦП, высшая вода RSS, концы."""
    cpu0, _ = _usage()
    wall0 = time.perf_counter()
    results = S.run_unit(unit, rate=arm["rate"], c_rate=arm["c_rate"],
                         c_shift=arm["c_shift"], regime=arm["regime"],
                         magnitude=arm["magnitude"])
    wall = time.perf_counter() - wall0
    cpu1, rss = _usage()
    return {"task_id": unit.task_id, "keys": [list(k) for k in unit.keys],
            "key_count": len(unit.keys), "wall_seconds": round(wall, 3),
            "cpu_seconds": round(cpu1 - cpu0, 3),
            "rss_high_water_mb": round(rss, 1),
            "endpoint_count": len(results)}, results


def _as_tuple(endpoint) -> tuple:
    return (tuple(endpoint.key), endpoint.delta_fraction, endpoint.point,
            endpoint.low, endpoint.high, endpoint.radius,
            endpoint.status.value, endpoint.look)


def compare(baseline: dict, merged: dict, groups: int) -> dict:
    """Слитый результат против неделёного, ПО ИДЕНТИЧНОСТЯМ и содержимому.

    Идентичность конца здесь — `(ключ, доля)`: рука и просмотр у вариантов
    общие по построению, и включать их значило бы сравнивать константы.
    """
    missing = sorted(set(baseline) - set(merged), key=repr)
    unexpected = sorted(set(merged) - set(baseline), key=repr)
    differing = [name for name in sorted(set(baseline) & set(merged), key=repr)
                 if _as_tuple(baseline[name]) != _as_tuple(merged[name])]
    out = {"groups": groups, "baseline_endpoints": len(baseline),
           "merged_endpoints": len(merged), "missing": len(missing),
           "unexpected": len(unexpected), "differing": len(differing),
           "examples": [repr(x) for x in (missing + unexpected + differing)[:3]]}
    out["identical"] = not (missing or unexpected or differing)
    return out


def amdahl(totals: dict[int, float]) -> dict:
    """Неделимая доля из сумм времён групп.

    Модель планировщика: вариант из g групп стоит
    `T1 * (s + (1 - s) / g)` на группу, значит СУММА по группам равна
    `T1 * (1 + (g - 1) * s)`. Отсюда s выводится алгеброй, а не подгонкой:

        s_g = (C_g / C_1 - 1) / (g - 1)

    Отдельная величина для каждого g печатается СВОЯ: если они
    расходятся, модель неверна, и усреднять их в удобное число нельзя.
    """
    base = totals[1]
    out = {}
    for g, total in sorted(totals.items()):
        if g == 1:
            continue
        out[f"s_{g}"] = round((total / base - 1.0) / (g - 1), 6)
    return out


def groups_for_target(full_seconds: float, budget_seconds: float,
                      share: float, cap: int = None) -> int | None:
    """Сколько групп нужно при измеренной доле `share`. `None` — не влезает."""
    cap = cap or len(KEYS)
    for g in range(1, cap + 1):
        if full_seconds * (share + (1.0 - share) / g) <= budget_seconds:
            return g
    return None


def run(arm_tag: str, look: int, *, deadline: float,
        variants=VARIANTS) -> dict:
    """Провести калибровку. Любое расхождение науки — немедленный отказ."""
    known = arms()
    if arm_tag not in known:
        raise SplitChangedTheScience(f"рука {arm_tag} не из замороженной сетки")
    arm = known[arm_tag]
    record = {"arm": arm_tag, "look": look,
              "effective_rate": arm["effective_rate"],
              "keys_total": len(KEYS), "fractions": list(FRACTIONS),
              "variants": [], "comparisons": [], "incomplete": None}
    baseline, totals = None, {}

    for groups in variants:
        left = deadline - time.monotonic() - TAIL_SECONDS
        need = (totals[1] * groups if 1 in totals
                else 0.0)                     # для базы оценки ещё нет
        if 1 in totals and left < need:
            record["incomplete"] = (
                f"вариант {groups} не начат: осталось {left/3600:.2f} ч, "
                f"худший случай требует {need/3600:.2f} ч "
                f"(= {groups} x база, s = 1)")
            break
        slices = key_slices(groups)
        rows, merged_parts, spent = [], [], 0.0
        for keys in slices:
            unit = S.Unit(arm=arm_tag, look=look, keys=keys, weight=0.0)
            row, results = measure_group(unit, arm)
            rows.append(row)
            merged_parts.append((unit, results))
            spent += row["wall_seconds"]
        expected = [u for u, _ in merged_parts]
        merged = S.merge(arm_tag, look, merged_parts, expected=expected)
        walls = [r["wall_seconds"] for r in rows]
        record["variants"].append({
            "groups": groups, "groups_actual": len(slices),
            "C_g_sum_wall": round(spent, 3),
            "W_g_max_wall": round(max(walls), 3),
            "min_group_wall": round(min(walls), 3),
            "spread_max_over_min": round(max(walls) / min(walls), 4),
            "C_g_sum_cpu": round(sum(r["cpu_seconds"] for r in rows), 3),
            "rss_high_water_mb": max(r["rss_high_water_mb"] for r in rows),
            "groups_detail": rows})
        totals[groups] = spent
        if baseline is None:
            baseline = merged
        else:
            verdict = compare(baseline, merged, groups)
            record["comparisons"].append(verdict)
            if not verdict["identical"]:
                record["shares"] = amdahl(totals)
                record["correctness"] = "KILL"
                raise SplitChangedTheScience(
                    f"деление на {groups} групп изменило результат: "
                    f"{verdict}")
    record["shares"] = amdahl(totals) if len(totals) > 1 else {}
    record["correctness"] = ("PASS" if record["comparisons"]
                             and all(c["identical"] for c in record["comparisons"])
                             else "NOT_MEASURED")
    return record
