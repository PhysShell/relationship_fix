"""Исполнение этапа 1: план, юнит, слияние, дымовая проба.

Тонкая обёртка над `s5b_shard` и `s5b_escalation`. Науки здесь нет —
только ввод-вывод и то, что нужно GitHub Actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import resource
import sys
import time

from simulation import s5b_escalation as E
from simulation import s5b_precision as PR
from simulation import s5b_shard as S


def _arms():
    return {a["tag"]: a for a in S.production_arms()}


def _units(look: int):
    arms = _arms()
    return [u for u in S.plan([(a["tag"], a["effective_rate"])
                               for a in arms.values()])
            if u.look == look]


def _encode(results) -> list:
    return [{"key": list(name[0]), "fraction": name[1],
             "point": e.point, "low": e.low, "high": e.high,
             "radius": e.radius, "status": e.status.value, "look": e.look}
            for name, e in sorted(results.items(), key=repr)]


def _run(unit, arm) -> dict:
    started = time.perf_counter()
    results = S.run_unit(unit, rate=arm["rate"], c_rate=arm["c_rate"],
                         c_shift=arm["c_shift"], regime=arm["regime"],
                         magnitude=arm["magnitude"])
    payload = {"task_id": unit.task_id, "arm": unit.arm, "look": unit.look,
               "keys": [list(k) for k in unit.keys],
               "endpoints": _encode(results)}
    payload["digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    payload["seconds"] = round(time.perf_counter() - started, 1)
    payload["peak_rss_mb"] = round(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "run", "merge", "smoke"))
    parser.add_argument("--look", type=int, default=PR.LOOKS[0])
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--out", default="out")
    args = parser.parse_args(argv)
    out = pathlib.Path(args.out)

    if args.mode == "plan":
        units = _units(args.look)
        shards = S.shards_needed(units)
        S.check_platform_limits(S.assign(units, shards))
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps(
            {"look": args.look, "shards": shards,
             "units": [{"task_id": u.task_id, "arm": u.arm, "look": u.look,
                        "keys": [list(k) for k in u.keys]} for u in units]},
            sort_keys=True))
        print(json.dumps({"shards": list(range(shards)), "count": shards,
                          "units": len(units)}))
        return 0

    if args.mode == "run":
        units = _units(args.look)
        bucket = S.assign(units, S.shards_needed(units))[args.shard]
        arms = _arms()
        out.mkdir(parents=True, exist_ok=True)
        for unit in bucket:
            payload = _run(unit, arms[unit.arm])
            (out / f"{unit.task_id}.json").write_text(
                json.dumps(payload, sort_keys=True))
            print(f"{unit.task_id} {unit.arm} {payload['seconds']}s "
                  f"{payload['digest']}", flush=True)
        return 0

    if args.mode == "smoke":
        arms = S.production_arms()
        worst = max(arms, key=lambda a: a["effective_rate"])
        unit = max((u for u in _units(PR.LOOKS[-1]) if u.arm == worst["tag"]),
                   key=lambda u: u.weight)
        payload = _run(unit, worst)
        payload["budget_hours"] = S.SHARD_BUDGET_HOURS
        payload["platform_cap_hours"] = S.GITHUB_JOB_MAX_HOURS
        payload["predicted_hours"] = round(unit.weight / 3600, 2)
        out.mkdir(parents=True, exist_ok=True)
        (out / "smoke.json").write_text(json.dumps(payload, sort_keys=True))
        print(json.dumps({k: v for k, v in payload.items()
                          if k != "endpoints"}, indent=1))
        return 0

    manifest = json.loads((out / "manifest.json").read_text())
    declared = {u["task_id"] for u in manifest["units"]}
    seen = {}
    for path in sorted(out.glob("*.json")):
        if path.name == "manifest.json":
            continue
        payload = json.loads(path.read_text())
        seen[payload["task_id"]] = payload
    missing = sorted(declared - set(seen))
    extra = sorted(set(seen) - declared)
    if missing or extra:
        print(f"СЛИЯНИЕ ОТКАЗАНО: не хватает {missing}, лишние {extra}",
              file=sys.stderr)
        return 1
    print(json.dumps({"look": manifest["look"], "units": len(seen),
                      "digest": hashlib.sha256(json.dumps(
                          sorted(p["digest"] for p in seen.values())
                      ).encode()).hexdigest()[:16]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
