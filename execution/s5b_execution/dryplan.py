"""Сухой план полного 64000 при balanced-g12. ЛОКАЛЬНО, без Actions.

Пилот квалифицировал размер ОДНОГО юнита (худший — 8835.4 с), но не всю
ступень. Этот план отвечает на вопрос «платформа это вообще проглотит?»:
сколько юнитов реально нужно после реестра 16000, сколько заданий даёт
LPT, влезает ли это в матрицу и в таймаут при стрессе.

Вес юнита — намеренно простая эмпирическая огибающая, без модели
деления:

    W(rate) = 8835.4 с x seconds_for(rate, 64000) / seconds_for(120, 64000)

Якорь — фактический худший юнит пилота (рука со ставкой 120, блок δ = 60).
δ = 60 считается худшим случаем для всех групп: дешёвые блоки завышены
сознательно. От прежней модели остаётся только форма зависимости от
эффективной ставки.

Жёсткие STOP, без дальнейших исследований:
    не упаковать в <= 256 заданий при бюджете 2.5 ч;
    хоть одно задание при стрессе x1.96 длиннее 350 мин;
    план не сохраняет раскладку balanced-g12, identities юнитов или
    семантику реестра.
Makespan порогом не является: он выводится для решения о бюджете проекта.
"""

from __future__ import annotations

import json
import math

from simulation import s5b_shard as S

from . import cost, scheduler
from .identity import EndpointId
from .layout import balanced_slices
from .scheduler import FRACTIONS, KEYS

#: Модуль ничего не планирует для исполнения и планировщиком не импортируется.
NOT_WIRED_INTO_THE_PLANNER = True

LOOK = 64000
GROUPS = 12
ANCHOR_SECONDS = 8835.4        # худший юнит пилота 36332456884
ANCHOR_RATE = 120.0            # его рука r96.0:c1.25:R0:m1.0
STRESS = 1.96                  # худший наблюдавшийся разброс раннеров
HARD_TIMEOUT_MINUTES = 350.0   # timeout-minutes заданий


def weight(rate: float) -> float:
    return (ANCHOR_SECONDS * cost.seconds_for(rate, LOOK)
            / cost.seconds_for(ANCHOR_RATE, LOOK))


def units(ledger) -> tuple[list, int]:
    """Нужные юниты и сколько их было всего. Семантика — `units_for`."""
    out, possible = [], 0
    for tag, arm in scheduler.arms().items():
        for keys in balanced_slices(GROUPS):
            possible += 1
            if ledger.unit_is_needed(tag, keys, FRACTIONS):
                out.append(S.Unit(arm=tag, look=LOOK, keys=tuple(keys),
                                  weight=weight(arm["effective_rate"])))
    return out, possible


def identity_problems(needed, ledger) -> list[str]:
    """Третий STOP: раскладка, identities и семантика реестра."""
    problems = []
    allowed = {tuple(s) for s in balanced_slices(GROUPS)}
    for u in needed:
        if tuple(u.keys) not in allowed:
            problems.append(f"{u.task_id}: ключи не из balanced-g12")
        rebuilt = S.Unit(arm=u.arm, look=u.look, keys=tuple(u.keys), weight=0.0)
        if rebuilt.task_id != u.task_id:
            problems.append(f"{u.task_id}: task_id не выводится из состава")
    if len({u.task_id for u in needed}) != len(needed):
        problems.append("task_id повторяются")
    # каждый ещё открытый конец обязан попасть в какой-то нужный юнит
    covered = {(u.arm, tuple(k)) for u in needed for k in u.keys}
    for tag in scheduler.arms():
        for k in KEYS:
            if (tag, tuple(k)) in covered:
                continue
            if not all(ledger.is_settled(EndpointId(tag, tuple(k), f))
                       for f in FRACTIONS):
                problems.append(f"{tag} {k}: открытый конец не покрыт")
    return problems


def plan(ledger) -> dict:
    budget = cost.SHARD_BUDGET_HOURS * 3600.0
    needed, possible = units(ledger)
    out = {"look": LOOK, "groups": GROUPS, "anchor_seconds": ANCHOR_SECONDS,
           "anchor_rate": ANCHOR_RATE, "stress": STRESS,
           "units_possible": possible, "units_needed": len(needed),
           "matrix_max_jobs": S.GITHUB_MATRIX_MAX_JOBS,
           "max_parallel": cost.MAX_PARALLEL,
           "budget_hours": cost.SHARD_BUDGET_HOURS,
           "hard_timeout_hours": HARD_TIMEOUT_MINUTES / 60.0}
    weights = [u.weight for u in needed]
    total = sum(weights)
    out["unit_hours_min"] = round(min(weights) / 3600, 3)
    out["unit_hours_max"] = round(max(weights) / 3600, 3)
    out["total_cpu_hours"] = round(total / 3600, 1)
    heavy = sum(1 for w in weights if w > budget / 2)
    out["units_heavier_than_half_budget"] = heavy
    out["jobs_lower_bound"] = max(math.ceil(total / budget), heavy)
    jobs, buckets = None, None
    for count in range(out["jobs_lower_bound"], len(needed) + 1):
        trial = S.assign(needed, count)
        if max(sum(u.weight for u in b) for b in trial) <= budget:
            jobs, buckets = count, trial
            break
    out["jobs_lpt"] = jobs
    sizes = [sum(u.weight for u in b) for b in buckets]
    out["heaviest_job_hours"] = round(max(sizes) / 3600, 3)
    out["heaviest_job_stress_hours"] = round(max(sizes) * STRESS / 3600, 3)
    span = scheduler.makespan(buckets, cost.MAX_PARALLEL)
    out["makespan_hours"] = round(span / 3600, 1)
    out["makespan_stress_hours"] = round(span * STRESS / 3600, 1)
    problems = identity_problems(needed, ledger)
    out["identity_problems"] = problems[:10]

    stops = []
    if jobs > S.GITHUB_MATRIX_MAX_JOBS:
        stops.append(f"{jobs} заданий при бюджете {cost.SHARD_BUDGET_HOURS} ч "
                     f"против потолка матрицы {S.GITHUB_MATRIX_MAX_JOBS}")
    if max(sizes) * STRESS > HARD_TIMEOUT_MINUTES * 60.0:
        stops.append("задание при стрессе длиннее таймаута")
    if problems:
        stops.append("план не сохраняет раскладку, identities или реестр")
    out["stops"] = stops
    out["status"] = "STOP" if stops else "PASS"
    return out


if __name__ == "__main__":
    import sys
    from .ledger import Ledger
    ledger = Ledger.from_checkpoint(json.loads(open(sys.argv[1]).read()))
    result = plan(ledger)
    result["ledger_digest"] = ledger.digest()
    print(json.dumps(result, ensure_ascii=False, indent=1))
