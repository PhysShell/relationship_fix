"""Командная оболочка слоя исполнения.

    plan    --look L [--prior D ...]   манифест ступени с учётом реестра
    run     --look L --shard N         посчитать свой мешок замороженным run_unit
    reduce  --look L --prior D ...     свести концы, каждый на своём tau

`reduce` — не «слияние ради полноты». Он строит реестр по ВОСХОДЯЩИМ
ступеням и отдаёт каждый конец на его собственном `tau`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import resource
import sys
import time

from simulation import s5b_prereg as P
from simulation import s5b_shard as S

from . import cost, guard, provenance, reduction, resume, scheduler
from .identity import load_unit_payloads
from .ledger import Ledger

LOOKS = tuple(P.LOOKS) if hasattr(P, "LOOKS") else None


def _ladder():
    from simulation import s5b_precision as PRC
    return tuple(PRC.LOOKS)


def _expected_units(directory, look: int):
    """Юниты, ОБЪЯВЛЕННЫЕ манифестом ступени.

    Читается манифест, а не приехавшие файлы. Вывести ожидаемое из
    полученного значило бы сделать проверку полноты тавтологией: она бы
    проходила всегда, ровно потому что сравнивает набор сам с собой.
    """
    path = pathlib.Path(directory) / "manifest.json"
    if not path.exists():
        raise SystemExit(f"{directory}: нет manifest.json — объявить нечего")
    manifest = json.loads(path.read_text())
    if manifest["look"] != look:
        raise SystemExit(f"{directory}: манифест на ступень {manifest['look']}, "
                         f"а файлы на {look}")
    return [S.Unit(arm=u["arm"], look=u["look"],
                   keys=tuple(tuple(k) for k in u["keys"]), weight=0.0)
            for u in manifest["units"]]


def _verify_arms(directory, payloads, scheduled: set[str]) -> None:
    """Три РАЗНЫХ множества рук, и их нельзя сливать.

        canonical  вся сетка замороженной науки — что вообще существует;
        scheduled  что объявил манифест ЭТОЙ ступени;
        arrived    что реально приехало.

    Требование `arrived == canonical` было верно ровно до тех пор, пока
    лестница считала всю сетку на каждой ступени. После остановки это
    неверно: рука, все концы которой закрылись, законно не планируется
    дальше, и её отсутствие — правильная работа реестра, а не пропажа.

    Проверяется поэтому: `arrived == scheduled` (ничего не потеряно и
    ничего лишнего) и `scheduled` подмножество `canonical` (ничего
    выдуманного). Каноническое множество берётся из ЗАМОРОЖЕННОЙ науки и
    остаётся утверждением, независимым от манифеста.
    """
    canonical = {a["tag"] for a in S.production_arms()}
    stray = sorted(scheduled - canonical)
    if stray:
        raise SystemExit(
            f"{directory}: манифест запланировал руки вне сетки замороженной "
            f"науки: {stray[:3]}")
    arrived = {p["arm"] for p in payloads}
    if arrived != scheduled:
        raise SystemExit(
            f"{directory}: приехавшие руки не совпали с запланированными; "
            f"нет {sorted(scheduled - arrived)[:3]}, лишние "
            f"{sorted(arrived - scheduled)[:3]}")


def _verify_with_frozen_merge(directory, look: int, payloads) -> int:
    """Собрать концы КАЖДОЙ руки замороженным `s5b_shard.merge`.

    Зовётся на ВСЕХ ступенях, а не только там, где рука дробится. На 4000
    и 16000 у руки одна группа ключей и слияние тривиально — но именно
    «тривиальный и потому не исполняемый путь» уронил прогон 35805206374:
    шаг merge был единственным, который до того не отрабатывал ни разу.
    """
    expected = _expected_units(directory, look)
    unit_of = {u.task_id: u for u in expected}
    _verify_arms(directory, payloads, {u.arm for u in expected})
    missing = [p["task_id"] for p in payloads if p["task_id"] not in unit_of]
    if missing:
        raise SystemExit(f"{directory}: файлы вне манифеста: {missing}")
    for arm in sorted({u.arm for u in expected}):
        reduction.merge_arm(arm, look, payloads, expected, unit_of)
    return len(expected)


def _prior_state(args) -> tuple[Ledger | None, dict]:
    """Состояние прошлых ступеней: из ЧЕКПОЙНТА либо из сырых частей.

    Чекпойнт предпочтительнее и на 64000 обязателен: сырые части 16000 не
    содержат концов, остановившихся на 4000, поэтому собрать из них
    полный реестр нельзя в принципе.
    """
    if args.checkpoint:
        data = json.loads(pathlib.Path(args.checkpoint).read_text())
        led = Ledger.from_checkpoint(data)
        return led, {args.checkpoint: data.get("ledger_digest", "")}
    if args.prior:
        return _ledger_from(args.prior, args.prior_digest)
    return None, {}


def _ledger_from(prior_dirs, expected_digest: str = "") -> tuple[Ledger, dict]:
    """Реестр по каталогам ступеней, впитанным ПО ВОЗРАСТАНИЮ.

    `expected_digest` относится к САМОЙ РАННЕЙ ступени набора. `prior_run`
    якорем не является: `task_id` кодирует научные координаты, а не байты
    реализации, поэтому совместимый чужой прогон даст ровно те же имена
    файлов. Отпечаток — единственное, что привязывает вход к конкретному
    вычислению.
    """
    ledger, inputs, loaded = Ledger(), {}, []
    for directory in prior_dirs:
        payloads = load_unit_payloads(directory)
        looks = {p["look"] for p in payloads}
        if len(looks) != 1:
            raise SystemExit(f"{directory}: смешаны ступени {sorted(looks)}")
        loaded.append((looks.pop(), payloads, directory))
    for index, (look, payloads, directory) in enumerate(
            sorted(loaded, key=lambda t: t[0])):
        _verify_with_frozen_merge(directory, look, payloads)
        got = provenance.digest_of(payloads)
        if index == 0 and expected_digest and got != expected_digest:
            raise SystemExit(
                f"{directory}: отпечаток входа {got}, заявлен "
                f"{expected_digest} — приехал не тот прогон")
        ledger.absorb(look, payloads)
        inputs[str(directory)] = got
    return ledger, inputs


def _encode(results) -> list:
    return [{"key": list(name[0]), "fraction": name[1],
             "point": e.point, "low": e.low, "high": e.high,
             "radius": e.radius, "status": e.status.value, "look": e.look}
            for name, e in sorted(results.items(), key=repr)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "run", "reduce"))
    parser.add_argument("--look", type=int, required=True)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--out", default="out")
    parser.add_argument("--prior", action="append", default=[])
    parser.add_argument("--manifest", default="manifest.json")
    parser.add_argument("--prior-digest", default="")
    parser.add_argument("--prior-run", default="")
    parser.add_argument("--repo", default="")
    parser.add_argument("--pin", default="")
    parser.add_argument("--workflow", default="")
    parser.add_argument("--workflow-sha256", default="")
    parser.add_argument("--science", default="")
    parser.add_argument("--resume", default="",
                        help="каталог частей прерванного прогона ЭТОЙ ступени")
    parser.add_argument("--checkpoint", default="",
                        help="чекпойнт реестра предыдущей ступени")
    args = parser.parse_args(argv)
    out = pathlib.Path(args.out)

    if args.mode == "plan":
        # PREFLIGHT. Порядок не косметический: всё, что может обрушиться
        # дёшево, обязано обрушиться ДО появления дорогой матрицы.
        # Отдельная дымовая проба проверяла бы почти то же самое и
        # добавляла бы ещё один церемониальный труп в историю проекта.
        checks: dict = {}
        if args.workflow and args.workflow_sha256:
            checks["workflow_sha256"] = guard.assert_workflow_matches(
                args.workflow, args.workflow_sha256)
        if args.repo and args.pin:
            head = os.environ.get("REQUEST_SHA", "HEAD")
            guard.assert_object_exists(args.repo, args.pin)
            guard.assert_is_ancestor(args.repo, args.pin, head)
            science = os.environ.get("EXECUTION_SHA", "")
            if science:
                guard.assert_object_exists(args.repo, science)
                guard.assert_pin_descends_from(args.repo, science, args.pin)
            changed = guard.changed_paths(args.repo, args.pin, head)
            guard.assert_request_is_only_a_signal(changed)
            checks["pin"] = args.pin
            checks["changed_since_pin"] = changed
        if args.science:
            checks["science_modules"] = guard.assert_science_comes_from(
                args.science)
        ledger, inputs = _prior_state(args)
        done: set[str] = set()
        if args.resume:
            got = resume.completed(args.resume, look=args.look,
                                   science_sha=os.environ.get("SCIENCE_SHA", ""))
            done = set(got)
            checks["reused_task_ids"] = len(done)
        units = scheduler.units_for(args.look, ledger, skip=done)
        if not units:
            raise SystemExit(
                f"все юниты ступени {args.look} уже посчитаны прошлым "
                f"прогоном: считать нечего, сразу reduce")
        count = scheduler.shards_needed(units)
        buckets = S.assign(units, count)
        scheduler.check_platform(buckets)
        # РАСКЛАДКА ПИШЕТСЯ В МАНИФЕСТ, а не выводится заново в `run`.
        # Пусть план и исполнение расходятся невозможным образом, а не
        # «одинаково считают»: сегодняшний отказ прогона был ровно из
        # расхождения двух мест, которые обязаны были совпасть.
        rows = []
        for shard, bucket in enumerate(buckets):
            for unit in bucket:
                rows.append({"task_id": unit.task_id, "arm": unit.arm,
                             "look": unit.look, "shard": shard,
                             "keys": [list(k) for k in unit.keys]})
        rows.sort(key=lambda r: r["task_id"])
        manifest = {"look": args.look, "shards": count, "units": rows}
        body = json.dumps(manifest, sort_keys=True)
        record = provenance.collect(
            inputs=inputs,
            manifest_digest=hashlib.sha256(body.encode()).hexdigest()[:16])
        record["look"] = args.look
        record["prior_run"] = args.prior_run
        record["prior_digest"] = args.prior_digest
        record["preflight"] = checks
        manifest["provenance"] = record
        # каждая строка манифеста обязана ДАВАТЬ свой task_id
        for row in rows:
            rebuilt = S.Unit(arm=row["arm"], look=row["look"],
                             keys=tuple(tuple(k) for k in row["keys"]),
                             weight=0.0)
            if rebuilt.task_id != row["task_id"]:
                raise SystemExit(f"манифест: {row['task_id']} не выводится "
                                 f"из состава юнита")
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        print(json.dumps({"shards": list(range(count)), "count": count,
                          "units": len(rows),
                          "carried": 0 if ledger is None
                          else ledger.settled_count()}))
        return 0

    if args.mode == "run":
        manifest = json.loads(
            pathlib.Path(args.manifest).read_text())
        if manifest["look"] != args.look:
            raise SystemExit(f"манифест на ступень {manifest['look']}, "
                             f"запрошена {args.look}")
        mine = [u for u in manifest["units"] if u["shard"] == args.shard]
        if not mine:
            raise SystemExit(f"в манифесте нет юнитов шарда {args.shard}")
        known = scheduler.arms()
        out.mkdir(parents=True, exist_ok=True)
        for row in mine:
            unit = S.Unit(arm=row["arm"], look=row["look"],
                          keys=tuple(tuple(k) for k in row["keys"]),
                          weight=0.0)
            if unit.task_id != row["task_id"]:
                raise SystemExit(
                    f"манифест объявил {row['task_id']}, а состав юнита даёт "
                    f"{unit.task_id}: происхождение нарушено")
            arm = known[unit.arm]
            started = time.perf_counter()
            results = S.run_unit(unit, rate=arm["rate"], c_rate=arm["c_rate"],
                                 c_shift=arm["c_shift"], regime=arm["regime"],
                                 magnitude=arm["magnitude"])
            payload = {"task_id": unit.task_id, "arm": unit.arm,
                       "look": unit.look,
                       "keys": [list(k) for k in unit.keys],
                       "endpoints": _encode(results)}
            payload["digest"] = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
            payload["seconds"] = round(time.perf_counter() - started, 1)
            payload["peak_rss_mb"] = round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
            (out / f"{unit.task_id}.json").write_text(
                json.dumps(payload, sort_keys=True))
            print(f"{unit.task_id} {unit.arm} {payload['seconds']}s "
                  f"{payload['digest']}", flush=True)
        return 0

    # reduce
    if args.science:
        guard.assert_science_comes_from(args.science)
    if args.resume:
        reused = resume.completed(args.resume, look=args.look,
                                  science_sha=os.environ.get("SCIENCE_SHA", ""))
        fresh = {p["task_id"]: p for p in load_unit_payloads(out)}
        merged = resume.merge_parts(reused, fresh)
        for tid, payload in reused.items():
            (out / f"{tid}.json").write_text(json.dumps(payload, sort_keys=True))
        print(f"переиспользовано {len(reused)}, посчитано заново {len(fresh)}, "
              f"всего {len(merged)}")
    if args.checkpoint:
        ledger = Ledger.from_checkpoint(
            json.loads(pathlib.Path(args.checkpoint).read_text()))
        payloads = load_unit_payloads(out)
        _verify_with_frozen_merge(out, args.look, payloads)
        ledger.absorb(args.look, payloads)
        inputs = {str(out): provenance.digest_of(payloads)}
    else:
        ledger, inputs = _ledger_from(list(args.prior) + [out],
                                      args.prior_digest)
    final = ledger.finalise(args.look)
    cells = reduction.cells_from(final)
    evaluable = sum(1 for c in cells if c["evaluable"])
    summary = {
        "look": args.look,
        "looks_absorbed": list(ledger.looks_absorbed),
        "endpoints_seen": ledger.seen_count(),
        "endpoints_settled": ledger.settled_count(),
        "ignored_because_already_settled": ledger.ignored_because_already_settled,
        "ledger_digest": ledger.digest(),
        "cells": len(cells), "cells_evaluable": evaluable,
        "inputs": inputs,
    }
    # Отпечаток ВЫХОДА берётся от НАУЧНОГО результата: ячейки и реестр.
    #
    # Прежде он считался от всей сводки, а та несёт `inputs`, ключами
    # которых служат ПУТИ каталогов. Тот же результат, собранный из другого
    # каталога, давал другой отпечаток — и «частичный + возобновление»
    # расходился с непрерывным прогоном при побайтово одинаковой науке.
    # Отпечаток, меняющийся от переноса каталога, отпечатком результата не
    # является.
    body = json.dumps({"cells": cells,
                       "ledger_digest": summary["ledger_digest"],
                       "endpoints_settled": summary["endpoints_settled"]},
                      sort_keys=True)
    summary["provenance"] = {
        "science_sha": os.environ.get("SCIENCE_SHA", ""),
        "execution_sha": os.environ.get("EXECUTION_SHA", ""),
        "request_sha": os.environ.get("REQUEST_SHA", ""),
        "look": args.look,
        "prior_run": args.prior_run,
        "prior_digest": args.prior_digest,
        "input_digest": provenance.digest_of(
            load_unit_payloads(out)),
        "output_digest": hashlib.sha256(body.encode()).hexdigest()[:16],
    }
    (out / "reduced.json").write_text(json.dumps(
        {"summary": summary, "cells": cells}, sort_keys=True))
    # ЧЕКПОЙНТ: без него следующая ступень не восстановит ранние tau
    (out / "checkpoint.json").write_text(json.dumps(
        ledger.to_checkpoint(
            canonical_arms={a["tag"] for a in S.production_arms()},
            provenance=summary["provenance"]), sort_keys=True))
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
