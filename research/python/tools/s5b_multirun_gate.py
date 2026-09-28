"""Локальный гейт многопрогонной ступени, v2. ОДИН запуск, без Actions.

v1 (коммит ed00d4f) проверял правило «не больше 165 за прогон» — PASS.
Правило заменено решением: повторы идут СВЕРХ номинальной партии, до
потолка матрицы. v2 проверяет новое правило и три регрессии к нему.

ПРАВИЛО. Номинальный прогон r (1..3) обязан продвинуть свою партию r
целиком — ни одно её задание прежде не запускалось; сверх неё — до
«матрица − партия» повторов (на 64000 256 − 165 = 91): заданий прошлых
партий, чей результат отсутствует или неполон, потому что задание упало;
не влезшие ждут дальше. Прогон 4 — единственный восстановительный: только
повторы, не больше матрицы; больше перед ним или остаток после него —
STOP, пятого нет. Выполненный юнит не пересчитывается. Приехавшая, но не
принятая часть — KILL, а не повтор.

СИНТЕТИКА. Ступень 4000 всей сетки, 156 юнитов; `plan --multirun` даёт 11
заданий; партия 4, матрица 6 — место для повторов 2, масштабный аналог
91. Счёт — настоящий `cli run` с подменённым `S.run_unit`; остальное —
настоящие `plan`, `select`, `progress`, `reduce`. Задание, упавшее до
выгрузки, не оставляет ничего; каталог возобновления — части всех
прошлых прогонов плюс манифест первого.

СЦЕНАРИИ
    REF  эталон: один прогон всех 11 заданий, `reduce` без возобновления.
    A    без падений: прогоны 1-3.
    B    падений не больше места: в прогоне 1 первое выбранное задание
         падает на первом юните, второе — на последнем и выгружает
         посчитанное; в прогоне 2 падает первое номинальное задание.
    D    падений больше места: в прогоне 1 падают три задания из четырёх,
         в прогоне 2 — два первых номинальных.
    K1   в прогоне 1 выгруженная часть подменена: содержимое не сходится с
         отпечатком.
    K2   в прогоне 1 выгруженная часть несёт чужие ключи при честном
         отпечатке — identity не та.
    C    неустранимое: один юнит падает в каждом прогоне.
    E    переполнение: в прогонах 1-3 падают все выбранные задания.

ПРОВЕРКИ — любая неудача = KILL
    R1  A: каждый task_id полного манифеста исполнен ровно раз.
    R2  B и D: номинальный прогон берёт свою партию целиком, и ни одно её
        задание прежде не запускалось; повторы — только из упавшего или
        неполного, идут раньше новых, не больше места; выгруженный юнит не
        исполнен повторно; каждый task_id выгружен ровно раз.
    R3  манифест всех продолжений побайтово равен первому и эталону;
        продолжение с изменённым манифестом цепочки `plan` отвергает.
    R4  сведение A, B и D против эталона: `cells` побайтово равны;
        `reduced.json` и `checkpoint.json` побайтово равны после удаления
        одного поля `provenance.reused`.
    N1  B: падения не больше места закрываются в номинальных прогонах —
        ступень COMPLETE в прогоне 3, четвёртого нет.
    N2  D: больше места — остаток переносится: перенесено после прогонов
        2 и 3 ровно по одному; восстановительный прогон 4 — только
        повторы, COMPLETE.
    N3  K1 и K2: итог прогона 1 — KILL с кодом 1, упавших заданий в нём
        нет, то есть в повторы ничего не встало; `select` прогона 2
        отказывает с KILL.
    S1  коды итогов: A 0,0,0; B 1,1,0; D 1,1,0,0.
    S2  `reduce` незаконченной ступени отказывает.
    S3  C: STOP после восстановительного, код 1, пятый прогон отвергнут;
        E: STOP уже в прогоне 3, код 1, `select` прогона 4 отвергает.
    S4  каждый выбор не больше матрицы.

Запуск: `python3 -B tools/s5b_multirun_gate.py <файл вердикта>`.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import platform
import shutil
import sys
import tempfile
import time
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
for extra in (ROOT / "research" / "python", ROOT / "execution"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from simulation import s5b_escalation as E                     # noqa: E402
from simulation import s5b_precision as PRC                    # noqa: E402
from simulation import s5b_shard as S                          # noqa: E402

from s5b_execution import cli                                  # noqa: E402
from s5b_execution.scheduler import FRACTIONS                  # noqa: E402

LOOK = 4000
CAP = 4
MATRIX = 6
ENV = {"SCIENCE_SHA": "a" * 40, "EXECUTION_SHA": "b" * 40,
       "REQUEST_SHA": "c" * 40}


class Crash(Exception):
    """Задание упало посреди счёта."""


class Stub:
    """Подменённый `run_unit`: журнал исполнений и назначенные падения."""

    def __init__(self):
        self.log: list[tuple[str, str]] = []
        self.where = ""
        self.crash: set[str] = set()

    def __call__(self, unit, **arm):
        self.log.append((self.where, unit.task_id))
        if unit.task_id in self.crash:
            raise Crash(unit.task_id)
        out = {}
        for key in unit.keys:
            for f in FRACTIONS:
                h = int(hashlib.sha256(
                    f"{unit.arm}|{list(key)}|{f}|{unit.look}".encode()
                ).hexdigest()[:8], 16)
                achieved = h % 5 != 0
                point = 100.0 + (h % 1000) / 10.0
                out[(tuple(key), f)] = E.Endpoint(
                    key=tuple(key), delta_fraction=f, point=point,
                    low=point - 1.0, high=point + 1.0, radius=1.0,
                    status=(PRC.PrecisionStatus.ACHIEVED if achieved
                            else PRC.PrecisionStatus.INSUFFICIENT),
                    look=unit.look if achieved else None)
        return out


STUB = Stub()


def call(argv, cwd) -> tuple[int, str, str]:
    """`cli.main` как процесс: код выхода, stdout, причина отказа."""
    buf, why = io.StringIO(), ""
    here = os.getcwd()
    os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(buf):
            code = cli.main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        why = "" if isinstance(exc.code, int) else str(exc.code)
    except Exception as exc:                     # noqa: BLE001
        # необработанное исключение процесса — код 1, как у интерпретатора
        code, why = 1, f"{type(exc).__name__}: {exc}"
    finally:
        os.chdir(here)
    return code, buf.getvalue(), why


def sha(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def parts_of(directory) -> list[pathlib.Path]:
    return sorted(p for p in pathlib.Path(directory).glob("*.json")
                  if p.name not in ("manifest.json", "reduced.json",
                                    "checkpoint.json"))


def compute(run_dir, manifest, shard, label, *, keep_partial=False) -> dict:
    """Одно задание матрицы. Выгрузка — только при успехе, если не сказано иное."""
    work = run_dir / f"work-{shard}"
    STUB.where = label
    code, _, why = call(["run", "--look", str(LOOK), "--manifest", manifest,
                         "--shard", str(shard), "--out", str(work)], run_dir)
    uploaded = []
    if code == 0 or keep_partial:
        dest = run_dir / "artifacts" / f"shard-{shard}"
        dest.mkdir(parents=True, exist_ok=True)
        for p in parts_of(work):
            shutil.copy(p, dest / p.name)
            uploaded.append(p.stem)
    return {"shard": shard, "code": code, "why": why, "uploaded": uploaded}


def reference(root) -> dict:
    run_dir = root / "REF"
    run_dir.mkdir(parents=True)
    code, out, why = call(["plan", "--look", str(LOOK), "--multirun",
                           "--out", "plan"], run_dir)
    assert code == 0, why
    shards = json.loads(out.strip().splitlines()[-1])["count"]
    for s in range(shards):
        got = compute(run_dir, "plan/manifest.json", s, "REF")
        assert got["code"] == 0, got
    target = run_dir / "out"
    target.mkdir()
    for p in (run_dir / "artifacts").rglob("*.json"):
        shutil.copy(p, target / p.name)
    shutil.copy(run_dir / "plan" / "manifest.json", target / "manifest.json")
    code, _, why = call(["reduce", "--look", str(LOOK), "--out", "out"],
                        run_dir)
    assert code == 0, why
    return {"dir": run_dir, "shards": shards,
            "manifest_sha256": sha(run_dir / "plan" / "manifest.json")}


def one_run(root, name, r, previous, crash_rule=None, after=None) -> dict:
    """Прогон r сценария: скачать цепочку, plan, select, счёт, итог, сведение."""
    run_dir = root / name / f"run{r}"
    run_dir.mkdir(parents=True)
    resume = []
    if previous:
        res = run_dir / "resumed"
        res.mkdir()
        for prev in previous:
            for p in (prev / "artifacts").rglob("*.json"):
                shutil.copy(p, res / p.name)
        shutil.copy(previous[0] / "plan" / "manifest.json",
                    res / "manifest.json")
        resume = ["--resume", "resumed"]
    rec = {"run": r}
    code, out, why = call(["plan", "--look", str(LOOK), "--multirun",
                           "--out", "plan"] + resume, run_dir)
    rec["plan_code"], rec["plan_why"] = code, why
    if code:
        return rec
    rec["manifest_sha256"] = sha(run_dir / "plan" / "manifest.json")
    code, out, why = call(["select", "--look", str(LOOK), "--manifest",
                           "plan/manifest.json", "--run", str(r),
                           "--batch-cap", str(CAP), "--run-matrix",
                           str(MATRIX), "--out", "batch"] + resume,
                          run_dir)
    rec["select_code"], rec["select_why"] = code, why
    if code:
        return rec
    batch = json.loads((run_dir / "batch" / "batch.json").read_text())
    sel = batch["selection"]
    rec["selection"] = {k: sel[k] for k in ("shards", "retries", "nominal",
                                            "carried", "batches",
                                            "pending_shards_before")}
    rec["selection"]["units"] = len(sel["units"])
    rows = {s: sorted(u["task_id"] for u in batch["units"] if u["shard"] == s)
            for s in sel["shards"]}
    crash, partial = (crash_rule(sel, rows) if crash_rule else (set(), set()))
    STUB.crash = crash
    rec["jobs"] = [compute(run_dir, "batch/batch.json", s, f"{name}{r}",
                           keep_partial=s in partial)
                   for s in sel["shards"]]
    STUB.crash = set()
    if after:
        rec["tampered"] = after(run_dir, sel, rows)
    target = run_dir / "out"
    target.mkdir()
    art = run_dir / "artifacts"
    if art.exists():
        for p in art.rglob("*.json"):
            shutil.copy(p, target / p.name)
    shutil.copy(run_dir / "plan" / "manifest.json", target / "manifest.json")
    code, out, why = call(["progress", "--look", str(LOOK), "--parts", "out",
                           "--batch", "batch/batch.json", "--out", "report"]
                          + resume, run_dir)
    rec["progress_code"], rec["progress_why"] = code, why
    if not (run_dir / "report" / "progress.json").exists():
        raise RuntimeError(f"{name} прогон {r}: итога нет — {why}")
    report = json.loads((run_dir / "report" / "progress.json").read_text())
    rec["progress"] = {k: report.get(k) for k in
                       ("status", "ok", "failed_shards", "failed_units",
                        "arrived_units", "remaining_units", "remaining_shards",
                        "reason")}
    if report["status"] == "KILL":
        return rec
    if report["status"] == "COMPLETE":
        code, _, why = call(["reduce", "--look", str(LOOK), "--out", "out"]
                            + resume, run_dir)
        rec["reduce_code"], rec["reduce_why"] = code, why
    else:
        # S2: сведение незаконченной ступени обязано отказать. На КОПИИ:
        # сведение с возобновлением дописывает части в свой каталог.
        probe = run_dir / "probe"
        shutil.copytree(target, probe / "out")
        if previous:
            shutil.copytree(run_dir / "resumed", probe / "resumed")
        code, _, why = call(["reduce", "--look", str(LOOK), "--out", "out"]
                            + resume, probe)
        rec["partial_reduce_code"], rec["partial_reduce_why"] = code, why[:200]
    return rec


def scenario(root, name, crash_rules, max_runs=4, after=None) -> list[dict]:
    runs, dirs = [], []
    for r in range(1, max_runs + 1):
        rec = one_run(root, name, r, dirs, crash_rules.get(r),
                      (after or {}).get(r))
        runs.append(rec)
        dirs.append(root / name / f"run{r}")
        if rec.get("plan_code") or rec.get("select_code"):
            break
        if rec["progress"]["status"] in ("COMPLETE", "STOP", "KILL"):
            break
    return runs


def _fresh(sel):
    return [s for s in sel["shards"] if s not in sel["retries"]]


def b_rules():
    def run1(sel, rows):
        first, second = sel["shards"][:2]
        return {rows[first][0], rows[second][-1]}, {second}

    def run2(sel, rows):
        first = _fresh(sel)[0]
        return {rows[first][0]}, set()
    return {1: run1, 2: run2}


def d_rules():
    def run1(sel, rows):
        return {rows[s][0] for s in sel["shards"][:3]}, set()

    def run2(sel, rows):
        return {rows[s][0] for s in _fresh(sel)[:2]}, set()
    return {1: run1, 2: run2}


def c_rules(victim):
    def rule(sel, rows):
        for s, ids in rows.items():
            if victim in ids:
                return {victim}, set()
        return set(), set()
    return {r: rule for r in range(1, 5)}


def e_rules():
    def rule(sel, rows):
        return {ids[0] for ids in rows.values()}, set()
    return {r: rule for r in range(1, 4)}


def _one_part(run_dir, sel):
    shard = sel["shards"][0]
    return sorted((run_dir / "artifacts" / f"shard-{shard}").glob("*.json"))[0]


def tamper_content(run_dir, sel, rows):
    """K1: содержимое части подменено, отпечаток оставлен прежним."""
    path = _one_part(run_dir, sel)
    data = json.loads(path.read_text())
    data["endpoints"][0]["point"] += 1.0
    path.write_text(json.dumps(data, sort_keys=True))
    return path.stem


def tamper_identity(run_dir, sel, rows):
    """K2: часть несёт чужие ключи, отпечаток пересчитан честно."""
    from s5b_execution.identity import recompute_digest
    path = _one_part(run_dir, sel)
    data = json.loads(path.read_text())
    data["keys"] = data["keys"][:-1]
    data["endpoints"] = [e for e in data["endpoints"]
                         if e["key"] in data["keys"]]
    data["digest"] = recompute_digest(data)
    path.write_text(json.dumps(data, sort_keys=True))
    return path.stem


def stripped(path) -> str:
    data = json.loads(pathlib.Path(path).read_text())
    prov = (data["summary"]["provenance"] if "summary" in data
            else data["provenance"])
    reused = prov.pop("reused", None)
    return json.dumps(data, sort_keys=True), reused


def compare_to_reference(ref_dir, got_dir) -> dict:
    out = {}
    a = json.loads((ref_dir / "out" / "reduced.json").read_text())
    b = json.loads((got_dir / "out" / "reduced.json").read_text())
    out["cells_bytes_equal"] = (json.dumps(a["cells"], sort_keys=True)
                                == json.dumps(b["cells"], sort_keys=True))
    out["cells"] = len(a["cells"])
    out["cells_evaluable"] = a["summary"]["cells_evaluable"]
    for name in ("reduced.json", "checkpoint.json"):
        ra, reused_a = stripped(ref_dir / "out" / name)
        rb, reused_b = stripped(got_dir / "out" / name)
        out[f"{name}_equal_without_reused"] = ra == rb
        out[f"{name}_raw_equal"] = (
            (ref_dir / "out" / name).read_bytes()
            == (got_dir / "out" / name).read_bytes())
        out[f"{name}_reused_ref"] = reused_a
        out[f"{name}_reused_got"] = reused_b
    out["ledger_digest"] = [a["summary"]["ledger_digest"],
                            b["summary"]["ledger_digest"]]
    out["output_digest"] = [a["summary"]["provenance"]["output_digest"],
                            b["summary"]["provenance"]["output_digest"]]
    return out


def tampered_continuation(root, first_run_dir) -> dict:
    """Контроль R3: продолжение с чужим манифестом цепочки."""
    run_dir = root / "TAMPER"
    res = run_dir / "resumed"
    res.mkdir(parents=True)
    for p in (first_run_dir / "artifacts").rglob("*.json"):
        shutil.copy(p, res / p.name)
    m = json.loads((first_run_dir / "plan" / "manifest.json").read_text())
    m["shard_seconds"][0] += 1.0                 # тот же состав, другой вес
    (res / "manifest.json").write_text(json.dumps(m, sort_keys=True))
    code, _, why = call(["plan", "--look", str(LOOK), "--multirun", "--out",
                         "plan", "--resume", "resumed"], run_dir)
    return {"code": code, "why": why[:200]}


def main(target) -> int:
    started = time.time()
    checks: dict[str, bool] = {}
    evidence: dict = {"look": LOOK, "cap": CAP, "matrix": MATRIX,
                      "python": platform.python_version()}
    try:
        _gate(checks, evidence)
    except Exception:                                # noqa: BLE001
        import traceback
        evidence["error"] = traceback.format_exc()
        checks["гейт дошёл до конца"] = False
    evidence["checks"] = checks
    evidence["verdict"] = ("PASS" if checks and all(checks.values())
                           else "KILL")
    evidence["seconds"] = round(time.time() - started, 1)
    pathlib.Path(target).write_text(json.dumps(
        evidence, sort_keys=True, ensure_ascii=False, indent=1))
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if "error" in evidence:
        print(evidence["error"])
    print(evidence["verdict"])
    return 0 if evidence["verdict"] == "PASS" else 1


def _attempted_before(runs, i):
    return {s for rec in runs[:i] for s in rec.get("selection", {})
            .get("shards", [])}


def _r2(runs, log, name):
    """Номинальная партия целиком и впервые; повторы — упавшее, первыми,
    не больше места; выгруженное не исполнено повторно."""
    ok, recomputed, uploaded_before = True, [], set()
    room = MATRIX - CAP
    for i, rec in enumerate(runs):
        sel = rec["selection"]
        plan = sel["batches"]
        if rec["run"] <= 3:
            ok &= sel["nominal"] == (plan[rec["run"] - 1]
                                     if rec["run"] <= len(plan) else [])
            ok &= not set(sel["nominal"]) & _attempted_before(runs, i)
            ok &= len(sel["retries"]) <= room
        else:
            ok &= sel["nominal"] == []
        ok &= set(sel["retries"]) <= _attempted_before(runs, i)
        ok &= sel["shards"] == sel["retries"] + sel["nominal"]
        if i:
            owed = set(runs[i - 1]["progress"]["remaining_shards"]) \
                & _attempted_before(runs, i)
            ok &= set(sel["retries"]) <= owed
            ok &= len(sel["retries"]) + sel["carried"] == len(owed)
        ran = [t for w, t in log if w == f"{name}{rec['run']}"]
        recomputed += sorted(set(ran) & uploaded_before)
        uploaded_before |= {u for j in rec["jobs"] for u in j["uploaded"]}
    uploaded = [u for rec in runs for j in rec["jobs"] for u in j["uploaded"]]
    return ok, recomputed, uploaded


def _gate(checks, evidence) -> None:
    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.dict(os.environ, ENV), \
            mock.patch.object(S, "run_unit", STUB):
        root = pathlib.Path(tmp)
        ref = reference(root)
        manifest = json.loads(
            (ref["dir"] / "plan" / "manifest.json").read_text())
        ids = sorted(r["task_id"] for r in manifest["units"])
        evidence["reference"] = {"shards": ref["shards"], "units": len(ids),
                                 "shard_seconds": manifest["shard_seconds"],
                                 "manifest_sha256": ref["manifest_sha256"]}
        logs = {}
        runs = {}
        for name, rules, after in (
                ("A", {}, None), ("B", b_rules(), None),
                ("D", d_rules(), None),
                ("K1", {}, {1: tamper_content}),
                ("K2", {}, {1: tamper_identity}),
                ("C", c_rules(ids[0]), None), ("E", e_rules(), None)):
            STUB.log.clear()
            runs[name] = scenario(root, name, rules, after=after)
            logs[name] = [(w, t) for w, t in STUB.log if w.startswith(name)]
            evidence[name] = runs[name]
        a, b, d, c, e = (runs[k] for k in "ABDCE")
        k_next = {k: one_run(root, k, 2, [root / k / "run1"])
                  for k in ("K1", "K2")}
        fifth = one_run(root, "C", 5, [root / "C" / f"run{r}"
                                       for r in range(1, 5)])
        e_fourth = one_run(root, "E", 4, [root / "E" / f"run{r}"
                                          for r in range(1, 4)])
        tamper = tampered_continuation(root, root / "A" / "run1")
        evidence["K_next_select"] = k_next
        evidence["C_fifth_run"] = fifth
        evidence["E_fourth_run"] = e_fourth
        evidence["R3_control"] = tamper

        # R1
        log_a = [t for _, t in logs["A"]]
        counts = {t: log_a.count(t) for t in set(log_a)}
        checks["R1 A: каждый task_id исполнен ровно раз"] = (
            sorted(counts) == ids and set(counts.values()) == {1})
        evidence["R1"] = {"executions": len(log_a), "distinct": len(counts)}

        # R2
        r2 = {}
        for name, runs_of in (("B", b), ("D", d)):
            ok, recomputed, uploaded = _r2(runs_of, logs[name], name)
            r2[name] = {"rule": ok, "recomputed_after_upload": recomputed,
                        "uploaded": len(uploaded),
                        "uploaded_once": sorted(uploaded) == ids,
                        "executions": len(logs[name]),
                        "failed_by_run": [x["progress"]["failed_shards"]
                                          for x in runs_of]}
        evidence["R2"] = r2
        checks["R2 B и D: партия целиком и впервые, повторы — упавшее, "
               "первыми, в пределах места; выгруженное не пересчитано"] = all(
            v["rule"] and not v["recomputed_after_upload"]
            and v["uploaded_once"] and any(v["failed_by_run"])
            for v in r2.values())

        # R3
        first = {k: runs[k][0]["manifest_sha256"] for k in "ABD"}
        same = all(rec.get("plan_code") == 0
                   and rec.get("manifest_sha256") == first[k]
                   for k in "ABD" for rec in runs[k])
        checks["R3 манифест продолжений побайтово равен первому; "
               "чужой отвергнут"] = (
            same and set(first.values()) == {ref["manifest_sha256"]}
            and tamper["code"] != 0 and "спланирована иначе" in tamper["why"])
        evidence["R3"] = {"first": first, "reference": ref["manifest_sha256"],
                          "runs": {k: [r.get("manifest_sha256")
                                       for r in runs[k]] for k in "ABD"}}

        # R4
        cmp = {k: compare_to_reference(ref["dir"],
                                       root / k / f"run{len(runs[k])}")
               for k in "ABD"}
        evidence["R4"] = cmp

        def r4(c):
            return (c["cells_bytes_equal"]
                    and c["reduced.json_equal_without_reused"]
                    and c["checkpoint.json_equal_without_reused"]
                    and c["reduced.json_reused_ref"] == {}
                    and c["checkpoint.json_reused_ref"] == {}
                    and bool(c["reduced.json_reused_got"])
                    and c["ledger_digest"][0] == c["ledger_digest"][1]
                    and c["output_digest"][0] == c["output_digest"][1])
        checks["R4 сведение A, B, D = эталон (без поля reused — "
               "побайтово)"] = all(
            runs[k][-1].get("reduce_code") == 0 and r4(cmp[k]) for k in "ABD")

        # N1
        checks["N1 B: падения в пределах места закрыты номинальными "
               "прогонами, четвёртого нет"] = (
            len(b) == 3 and b[-1]["progress"]["status"] == "COMPLETE"
            and sum(len(x["progress"]["failed_shards"]) for x in b[:1])
            == MATRIX - CAP)

        # N2
        checks["N2 D: сверх места остаток перенесён, восстановительный — "
               "только повторы"] = (
            len(d) == 4 and d[-1]["progress"]["status"] == "COMPLETE"
            and [x["selection"]["carried"] for x in d] == [0, 1, 1, 0]
            and d[-1]["selection"]["nominal"] == []
            and set(d[-1]["selection"]["shards"])
            <= _attempted_before(d, 3))

        # N3
        n3 = True
        for k in ("K1", "K2"):
            first_run = runs[k][0]
            n3 &= (len(runs[k]) == 1
                   and first_run["progress"]["status"] == "KILL"
                   and first_run["progress_code"] == 1
                   and not first_run["progress"]["failed_shards"]
                   and "не принята" in (first_run["progress"]["reason"]
                                         or "")
                   and k_next[k].get("select_code") == 1
                   and "KILL" in k_next[k].get("select_why", ""))
        checks["N3 K1 и K2: приехавшее, но не принятое — KILL, не повтор"] = n3

        # S1
        codes = {k: [x["progress_code"] for x in runs[k]] for k in "ABD"}
        evidence["S1"] = codes
        checks["S1 коды итогов: PARTIAL зелёный, падение красное"] = (
            codes == {"A": [0, 0, 0], "B": [1, 1, 0], "D": [1, 1, 0, 0]}
            and [x["progress"]["status"] for x in a]
            == ["PARTIAL", "PARTIAL", "COMPLETE"])

        # S2
        partial = [x for k in "ABD" for x in runs[k]
                   if x["progress"]["status"] != "COMPLETE"]
        checks["S2 сведение незаконченной ступени отказывает"] = (
            bool(partial)
            and all(x.get("partial_reduce_code", 0) != 0 for x in partial)
            and any(x["run"] == 1 for x in partial)
            and any(x["run"] > 1 for x in partial))

        # S3
        checks["S3 STOP: после восстановительного и до него; пятого нет"] = (
            len(c) == 4 and c[-1]["progress"]["status"] == "STOP"
            and c[-1]["progress_code"] == 1
            and fifth.get("select_code") == 1
            and "STOP" in fifth.get("select_why", "")
            and len(e) == 3 and e[-1]["progress"]["status"] == "STOP"
            and e[-1]["progress_code"] == 1
            and e_fourth.get("select_code") == 1
            and "STOP" in e_fourth.get("select_why", ""))

        # S4
        checks["S4 ни один выбор не больше матрицы"] = all(
            len(x["selection"]["shards"]) <= MATRIX
            for k in runs for x in runs[k] if "selection" in x)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
