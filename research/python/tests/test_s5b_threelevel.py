"""Гейты Gate A-F1: трёхуровневая модель стоимости группы ключей.

Вердикт проверяется на синтетических записях с ИЗВЕСТНОЙ истиной: каждая
ветка вердикта обязана сработать на той истине, ради которой заведена, и
не сработать на честной трёхуровневой. Исполнитель проверяется с
подставным замером и фальшивыми часами — без науки и без минут ЦП.
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

from s5b_execution import calibrate, cost, threelevel as T       # noqa: E402

KEYS = T.KEYS
HORIZONS = sorted({k[2] for k in KEYS})

#: Масштаб как у Gate A на 4000 (секунды ЦП): A — группа, B — пара
#: (группа, δ), C — ключ. Истина по умолчанию РОВНО трёхуровневая.
TRUE_A = 85.0
TRUE_B = {1.0: 40.0, 5.0: 44.0, 15.0: 48.0, 60.0: 52.0}
TRUE_C = {1.0: 20.9, 5.0: 22.5, 15.0: 26.8, 60.0: 55.2}


def _truth(a=TRUE_A, b=None, c=None, horizon_effect=0.0, days_overhead=0.0,
           group_growth=0.0):
    """Стоимость группы по истине. Лишние слагаемые — то, что модель НЕ видит."""
    b = TRUE_B if b is None else b
    c = TRUE_C if c is None else c

    def group(keys, n_groups):
        cost_a = a * (1.0 + group_growth * (n_groups - 1))
        per_key = sum(c[k[0]] * (1.0 + (horizon_effect if k[2] == HORIZONS[-1]
                                        else 0.0)) for k in keys)
        return (cost_a + sum(b[d] for d in {k[0] for k in keys})
                + days_overhead * len({(k[0], k[1]) for k in keys}) + per_key)
    return group


def _record(truth=None, noise=0.0, identical=True, drop=None, incomplete=None):
    """Запись в формате исполнителя: ABBA, два повтора, сравнения с базой."""
    truth = truth or _truth()
    parts = T.partitions()
    order = list(parts)
    schedule = [(lbl, 0) for lbl in order] + [(lbl, 1) for lbl in reversed(order)]
    rec = {"runs": [], "comparisons": [], "incomplete": incomplete}
    for label, rep in schedule:
        if drop == (label, rep):
            continue
        rows = []
        for j, keys in enumerate(parts[label]):
            t = truth(keys, len(parts[label]))
            if rep == 1 and j % 2 == 0:
                t *= 1.0 + noise
            rows.append({"keys": [list(k) for k in keys],
                         "cpu_seconds": t, "wall_seconds": t})
        rec["runs"].append({"label": label, "rep": rep, "groups_detail": rows,
                            "C_cpu": sum(r["cpu_seconds"] for r in rows),
                            "C_wall": sum(r["wall_seconds"] for r in rows)})
        if len(rec["runs"]) > 1:
            rec["comparisons"].append({"identical": identical,
                                       "label": label, "rep": rep})
    return rec


class ThePartitionsMeasureWhatTheyClaimTests(unittest.TestCase):
    """Каждое разбиение покрывает 72 ключа и несёт объявленную структуру."""

    def test_every_partition_covers_every_key_exactly_once(self):
        for label, slices in T.partitions().items():
            flat = [k for g in slices for k in g]
            self.assertEqual(sorted(flat, key=repr), sorted(KEYS, key=repr), label)

    def test_the_structure_is_the_declared_one(self):
        want = {"P1": (1, 4), "P2": (2, 4), "P4": (4, 4), "F6": (6, 24),
                "C6": (6, 24)}
        want.update({f"P_d{d:g}": (2, 5) for d in T.DELTAS})
        got = {lbl: T.structure(sl) for lbl, sl in T.partitions().items()}
        self.assertEqual(got, want)

    def test_only_its_own_block_is_split_in_p_delta(self):
        for d in T.DELTAS:
            a, b = T.partitions()[f"P_d{d:g}"]
            shared = {k[0] for k in a} & {k[0] for k in b}
            self.assertEqual(shared, {d})

    def test_factorial_and_cells_have_equal_sufficient_statistics(self):
        """Модель обязана предсказать ИМ одинаковую группу — в этом весь зонд."""
        for label in ("F6", "C6"):
            for g in T.partitions()[label]:
                counts = {d: sum(1 for k in g if k[0] == d) for d in T.DELTAS}
                self.assertEqual(set(counts.values()), {3}, label)


class TheEstimatesRecoverAKnownTruthTests(unittest.TestCase):

    def test_an_exact_three_level_truth_is_recovered_and_passes(self):
        got = T.verdict(_record())
        c = got["checks"]
        self.assertEqual(got["status"], "PASS", got)
        self.assertAlmostEqual(c["A"], TRUE_A, places=3)
        for d in T.DELTAS:
            self.assertAlmostEqual(c["B"][f"{d:g}"], TRUE_B[d], places=3)
            self.assertAlmostEqual(c["C"][f"{d:g}"], TRUE_C[d], places=3)
        self.assertEqual(c["uniformity_status"],
                         "HORIZON_MAXIMISE_EFFECT_NOT_DETECTED_DAYS_UNMEASURED")

    def test_the_pass_does_not_claim_days(self):
        self.assertIn("days НЕ измерена", T.verdict(_record())["verdict"])


class TheVerdictKillsWhatItMustTests(unittest.TestCase):

    def test_a_hidden_level_below_delta_is_killed_by_the_heldout(self):
        """Работа на (группа, δ, days): P_dδ её частично видят, factorial — нет."""
        got = T.verdict(_record(_truth(days_overhead=10.0)))
        self.assertEqual(got["status"], "KILL_HELDOUT", got["checks"])

    def test_a_growing_group_cost_is_killed(self):
        got = T.verdict(_record(_truth(group_growth=0.5)))
        self.assertEqual(got["status"], "KILL_GROUP_COST", got["checks"])

    def test_a_negative_component_beyond_noise_is_a_kill_not_a_zero(self):
        b = {**TRUE_B, 60.0: -80.0}
        got = T.verdict(_record(_truth(b=b), noise=0.001))
        self.assertEqual(got["status"], "KILL_NEGATIVE_COST", got["checks"])
        self.assertLess(got["checks"]["B"]["60"], 0.0, "отрицательное зажато")

    def test_a_negative_component_within_noise_is_unresolved(self):
        b = {**TRUE_B, 60.0: -1.0}
        got = T.verdict(_record(_truth(b=b), noise=0.004))
        self.assertEqual(got["status"], "INCONCLUSIVE_UNRESOLVED_COMPONENT",
                         got["checks"])

    def test_noise_above_the_ceiling_decides_nothing(self):
        got = T.verdict(_record(noise=2 * T.NOISE_CEILING))
        self.assertEqual(got["status"], "INCONCLUSIVE_NOISE")

    def test_changed_science_is_a_kill_before_anything_else(self):
        got = T.verdict(_record(identical=False))
        self.assertEqual(got["status"], "KILL_SPLIT_CHANGED_SCIENCE")

    def test_a_missing_repeat_is_incomplete(self):
        got = T.verdict(_record(drop=("C6", 1)))
        self.assertEqual(got["status"], "INCOMPLETE")

    def test_a_declared_incomplete_run_is_incomplete(self):
        got = T.verdict(_record(incomplete="бюджет"))
        self.assertEqual(got["status"], "INCOMPLETE")


class TheProbeInsideTheBlockTests(unittest.TestCase):
    """cells6 против factorial6 на части «только ключи»."""

    def test_a_large_horizon_effect_kills_uniformity(self):
        got = T.verdict(_record(_truth(horizon_effect=0.3)))
        self.assertEqual(got["status"], "KILL_UNIFORM_WITHIN_BLOCK", got["checks"])

    def test_the_factorial_heldout_survives_a_horizon_effect(self):
        """Factorial балансирует горизонты: ось видна ТОЛЬКО через cells."""
        c = T.verdict(_record(_truth(horizon_effect=0.3)))["checks"]
        self.assertLess(abs(c["F6_C_error"]), 1e-9)
        self.assertLess(abs(c["F6_W_error"]), 1e-9)

    def test_a_middle_effect_is_unresolved_and_stops(self):
        got = T.verdict(_record(_truth(horizon_effect=0.1)))
        self.assertEqual(got["status"], "UNRESOLVED", got["checks"])
        self.assertIn("STOP", got["verdict"])

    def test_a_small_effect_is_not_detected_not_a_pass_of_days(self):
        got = T.verdict(_record(_truth(horizon_effect=0.03)))
        self.assertEqual(got["checks"]["uniformity_status"],
                         "HORIZON_MAXIMISE_EFFECT_NOT_DETECTED_DAYS_UNMEASURED")

    def test_overhead_does_not_dilute_the_probe(self):
        """Gate A: 44% накладных в клетке прятали эффект. Здесь они вычтены."""
        light = {1.0: 10.0, 5.0: 11.0, 15.0: 13.0, 60.0: 26.0}
        got = T.verdict(_record(_truth(c=light, horizon_effect=0.3)))
        self.assertEqual(got["checks"]["uniformity_status"],
                         "KILL_UNIFORM_WITHIN_BLOCK", got["checks"])

    def test_thresholds_are_declared_and_ordered(self):
        self.assertLess(T.UNIFORM_NOT_DETECTED, T.UNIFORM_KILL)
        self.assertLessEqual(T.HELDOUT_TOLERANCE, 0.05)
        self.assertLessEqual(T.GROUP_COST_TOLERANCE, 0.05)
        self.assertLessEqual(T.NOISE_CEILING, 0.02)
        self.assertLessEqual(T.BUDGET_SECONDS, 900.0)


# --- исполнитель с подставным замером ---------------------------------------

class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _endpoint(point=1.0):
    return types.SimpleNamespace(key=("k",), delta_fraction=0.1, point=point,
                                 low=0.0, high=2.0, radius=0.1,
                                 status=types.SimpleNamespace(value="x"),
                                 look=1)


def _stub(clock, *, per_period=0.7, change_on=None, truth=None, spike=1.0):
    """Замер: стоимость по истине, пропорциональна просмотру; часы идут.

    `spike` умножает шестигрупповые разбиения: охранник их пропускает по
    оценке, а они всё равно переезжают бюджет.
    """
    truth = truth or _truth()
    calls = []

    def measure(slices, arm, look):
        calls.append(len(slices))
        rows = []
        for keys in slices:
            t = truth(keys, len(slices)) * per_period * look / 2500.0
            if len(slices) == 6:
                t *= spike
            clock.now += t
            rows.append({"keys": [list(k) for k in keys], "cpu_seconds": t,
                         "wall_seconds": t})
        changed = change_on is not None and len(calls) == change_on
        return rows, {("k",): _endpoint(2.0 if changed else 1.0)}
    measure.calls = calls
    return measure


class TheRunnerTests(unittest.TestCase):

    def test_the_look_doubles_until_the_probe_is_long_enough(self):
        clock = _Clock()
        look, probes = T.choose_look({}, _stub(clock))
        self.assertEqual([p["look"] for p in probes], [2, 4, 8])
        self.assertLess(probes[-2]["cpu_seconds"], T.PROBE_MIN_SECONDS)
        self.assertGreaterEqual(probes[-1]["cpu_seconds"], T.PROBE_MIN_SECONDS)
        self.assertEqual(look, round(T.BASELINE_TARGET_SECONDS * 8
                                     / probes[-1]["cpu_seconds"]))

    def test_a_full_run_is_abba_and_passes_on_a_three_level_truth(self):
        clock = _Clock()
        rec = T.run(clock=clock, measure_fn=_stub(clock), changes_fn=list)
        order = list(T.partitions())
        self.assertEqual([r["label"] for r in rec["runs"]],
                         order + order[::-1])
        self.assertEqual(rec["verdict"]["status"], "PASS", rec["verdict"])

    def test_changed_science_refuses_before_measuring(self):
        clock = _Clock()
        stub = _stub(clock)
        with self.assertRaises(T.ScienceNotFrozen):
            T.run(clock=clock, measure_fn=stub,
                  changes_fn=lambda: ["research/python/simulation/x.py"])
        self.assertEqual(stub.calls, [])

    def test_a_split_that_changes_the_result_stops_the_run(self):
        clock = _Clock()
        # три пробы, база, затем P2 — пятый вызов — даёт другой результат
        with self.assertRaises(calibrate.SplitChangedTheScience):
            T.run(clock=clock, measure_fn=_stub(clock, change_on=5),
                  changes_fn=list)

    def test_the_guard_does_not_start_what_cannot_fit(self):
        clock = _Clock()
        rec = T.run(clock=clock, measure_fn=_stub(clock), changes_fn=list,
                    budget=60.0)
        self.assertIn("не начат", rec["incomplete"] or "")
        self.assertEqual(rec["verdict"]["status"], "INCOMPLETE")
        self.assertLess(len(rec["runs"]), 2 * len(T.partitions()))

    def test_overrunning_the_budget_is_incomplete_not_a_bit_more(self):
        clock = _Clock()
        rec = T.run(clock=clock, measure_fn=_stub(clock, spike=40.0),
                    changes_fn=list)
        self.assertIn("превышен", rec["incomplete"] or "")
        self.assertEqual(rec["runs"][-1]["label"], "F6")
        self.assertEqual(rec["verdict"]["status"], "INCOMPLETE")


class TheGateIsNotWiredTests(unittest.TestCase):

    def test_the_planner_does_not_import_the_gate(self):
        code = ("import sys; sys.path[:0] = ['research/python', 'execution'];"
                "import s5b_execution.cli, s5b_execution.scheduler;"
                "print('s5b_execution.threelevel' in sys.modules)")
        done = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "False",
                         "планировщик тянет локальный gate")

    def test_the_share_is_still_unset(self):
        self.assertIsNone(cost.UNDIVIDED_SHARE)
        self.assertTrue(T.COEFFICIENTS_DO_NOT_TRANSFER_TO_PRODUCTION)


if __name__ == "__main__":
    unittest.main()
