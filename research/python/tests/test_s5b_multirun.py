"""Гейты многопрогонной ступени: партии, выбор, итог прогона.

Сквозной сценарий через CLI — это локальный гейт
`tools/s5b_multirun_gate.py`; здесь — его части по отдельности.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "execution") not in sys.path:
    sys.path.insert(0, str(ROOT / "execution"))

from simulation import s5b_shard as S                                # noqa: E402

from s5b_execution import cost, multirun as M, scheduler             # noqa: E402

BUDGET = cost.SHARD_BUDGET_HOURS * 3600.0


def _manifest(look=4000):
    units = scheduler.units_for(look)
    buckets = M.pack(units, BUDGET)
    rows = sorted(({"task_id": u.task_id, "arm": u.arm, "look": u.look,
                    "shard": s, "keys": [list(k) for k in u.keys]}
                   for s, b in enumerate(buckets) for u in b),
                  key=lambda r: r["task_id"])
    return {"look": look, "shards": len(buckets), "units": rows,
            "shard_seconds": [round(sum(u.weight for u in b), 1)
                              for b in buckets]}


def _ids(manifest, shards):
    return {r["task_id"] for r in manifest["units"] if r["shard"] in shards}


class TheFullPackingTests(unittest.TestCase):

    def test_the_synthetic_stage_packs_into_eleven_jobs(self):
        m = _manifest()
        self.assertEqual((m["shards"], len(m["units"])), (11, 156))
        self.assertTrue(all(s <= BUDGET for s in m["shard_seconds"]))

    def test_the_64000_packing_is_the_dry_plan_packing(self):
        from s5b_execution import dryplan

        class Open:
            def unit_is_needed(self, *a):
                return True
        units, _ = dryplan.units(Open())
        buckets = M.pack(units, BUDGET)
        self.assertEqual(len(buckets), 495)
        self.assertEqual(
            [tuple(u.task_id for u in b) for b in buckets],
            [tuple(u.task_id for u in b) for b in S.assign(units, 495)])
        plan = M.batches([sum(u.weight for u in b) for b in buckets],
                         M.BATCH_CAP)
        self.assertEqual([len(b) for b in plan], [165, 165, 165])
        sums = [sum(sum(u.weight for u in buckets[s]) for s in b)
                for b in plan]
        self.assertLess(max(sums) / min(sums), 1.001)


class TheSecondLevelLptTests(unittest.TestCase):

    def test_eleven_by_four_is_three_batches_full_first(self):
        w = [5.0, 9.0, 1.0, 7.0, 3.0, 8.0, 2.0, 6.0, 4.0, 10.0, 11.0]
        plan = M.batches(w, 4)
        self.assertEqual([len(b) for b in plan], [4, 4, 3])
        self.assertEqual(sorted(s for b in plan for s in b), list(range(11)))
        for b in plan:
            self.assertEqual(list(b), sorted(b, key=lambda s: (-w[s], s)))
        self.assertEqual(plan, M.batches(list(w), 4))

    def test_it_balances_rather_than_slices(self):
        w = [float(100 - i) for i in range(12)]
        plan = M.batches(w, 4)
        sums = [sum(w[s] for s in b) for b in plan]
        self.assertLess(max(sums) - min(sums), 4.0)
        self.assertNotEqual(plan[0], (0, 1, 2, 3))

    def test_a_cap_above_the_matrix_is_refused(self):
        with self.assertRaises(M.MultiRunRefused):
            M.batches([1.0] * 10, S.GITHUB_MATRIX_MAX_JOBS + 1)


class TheSelectorTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = _manifest()
        cls.plan = M.batches(cls.m["shard_seconds"], 4)

    def test_a_fresh_stage_takes_exactly_the_first_batch(self):
        sel = M.select(self.m, set(), run=1, cap=4)
        self.assertEqual(sel["shards"], list(self.plan[0]))
        self.assertEqual(set(sel["units"]), _ids(self.m, self.plan[0]))
        self.assertEqual(sel["retries"], [])

    def test_a_nominal_run_takes_its_whole_batch_and_retries_on_top(self):
        failed = self.plan[0][1]
        done = _ids(self.m, set(self.plan[0]) - {failed})
        sel = M.select(self.m, done, run=2, cap=4, matrix=6)
        self.assertEqual(sel["retries"], [failed])
        self.assertEqual(sel["nominal"], list(self.plan[1]))
        self.assertEqual(sel["shards"], [failed] + list(self.plan[1]),
                         "повтор идёт раньше новой партии")
        self.assertEqual(sel["carried"], 0)
        self.assertFalse(set(sel["units"]) & done)

    def test_retries_beyond_the_room_are_carried_not_squeezed_in(self):
        lost = list(self.plan[0][:3])
        done = _ids(self.m, set(self.plan[0]) - set(lost))
        sel = M.select(self.m, done, run=2, cap=4, matrix=6)
        self.assertEqual(sel["retries"], lost[:2])
        self.assertEqual(sel["carried"], 1)
        self.assertEqual(sel["nominal"], list(self.plan[1]),
                         "повторы урезали номинальную партию")
        done |= _ids(self.m, set(lost[:2]) | set(self.plan[1]))
        nxt = M.select(self.m, done, run=3, cap=4, matrix=6)
        self.assertEqual(nxt["retries"], lost[2:])
        self.assertEqual(nxt["nominal"], list(self.plan[2]))

    def test_the_recovery_run_holds_only_retries_up_to_the_matrix(self):
        every = {r["task_id"] for r in self.m["units"]}
        lost = [self.plan[2][0], self.plan[0][2], self.plan[1][3]]
        done = every - _ids(self.m, set(lost))
        sel = M.select(self.m, done, run=M.MAX_RUNS, cap=4, matrix=6)
        order = [s for b in self.plan for s in b]
        self.assertEqual(sel["shards"], sorted(lost, key=order.index))
        self.assertEqual((sel["nominal"], sel["carried"]), ([], 0))

    def test_results_in_a_batch_never_launched_are_refused(self):
        done = _ids(self.m, set(self.plan[0]) | {self.plan[1][0]})
        with self.assertRaises(M.MultiRunRefused) as caught:
            M.select(self.m, done, run=2, cap=4, matrix=6)
        self.assertIn("не та, что номер прогона", str(caught.exception))

    def test_the_retry_room_is_the_matrix_minus_the_batch(self):
        with self.assertRaises(M.MultiRunRefused):
            M.select(self.m, set(), run=1, cap=4, matrix=4)
        with self.assertRaises(M.MultiRunRefused):
            M.select(self.m, set(), run=1, cap=4,
                     matrix=S.GITHUB_MATRIX_MAX_JOBS + 1)

    def test_only_the_missing_units_of_a_partial_shard_are_selected(self):
        shard = self.plan[0][0]
        ids = sorted(_ids(self.m, {shard}))
        done = _ids(self.m, set(self.plan[0])) - {ids[-1]}
        sel = M.select(self.m, done, run=2, cap=4)
        self.assertEqual(sel["shards"][0], shard)
        self.assertIn(ids[-1], sel["units"])
        self.assertFalse(set(ids[:-1]) & set(sel["units"]))

    def test_the_recovery_run_must_be_able_to_close_the_stage(self):
        with self.assertRaises(M.MultiRunRefused) as caught:
            M.select(self.m, set(), run=M.MAX_RUNS, cap=4, matrix=6)
        self.assertIn("STOP", str(caught.exception))

    def test_there_is_no_fifth_run(self):
        done = {r["task_id"] for r in self.m["units"]} - {
            self.m["units"][0]["task_id"]}
        with self.assertRaises(M.MultiRunRefused) as caught:
            M.select(self.m, done, run=M.MAX_RUNS + 1, cap=4)
        self.assertIn("STOP", str(caught.exception))
        with self.assertRaises(M.MultiRunRefused):
            M.select(self.m, done, run=0, cap=4)

    def test_nothing_pending_is_a_refusal_not_an_empty_run(self):
        done = {r["task_id"] for r in self.m["units"]}
        with self.assertRaises(M.MultiRunRefused) as caught:
            M.select(self.m, done, run=M.MAX_RUNS, cap=4)
        self.assertIn("остатка нет", str(caught.exception))

    def test_done_units_outside_the_manifest_are_refused(self):
        with self.assertRaises(M.MultiRunRefused):
            M.select(self.m, {"0" * 16}, run=2, cap=4)

    def test_more_batches_than_nominal_runs_is_refused(self):
        with self.assertRaises(M.MultiRunRefused) as caught:
            M.select(self.m, set(), run=1, cap=3)
        self.assertIn("номинальных", str(caught.exception))

    def test_the_batch_manifest_carries_the_rows_verbatim(self):
        sel = M.select(self.m, set(), run=1, cap=4)
        batch = M.batch_manifest(self.m, sel)
        rows = {r["task_id"]: r for r in self.m["units"]}
        self.assertEqual({r["task_id"] for r in batch["units"]},
                         set(sel["units"]))
        for r in batch["units"]:
            self.assertEqual(r, rows[r["task_id"]])


class TheProgressTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = _manifest()
        cls.sel = M.select(cls.m, set(), run=1, cap=4)

    def test_an_unfinished_stage_without_failures_is_ok(self):
        got = M.progress(self.m, self.sel, set(), set(self.sel["units"]))
        self.assertEqual((got["status"], got["ok"]), (M.PARTIAL, True))
        self.assertEqual(got["failed_units"], [])

    def test_a_failed_selected_unit_is_not_ok(self):
        arrived = set(self.sel["units"]) - {self.sel["units"][0]}
        got = M.progress(self.m, self.sel, set(), arrived)
        self.assertEqual((got["status"], got["ok"]), (M.PARTIAL, False))
        self.assertEqual(len(got["failed_units"]), 1)

    def test_the_last_units_complete_the_stage(self):
        every = {r["task_id"] for r in self.m["units"]}
        done = every - set(self.sel["units"])
        sel = dict(self.sel)
        got = M.progress(self.m, sel, done, set(self.sel["units"]))
        self.assertEqual((got["status"], got["ok"]), (M.COMPLETE, True))

    def test_the_last_nominal_run_that_overflows_the_recovery_is_a_stop(self):
        every = {r["task_id"] for r in self.m["units"]}
        left = _ids(self.m, {0, 1, 2})
        sel = dict(self.sel, run=M.NOMINAL_RUNS, matrix=2,
                   units=sorted(every - left))
        got = M.progress(self.m, sel, set(), every - left)
        self.assertEqual((got["status"], got["ok"]), (M.STOP, False))
        got = M.progress(self.m, dict(sel, matrix=3), set(), every - left)
        self.assertEqual((got["status"], got["ok"]), (M.PARTIAL, True))

    def test_the_recovery_run_that_leaves_work_is_a_stop(self):
        sel = dict(self.sel, run=M.MAX_RUNS)
        got = M.progress(self.m, sel, set(), set(self.sel["units"]))
        self.assertEqual((got["status"], got["ok"]), (M.STOP, False))

    def test_a_recomputed_unit_is_refused_as_recomputed(self):
        """Отказ ИМЕННО с этой причиной.

        Повторный счёт отвергли бы и два соседних гейта — выбор с
        выполненным или невыбранная часть. Первая версия теста ловила
        любой отказ и потому пропустила диверсию, снявшую этот: проверка
        прошла по чужой причине. Причина и есть диагноз."""
        tid = self.sel["units"][0]
        sel = dict(self.sel, units=self.sel["units"][1:])
        with self.assertRaises(M.MultiRunRefused) as caught:
            M.progress(self.m, sel, {tid}, set(self.sel["units"]))
        self.assertIn("посчитаны повторно", str(caught.exception))

    def test_a_selection_holding_done_units_is_refused(self):
        tid = self.sel["units"][0]
        with self.assertRaises(M.MultiRunRefused) as caught:
            M.progress(self.m, self.sel, {tid}, set())
        self.assertIn("выбор включает уже выполненное", str(caught.exception))

    def test_an_unselected_arrival_is_refused(self):
        other = sorted({r["task_id"] for r in self.m["units"]}
                       - set(self.sel["units"]))[0]
        with self.assertRaises(M.MultiRunRefused) as caught:
            M.progress(self.m, self.sel, set(),
                       set(self.sel["units"]) | {other})
        self.assertIn("невыбранные", str(caught.exception))

    def test_a_selection_from_another_manifest_is_refused(self):
        sel = dict(self.sel, manifest_digest="0" * 16)
        with self.assertRaises(M.MultiRunRefused):
            M.progress(self.m, sel, set(), set())


class TheManifestIsCheckedTests(unittest.TestCase):

    def test_a_manifest_without_job_weights_is_not_multirun(self):
        m = _manifest()
        del m["shard_seconds"]
        with self.assertRaises(M.MultiRunRefused):
            M.check(m)

    def test_a_row_whose_keys_do_not_give_its_task_id_is_refused(self):
        m = _manifest()
        m["units"][0] = dict(m["units"][0], keys=m["units"][1]["keys"][:1])
        with self.assertRaises(M.MultiRunRefused):
            M.check(m)

    def test_the_body_ignores_provenance_only(self):
        m = _manifest()
        a = M.body_digest(m)
        self.assertEqual(a, M.body_digest(dict(m, provenance={"x": 1})))
        self.assertNotEqual(a, M.body_digest(
            dict(m, shard_seconds=[s + 1 for s in m["shard_seconds"]])))


class TheConstantsAreTheDecisionTests(unittest.TestCase):

    def test_three_nominal_runs_of_165_and_one_recovery(self):
        self.assertEqual((M.BATCH_CAP, M.NOMINAL_RUNS, M.RECOVERY_RUNS,
                          M.MAX_RUNS, M.MAX_PREVIOUS_RUNS), (165, 3, 1, 4, 3))
        self.assertEqual((M.RUN_MATRIX, M.RETRY_CAP), (256, 91))
        self.assertIsNone(cost.UNDIVIDED_SHARE)


if __name__ == "__main__":
    unittest.main()


# --- ЧЕРЕЗ CLI ---------------------------------------------------------

import contextlib                                                  # noqa: E402
import hashlib                                                     # noqa: E402
import json                                                        # noqa: E402
import os                                                          # noqa: E402
import shutil                                                      # noqa: E402
import tempfile                                                    # noqa: E402
from unittest import mock                                          # noqa: E402

from tools import s5b_multirun_gate as G                           # noqa: E402

ENV = {"SCIENCE_SHA": "a" * 40, "EXECUTION_SHA": "b" * 40,
       "REQUEST_SHA": "c" * 40}


@contextlib.contextmanager
def _stubbed(**env):
    stub = G.Stub()
    with mock.patch.dict(os.environ, {**ENV, **env}), \
            mock.patch.object(S, "run_unit", stub):
        yield stub


def _ok(argv, cwd):
    code, out, why = G.call(argv, cwd)
    if code:
        raise AssertionError(f"{argv[0]}: код {code}: {why}")
    return out


def _run_all(run_dir, look, manifest, count):
    target = run_dir / "out"
    target.mkdir(parents=True, exist_ok=True)
    for s in range(count):
        _ok(["run", "--look", str(look), "--manifest", manifest,
             "--shard", str(s), "--out", "out"], run_dir)
    shutil.copy(run_dir / manifest, target / "manifest.json")


class TheRecordedGateReproducesTests(unittest.TestCase):
    """Гейт исполнен ОДИН раз, вердикт записан. Здесь — не второй гейт, а
    регрессия: закоммиченный слой обязан воспроизвести записанное
    свидетельство целиком, до сообщений отказа. Иначе вердикт относился бы
    к коду, которого в репозитории нет."""

    def test_the_committed_layer_reproduces_the_recorded_evidence(self):
        recorded = json.loads((ROOT / "docs/research/s5b-multirun-gate.json")
                              .read_text())
        self.assertEqual(recorded["verdict"], "PASS")
        checks, evidence = {}, {"look": G.LOOK, "cap": G.CAP,
                                "matrix": G.MATRIX}
        G._gate(checks, evidence)
        self.assertEqual(checks, recorded["checks"])
        for key in evidence:
            if key == "python":
                continue
            self.assertEqual(evidence[key], recorded[key], key)


class TheContinuationCarriesTheFirstManifestTests(unittest.TestCase):

    def test_bytes_not_a_fresh_copy_under_another_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            with _stubbed():
                _ok(["plan", "--look", "4000", "--multirun", "--out",
                     "first"], tmp)
            (tmp / "resumed").mkdir()
            shutil.copy(tmp / "first/manifest.json",
                        tmp / "resumed/manifest.json")
            with _stubbed(REQUEST_SHA="d" * 40):
                _ok(["plan", "--look", "4000", "--multirun", "--resume",
                     "resumed", "--out", "second"], tmp)
                _ok(["plan", "--look", "4000", "--multirun", "--out",
                     "fresh"], tmp)
            first = (tmp / "first/manifest.json").read_bytes()
            self.assertEqual((tmp / "second/manifest.json").read_bytes(), first)
            self.assertNotEqual((tmp / "fresh/manifest.json").read_bytes(),
                                first, "контроль: провенанс другой заявки")

    def test_select_refuses_a_chain_of_another_stage_plan(self):
        with tempfile.TemporaryDirectory() as tmp, _stubbed():
            tmp = pathlib.Path(tmp)
            _ok(["plan", "--look", "4000", "--multirun", "--out", "plan"], tmp)
            (tmp / "resumed").mkdir()
            m = json.loads((tmp / "plan/manifest.json").read_text())
            m["shard_seconds"][0] += 1.0
            (tmp / "resumed/manifest.json").write_text(json.dumps(m))
            code, _, why = G.call(["select", "--look", "4000", "--manifest",
                                   "plan/manifest.json", "--run", "2",
                                   "--resume", "resumed", "--out", "b"], tmp)
            self.assertEqual(code, 1)
            self.assertIn("не тот, что у этого прогона", why)

    def test_select_refuses_another_science(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            with _stubbed():
                _ok(["plan", "--look", "4000", "--multirun", "--out",
                     "plan"], tmp)
            with _stubbed(SCIENCE_SHA="e" * 40):
                code, _, why = G.call(["select", "--look", "4000",
                                       "--manifest", "plan/manifest.json",
                                       "--run", "1", "--out", "b"], tmp)
            self.assertEqual(code, 1)
            self.assertIn("разные вычисления", why)


def _checkpoint(tmp, looks=(4000, 16000)):
    from s5b_execution.ledger import Ledger
    led = Ledger()
    led._absorbed = list(looks)
    cp = led.to_checkpoint(canonical_arms=set(scheduler.arms()),
                           provenance={})
    path = pathlib.Path(tmp) / "checkpoint.json"
    path.write_text(json.dumps(cp, sort_keys=True))
    return path, cp["ledger_digest"]


class TheProductionPlanShapeTests(unittest.TestCase):
    """Закоммиченный CLI планирует 64000 так, как записано в сухом плане."""

    def test_the_64000_manifest_and_the_first_batch(self):
        with tempfile.TemporaryDirectory() as tmp, _stubbed():
            tmp = pathlib.Path(tmp)
            cp, digest = _checkpoint(tmp)
            out = json.loads(_ok(
                ["plan", "--look", "64000", "--multirun", "--checkpoint",
                 str(cp), "--prior-digest", digest, "--out", "plan"],
                tmp).strip().splitlines()[-1])
            self.assertEqual((out["count"], out["units"]), (495, 1872))
            sel = json.loads(_ok(
                ["select", "--look", "64000", "--manifest",
                 "plan/manifest.json", "--run", "1", "--out", "batch"],
                tmp).strip().splitlines()[-1])
            self.assertEqual(len(sel["shards"]), M.BATCH_CAP)
            self.assertEqual(sel["units"], 624)

    def test_a_checkpoint_of_another_run_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, _stubbed():
            tmp = pathlib.Path(tmp)
            cp, _ = _checkpoint(tmp)
            for argv in (["plan", "--multirun"], ["reduce"]):
                code, _, why = G.call(
                    argv + ["--look", "64000", "--checkpoint", str(cp),
                            "--prior-digest", "0" * 16, "--out", "x"], tmp)
                self.assertEqual(code, 1, argv)
                self.assertIn("приехал не тот прогон", why, argv)


class TheCheckpointBranchChainTests(unittest.TestCase):
    """Гейт прошёл ветку сведения без прошлой ступени. 64000 идёт другой —
    от ЧЕКПОЙНТА. Та же механика на 16000 от синтетического чекпойнта
    4000: три прогона против одного, наука побайтово та же."""

    def test_three_runs_from_a_checkpoint_equal_one(self):
        with tempfile.TemporaryDirectory() as tmp, _stubbed():
            root = pathlib.Path(tmp)
            s4 = root / "s4"
            s4.mkdir()
            _ok(["plan", "--look", "4000", "--multirun", "--out", "plan"], s4)
            n4 = json.loads((s4 / "plan/manifest.json").read_text())["shards"]
            _run_all(s4, 4000, "plan/manifest.json", n4)
            _ok(["reduce", "--look", "4000", "--out", "out"], s4)
            cp = s4 / "out/checkpoint.json"
            digest = json.loads(cp.read_text())["ledger_digest"]
            prior = ["--checkpoint", str(cp), "--prior-digest", digest]

            ref = root / "ref"
            ref.mkdir()
            _ok(["plan", "--look", "16000", "--multirun", "--out", "plan"]
                + prior, ref)
            n = json.loads((ref / "plan/manifest.json").read_text())["shards"]
            _run_all(ref, 16000, "plan/manifest.json", n)
            _ok(["reduce", "--look", "16000", "--out", "out"] + prior, ref)

            cap = -(-n // 3)
            dirs = []
            for r in (1, 2, 3):
                d = root / f"run{r}"
                d.mkdir()
                resume = []
                if dirs:
                    (d / "resumed").mkdir()
                    for prev in dirs:
                        for p in G.parts_of(prev / "out"):
                            shutil.copy(p, d / "resumed" / p.name)
                    shutil.copy(dirs[0] / "plan/manifest.json",
                                d / "resumed/manifest.json")
                    resume = ["--resume", "resumed"]
                _ok(["plan", "--look", "16000", "--multirun", "--out", "plan"]
                    + prior + resume, d)
                _ok(["select", "--look", "16000", "--manifest",
                     "plan/manifest.json", "--run", str(r), "--batch-cap",
                     str(cap), "--out", "batch"] + resume, d)
                batch = json.loads((d / "batch/batch.json").read_text())
                for s in batch["selection"]["shards"]:
                    _ok(["run", "--look", "16000", "--manifest",
                         "batch/batch.json", "--shard", str(s), "--out",
                         "out"], d)
                shutil.copy(d / "plan/manifest.json", d / "out/manifest.json")
                code, _, why = G.call(
                    ["progress", "--look", "16000", "--parts", "out",
                     "--batch", "batch/batch.json", "--out", "report"]
                    + resume, d)
                self.assertEqual(code, 0, why)
                dirs.append(d)
            status = json.loads((d / "report/progress.json").read_text())
            self.assertEqual(status["status"], M.COMPLETE)
            _ok(["reduce", "--look", "16000", "--out", "out"] + prior
                + ["--resume", "resumed"], d)
            for name in ("reduced.json", "checkpoint.json"):
                a, reused_a = G.stripped(ref / "out" / name)
                b, reused_b = G.stripped(d / "out" / name)
                self.assertEqual(a, b, name)
                self.assertEqual(reused_a, {})
                self.assertTrue(reused_b)
            self.assertEqual(
                hashlib.sha256((ref / "plan/manifest.json").read_bytes())
                .hexdigest(),
                hashlib.sha256((d / "plan/manifest.json").read_bytes())
                .hexdigest())


class AViolationIsAKillReportTests(unittest.TestCase):
    """Нарушение итога — не трассировка, а KILL с причиной и кодом 1."""

    def test_an_unselected_part_in_the_run_is_a_kill(self):
        with tempfile.TemporaryDirectory() as tmp, _stubbed():
            tmp = pathlib.Path(tmp)
            _ok(["plan", "--look", "4000", "--multirun", "--out", "plan"], tmp)
            _ok(["select", "--look", "4000", "--manifest", "plan/manifest.json",
                 "--run", "1", "--batch-cap", "4", "--run-matrix", "6",
                 "--out", "batch"], tmp)
            sel = json.loads((tmp / "batch/batch.json").read_text())
            other = [s for s in range(11)
                     if s not in sel["selection"]["shards"]][0]
            _ok(["run", "--look", "4000", "--manifest", "plan/manifest.json",
                 "--shard", str(other), "--out", "out"], tmp)
            shutil.copy(tmp / "plan/manifest.json", tmp / "out/manifest.json")
            code, _, _ = G.call(["progress", "--look", "4000", "--parts", "out",
                                 "--batch", "batch/batch.json", "--out", "r"],
                                tmp)
            report = json.loads((tmp / "r/progress.json").read_text())
        self.assertEqual(code, 1)
        self.assertEqual((report["status"], report["ok"]), (M.KILL, False))
        self.assertIn("невыбранные", report["reason"])
