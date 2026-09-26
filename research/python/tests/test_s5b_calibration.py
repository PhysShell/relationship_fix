"""Гейты калибровки экономии деления ключей.

Ось деления не включалась ни на 4000, ни на 16000: `groups_needed == 1` у
всех рук. Поэтому здесь проверяется не «функция возвращает число», а то,
что измерение мерит ИМЕННО раскладку планировщика, что расхождение науки
останавливает опыт, и что нехватка времени задания записывается как
INCOMPLETE, а не превращается в удобное число.
"""

from __future__ import annotations

import io
import contextlib
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "execution") not in sys.path:
    sys.path.insert(0, str(ROOT / "execution"))

from s5b_execution import calibrate, cli, cost, scheduler       # noqa: E402

LIGHT = "r1.5:c1.0:R0:m1.0"          # самая дешёвая рука сетки
TOY = 16                             # игрушечный просмотр: наука настоящая


class KeySlicesArePartitionTests(unittest.TestCase):
    """Разрез ключей — разбиение, а не «примерно все ключи»."""

    def test_every_key_exactly_once_for_every_group_count(self):
        keys = list(scheduler.KEYS)
        for groups in list(range(1, 13)) + [17, 36, 71, 72]:
            slices = scheduler.key_slices(groups)
            flat = [k for s in slices for k in s]
            self.assertEqual(sorted(flat, key=repr), sorted(keys, key=repr),
                             f"g={groups}: покрытие ключей нарушено")
            self.assertEqual(len(flat), len(set(flat)),
                             f"g={groups}: ключ попал в две группы")
            self.assertLessEqual(len(slices), groups,
                                 f"g={groups}: групп больше заказанного")

    def test_refuses_impossible_group_counts(self):
        for bad in (0, -1, len(scheduler.KEYS) + 1):
            with self.assertRaises(scheduler.PlanRefused):
                scheduler.key_slices(bad)


class CalibrationMeasuresThePlannerLayoutTests(unittest.TestCase):
    """Калибровка обязана звать РАСКЛАДКУ ПЛАНИРОВЩИКА, а не свою копию.

    Вторая реализация того же разреза означала бы, что измеряется не то,
    что потом исполняется. Гейт поведенческий: подменяется функция
    планировщика, и калибровка обязана поехать по подмене.
    """

    def test_calibration_goes_through_scheduler_key_slices(self):
        seen = []
        real = scheduler.key_slices

        def spy(groups):
            seen.append(groups)
            return real(groups)

        scheduler.key_slices = spy
        calibrate.key_slices = spy
        try:
            calibrate.run(LIGHT, TOY, deadline=time.monotonic() + 600)
        finally:
            scheduler.key_slices = real
            calibrate.key_slices = real
        self.assertEqual(seen, [1, 2, 4],
                         "калибровка режет ключи не раскладкой планировщика")

    def test_the_planner_uses_the_same_function(self):
        real = scheduler.key_slices
        scheduler.key_slices = lambda groups: (scheduler.KEYS[:1],)
        try:
            units = scheduler.units_for(4000)
        finally:
            scheduler.key_slices = real
        self.assertTrue(all(len(u.keys) == 1 for u in units),
                        "планировщик режет ключи своей копией")


class SplitPreservesTheScienceTests(unittest.TestCase):
    """Научный гейт: слитый делёный результат равен неделёному.

    Настоящая наука на игрушечном просмотре: проверяется механизм, а не
    длительность. Производственный замер идёт на 4000 отдельным заданием.
    """

    def test_two_and_four_groups_give_the_identical_result(self):
        rec = calibrate.run(LIGHT, TOY, deadline=time.monotonic() + 600)
        self.assertEqual(rec["correctness"], "PASS")
        self.assertEqual([c["groups"] for c in rec["comparisons"]], [2, 4])
        for c in rec["comparisons"]:
            self.assertEqual((c["missing"], c["unexpected"], c["differing"]),
                             (0, 0, 0), f"деление на {c['groups']} изменило науку")
            self.assertEqual(c["baseline_endpoints"], c["merged_endpoints"])
            self.assertEqual(c["baseline_endpoints"],
                             len(scheduler.KEYS) * len(scheduler.FRACTIONS))

    def test_a_changed_value_is_caught_not_only_a_missing_key(self):
        """Расхождение ЗНАЧЕНИЯ ловится, а не только пропажа ключа."""
        from simulation import s5b_shard as S
        real_merge = S.merge

        def tamper(arm, look, parts, *, expected):
            merged = real_merge(arm, look, parts, expected=expected)
            if len(parts) > 1:                      # портим только делёный
                name = sorted(merged, key=repr)[0]
                e = merged[name]
                merged[name] = e.__class__(
                    key=e.key, delta_fraction=e.delta_fraction,
                    point=e.point + 1.0, low=e.low, high=e.high,
                    radius=e.radius, status=e.status, look=e.look)
            return merged

        S.merge = tamper
        calibrate.S.merge = tamper
        try:
            with self.assertRaises(calibrate.SplitChangedTheScience) as caught:
                calibrate.run(LIGHT, TOY, deadline=time.monotonic() + 600)
        finally:
            S.merge = real_merge
            calibrate.S.merge = real_merge
        self.assertIn("изменило результат", str(caught.exception))

    def test_a_missing_endpoint_is_caught(self):
        from s5b_execution import reduction
        key = list(scheduler.KEYS[0])

        def end(fraction, point):
            return reduction.rehydrate(
                {"key": key, "fraction": fraction, "point": point,
                 "low": point - 1.0, "high": point + 1.0, "radius": 1.0,
                 "status": "MC_PRECISION_ACHIEVED", "look": 4000})

        base = {(tuple(key), 0.1): end(0.1, 5.0),
                (tuple(key), 0.01): end(0.01, 7.0)}
        merged = {(tuple(key), 0.1): base[(tuple(key), 0.1)]}
        verdict = calibrate.compare(base, merged, 2)
        self.assertFalse(verdict["identical"])
        self.assertEqual((verdict["missing"], verdict["unexpected"],
                          verdict["differing"]), (1, 0, 0))


class TheShareIsAlgebraNotFittingTests(unittest.TestCase):
    """`s` выводится алгеброй, и НЕ усредняется между вариантами."""

    def test_matches_the_declared_formulas(self):
        got = calibrate.amdahl({1: 100.0, 2: 110.0, 4: 130.0})
        self.assertAlmostEqual(got["s_2"], 110.0 / 100.0 - 1.0, places=6)
        self.assertAlmostEqual(got["s_4"], (130.0 / 100.0 - 1.0) / 3.0, places=6)

    def test_disagreement_is_reported_not_averaged(self):
        got = calibrate.amdahl({1: 100.0, 2: 200.0, 4: 130.0})
        self.assertEqual(sorted(got), ["s_2", "s_4"])
        self.assertNotAlmostEqual(got["s_2"], got["s_4"], places=3)
        self.assertNotIn("s", got, "варианты усреднены в одно удобное число")

    def test_perfect_split_gives_zero_share(self):
        self.assertAlmostEqual(
            calibrate.amdahl({1: 100.0, 2: 100.0, 4: 100.0})["s_4"], 0.0)


class ThresholdsForTheWorstUnitTests(unittest.TestCase):
    """Пороги, объявленные протоколом kill-first, обязаны сходиться."""

    #: худший полный юнит ступени 64000 — 9.74 ч, а не 7.81 ч первого отказа
    def test_worst_unit_at_64000(self):
        from simulation import s5b_shard as S
        worst = max(cost.seconds_for(a["effective_rate"], 64_000)
                    for a in S.production_arms())
        self.assertAlmostEqual(worst / 3600.0, 9.74, places=2)

    def test_declared_thresholds(self):
        worst = 9.739 * 3600
        budget = cost.SHARD_BUDGET_HOURS * 3600
        for groups, share in ((4, 0.00890), (5, 0.07084), (6, 0.10801),
                              (8, 0.15048), (72, 0.24620)):
            at = calibrate.groups_for_target(worst, budget, share * 0.999)
            self.assertLessEqual(
                at, groups,
                f"при s={share} должно хватать {groups} групп, нужно {at}")
        self.assertIsNone(calibrate.groups_for_target(worst, budget, 0.25),
                          "s = 0.25 обязан быть KILL для цели 2.5 ч")


class TheTimeGuardRefusesInsteadOfGuessingTests(unittest.TestCase):
    """Нехватка времени — INCOMPLETE, а не измерение по обрезанным данным."""

    def test_a_variant_that_cannot_finish_is_not_started(self):
        rec = calibrate.run(LIGHT, TOY, deadline=time.monotonic())
        self.assertIsNotNone(rec["incomplete"])
        self.assertIn("не начат", rec["incomplete"])
        self.assertEqual([v["groups"] for v in rec["variants"]], [1],
                         "после отказа охранника опыт продолжился")
        self.assertEqual(rec["shares"], {},
                         "доля посчитана по одному варианту")
        self.assertEqual(rec["correctness"], "NOT_MEASURED")

    def test_the_guard_uses_the_worst_case_not_the_hoped_case(self):
        self.assertTrue(calibrate.WORST_CASE_COST_IS_G_TIMES_BASELINE)


class TheCliRefusesWithoutAGuardTests(unittest.TestCase):

    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(argv)
        return buf.getvalue()

    def test_calibration_without_a_deadline_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as caught:
                self._run(["calibrate", "--look", str(TOY), "--arm", LIGHT,
                           "--out", tmp])
            self.assertIn("охранника времени", str(caught.exception))

    def test_calibration_without_an_arm_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as caught:
                self._run(["calibrate", "--look", str(TOY),
                           "--deadline-minutes", "10", "--out", tmp])
            self.assertIn("--arm", str(caught.exception))

    def test_an_arm_outside_the_frozen_grid_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(calibrate.SplitChangedTheScience):
                calibrate.run("выдумка", TOY, deadline=time.monotonic() + 60)

    def test_the_artifact_carries_the_implications_for_64000(self):
        env = {"SCIENCE_SHA": "a" * 40, "EXECUTION_SHA": "b" * 40,
               "REQUEST_SHA": "c" * 40}
        keep = {k: os.environ.get(k) for k in env}
        try:
            os.environ.update(env)
            with tempfile.TemporaryDirectory() as tmp:
                self._run(["calibrate", "--look", str(TOY), "--arm", LIGHT,
                           "--deadline-minutes", "10", "--out", tmp])
                got = json.loads(
                    (pathlib.Path(tmp) / "calibration.json").read_text())
        finally:
            for name, value in keep.items():
                os.environ.pop(name, None)
                if value is not None:
                    os.environ[name] = value
        self.assertEqual(got["correctness"], "PASS")
        self.assertIn("s_2", got["implications"])
        self.assertIn("groups_for_budget", got["implications"]["s_2"])
        self.assertAlmostEqual(got["worst_unit_64000_hours"], 9.74, places=2)
        self.assertEqual(got["provenance"]["science_sha"], "a" * 40)
        # разброс между группами записан: planner интересует худшая группа
        for v in got["variants"]:
            self.assertIn("spread_max_over_min", v)
            self.assertIn("W_g_max_wall", v)


if __name__ == "__main__":
    unittest.main()
