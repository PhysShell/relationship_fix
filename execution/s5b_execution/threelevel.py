"""Gate A-F1: трёхуровневая модель стоимости группы ключей. ЛОКАЛЬНО.

Зачем. Gate A убил `T(G) = S + Σ cost(key)`: разбиение, раздающее каждый
блок первой координаты по всем группам, стоило на 58% больше неделёного,
а модель занизила каждую его группу на 24–26%. Код науки
(`s5b_escalation.accumulate`) показывает, почему: работа группы
трёхуровневая —

    на период на ГРУППУ          generate_dyad
    на период на пару (группа,δ) to_bins + префиксы по всем days
    на период на КЛЮЧ            achievable_frontier + hull_of

Отсюда минимально честная модель

    T(G) = A + Σ_{δ ∈ D(G)} B_δ + Σ_{k ∈ G} C_δ(k)

с C_δ одинаковой внутри блока δ. Это ГИПОТЕЗА ДЛЯ УБИЙСТВА, а не
константа для `cost.py`.

Каждый уровень измеряется СВОИМ разбиением, а не выводится задним числом:

    P1        неделёный                     A + ΣB + ΣC
    P2        два целых блока в группе      +A          -> A
    P_dδ      две группы, делится ТОЛЬКО δ  +A + B_δ    -> B_δ = C(P_dδ) − C(P2)
    P4        блок на группу                -> C_δ = (T_δ − A − B_δ) / 18

Проверки на данных, НЕ вошедших в подгонку:

- согласие цены группы: C(P1) предсказан из P2 и P4 (один лишний отсчёт);
- factorial6: C и W по модели;
- cells6: сумма C по модели.

У factorial6 и cells6 одинаковые достаточные статистики — в каждой группе
все четыре δ и по три ключа каждого, — поэтому модель предсказывает им
ОДНУ И ТУ ЖЕ стоимость группы. Factorial размазывает days/horizon/maximise
поровну, cells изолирует клетку (horizon, maximise). Их расхождение на
части «только ключи» (накладные A + ΣB вычтены структурно, а не
изображают ключи, как в Gate A) — прямое измерение оси внутри блока.
Никакая переподгонка A/B/C его не замажет.

Чего этот gate НЕ даёт: коэффициенты малого просмотра в планировщик не
переносятся; масштаб на 4000/16000/64000 он не проверяет вовсе. PASS даёт
право СФОРМУЛИРОВАТЬ новый Gate B — и только его.
"""

from __future__ import annotations

import gc
import json
import pathlib
import platform
import subprocess
import time

from simulation import s5b_shard as S

from . import calibrate
from .keycost import factorial_partition
from .scheduler import KEYS, arms, key_slices

#: Модуль — локальный gate. Планировщик его не импортирует; это
#: проверяется импортом в отдельном процессе, а не обещанием.
NOT_WIRED_INTO_THE_PLANNER = True

#: Коэффициенты малого просмотра НЕ переносятся ни в `cost.py`, ни в
#: планировщик: gate проверяет ФОРМУ модели, а не масштаб.
COEFFICIENTS_DO_NOT_TRANSFER_TO_PRODUCTION = True

ARM = "r96.0:c1.25:R0:m1.0"
SCIENCE_SHA = "7a62a3911f8bc000cf08ad97f76c0f962b07e615"

# --- ПОРОГИ. Объявлены ДО прогона и после него не меняются. ---------------

#: Весь локальный gate, включая подбор просмотра: 15 минут стены. После —
#: INCOMPLETE, а не «ещё немножко».
BUDGET_SECONDS = 900.0

#: Просмотр подбирается так, чтобы неделёный прогон стоил около 18 с ЦП
#: (полоса 10–20 с): сотые доли секунды мерили бы таймер, а не работу.
BASELINE_TARGET_SECONDS = 18.0
BASELINE_BAND_SECONDS = (10.0, 20.0)
PROBE_MIN_SECONDS = 3.0
LOOK_CAP = 4000

#: Каждое разбиение дважды: прямой порядок, затем обратный (ABBA гасит
#: линейный дрейф машины). Берётся среднее двух.
REPEATS = 2

#: Шум: наибольший относительный разброс двух повторов по ЛЮБОЙ группе
#: ЛЮБОГО разбиения. Выше 2% допуски в 5% перестают что-либо различать —
#: тогда INCONCLUSIVE, а не вердикт.
NOISE_CEILING = 0.02

#: Отрицательная A, B_δ или 18·C_δ — не зажимается в ноль. Глубже двух
#: наибольших разбросов повторов (в секундах) — KILL модели; мельче —
#: компонент не разрешён, INCONCLUSIVE.
NEGATIVE_NOISE_MULTIPLE = 2.0

#: Согласие цены группы (P2 против P4) и отложенные factorial6/cells6.
GROUP_COST_TOLERANCE = 0.05
HELDOUT_TOLERANCE = 0.05

#: cells6 против factorial6 на части «только ключи»:
#: <= 5% — эффект horizon/maximise не обнаружен (days НЕ измерена);
#: 5–10% — НЕ РЕШЕНО, и это STOP: запас бюджета того же порядка (10–14%);
#: > 10% — равномерность внутри блока убита.
UNIFORM_NOT_DETECTED = 0.05
UNIFORM_KILL = 0.10

#: Охранник: разбиение не начинается, если на него может не хватить
#: бюджета. cells6 на 4000 стоил 1.58 неделёного.
GUARD_FACTOR = 1.6

DELTAS = tuple(sorted({k[0] for k in KEYS}))


class ScienceNotFrozen(Exception):
    """Локальная наука отличается от замороженной. Мерить нечего."""


# --- разбиения -------------------------------------------------------------

def block(delta) -> tuple:
    return tuple(k for k in KEYS if k[0] == delta)


def partitions() -> dict[str, tuple]:
    """Все разбиения gate, в порядке исполнения. Каждое покрывает 72 ключа."""
    out = {"P1": (tuple(KEYS),), "P2": tuple(tuple(g) for g in key_slices(2))}
    for d in DELTAS:
        own = block(d)
        half = len(own) // 2
        rest = [block(x) for x in DELTAS if x != d]
        out[f"P_d{d:g}"] = (own[:half] + rest[0],
                            own[half:] + rest[1] + rest[2])
    out["P4"] = tuple(tuple(g) for g in key_slices(4))
    out["F6"] = tuple(tuple(g) for g in factorial_partition(6))
    out["C6"] = tuple(tuple(g) for g in calibrate.cells_partition())
    return out


def structure(slices) -> tuple[int, int]:
    """(групп, пар (группа, δ)) — достаточная статистика накладных."""
    return len(slices), sum(len({k[0] for k in g}) for g in slices)


# --- оценка и предсказание -------------------------------------------------

def _grouped(record) -> dict[str, list]:
    by: dict[str, list] = {}
    for run in record["runs"]:
        by.setdefault(run["label"], []).append(run)
    return by


def means(record) -> dict:
    """Средние по повторам: сумма разбиения и каждая его группа."""
    out = {}
    for label, runs in _grouped(record).items():
        n = len(runs)
        groups = len(runs[0]["groups_detail"])
        out[label] = {
            "total": sum(r["C_cpu"] for r in runs) / n,
            "groups": [sum(r["groups_detail"][j]["cpu_seconds"] for r in runs) / n
                       for j in range(groups)],
            "keys": [tuple(tuple(k) for k in runs[0]["groups_detail"][j]["keys"])
                     for j in range(groups)]}
    return out


def noise(record) -> dict:
    """Разброс повторов: относительный по группам и абсолютный по суммам."""
    rel, absolute = 0.0, 0.0
    for runs in _grouped(record).values():
        if len(runs) < 2:
            continue
        totals = [r["C_cpu"] for r in runs]
        absolute = max(absolute, max(totals) - min(totals))
        for j in range(len(runs[0]["groups_detail"])):
            v = [r["groups_detail"][j]["cpu_seconds"] for r in runs]
            mean = sum(v) / len(v)
            if mean > 0:
                rel = max(rel, (max(v) - min(v)) / mean)
    return {"group_relative": rel, "total_absolute": absolute}


def estimate(m: dict) -> dict:
    """A, B_δ, C_δ из средних. БЕЗ зажима в ноль: знак — это данные."""
    a = m["P2"]["total"] - m["P1"]["total"]
    b = {d: m[f"P_d{d:g}"]["total"] - m["P2"]["total"] for d in DELTAS}
    p4 = {g[0][0]: t for g, t in zip(m["P4"]["keys"], m["P4"]["groups"])}
    c = {d: (p4[d] - a - b[d]) / len(block(d)) for d in DELTAS}
    return {"A": a, "B": b, "C": c}


def predict_group(est: dict, keys) -> float:
    return (est["A"] + sum(est["B"][d] for d in {k[0] for k in keys})
            + sum(est["C"][k[0]] for k in keys))


def _rel(predicted: float, observed: float) -> float:
    return (predicted - observed) / observed


# --- вердикт ---------------------------------------------------------------

def verdict(record: dict) -> dict:
    """Статус машиночитаемый; порядок проверок — порядок их старшинства."""
    out = {"checks": {}, "status": None, "verdict": None}
    c = out["checks"]
    labels = list(partitions())
    by = _grouped(record)
    complete = (not record.get("incomplete")
                and all(len(by.get(lbl, ())) == REPEATS for lbl in labels))
    c["complete"] = complete
    if not complete:
        out["status"] = "INCOMPLETE"
        out["verdict"] = "INCOMPLETE: выводов нет"
        return out

    comparisons = record.get("comparisons", [])
    c["correctness"] = (len(comparisons) == len(labels) * REPEATS - 1
                        and all(x["identical"] for x in comparisons))
    if not c["correctness"]:
        out["status"] = "KILL_SPLIT_CHANGED_SCIENCE"
        out["verdict"] = "KILL: деление изменило научный результат"
        return out

    n = noise(record)
    base = record.get("baseline_cpu_seconds")
    c["baseline_cpu_seconds"] = base
    c["baseline_in_band"] = (None if base is None else
                             BASELINE_BAND_SECONDS[0] <= base <= BASELINE_BAND_SECONDS[1])
    c["noise_group_relative"] = round(n["group_relative"], 5)
    c["noise_total_absolute"] = round(n["total_absolute"], 4)
    m = means(record)
    est = estimate(m)
    c["A"] = round(est["A"], 4)
    c["B"] = {f"{d:g}": round(v, 4) for d, v in est["B"].items()}
    c["C"] = {f"{d:g}": round(v, 5) for d, v in est["C"].items()}

    # отрицательные компоненты: A, B_δ и полная работа блока 18·C_δ
    parts = {"A": est["A"]}
    parts.update({f"B_{d:g}": v for d, v in est["B"].items()})
    parts.update({f"C_{d:g}x{len(block(d))}": v * len(block(d))
                  for d, v in est["C"].items()})
    bar = NEGATIVE_NOISE_MULTIPLE * n["total_absolute"]
    c["negative_beyond_noise"] = sorted(k for k, v in parts.items() if v < -bar)
    c["negative_within_noise"] = sorted(k for k, v in parts.items()
                                        if -bar <= v < 0)

    predicted_p1 = predict_group(est, KEYS)
    c["group_cost_error"] = round(_rel(predicted_p1, m["P1"]["total"]), 5)

    f6 = [predict_group(est, keys) for keys in m["F6"]["keys"]]
    c["F6_C_error"] = round(_rel(sum(f6), m["F6"]["total"]), 5)
    c["F6_W_error"] = round(_rel(max(f6), max(m["F6"]["groups"])), 5)
    c6 = [predict_group(est, keys) for keys in m["C6"]["keys"]]
    c["C6_C_error"] = round(_rel(sum(c6), m["C6"]["total"]), 5)

    # ось внутри блока: часть «только ключи», накладные вычтены структурно
    overhead = est["A"] + sum(est["B"].values())
    kf = [t - overhead for t in m["F6"]["groups"]]
    kc = [t - overhead for t in m["C6"]["groups"]]
    ref = sum(kf) / len(kf)
    c["overhead_per_group"] = round(overhead, 4)
    if ref <= 0:
        # накладные съели всю группу: сравнивать ключи не с чем
        metric = float("inf")
        c["F6_key_part_spread"] = None
    else:
        c["F6_key_part_spread"] = round(max(abs(k / ref - 1.0) for k in kf), 5)
        metric = max(abs(k / ref - 1.0) for k in kc)
    c["cells_vs_factorial"] = round(metric, 5)
    if metric <= UNIFORM_NOT_DETECTED:
        c["uniformity_status"] = "HORIZON_MAXIMISE_EFFECT_NOT_DETECTED_DAYS_UNMEASURED"
    elif metric <= UNIFORM_KILL:
        c["uniformity_status"] = "UNRESOLVED"
    else:
        c["uniformity_status"] = "KILL_UNIFORM_WITHIN_BLOCK"

    if n["group_relative"] > NOISE_CEILING:
        out["status"] = "INCONCLUSIVE_NOISE"
        out["verdict"] = "INCONCLUSIVE: шум повторов выше потолка"
    elif c["negative_beyond_noise"]:
        out["status"] = "KILL_NEGATIVE_COST"
        out["verdict"] = "KILL: отрицательная стоимость за пределами шума"
    elif c["negative_within_noise"]:
        out["status"] = "INCONCLUSIVE_UNRESOLVED_COMPONENT"
        out["verdict"] = "INCONCLUSIVE: компонент не отличим от нуля снизу"
    elif abs(c["group_cost_error"]) > GROUP_COST_TOLERANCE:
        out["status"] = "KILL_GROUP_COST"
        out["verdict"] = "KILL: цена группы не постоянна (P2 против P4)"
    elif max(abs(c["F6_C_error"]), abs(c["F6_W_error"]),
             abs(c["C6_C_error"])) > HELDOUT_TOLERANCE:
        out["status"] = "KILL_HELDOUT"
        out["verdict"] = "KILL: трёхуровневая модель не держит отложенные"
    elif c["uniformity_status"] == "KILL_UNIFORM_WITHIN_BLOCK":
        out["status"] = "KILL_UNIFORM_WITHIN_BLOCK"
        out["verdict"] = "KILL: ключи внутри блока неравны по horizon/maximise"
    elif c["uniformity_status"] == "UNRESOLVED":
        out["status"] = "UNRESOLVED"
        out["verdict"] = "НЕ РЕШЕНО: STOP, Gate B не проектировать"
    else:
        out["status"] = "PASS"
        out["verdict"] = ("PASS: форма не опровергнута на малом просмотре; "
                          "days НЕ измерена; коэффициенты не переносятся")
    return out


# --- исполнение --------------------------------------------------------------

def science_changes() -> list[str]:
    """Файлы науки, отличающиеся от SCIENCE_SHA (рабочее дерево включено)."""
    root = pathlib.Path(__file__).resolve().parents[2]
    out = subprocess.run(
        ["git", "diff", "--name-only", SCIENCE_SHA, "--", "research/python",
         ":!research/python/tests", ":!research/python/tools"],
        cwd=root, capture_output=True, text=True, check=True)
    return out.stdout.split()


def measure(slices, arm: dict, look: int) -> tuple[list, dict]:
    """Одно разбиение: строки групп и слитый ЗАМОРОЖЕННЫМ `S.merge` итог."""
    rows, parts = [], []
    for keys in slices:
        unit = S.Unit(arm=ARM, look=look, keys=tuple(keys), weight=0.0)
        gc.collect()  # мусор прошлой группы — вне замера этой
        row, results = calibrate.measure_group(unit, arm)
        rows.append(row)
        parts.append((unit, results))
    merged = S.merge(ARM, look, parts, expected=[u for u, _ in parts])
    return rows, merged


def choose_look(arm: dict, measure_fn=measure) -> tuple[int, list]:
    """Удвоение, пока неделёный не стоит PROBE_MIN_SECONDS, затем пересчёт."""
    look, probes = 2, []
    while True:
        rows, _ = measure_fn((tuple(KEYS),), arm, look)
        cpu = rows[0]["cpu_seconds"]
        probes.append({"look": look, "cpu_seconds": cpu})
        if cpu >= PROBE_MIN_SECONDS or look >= LOOK_CAP:
            break
        look *= 2
    chosen = max(1, round(BASELINE_TARGET_SECONDS * look / max(cpu, 1e-9)))
    return min(chosen, LOOK_CAP), probes


def _checkpoint(path, record) -> None:
    if path is not None:
        pathlib.Path(path).write_text(json.dumps(record, sort_keys=True))


def run(*, out_path=None, budget: float = BUDGET_SECONDS,
        clock=time.monotonic, measure_fn=measure,
        changes_fn=science_changes) -> dict:
    """Весь gate. Изменение науки — немедленный отказ, бюджет — жёсткий."""
    start = clock()
    changed = changes_fn()
    if changed:
        raise ScienceNotFrozen(f"наука отличается от {SCIENCE_SHA}: {changed}")
    arm = arms()[ARM]
    parts = partitions()
    record = {"arm": ARM, "runs": [], "comparisons": [], "incomplete": None,
              "thresholds": {
                  "budget_seconds": BUDGET_SECONDS, "repeats": REPEATS,
                  "noise_ceiling": NOISE_CEILING,
                  "negative_noise_multiple": NEGATIVE_NOISE_MULTIPLE,
                  "group_cost_tolerance": GROUP_COST_TOLERANCE,
                  "heldout_tolerance": HELDOUT_TOLERANCE,
                  "uniform_not_detected": UNIFORM_NOT_DETECTED,
                  "uniform_kill": UNIFORM_KILL},
              "structure": {lbl: list(structure(sl)) for lbl, sl in parts.items()},
              "provenance": {"science_sha": SCIENCE_SHA,
                             "python": platform.python_version(),
                             "machine": platform.machine(),
                             "platform": platform.platform()}}
    look, probes = choose_look(arm, measure_fn)
    record["look"], record["probes"] = look, probes
    order = list(parts)
    schedule = [(lbl, 0) for lbl in order] + [(lbl, 1) for lbl in reversed(order)]
    baseline, base_cpu = None, None
    for label, rep in schedule:
        elapsed = clock() - start
        need = GUARD_FACTOR * base_cpu if base_cpu is not None else 0.0
        if elapsed + need > budget:
            record["incomplete"] = (
                f"{label}#{rep} не начат: прошло {elapsed:.0f} с, охранник "
                f"закладывает {need:.0f} с из бюджета {budget:.0f} с")
            break
        rows, merged = measure_fn(parts[label], arm, look)
        record["runs"].append({
            "label": label, "rep": rep, "groups_detail": rows,
            "C_cpu": round(sum(r["cpu_seconds"] for r in rows), 4),
            "C_wall": round(sum(r["wall_seconds"] for r in rows), 4)})
        if baseline is None:
            baseline, base_cpu = merged, record["runs"][-1]["C_cpu"]
            record["baseline_cpu_seconds"] = base_cpu
        else:
            cmp = calibrate.compare(baseline, merged, len(rows))
            cmp.update({"label": label, "rep": rep})
            record["comparisons"].append(cmp)
            if not cmp["identical"]:
                record["verdict"] = verdict(record)
                _checkpoint(out_path, record)
                raise calibrate.SplitChangedTheScience(
                    f"{label}#{rep} изменил результат: {cmp}")
        if clock() - start > budget:
            record["incomplete"] = (f"бюджет {budget:.0f} с превышен на "
                                    f"{label}#{rep}")
            break
        _checkpoint(out_path, record)
    record["elapsed_seconds"] = round(clock() - start, 1)
    record["verdict"] = verdict(record)
    _checkpoint(out_path, record)
    return record


if __name__ == "__main__":
    import sys
    rec = run(out_path=sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(rec["verdict"], ensure_ascii=False, indent=1))
