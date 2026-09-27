"""Гейты Gate A-F2a: агрегатная модель с усиленным контрастом.

Вердикт проверяется на синтетических записях с ИЗВЕСТНОЙ истиной, по
одной на каждую ветку; исполнитель — с подставным замером и фальшивыми
часами, без науки и без минут ЦП.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "execution") not in sys.path:
    sys.path.insert(0, str(ROOT / "execution"))

from s5b_execution import af2a as F, calibrate, cost                # noqa: E402

KEYS = F.KEYS
HORIZONS = sorted({k[2] for k in KEYS})

#: Истина в долях неделёного 60 с, как в Gate A / A-F1.
C1 = 60.0
TRUE_A = 0.046 * C1
TRUE_B = {d: 0.019 * C1 for d in F.DELTAS}
_PROFILE = {1.0: 20.9, 5.0: 22.5, 15.0: 26.8, 60.0: 55.2}
_K = C1 - TRUE_A - sum(TRUE_B.values())
TRUE_C = {d: _K * r / (18 * sum(_PROFILE.values())) for d, r in _PROFILE.items()}


def _truth(*, b=None, horizon_effect=0.0, days_overhead=0.0, scale=1.0):
    b = TRUE_B if b is None else b

    def group(keys):
        per_key = sum(TRUE_C[k[0]] * (1.0 + (horizon_effect if k[2] == HORIZONS[-1]
                                             else 0.0)) for k in keys)
        return scale * (TRUE_A + sum(b[d] for d in {k[0] for k in keys})
                        + days_overhead * len({(k[0], k[1]) for k in keys})
                        + per_key)
    return group


def _rows(slices, truth, factor=1.0, bump=None):
    rows = []
    for j, keys in enumerate(slices):
        t = truth(keys) * factor
        if bump and j == 0:
            t *= bump
        rows.append({"keys": [list(k) for k in keys], "cpu_seconds": t,
                     "wall_seconds": t})
    return rows


def _run(label, rows, **tags):
    return {"label": label, **tags, "groups_detail": rows,
            "C_cpu": sum(r["cpu_seconds"] for r in rows),
            "C_wall": sum(r["wall_seconds"] for r in rows)}


def _record(truth=None, *, noise=None, step0_noise=0.0, identical=True,
            drop=None, drop_comparison=False, factorial_bump=None,
            step0_only=False):
    """Запись в формате исполнителя: шаг 0, три раунда, сравнения с базой."""
    truth = truth or _truth()
    parts = F.partitions()
    rec = {"step0": [], "runs": [], "comparisons": [], "incomplete": None}
    for i in range(F.STEP0_REPEATS):
        factor = 1.0 + (step0_noise if i == 1 else 0.0)
        rec["step0"].append(_run("P1", _rows(parts["P1"], truth, factor), rep=i))
    if not step0_only:
        for r, order in enumerate(F.rounds()):
            for label in order:
                if drop == (label, r):
                    continue
                factor = 1.0 + (noise[1] if noise and noise[0] == label and r == 1
                                else 0.0)
                bump = factorial_bump if label == "F6" else None
                rec["runs"].append(_run(label, _rows(parts[label], truth,
                                                     factor, bump), round=r))
    total = len(rec["step0"]) + len(rec["runs"]) - 1
    rec["comparisons"] = [{"identical": identical} for _ in range(total)]
    if drop_comparison:
        rec["comparisons"].pop()
    return rec


class ThePartitionsCarryTheDeclaredShapeTests(unittest.TestCase):

    def test_every_partition_covers_every_key_exactly_once(self):
        for label, slices in F.partitions().items():
            flat = [k for g in slices for k in g]
            self.assertEqual(sorted(flat, key=repr), sorted(KEYS, key=repr), label)

    def test_every_delta_is_present_equally_often(self):
        got = {lbl: F.shape(sl) for lbl, sl in F.partitions().items()}
        self.assertEqual(got, {"P1": (1, 1), "P4": (4, 1), "Q6": (6, 2),
                               "H4": (4, 2), "F6": (6, 6), "C6": (6, 6)})

    def test_q6_is_the_one_heldout_that_keeps_day_blocks_whole(self):
        """Скрытый уровень (группа, δ, days) виден через Q6, и только так."""
        got = {lbl: F.day_pairs(sl) for lbl, sl in F.partitions().items()}
        self.assertEqual(got, {"P1": 12, "P4": 12, "Q6": 12, "H4": 16,
                               "F6": 72, "C6": 72})

    def test_the_ring_puts_two_half_blocks_in_each_group(self):
        for g in F.ring4():
            self.assertEqual(len(g), 18)
            self.assertEqual(len({k[0] for k in g}), 2)

    def test_the_schedule_is_nearly_balanced_against_drift(self):
        rounds = F.rounds()
        for r in rounds:
            self.assertEqual(sorted(r), sorted(F.ORDER))
        sums = {t: sum(r.index(t) for r in rounds) for t in F.ORDER}
        self.assertEqual(sorted(sums.values()), [7, 7, 7, 8, 8, 8])


class TheFitDoesNotTouchTheHeldoutTests(unittest.TestCase):

    def test_q6_and_h4_and_c6_do_not_enter_the_fit(self):
        base = {"P1": 60.0, "P4": 68.0, "F6": 97.0, "Q6": 78.0, "H4": 74.0,
                "C6": 97.0}
        moved = dict(base, Q6=1.0, H4=1.0, C6=1.0)
        self.assertEqual(F.fit(base), F.fit(moved))

    def test_an_exact_truth_is_recovered_and_passes(self):
        got = F.verdict(_record())
        c = got["checks"]
        self.assertEqual(got["status"], "PASS", got)
        self.assertAlmostEqual(c["A"], TRUE_A, places=3)
        self.assertAlmostEqual(c["sumB"], sum(TRUE_B.values()), places=3)
        self.assertLess(max(abs(e) for e in c["heldout_errors"].values()), 1e-9)
        self.assertIn("days НЕ измерена", got["verdict"])


class TheVerdictKillsWhatItMustTests(unittest.TestCase):

    def test_a_hidden_day_level_is_killed_by_the_heldout(self):
        got = F.verdict(_record(_truth(days_overhead=0.5 * TRUE_B[1.0])))
        self.assertEqual(got["status"], "KILL_HELDOUT", got["checks"])
        self.assertGreater(abs(got["checks"]["heldout_errors"]["Q6"]),
                           F.HELDOUT_TOLERANCE)

    def test_a_negative_pair_cost_is_a_kill_not_a_zero(self):
        got = F.verdict(_record(_truth(b={d: -1.0 for d in F.DELTAS})))
        self.assertEqual(got["status"], "KILL_NEGATIVE_COST", got["checks"])
        self.assertLess(got["checks"]["sumB"], 0.0)

    def test_noise_in_the_main_repeats_decides_nothing(self):
        got = F.verdict(_record(noise=("Q6", 0.08)))
        self.assertEqual(got["status"], "INCONCLUSIVE_NOISE")

    def test_noise_in_step0_stops_before_anything(self):
        got = F.verdict(_record(step0_noise=0.08, step0_only=True))
        self.assertEqual(got["status"], "INCONCLUSIVE_NOISE")
        self.assertEqual(got["checks"]["step0_gate"], "INCONCLUSIVE_NOISE")

    def test_a_look_that_missed_the_window_is_incomplete(self):
        got = F.verdict(_record(_truth(scale=0.5)))
        self.assertEqual(got["status"], "INCOMPLETE")

    def test_changed_science_is_a_kill_before_anything_else(self):
        got = F.verdict(_record(identical=False))
        self.assertEqual(got["status"], "KILL_SPLIT_CHANGED_SCIENCE")

    def test_a_missing_run_is_incomplete(self):
        got = F.verdict(_record(drop=("C6", 2)))
        self.assertEqual(got["status"], "INCOMPLETE")

    def test_a_missing_comparison_is_not_a_pass(self):
        got = F.verdict(_record(drop_comparison=True))
        self.assertEqual(got["status"], "KILL_SPLIT_CHANGED_SCIENCE")


class TheUniformityProbeTests(unittest.TestCase):
    """Контроль — factorial (балансирует всё), зонд — cells (изолирует клетку)."""

    def test_a_large_cell_effect_kills_uniformity(self):
        got = F.verdict(_record(_truth(horizon_effect=0.3)))
        self.assertEqual(got["status"], "KILL_UNIFORM_WITHIN_BLOCK", got["checks"])
        self.assertEqual(got["model_status"], "PASS")

    def test_the_factorial_control_is_flat_under_a_cell_effect(self):
        c = F.verdict(_record(_truth(horizon_effect=0.3)))["checks"]
        self.assertAlmostEqual(c["factorial_spread"], 1.0, places=6)

    def test_a_middle_effect_is_unresolved_and_stops(self):
        got = F.verdict(_record(_truth(horizon_effect=0.07)))
        self.assertEqual(got["uniformity_status"], "UNRESOLVED")
        self.assertEqual(got["status"], "UNRESOLVED")
        self.assertIn("STOP", got["verdict"])

    def test_a_small_effect_is_not_detected_and_days_is_not_claimed(self):
        got = F.verdict(_record(_truth(horizon_effect=0.03)))
        self.assertEqual(got["uniformity_status"],
                         "HORIZON_MAXIMISE_EFFECT_NOT_DETECTED_DAYS_UNMEASURED")

    def test_a_noisy_control_withholds_the_kill(self):
        """Эффект есть, но контроль шумит: вердикт — НЕ РЕШЕНО, а не KILL."""
        got = F.verdict(_record(_truth(horizon_effect=0.3), factorial_bump=1.1))
        self.assertEqual(got["model_status"], "PASS", got["checks"])
        self.assertEqual(got["uniformity_status"], "UNRESOLVED_NOISE")
        self.assertEqual(got["status"], "UNRESOLVED")

    def test_a_non_positive_residual_is_unresolved_not_negative_time(self):
        est = {"A": 5.0, "sumB": 10.0}
        got = F.uniformity({"F6": [20.0] * 6, "C6": [20.0] * 5 + [14.0]}, est)
        self.assertEqual(got["uniformity_status"], "UNRESOLVED")

    def test_thresholds_are_declared_and_ordered(self):
        self.assertLess(F.UNIFORM_NOT_DETECTED, F.UNIFORM_KILL)
        self.assertLessEqual(F.NOISE_SPREAD, 1.05)
        self.assertLessEqual(F.HELDOUT_TOLERANCE, 0.05)
        self.assertLessEqual(F.BUDGET_SECONDS, 2100.0)


# --- исполнитель с подставным замером ---------------------------------------

class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _endpoint(point=1.0):
    return types.SimpleNamespace(key=("k",), delta_fraction=0.1, point=point,
                                 low=0.0, high=2.0, radius=0.1,
                                 status=types.SimpleNamespace(value="x"), look=1)


def _stub(clock, *, change_on=None, slow_on=None, spike6=1.0):
    """Стоимость по истине, пропорциональна просмотру: 60 с при просмотре 100."""
    truth = _truth()
    calls = []

    def measure(slices, arm, look):
        calls.append(len(slices))
        rows = []
        for keys in slices:
            t = truth(keys) * look / 100.0
            if slow_on is not None and len(calls) == slow_on:
                t *= 1.1
            if len(slices) == 6:
                t *= spike6
            clock.now += t
            rows.append({"keys": [list(k) for k in keys], "cpu_seconds": t,
                         "wall_seconds": t})
        changed = change_on is not None and len(calls) == change_on
        return rows, {("k",): _endpoint(2.0 if changed else 1.0)}
    measure.calls = calls
    return measure


class TheRunnerTests(unittest.TestCase):

    def test_the_look_is_chosen_by_doubling_then_frozen(self):
        look, probes = F.choose_look({}, _stub(_Clock()))
        self.assertEqual([p["look"] for p in probes], [2, 4, 8])
        self.assertEqual(look, 100)

    def test_a_full_run_is_step0_then_three_balanced_rounds_and_passes(self):
        clock = _Clock()
        stub = _stub(clock)
        rec = F.run(clock=clock, measure_fn=stub, changes_fn=list)
        self.assertEqual(len(rec["probes"]), 3)
        self.assertEqual([r["label"] for r in rec["step0"]], ["P1"] * 3)
        self.assertEqual([r["label"] for r in rec["runs"]],
                         [lbl for order in F.rounds() for lbl in order])
        self.assertEqual(rec["verdict"]["status"], "PASS", rec["verdict"])

    def test_noisy_step0_stops_before_the_main_design(self):
        clock = _Clock()
        # три пробы, затем шаг 0: пятый вызов — второй свежий P1 — шумит
        rec = F.run(clock=clock, measure_fn=_stub(clock, slow_on=5),
                    changes_fn=list)
        self.assertEqual(rec["stopped_at_step0"], "INCONCLUSIVE_NOISE")
        self.assertEqual(rec["runs"], [])
        self.assertEqual(rec["verdict"]["status"], "INCONCLUSIVE_NOISE")

    def test_changed_science_refuses_before_measuring(self):
        clock = _Clock()
        stub = _stub(clock)
        with self.assertRaises(F.ScienceNotFrozen):
            F.run(clock=clock, measure_fn=stub,
                  changes_fn=lambda: ["research/python/simulation/x.py"])
        self.assertEqual(stub.calls, [])

    def test_a_split_that_changes_the_result_stops_the_run(self):
        clock = _Clock()
        with self.assertRaises(calibrate.SplitChangedTheScience):
            F.run(clock=clock, measure_fn=_stub(clock, change_on=5),
                  changes_fn=list)

    def test_the_guard_does_not_start_what_cannot_fit(self):
        clock = _Clock()
        rec = F.run(clock=clock, measure_fn=_stub(clock), changes_fn=list,
                    budget=400.0)
        self.assertIn("не начат", rec["incomplete"] or "")
        self.assertEqual(rec["verdict"]["status"], "INCOMPLETE")

    def test_overrunning_the_budget_is_incomplete_not_a_bit_more(self):
        clock = _Clock()
        rec = F.run(clock=clock, measure_fn=_stub(clock, spike6=40.0),
                    changes_fn=list)
        self.assertIn("превышен", rec["incomplete"] or "")
        self.assertEqual(rec["runs"][-1]["label"], "Q6")
        self.assertEqual(rec["verdict"]["status"], "INCOMPLETE")

    def test_the_record_carries_the_preregistered_thresholds(self):
        clock = _Clock()
        rec = F.run(clock=clock, measure_fn=_stub(clock), changes_fn=list)
        self.assertEqual(rec["thresholds"], F.thresholds())


class ThePowerRationaleTests(unittest.TestCase):
    """Обоснование дизайна, НЕ evidence: воспроизводимо и указывает туда же."""

    def test_it_is_reproducible_from_its_seed(self):
        self.assertEqual(F.power_rationale(n=200), F.power_rationale(n=200))

    def test_the_chosen_roles_do_not_kill_a_true_model_where_the_old_did(self):
        rows = {(r["sigma"], r["hidden_E_over_B"]): r
                for r in F.power_rationale(n=400)}
        honest = rows[(0.012, 0.0)]
        self.assertLess(honest["kill_given_passed_prereg"], 0.05)
        self.assertGreater(honest["kill_given_passed_old"], 0.15)


class TheGateIsNotWiredTests(unittest.TestCase):

    def test_the_planner_does_not_import_the_gate(self):
        code = ("import sys; sys.path[:0] = ['research/python', 'execution'];"
                "import s5b_execution.cli, s5b_execution.scheduler;"
                "print('s5b_execution.af2a' in sys.modules)")
        done = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "False",
                         "планировщик тянет локальный gate")

    def test_the_share_is_still_unset(self):
        self.assertIsNone(cost.UNDIVIDED_SHARE)
        self.assertTrue(F.COEFFICIENTS_DO_NOT_TRANSFER_TO_PRODUCTION)


if __name__ == "__main__":
    unittest.main()
