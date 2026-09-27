"""Гейты сухого плана полного 64000 при balanced-g12.

Реестр 16000 (7 МБ, артефакт s5b-reduced-16000) в репозиторий не кладётся;
тесты работают на подставном реестре. Настоящий не выбросил ни одного
юнита, поэтому записанный результат воспроизводится и на пустом.
"""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "execution") not in sys.path:
    sys.path.insert(0, str(ROOT / "execution"))

from s5b_execution import cost, dryplan as D, scheduler            # noqa: E402
from s5b_execution.identity import EndpointId                       # noqa: E402
from s5b_execution.layout import balanced_slices                    # noqa: E402
from s5b_execution.scheduler import FRACTIONS, KEYS, key_slices     # noqa: E402


class _Ledger:
    """Подставной реестр: закрыты ровно перечисленные концы."""

    def __init__(self, settled=()):
        self.settled = set(settled)

    def is_settled(self, identity: EndpointId) -> bool:
        return (identity.arm, tuple(identity.key), identity.fraction) in self.settled

    def unit_is_needed(self, arm, keys, fractions) -> bool:
        return any((arm, tuple(k), f) not in self.settled
                   for k in keys for f in fractions)


def _close(arms, keys_by_arm=None):
    out = set()
    for tag in arms:
        for k in (keys_by_arm or {}).get(tag, KEYS):
            for f in FRACTIONS:
                out.add((tag, tuple(k), f))
    return out


class TheWeightIsTheDeclaredEnvelopeTests(unittest.TestCase):

    def test_the_anchor_arm_weighs_exactly_the_pilot_worst_unit(self):
        self.assertAlmostEqual(D.weight(120.0), 8835.4, places=6)

    def test_the_weight_follows_the_envelope_shape_only(self):
        for rate in (0.84, 6.0, 30.0, 96.0):
            self.assertAlmostEqual(
                D.weight(rate) / D.weight(120.0),
                cost.seconds_for(rate, 64000) / cost.seconds_for(120.0, 64000))
        self.assertLess(D.weight(0.84), D.weight(120.0))


class TheRecordedPlanIsAStopTests(unittest.TestCase):
    """Записанный результат: 1872 юнита, 495 заданий против 256 — STOP."""

    @classmethod
    def setUpClass(cls):
        cls.got = D.plan(_Ledger())

    def test_nothing_is_dropped_and_the_matrix_is_what_stops_it(self):
        g = self.got
        self.assertEqual((g["units_possible"], g["units_needed"]), (1872, 1872))
        self.assertEqual(g["jobs_lpt"], 495)
        self.assertEqual(g["status"], "STOP")
        self.assertEqual(len(g["stops"]), 1)
        self.assertIn("потолка матрицы", g["stops"][0])

    def test_the_reported_figures_are_reproduced(self):
        g = self.got
        self.assertEqual(g["total_cpu_hours"], 1225.7)
        self.assertEqual(g["heaviest_job_hours"], 2.497)
        self.assertEqual(g["heaviest_job_stress_hours"], 4.894)
        self.assertEqual(g["makespan_hours"], 206.2)
        self.assertEqual(g["makespan_stress_hours"], 404.2)
        self.assertEqual(g["identity_problems"], [])


class TheGatesDecideWhatTheyMustTests(unittest.TestCase):

    def test_a_ledger_that_leaves_only_the_heaviest_arms_passes(self):
        heavy = {t for t, a in scheduler.arms().items()
                 if a["effective_rate"] == 120.0}
        got = D.plan(_Ledger(_close(set(scheduler.arms()) - heavy)))
        self.assertEqual(got["units_needed"], 12 * len(heavy))
        self.assertLessEqual(got["jobs_lpt"], 256)
        self.assertEqual(got["status"], "PASS", got["stops"])

    def test_a_fully_closed_group_is_dropped_by_the_ledger(self):
        tag = next(iter(scheduler.arms()))
        group = balanced_slices(12)[0]
        needed, possible = D.units(_Ledger(_close({tag}, {tag: group})))
        self.assertEqual((len(needed), possible), (1871, 1872))

    def test_a_stress_over_the_timeout_is_a_stop(self):
        heavy = {t for t, a in scheduler.arms().items()
                 if a["effective_rate"] == 120.0}
        with mock.patch.object(D, "STRESS", 3.0):
            got = D.plan(_Ledger(_close(set(scheduler.arms()) - heavy)))
        self.assertEqual(got["status"], "STOP")
        self.assertTrue(any("таймаута" in s for s in got["stops"]))

    def test_a_contiguous_unit_breaks_the_layout(self):
        from simulation import s5b_shard as S
        tag = next(iter(scheduler.arms()))
        bad = [S.Unit(arm=tag, look=64000, keys=tuple(key_slices(12)[0]),
                      weight=0.0)]
        problems = D.identity_problems(bad, _Ledger(_close(scheduler.arms())))
        self.assertTrue(any("balanced-g12" in p for p in problems))

    def test_an_open_endpoint_without_a_unit_breaks_ledger_semantics(self):
        problems = D.identity_problems([], _Ledger())
        self.assertTrue(any("не покрыт" in p for p in problems))


class TheDryPlanIsWiredOnlyIntoMultiRunTests(unittest.TestCase):
    """Его юниты берёт многопрогонный план 64000 — и только он."""

    def test_the_single_run_planner_still_refuses_64000(self):
        with self.assertRaises(cost.SplitEconomyUnmeasured):
            scheduler.units_for(64000)
        self.assertIsNone(cost.UNDIVIDED_SHARE)

    def test_the_multirun_units_are_exactly_the_dry_plan_units(self):
        from s5b_execution import multirun
        led = _Ledger(_close({next(iter(scheduler.arms()))}))
        want, _ = D.units(led)
        got = multirun.units(64000, led)
        self.assertEqual([(u.task_id, u.weight) for u in got],
                         [(u.task_id, u.weight) for u in want])
        self.assertEqual(len(got), 1872 - 12)

    def test_the_third_stop_is_a_refusal_there(self):
        from s5b_execution import multirun
        with mock.patch.object(D, "identity_problems",
                               lambda needed, ledger: ["сломано"]):
            with self.assertRaises(multirun.MultiRunRefused):
                multirun.units(64000, _Ledger())

    def test_64000_is_not_planned_without_the_prior_ledger(self):
        from s5b_execution import multirun
        with self.assertRaises(multirun.MultiRunRefused):
            multirun.units(64000, None)

    def test_keycost_stays_unwired(self):
        import subprocess
        code = ("import sys; sys.path[:0] = ['research/python', 'execution'];"
                "import s5b_execution.cli, s5b_execution.multirun;"
                "print('s5b_execution.keycost' in sys.modules)")
        done = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), "False", done.stderr)


if __name__ == "__main__":
    unittest.main()
