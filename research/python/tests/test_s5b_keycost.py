"""Гейты PoC модели стоимости группы ключей.

Модель НЕ подключена к планировщику. Гейты держат три вещи: что проверка
идёт на данных, НЕ вошедших в подгонку; что неподключённость — факт, а
не обещание; и что «сбалансированная» раскладка сбалансирована и по
тому, чего модель не видит.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "execution") not in sys.path:
    sys.path.insert(0, str(ROOT / "execution"))

from s5b_execution import cost, keycost as K                  # noqa: E402

RECORD = json.loads(
    (ROOT / "docs/research/s5b-calibration-4000.json").read_text())


class TheCheckIsOnDataNotUsedForFittingTests(unittest.TestCase):
    """Подгонка точная: 5 неизвестных на 5 наблюдений. Проверка — только g=2."""

    def test_fitting_uses_exactly_variants_1_and_4(self):
        self.assertEqual(K.fit(RECORD)["fitted_on"], [1, 4])

    def test_a_fitted_variant_is_refused_as_a_check(self):
        m = K.fit(RECORD)
        for fitted in (1, 4):
            with self.assertRaises(K.ModelRefused):
                K.check_heldout(m, RECORD, fitted)

    def test_the_heldout_variant_is_reproduced_within_the_declared_tolerance(self):
        got = K.check_heldout(K.fit(RECORD), RECORD, 2)
        self.assertTrue(got["passed"], f"модель не воспроизвела g=2: {got}")
        self.assertLessEqual(got["worst_relative_error"], K.HELDOUT_TOLERANCE)

    def test_the_tolerance_is_declared_and_not_loose(self):
        """Допуск на порядок меньше запаса решения, а не подобран под невязку."""
        self.assertLessEqual(K.HELDOUT_TOLERANCE, 0.05)

    def test_a_model_that_ignores_the_profile_fails_the_same_check(self):
        """Равные ключи — ровно то, что сейчас делает планировщик.

        Та же проверка обязана его ОТВЕРГНУТЬ: иначе она не различает
        модели и ничего не доказывает про нашу.
        """
        m = K.fit(RECORD)
        mean = sum(m["per_key"].values()) / len(m["per_key"])
        flat = {"undivided": m["undivided"],
                "per_key": {t: mean for t in m["per_key"]},
                "fitted_on": m["fitted_on"]}
        self.assertFalse(K.check_heldout(flat, RECORD, 2)["passed"],
                         "проверка пропускает и модель равных ключей")


class ThePocIsNotWiredTests(unittest.TestCase):
    """Неподключённость проверяется импортом, а не обещанием в константе."""

    def test_the_planner_does_not_import_the_model(self):
        code = ("import sys; sys.path[:0] = ['research/python', 'execution'];"
                "import s5b_execution.cli, s5b_execution.scheduler;"
                "print('s5b_execution.keycost' in sys.modules)")
        done = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "False",
                         "планировщик тянет PoC модели стоимости")

    def test_the_share_is_still_unset(self):
        """Измерение есть, а подстановки нет: это отдельное решение."""
        self.assertIsNone(cost.UNDIVIDED_SHARE)


class BalanceOnWhatTheModelCannotSeeTests(unittest.TestCase):
    """Сбалансированность по модели ≠ сбалансированность по ключам."""

    def test_lpt_is_flagged_as_aligned_with_unmeasured_axes(self):
        m = K.scaled(K.fit(RECORD), 16.0)
        bal = K.coordinate_balance(K.balanced_partition(m, 6))
        horizon_rows = bal[2]
        self.assertTrue(any(len(set(r)) > 1 for r in horizon_rows),
                        "LPT вдруг перемешал горизонты — пометка устарела")
        self.assertTrue(K.LPT_ALIGNS_WITH_UNMEASURED_AXES)

    def test_factorial_partition_is_balanced_on_every_coordinate(self):
        bins = K.factorial_partition(6)
        self.assertEqual(sorted(k for b in bins for k in b),
                         sorted(K.KEYS), "не разбиение ключей")
        for axis, rows in K.coordinate_balance(bins).items():
            for row in rows:
                self.assertEqual(len(set(row)), 1,
                                 f"координата {axis}: {row} неравномерно")
            self.assertTrue(all(r == rows[0] for r in rows),
                            f"координата {axis}: группы различаются")

    def test_factorial_costs_the_same_as_lpt_under_the_model(self):
        m = K.scaled(K.fit(RECORD), 16.0)
        lpt = max(K.group_seconds(m, b) for b in K.balanced_partition(m, 6))
        fac = max(K.group_seconds(m, b) for b in K.factorial_partition(6))
        self.assertAlmostEqual(lpt, fac, places=6)

    def test_factorial_is_refused_where_it_is_not_derived(self):
        for g in (4, 5, 7):
            with self.assertRaises(K.ModelRefused):
                K.factorial_partition(g)


class WhatTheModelSaysAbout64000Tests(unittest.TestCase):
    """Условно: линейность по просмотру — допущение, а не замер."""

    def _model(self, factor):
        return K.scaled(K.fit(RECORD), factor)

    def test_contiguous_needs_more_groups_than_balanced(self):
        budget = cost.SHARD_BUDGET_HOURS * 3600
        for factor in (16.0, cost.seconds_for(120.0, 64000)
                       / RECORD["variants"][0]["C_g_sum_wall"]):
            m = self._model(factor)
            contiguous = K.minimum_groups(m, budget, K.worst_contiguous)
            balanced = K.minimum_groups(m, budget, K.worst_balanced)
            self.assertIsNotNone(contiguous)
            self.assertGreater(contiguous, balanced,
                               f"при x{factor:.2f} смежная раскладка не хуже")

    def test_the_planner_weight_underestimates_the_tail_group(self):
        """Вес `T_full * len/72` занижает хвостовую группу смежной раскладки."""
        from s5b_execution.scheduler import key_slices
        m = self._model(16.0)
        full = K.group_seconds(m, K.KEYS)
        tail = key_slices(5)[-1]
        planner = full * len(tail) / len(K.KEYS)
        self.assertGreater(K.group_seconds(m, tail), 1.5 * planner,
                           "хвост оказался не тяжелее оценки планировщика")


if __name__ == "__main__":
    unittest.main()
