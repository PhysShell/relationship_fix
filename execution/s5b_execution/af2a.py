"""Gate A-F2a: агрегатная трёхуровневая модель, усиленный контраст. ЛОКАЛЬНО.

A-F1 мерил одну B_δ разностью порядка 0.3 с при разбросе сумм больше
секунды и вернул INCONCLUSIVE. Здесь проверяется более необходимое
условие, и сигнал строится большим, а не выслеживается:

    C(P) = g(P)·A + n(P)·ΣB + K          (n — в скольких группах каждый δ)

Все разбиения ниже держат n ОДИНАКОВЫМ для всех δ, поэтому отдельные B_δ
не нужны — только A и ΣB. K (работа ключей) одинакова у всех: каждый ключ
ровно один раз.

    P1  g=1 n=1   неделёный
    P4  g=4 n=1   блок на группу                  A  = (P4 − P1)/3
    F6  g=6 n=6   factorial (2h + x + 2d + t)      ΣB = (F6 − P1 − 5A)/5
    Q6  g=6 n=2   смежные 12                       ОТЛОЖЕН: P1 + 5A + ΣB
    H4  g=4 n=2   кольцо 9+9                       ОТЛОЖЕН: P1 + 3A + ΣB
    C6  g=6 n=6   cells (horizon, maximise)        ОТЛОЖЕН: = F6

Почему ΣB из F6, а не из Q6: у оценки плечо 5, а отложенные — интерполяция.
Обратная схема экстраполирует F6 = 5·Q6 + 2.67·P1 − 6.67·P4, и шум трёх
сумм раздувается примерно в 8.7 раза (расчёт — `power_rationale`).

Загрязнение подгонки здесь — сила проверки: если у F6 есть скрытый уровень
(группа, δ, days), он уйдёт в ΣB, а Q6 — единственный, чьи блоки days не
дробятся (пар (δ, days) у него 12, как у неделёного) — его и поймает.

Равномерность внутри блока — ТОЛЬКО на уровне групп: суммы C6 и F6 при
аддитивных эффектах ключей совпадают тождественно. Накладные A + ΣB у всех
шести групп обоих одинаковы и вычитаются. F6 балансирует все координаты —
он КОНТРОЛЬ шума; C6 изолирует клетку — он ЗОНД эффекта. Тот же объект не
может одновременно искать эффект и объявлять его шумом.

Чего gate НЕ даёт: отдельные B_δ (это A-F2b), масштаб на 4000/16000/64000,
право подключить модель или выставить `UNDIVIDED_SHARE`.
"""

from __future__ import annotations

import json
import pathlib
import platform
import random
import time

from . import calibrate
from .keycost import factorial_partition
from .scheduler import KEYS, arms, key_slices
from .threelevel import (ARM, SCIENCE_SHA, ScienceNotFrozen, block, measure,
                         science_changes, structure)

#: Локальный gate. Планировщик его не импортирует — проверяется импортом.
NOT_WIRED_INTO_THE_PLANNER = True

#: Коэффициенты малого просмотра никуда не переносятся.
COEFFICIENTS_DO_NOT_TRANSFER_TO_PRODUCTION = True

# --- ПОРОГИ. Объявлены ДО замера и после него не меняются. ----------------

#: Весь gate, включая подбор просмотра и шаг 0: 35 минут стены.
BUDGET_SECONDS = 2100.0

#: Подбор просмотра: удвоение от 2, пока неделёный не стоит 4 с ЦП, затем
#: пересчёт на 60 с и заморозка. Три СВЕЖИХ неделёных шага 0 обязаны в
#: среднем лечь в окно 45–75 с, иначе INCOMPLETE: мерили не то.
BASELINE_TARGET_SECONDS = 60.0
BASELINE_WINDOW_SECONDS = (45.0, 75.0)
PROBE_MIN_SECONDS = 4.0
LOOK_CAP = 4000

#: Шаг 0: три свежих P1 после заморозки просмотра; пробы в них не входят.
STEP0_REPEATS = 3

#: Основной замер: три повтора каждого разбиения.
REPEATS = 3

#: Разброс повторов суммы, max/min: выше — INCONCLUSIVE_NOISE.
NOISE_SPREAD = 1.05

#: Отложенные Q6, H4, C6: относительная ошибка суммы.
HELDOUT_TOLERANCE = 0.05

#: Равномерность, max/min остатков групп после вычета A + ΣB.
#: Контроль (factorial) выше 1.05 — UNRESOLVED_NOISE, зонд не читается.
#: Зонд (cells): <= 1.05 — не обнаружено; 1.05–1.10 — НЕ РЕШЕНО; > 1.10 — KILL.
UNIFORM_CONTROL_SPREAD = 1.05
UNIFORM_NOT_DETECTED = 1.05
UNIFORM_KILL = 1.10

#: Охранник бюджета: F6 на 4000 и на малом просмотре стоил 1.61 неделёного.
GUARD_FACTOR = 1.7

ORDER = ("P1", "P4", "Q6", "H4", "F6", "C6")

#: Позиция КАЖДОГО разбиения (по ORDER) в каждом из трёх раундов. Суммы
#: позиций 7, 7, 7, 8, 8, 8: линейный дрейф машины почти отвязан от типа
#: разбиения. Простой сдвиг +2 давал 6/9.
ROUND_POSITIONS = ((0, 1, 2, 3, 4, 5), (2, 3, 4, 5, 0, 1), (5, 3, 1, 0, 4, 2))

DELTAS = tuple(sorted({k[0] for k in KEYS}))

STATUS_TEXT = {
    "KILL_SPLIT_CHANGED_SCIENCE": "KILL: деление изменило научный результат",
    "INCOMPLETE": "INCOMPLETE: выводов нет",
    "INCONCLUSIVE_NOISE": "INCONCLUSIVE: разброс повторов выше 1.05 — STOP",
    "KILL_NEGATIVE_COST": "KILL: A или ΣB отрицательна",
    "KILL_HELDOUT": "KILL: агрегатная модель не держит отложенные",
    "KILL_UNIFORM_WITHIN_BLOCK": "KILL: ключи внутри блока неравны по horizon/maximise",
    "UNRESOLVED": "НЕ РЕШЕНО: равномерность не разрешена — STOP",
    "PASS": ("PASS: агрегатная форма не опровергнута на малом просмотре; "
             "days НЕ измерена; коэффициенты не переносятся"),
}


# --- разбиения ---------------------------------------------------------------

def ring4() -> tuple:
    """Кольцо: каждый блок 9+9, половины — в две соседние из четырёх групп."""
    b = [block(d) for d in DELTAS]
    half = len(b[0]) // 2
    return tuple(b[j][:half] + b[j - 1][half:] for j in range(len(b)))


def partitions() -> dict[str, tuple]:
    out = {"P1": (tuple(KEYS),),
           "P4": tuple(tuple(g) for g in key_slices(4)),
           "Q6": tuple(tuple(g) for g in key_slices(6)),
           "H4": ring4(),
           "F6": tuple(tuple(g) for g in factorial_partition(6)),
           "C6": tuple(tuple(g) for g in calibrate.cells_partition())}
    return {lbl: out[lbl] for lbl in ORDER}


def presence(slices) -> dict:
    """δ -> в скольких группах он встречается."""
    return {d: sum(1 for g in slices if any(k[0] == d for k in g)) for d in DELTAS}


def day_pairs(slices) -> int:
    """Пары (группа, δ, days): уровень, который модель НЕ видит."""
    return sum(len({(k[0], k[1]) for k in g}) for g in slices)


def shape(slices) -> tuple[int, int]:
    """(g, n) — достаточная статистика модели; n обязан быть общим для δ."""
    n = set(presence(slices).values())
    if len(n) != 1:
        raise ValueError(f"δ встречаются в разном числе групп: {presence(slices)}")
    return len(slices), n.pop()


def rounds() -> tuple[tuple[str, ...], ...]:
    out = []
    for positions in ROUND_POSITIONS:
        order = [None] * len(ORDER)
        for treatment, position in enumerate(positions):
            order[position] = ORDER[treatment]
        out.append(tuple(order))
    return tuple(out)


# --- модель ------------------------------------------------------------------

def fit(totals: dict) -> dict:
    """A из P4, ΣB из F6. Без зажима в ноль: знак — это данные."""
    a = (totals["P4"] - totals["P1"]) / 3
    sb = (totals["F6"] - totals["P1"] - 5 * a) / 5
    return {"A": a, "sumB": sb}


def predict(totals: dict, est: dict) -> dict:
    """Отложенные по модели: C(P) = C(P1) + (g − 1)·A + (n − 1)·ΣB."""
    parts = partitions()
    out = {}
    for lbl in ("Q6", "H4", "C6"):
        g, n = shape(parts[lbl])
        out[lbl] = totals["P1"] + (g - 1) * est["A"] + (n - 1) * est["sumB"]
    return out


def _spread(values) -> float:
    return max(values) / min(values)


def uniformity(groups: dict, est: dict) -> dict:
    """Остатки групп F6 и C6 после вычета общей структурной части A + ΣB."""
    overhead = est["A"] + est["sumB"]
    rf = [t - overhead for t in groups["F6"]]
    rc = [t - overhead for t in groups["C6"]]
    out = {"overhead_per_group": round(overhead, 4),
           "factorial_residuals": [round(x, 4) for x in rf],
           "cells_residuals": [round(x, 4) for x in rc]}
    if min(rf + rc) <= 0:
        out["uniformity_status"] = "UNRESOLVED"
        out["uniformity_reason"] = "остаток <= 0: сравнивать нечего"
        return out
    out["factorial_spread"] = round(_spread(rf), 5)
    out["cells_spread"] = round(_spread(rc), 5)
    if out["factorial_spread"] > UNIFORM_CONTROL_SPREAD:
        out["uniformity_status"] = "UNRESOLVED_NOISE"
    elif out["cells_spread"] <= UNIFORM_NOT_DETECTED:
        out["uniformity_status"] = "HORIZON_MAXIMISE_EFFECT_NOT_DETECTED_DAYS_UNMEASURED"
    elif out["cells_spread"] <= UNIFORM_KILL:
        out["uniformity_status"] = "UNRESOLVED"
    else:
        out["uniformity_status"] = "KILL_UNIFORM_WITHIN_BLOCK"
    return out


# --- вердикт -----------------------------------------------------------------

def step0_gate(runs) -> str | None:
    """None — шаг 0 пройден; иначе статус остановки."""
    if len(runs) < STEP0_REPEATS:
        return "INCOMPLETE"
    totals = [r["C_cpu"] for r in runs]
    lo, hi = BASELINE_WINDOW_SECONDS
    if not lo <= sum(totals) / len(totals) <= hi:
        return "INCOMPLETE"
    if _spread(totals) > NOISE_SPREAD:
        return "INCONCLUSIVE_NOISE"
    return None


def _grouped(runs) -> dict[str, list]:
    by: dict[str, list] = {}
    for run in runs:
        by.setdefault(run["label"], []).append(run)
    return by


def _final(out: dict, status: str) -> dict:
    out["status"] = status
    out["verdict"] = STATUS_TEXT[status]
    if out["model_status"] is None:
        out["model_status"] = status
    return out


def verdict(record: dict) -> dict:
    """Статус машиночитаемый; порядок проверок — их старшинство."""
    out = {"checks": {}, "status": None, "model_status": None,
           "uniformity_status": None, "verdict": None}
    c = out["checks"]
    comparisons = record.get("comparisons", [])
    c["correctness"] = all(x["identical"] for x in comparisons)
    if not c["correctness"]:
        return _final(out, "KILL_SPLIT_CHANGED_SCIENCE")

    s0 = record.get("step0", [])
    c["step0_cpu"] = [r["C_cpu"] for r in s0]
    if len(s0) == STEP0_REPEATS:
        c["step0_mean"] = round(sum(c["step0_cpu"]) / STEP0_REPEATS, 4)
        c["step0_spread"] = round(_spread(c["step0_cpu"]), 5)
    gate = step0_gate(s0)
    c["step0_gate"] = gate or "PASSED"
    if gate is not None:
        return _final(out, gate)

    by = _grouped(record.get("runs", []))
    c["complete"] = (not record.get("incomplete")
                     and all(len(by.get(lbl, ())) == REPEATS for lbl in ORDER))
    if not c["complete"]:
        return _final(out, "INCOMPLETE")
    if len(comparisons) != STEP0_REPEATS - 1 + len(ORDER) * REPEATS:
        return _final(out, "KILL_SPLIT_CHANGED_SCIENCE")

    c["spreads"] = {lbl: round(_spread([r["C_cpu"] for r in by[lbl]]), 5)
                    for lbl in ORDER}
    if max(c["spreads"].values()) > NOISE_SPREAD:
        return _final(out, "INCONCLUSIVE_NOISE")

    totals = {lbl: sum(r["C_cpu"] for r in by[lbl]) / REPEATS for lbl in ORDER}
    groups = {lbl: [sum(r["groups_detail"][j]["cpu_seconds"] for r in by[lbl])
                    / REPEATS for j in range(len(by[lbl][0]["groups_detail"]))]
              for lbl in ("F6", "C6")}
    c["totals"] = {lbl: round(v, 4) for lbl, v in totals.items()}
    est = fit(totals)
    c["A"], c["sumB"] = round(est["A"], 4), round(est["sumB"], 4)
    if est["A"] < 0 or est["sumB"] < 0:
        return _final(out, "KILL_NEGATIVE_COST")

    pred = predict(totals, est)
    c["heldout_predicted"] = {lbl: round(v, 4) for lbl, v in pred.items()}
    c["heldout_errors"] = {lbl: round((pred[lbl] - totals[lbl]) / totals[lbl], 5)
                           for lbl in pred}
    if max(abs(e) for e in c["heldout_errors"].values()) > HELDOUT_TOLERANCE:
        return _final(out, "KILL_HELDOUT")
    out["model_status"] = "PASS"

    u = uniformity(groups, est)
    c.update(u)
    out["uniformity_status"] = u["uniformity_status"]
    if u["uniformity_status"] == "KILL_UNIFORM_WITHIN_BLOCK":
        return _final(out, "KILL_UNIFORM_WITHIN_BLOCK")
    if u["uniformity_status"] in ("UNRESOLVED", "UNRESOLVED_NOISE"):
        return _final(out, "UNRESOLVED")
    return _final(out, "PASS")


# --- исполнение --------------------------------------------------------------

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
    """Весь gate. Изменение науки — отказ; бюджет жёсткий; шаг 0 — стоп-кран."""
    start = clock()
    changed = changes_fn()
    if changed:
        raise ScienceNotFrozen(f"наука отличается от {SCIENCE_SHA}: {changed}")
    arm = arms()[ARM]
    parts = partitions()
    record = {"arm": ARM, "step0": [], "runs": [], "comparisons": [],
              "incomplete": None, "stopped_at_step0": None,
              "rounds": [list(r) for r in rounds()],
              "thresholds": thresholds(),
              "structure": {lbl: {"groups": len(sl), "presence": shape(sl)[1],
                                  "pairs": structure(sl)[1],
                                  "day_pairs": day_pairs(sl)}
                            for lbl, sl in parts.items()},
              "provenance": {"science_sha": SCIENCE_SHA,
                             "python": platform.python_version(),
                             "machine": platform.machine(),
                             "platform": platform.platform()}}
    look, probes = choose_look(arm, measure_fn)
    record["look"], record["probes"] = look, probes
    state = {"baseline": None, "expect": BASELINE_TARGET_SECONDS}

    def one(label: str, where: str, **tags) -> bool:
        elapsed = clock() - start
        need = GUARD_FACTOR * state["expect"]
        if elapsed + need > budget:
            record["incomplete"] = (
                f"{label} {tags} не начат: прошло {elapsed:.0f} с, охранник "
                f"закладывает {need:.0f} с из бюджета {budget:.0f} с")
            return False
        rows, merged = measure_fn(parts[label], arm, look)
        record[where].append({
            "label": label, **tags, "groups_detail": rows,
            "C_cpu": round(sum(r["cpu_seconds"] for r in rows), 4),
            "C_wall": round(sum(r["wall_seconds"] for r in rows), 4)})
        if state["baseline"] is None:
            state["baseline"] = merged
        else:
            cmp = calibrate.compare(state["baseline"], merged, len(rows))
            cmp.update({"label": label, "where": where, **tags})
            record["comparisons"].append(cmp)
            if not cmp["identical"]:
                record["verdict"] = verdict(record)
                _checkpoint(out_path, record)
                raise calibrate.SplitChangedTheScience(
                    f"{label} {tags} изменил результат: {cmp}")
        if clock() - start > budget:
            record["incomplete"] = f"бюджет {budget:.0f} с превышен на {label} {tags}"
            return False
        _checkpoint(out_path, record)
        return True

    for i in range(STEP0_REPEATS):
        if not one("P1", "step0", rep=i):
            break
    gate = step0_gate(record["step0"])
    if gate is not None:
        record["stopped_at_step0"] = gate
    else:
        state["expect"] = sum(r["C_cpu"] for r in record["step0"]) / STEP0_REPEATS
        stop = False
        for r, order in enumerate(rounds()):
            for label in order:
                if not one(label, "runs", round=r):
                    stop = True
                    break
            if stop:
                break
    record["elapsed_seconds"] = round(clock() - start, 1)
    record["verdict"] = verdict(record)
    _checkpoint(out_path, record)
    return record


def thresholds() -> dict:
    return {"budget_seconds": BUDGET_SECONDS,
            "baseline_target_seconds": BASELINE_TARGET_SECONDS,
            "baseline_window_seconds": list(BASELINE_WINDOW_SECONDS),
            "step0_repeats": STEP0_REPEATS, "repeats": REPEATS,
            "noise_spread": NOISE_SPREAD,
            "heldout_tolerance": HELDOUT_TOLERANCE,
            "uniform_control_spread": UNIFORM_CONTROL_SPREAD,
            "uniform_not_detected": UNIFORM_NOT_DETECTED,
            "uniform_kill": UNIFORM_KILL}


# --- обоснование дизайна: расчёт мощности. НЕ evidence. -----------------------
#
# Шум — мультипликативный N(0, σ) на каждый прогон, независимо. σ = 2.4%
# оценена ПОСТФАКТУМ из A-F1: средний модуль разности двух повторов суммы
# 2.72% по девяти разбиениям, σ = 2.72% / 1.128. Истина — доли неделёного из
# Gate A и A-F1: A = 4.6%, каждая B_δ = 1.9%. Альтернатива — скрытый уровень
# (группа, δ, days) с E = B/3; выбрана для иллюстрации ДО замера.

POWER_SEED = 20260927
POWER_N = 20000
POWER_SIGMAS = (0.024, 0.012, 0.006)
POWER_A, POWER_B, POWER_HIDDEN = 0.046, 0.019, 1.0 / 3.0


def _kills_prereg(totals: dict) -> bool:
    est = fit(totals)
    if est["A"] < 0 or est["sumB"] < 0:
        return True
    pred = predict(totals, est)
    return max(abs(pred[k] / totals[k] - 1) for k in pred) > HELDOUT_TOLERANCE


def _kills_old(totals: dict) -> bool:
    """Отвергнутая схема: ΣB из Q6, F6 и H4 отложены."""
    a = (totals["P4"] - totals["P1"]) / 3
    sb = totals["Q6"] - totals["P1"] - 5 * a
    if a < 0 or sb < 0:
        return True
    pred = {"H4": totals["P1"] + 3 * a + sb, "F6": totals["P1"] + 5 * a + 5 * sb}
    pred["C6"] = pred["F6"]
    return max(abs(pred[k] / totals[k] - 1) for k in pred) > HELDOUT_TOLERANCE


def power_rationale(*, seed: int = POWER_SEED, n: int = POWER_N,
                    sigmas=POWER_SIGMAS) -> list[dict]:
    rng = random.Random(seed)
    parts = partitions()
    base_day_pairs = day_pairs(parts["P1"])
    c1 = 60.0
    a, b = POWER_A * c1, POWER_B * c1
    k = c1 - a - len(DELTAS) * b
    rows = []
    for sigma in sigmas:
        for hidden in (0.0, POWER_HIDDEN):
            truth = {}
            for lbl, sl in parts.items():
                g, m = shape(sl)
                extra = day_pairs(sl) - base_day_pairs
                truth[lbl] = g * a + m * len(DELTAS) * b + k + extra * hidden * b
            stopped = passed = kill_new = kill_old = 0
            for _ in range(n):
                s0 = [truth["P1"] * (1 + rng.gauss(0, sigma))
                      for _ in range(STEP0_REPEATS)]
                reps = {lbl: [v * (1 + rng.gauss(0, sigma)) for _ in range(REPEATS)]
                        for lbl, v in truth.items()}
                if (_spread(s0) > NOISE_SPREAD
                        or any(_spread(x) > NOISE_SPREAD for x in reps.values())):
                    stopped += 1
                    continue
                passed += 1
                totals = {lbl: sum(x) / REPEATS for lbl, x in reps.items()}
                kill_new += _kills_prereg(totals)
                kill_old += _kills_old(totals)
            rows.append({"sigma": sigma, "hidden_E_over_B": round(hidden, 4),
                         "inconclusive_noise": round(stopped / n, 4),
                         "kill_given_passed_prereg": round(kill_new / max(passed, 1), 4),
                         "kill_given_passed_old": round(kill_old / max(passed, 1), 4)})
    return rows


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--power":
        print(json.dumps(power_rationale(), ensure_ascii=False, indent=1))
    else:
        rec = run(out_path=sys.argv[1] if len(sys.argv) > 1 else None)
        print(json.dumps(rec["verdict"], ensure_ascii=False, indent=1))
