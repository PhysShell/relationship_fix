"""Локальный гейт многопрогонной ступени. ОДИН запуск, без Actions.

Решение: GO на multi-run packaging 64000, local-only. До production
workflow — ровно один дешёвый локальный гейт на синтетике; не проходит
чисто — KILL многопрогонной стратегии.

СИНТЕТИКА. Ступень 4000 всей сетки, 156 юнитов. `plan --multirun` — тот
же поиск упаковки, что дал 495 заданий на 64000, — здесь даёт 11
заданий; потолок партии 4 -> три номинальные партии 4 / 4 / 3. Счёт —
настоящий `cli run` с подменённым `S.run_unit`: концы детерминированы
научными координатами (рука, ключ, доля, просмотр), смесь достигнутых и
недостигнутых. Наука здесь не проверяется, проверяется механика. Всё
остальное — настоящие `plan`, `select`, `progress`, `reduce`.

«Артефакты» прогона — как их отдаёт воркфлоу: задание, упавшее до
выгрузки, не оставляет ничего; каталог возобновления — части всех
прошлых прогонов плюс манифест первого.

СЦЕНАРИИ

    REF  эталон: один прогон, все 11 заданий того же полного манифеста,
         `reduce` без возобновления.
    A    без падений: прогоны 1, 2, 3.
    B    с падениями: в прогоне 1 первое выбранное задание падает на
         первом же юните и не выгружает ничего; в прогоне 2 первое
         задание текущей партии падает на последнем юните и выгружает
         посчитанное до падения; прогоны 3 и 4 (восстановительный) без
         падений.
    C    неустранимое: один юнит падает в каждом прогоне.

ОБЯЗАТЕЛЬНЫЕ ПРОВЕРКИ — любая неудача = KILL

    R1  A: каждый task_id полного манифеста исполнен ровно один раз, иных
        исполнений нет.
    R2  B: задания, упавшие в прогоне r, выбраны в прогоне r + 1, и в
        выборе каждое повторное идёт раньше любого нового; ни один юнит,
        чья часть выгружена, не исполнен повторно; каждый task_id
        выгружен ровно один раз.
    R3  манифест каждого продолжения (A и B) побайтово равен манифесту
        первого прогона, и `plan` продолжения совпал с ним, спланировав
        ступень заново; контроль: продолжение с изменённым манифестом
        цепочки `plan` отвергает.
    R4  финальное сведение A и B против эталона: `cells` побайтово равны;
        `reduced.json` и `checkpoint.json` побайтово равны после удаления
        ОДНОГО поля `provenance.reused` — оно по построению записывает
        происхождение переиспользованных частей и у эталона пусто.

СОПУТСТВУЮЩИЕ — тоже KILL: «не получается чисто»

    S1  итог прогона: PARTIAL без падений — код 0, не красный; упавшее
        выбранное — код 1; COMPLETE — код 0.
    S2  `reduce` незаконченной ступени отказывает — и без возобновления,
        и с ним.
    S3  C: после восстановительного прогона — STOP с кодом 1; пятый
        прогон `select` отвергает.
    S4  ни один выбор не больше потолка.

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


def one_run(root, name, r, previous, crash_rule=None) -> dict:
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
                           "--batch-cap", str(CAP), "--out", "batch"] + resume,
                          run_dir)
    rec["select_code"], rec["select_why"] = code, why
    if code:
        return rec
    batch = json.loads((run_dir / "batch" / "batch.json").read_text())
    sel = batch["selection"]
    rec["selection"] = {k: sel[k] for k in ("shards", "retries", "batches",
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
    rec["progress"] = {k: report[k] for k in
                       ("status", "ok", "failed_shards", "failed_units",
                        "arrived_units", "remaining_units", "remaining_shards")}
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


def scenario(root, name, crash_rules, max_runs=4) -> list[dict]:
    runs, dirs = [], []
    for r in range(1, max_runs + 1):
        rec = one_run(root, name, r, dirs, crash_rules.get(r))
        runs.append(rec)
        dirs.append(root / name / f"run{r}")
        if rec.get("plan_code") or rec.get("select_code"):
            break
        if rec["progress"]["status"] in ("COMPLETE", "STOP"):
            break
    return runs


def _no_crash(sel, rows):
    return set(), set()


def b_rules():
    def run1(sel, rows):
        first = sel["shards"][0]
        return {rows[first][0]}, set()           # падает сразу, ничего не выгружено

    def run2(sel, rows):
        fresh = [s for s in sel["shards"] if s not in sel["retries"]
                 and len(rows[s]) >= 2][0]
        return {rows[fresh][-1]}, {fresh}         # выгружено до падения
    return {1: run1, 2: run2}


def c_rules(victim):
    def rule(sel, rows):
        for s, ids in rows.items():
            if victim in ids:
                return {victim}, set()
        return set(), set()
    return {r: rule for r in range(1, 5)}


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
    evidence: dict = {"look": LOOK, "cap": CAP,
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

        STUB.log.clear()
        a = scenario(root, "A", {})
        log_a = [t for w, t in STUB.log if w.startswith("A")]
        STUB.log.clear()
        b = scenario(root, "B", b_rules())
        log_b = [(w, t) for w, t in STUB.log if w.startswith("B")]
        STUB.log.clear()
        victim = ids[0]
        c = scenario(root, "C", c_rules(victim))
        fifth = one_run(root, "C", 5, [root / "C" / f"run{r}"
                                       for r in range(1, 5)])
        tamper = tampered_continuation(root, root / "A" / "run1")
        evidence["A"], evidence["B"], evidence["C"] = a, b, c
        evidence["C_fifth_run"] = fifth
        evidence["R3_control"] = tamper

        # R1
        counts = {t: log_a.count(t) for t in set(log_a)}
        checks["R1 A: каждый task_id исполнен ровно один раз"] = (
            sorted(counts) == ids and set(counts.values()) == {1})
        evidence["R1"] = {"executions": len(log_a), "distinct": len(counts)}

        # R2
        uploaded_b = [u for rec in b for j in rec["jobs"] for u in j["uploaded"]]
        retry_ok, uploaded_before = True, set()
        recomputed = []
        for i, rec in enumerate(b):
            label = f"B{rec['run']}"
            ran = [t for w, t in log_b if w == label]
            recomputed += sorted(set(ran) & uploaded_before)
            if i:
                failed = set(b[i - 1]["progress"]["failed_shards"])
                shards = rec["selection"]["shards"]
                retries = rec["selection"]["retries"]
                if not failed <= set(retries):
                    retry_ok = False
                cut = [shards.index(s) for s in shards if s not in retries]
                if cut and any(shards.index(s) > min(cut) for s in retries):
                    retry_ok = False
            uploaded_before |= {u for j in rec["jobs"] for u in j["uploaded"]}
        once = (sorted(uploaded_b) == ids)
        checks["R2 B: упавшее повторено первым, выгруженное не пересчитано, "
               "каждый выгружен ровно один раз"] = (
            retry_ok and not recomputed and once
            and bool(b[0]["progress"]["failed_shards"])
            and bool(b[1]["progress"]["failed_shards"]))
        evidence["R2"] = {"retry_priority": retry_ok,
                          "recomputed_after_upload": recomputed,
                          "uploaded": len(uploaded_b),
                          "executions": len(log_b),
                          "failed_by_run": [rec["progress"]["failed_shards"]
                                            for rec in b]}

        # R3
        first = {"A": a[0]["manifest_sha256"], "B": b[0]["manifest_sha256"]}
        same = all(rec.get("plan_code") == 0
                   and rec.get("manifest_sha256") == first[n]
                   for n, runs in (("A", a), ("B", b)) for rec in runs)
        checks["R3 манифест продолжений побайтово равен первому; "
               "чужой отвергнут"] = (
            same and first["A"] == first["B"] == ref["manifest_sha256"]
            and tamper["code"] != 0
            and "спланирована иначе" in tamper["why"])
        evidence["R3"] = {"first": first, "reference": ref["manifest_sha256"],
                          "runs_A": [r.get("manifest_sha256") for r in a],
                          "runs_B": [r.get("manifest_sha256") for r in b]}

        # R4
        cmp_a = compare_to_reference(ref["dir"], root / "A" / f"run{len(a)}")
        cmp_b = compare_to_reference(ref["dir"], root / "B" / f"run{len(b)}")
        evidence["R4"] = {"A": cmp_a, "B": cmp_b}

        def r4(c):
            return (c["cells_bytes_equal"]
                    and c["reduced.json_equal_without_reused"]
                    and c["checkpoint.json_equal_without_reused"]
                    and c["reduced.json_reused_ref"] == {}
                    and c["checkpoint.json_reused_ref"] == {}
                    and bool(c["reduced.json_reused_got"])
                    and c["ledger_digest"][0] == c["ledger_digest"][1]
                    and c["output_digest"][0] == c["output_digest"][1])
        checks["R4 сведение A и B = эталон (без поля reused — побайтово)"] = (
            a[-1].get("reduce_code") == 0 and b[-1].get("reduce_code") == 0
            and r4(cmp_a) and r4(cmp_b))

        # S1
        s1 = (
            [r["progress"]["status"] for r in a] == ["PARTIAL", "PARTIAL",
                                                      "COMPLETE"]
            and [r["progress_code"] for r in a] == [0, 0, 0]
            and [r["progress_code"] for r in b][:2] == [1, 1]
            and all(r["progress_code"] == 0 for r in b[2:])
            and b[-1]["progress"]["status"] == "COMPLETE" and len(b) == 4)
        checks["S1 PARTIAL без падений зелёный, падение красное"] = s1

        # S2
        partial = [r for r in a + b if r["progress"]["status"] != "COMPLETE"]
        checks["S2 сведение незаконченной ступени отказывает"] = (
            bool(partial)
            and all(r.get("partial_reduce_code", 0) != 0 for r in partial)
            and any(r["run"] == 1 for r in partial)
            and any(r["run"] > 1 for r in partial))

        # S3
        checks["S3 C: STOP после восстановительного, пятый отвергнут"] = (
            len(c) == 4 and c[-1]["progress"]["status"] == "STOP"
            and c[-1]["progress_code"] == 1
            and fifth.get("select_code") == 1
            and "STOP" in fifth.get("select_why", ""))

        # S4
        checks["S4 ни один выбор не больше потолка"] = all(
            len(r["selection"]["shards"]) <= CAP
            for r in a + b + c if "selection" in r)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
