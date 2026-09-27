"""Ступень в несколько прогонов: один полный манифест, партии, остаток.

Потолок 256 заданий — это матрица ОДНОГО прогона воркфлоу, а не серии
прогонов. Сухой план полного 64000 упаковал 1872 юнита в 495 заданий и
остановился ровно на этом потолке: убита гипотеза «одним прогоном», а не
ступень.

Механика:

    первый прогон планирует ОДИН полный манифест всех заданий; юниты,
        `task_id` и состав заданий от партий не зависят;
    задания раскладываются по партиям LPT второго уровня с потолком
        `BATCH_CAP` заданий на партию — чтобы суммы CPU партий были
        близки, а не «первые 165, следующие 165»;
    каждый прогон берёт не больше `BATCH_CAP` ещё не выполненных заданий
        в порядке партий, поэтому упавшее раньше идёт первым;
    продолжение получает цепочку прошлых прогонов, планирует ступень
        заново и обязано получить ТОТ ЖЕ манифест — иначе отказ;
    научное сведение — только когда остаток пуст; промежуточный прогон
        кончается отчётом о ходе, а не частичной наукой;
    `NOMINAL_RUNS` номинальных прогонов и `RECOVERY_RUNS`
        восстановительный; не закрыл ступень — STOP.

Партия — исполнительное понятие. В `task_id` и в манифест она не входит:
раскладка по партиям выводится из манифеста детерминированно, заново в
каждом прогоне, и потому одинакова во всех.
"""

from __future__ import annotations

import hashlib
import json
import math

from simulation import s5b_shard as S

from . import cost, dryplan, scheduler

#: Потолок заданий одного прогона. 495 / 3 = 165 ровно; до потолка
#: матрицы 256 остаётся запас.
BATCH_CAP = 165

#: Номинальные прогоны и один восстановительный. Воркфлоу принимает не
#: больше трёх прошлых прогонов, поэтому четвёртый — последний возможный.
NOMINAL_RUNS = 3
RECOVERY_RUNS = 1
MAX_RUNS = NOMINAL_RUNS + RECOVERY_RUNS
MAX_PREVIOUS_RUNS = MAX_RUNS - 1

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
STOP = "STOP"

#: Партии задают только порядок исполнения замороженных юнитов
BATCHES_ARE_EXECUTION_ONLY = True


class MultiRunRefused(Exception):
    """Шаг многопрогонной ступени не выполняется: вход не тот, что объявлен."""


def units(look: int, ledger):
    """Юниты полного манифеста.

    На 64000 — ровно юниты сухого плана: сбалансированная раскладка g = 12,
    вес — его огибающая от худшего юнита пилота, фильтр — реестр 16000.
    Третий STOP сухого плана (раскладка, identities, семантика реестра)
    остаётся отказом и здесь. Иначе — `units_for`, как у лестницы.
    """
    if look == dryplan.LOOK:
        if ledger is None:
            raise MultiRunRefused(
                f"{look} планируется только от чекпойнта прошлой ступени")
        needed, _ = dryplan.units(ledger)
        problems = dryplan.identity_problems(needed, ledger)
        if problems:
            raise MultiRunRefused(
                f"план не сохраняет раскладку, identities или реестр: "
                f"{problems[:3]}")
        return needed
    return scheduler.units_for(look, ledger)


def pack(units, budget_seconds: float):
    """Наименьшее число заданий, при котором каждое укладывается в бюджет.

    Тот же поиск, что у сухого плана: от нижней границы вверх, раскладка —
    замороженный LPT `s5b_shard.assign`. Потолка матрицы здесь нет: его
    держит партия, а не манифест.
    """
    if not units:
        raise MultiRunRefused("юнитов нет: считать нечего")
    weights = [u.weight for u in units]
    if max(weights) > budget_seconds:
        raise MultiRunRefused(
            f"юнит весом {max(weights) / 3600:.2f} ч не влезает в бюджет "
            f"{budget_seconds / 3600:.2f} ч и неделим")
    lower = max(1, math.ceil(sum(weights) / budget_seconds),
                sum(1 for w in weights if w > budget_seconds / 2))
    for count in range(lower, len(units) + 1):
        trial = S.assign(units, count)
        if max(sum(u.weight for u in b) for b in trial) <= budget_seconds:
            return trial
    raise MultiRunRefused("юниты не раскладываются даже по одному")


def check_jobs(buckets) -> None:
    """Каждое задание ниже платформенного потолка."""
    for index, bucket in enumerate(buckets):
        total = sum(u.weight for u in bucket)
        if not cost.fits_platform(total):
            raise MultiRunRefused(
                f"задание {index}: {total / 3600:.2f} ч против потолка "
                f"{cost.PLATFORM_CAP_HOURS:.2f} ч")


def body(manifest: dict) -> dict:
    """Манифест без провенанса: то, что обязано совпадать во всех прогонах."""
    return {k: v for k, v in manifest.items() if k != "provenance"}


def body_digest(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(
        body(manifest), sort_keys=True).encode()).hexdigest()[:16]


def batches(shard_seconds, cap: int) -> tuple[tuple[int, ...], ...]:
    """LPT второго уровня: задания по партиям, не больше `cap` в каждой.

    Задания — по убыванию веса, каждое в наименее загруженную НЕПОЛНУЮ
    партию. Партий ровно `ceil(N / cap)`. Внутри партии задания идут
    тяжёлыми вперёд; полные партии — раньше неполных, чтобы прогон без
    падений брал ровно одну партию.
    """
    if not 1 <= cap <= S.GITHUB_MATRIX_MAX_JOBS:
        raise MultiRunRefused(
            f"потолок партии {cap} вне 1..{S.GITHUB_MATRIX_MAX_JOBS}")
    n = len(shard_seconds)
    if not n:
        raise MultiRunRefused("заданий нет")
    count = -(-n // cap)
    members: list[list[int]] = [[] for _ in range(count)]
    load = [0.0] * count
    for shard in sorted(range(n), key=lambda i: (-shard_seconds[i], i)):
        target = min((b for b in range(count) if len(members[b]) < cap),
                     key=lambda b: (load[b], b))
        members[target].append(shard)
        load[target] += shard_seconds[shard]
    order = sorted(range(count), key=lambda b: (-len(members[b]), b))
    return tuple(tuple(members[b]) for b in order)


def check(manifest: dict) -> dict[int, list[dict]]:
    """Строки полного манифеста по заданиям. Проверяются, а не принимаются."""
    n = manifest.get("shards")
    seconds = manifest.get("shard_seconds")
    if not isinstance(n, int) or n < 1:
        raise MultiRunRefused(f"число заданий {n!r}")
    if seconds is None or len(seconds) != n:
        raise MultiRunRefused(
            "манифест не многопрогонный: нет веса каждого задания")
    by_shard: dict[int, list[dict]] = {s: [] for s in range(n)}
    seen = set()
    for row in manifest["units"]:
        tid = row["task_id"]
        if tid in seen:
            raise MultiRunRefused(f"манифест объявил {tid} дважды")
        seen.add(tid)
        if row["shard"] not in by_shard:
            raise MultiRunRefused(f"{tid}: задание {row['shard']} вне 0..{n - 1}")
        rebuilt = S.Unit(arm=row["arm"], look=row["look"],
                         keys=tuple(tuple(k) for k in row["keys"]), weight=0.0)
        if rebuilt.task_id != tid:
            raise MultiRunRefused(f"{tid}: состав юнита даёт {rebuilt.task_id}")
        by_shard[row["shard"]].append(row)
    empty = [s for s, rows in by_shard.items() if not rows]
    if empty:
        raise MultiRunRefused(f"пустые задания: {empty[:3]}")
    return by_shard


def select(manifest: dict, done: set[str], *, run: int,
           cap: int = BATCH_CAP) -> dict:
    """Задания этого прогона: не больше `cap` ещё не выполненных.

    Порядок — партия за партией, внутри партии тяжёлые вперёд. Всё, что
    осталось от прошлых партий (упавшее или не влезшее), поэтому идёт
    раньше текущей партии. Задание берётся, если в нём есть хоть один
    не выполненный юнит, и исполняются ТОЛЬКО такие юниты: выполненное не
    считается повторно ни при каком исходе.
    """
    if not 1 <= run <= MAX_RUNS:
        raise MultiRunRefused(
            f"STOP: прогон {run} — допустимы 1..{MAX_RUNS} "
            f"({NOMINAL_RUNS} номинальных и {RECOVERY_RUNS} восстановительный)")
    by_shard = check(manifest)
    declared = {r["task_id"] for rows in by_shard.values() for r in rows}
    stray = sorted(done - declared)
    if stray:
        raise MultiRunRefused(f"выполненные юниты вне манифеста: {stray[:3]}")
    plan = batches(manifest["shard_seconds"], cap)
    if len(plan) > NOMINAL_RUNS:
        raise MultiRunRefused(
            f"{len(plan)} партий при потолке {cap}: в {NOMINAL_RUNS} "
            f"номинальных прогона ступень не укладывается")
    batch_of = {s: b for b, members in enumerate(plan) for s in members}
    order = [s for members in plan for s in members]
    pending = [s for s in order
               if any(r["task_id"] not in done for r in by_shard[s])]
    if not pending:
        raise MultiRunRefused("остатка нет: считать нечего, сразу сведение")
    if run == MAX_RUNS and len(pending) > cap:
        raise MultiRunRefused(
            f"STOP: восстановительный прогон не закроет ступень — осталось "
            f"{len(pending)} заданий при потолке {cap}")
    chosen = pending[:cap]
    units = sorted(r["task_id"] for s in chosen for r in by_shard[s]
                   if r["task_id"] not in done)
    return {"run": run, "cap": cap,
            "manifest_digest": body_digest(manifest),
            "batches": [list(b) for b in plan],
            "shards": chosen,
            "retries": [s for s in chosen if batch_of[s] < run - 1],
            "units": units,
            "done_before": len(done),
            "pending_units_before": len(declared) - len(done),
            "pending_shards_before": len(pending)}


def batch_manifest(manifest: dict, selection: dict) -> dict:
    """Строки выбранных заданий, дословно из полного манифеста.

    Номер задания — тот же, что в полном манифесте. `run` читает этот файл
    так же, как полный, и исполняет только перечисленные юниты.
    """
    by_shard = check(manifest)
    if selection["manifest_digest"] != body_digest(manifest):
        raise MultiRunRefused("выбор сделан по другому манифесту")
    wanted = set(selection["units"])
    rows = [r for s in selection["shards"] for r in by_shard[s]
            if r["task_id"] in wanted]
    if {r["task_id"] for r in rows} != wanted:
        raise MultiRunRefused("выбор объявил юниты вне своих заданий")
    return {"look": manifest["look"], "shards": manifest["shards"],
            "units": sorted(rows, key=lambda r: r["task_id"]),
            "selection": selection}


def progress(manifest: dict, selection: dict, done_before: set[str],
             arrived: set[str]) -> dict:
    """Итог прогона: сколько сделано, что упало, что осталось.

    Не наука: реестр и ячейки здесь не строятся. Незаконченная ступень —
    PARTIAL, и это не ошибка; ошибка — упавшее выбранное задание.
    Посчитанное повторно или невыбранное — отказ.
    """
    by_shard = check(manifest)
    if selection["manifest_digest"] != body_digest(manifest):
        raise MultiRunRefused("выбор сделан по другому манифесту")
    shard_of = {r["task_id"]: s for s, rows in by_shard.items() for r in rows}
    declared = set(shard_of)
    chosen = set(selection["units"])
    if chosen & done_before:
        raise MultiRunRefused(
            "выбор включает уже выполненное: цепочка не та, по которой выбирали")
    again = sorted(arrived & done_before)
    if again:
        raise MultiRunRefused(
            f"{len(again)} юнитов посчитаны повторно: {again[:3]}")
    stray = sorted(arrived - chosen)
    if stray:
        raise MultiRunRefused(f"приехали невыбранные юниты: {stray[:3]}")
    failed = chosen - arrived
    remaining = declared - done_before - arrived
    run = selection["run"]
    if not remaining:
        status = COMPLETE
    elif run >= MAX_RUNS:
        status = STOP
    else:
        status = PARTIAL
    return {"run": run, "status": status,
            "ok": not failed and status != STOP,
            "manifest_digest": selection["manifest_digest"],
            "units_total": len(declared),
            "selected_shards": list(selection["shards"]),
            "selected_units": len(chosen),
            "arrived_units": len(arrived),
            "failed_units": sorted(failed),
            "failed_shards": sorted({shard_of[t] for t in failed}),
            "done_units": len(done_before | arrived),
            "remaining_units": len(remaining),
            "remaining_shards": sorted({shard_of[t] for t in remaining})}
