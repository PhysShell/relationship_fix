"""Инверсия теста обязана возвращать ПОЛНОЕ множество принятия.

Найдено восьмым враждебным чтением, и находка не про изломы: у
стьютентизованной статистики знаменатель тоже зависит от λ, поэтому
монотонность числителя связности множества не даёт.
"""

import unittest

from coarsening.inversion import (Piece, ZERO_VARIANCE_IS_ACCEPTED,
                                  acceptance_set, convex_hull_interval, psi)

Z = 1.959963984540054


class FiellerGoldenTests(unittest.TestCase):
    """ПОСТОЯННЫЙ СВИДЕТЕЛЬ. Ни один прежний подозреваемый не участвует:

        N >= 1 везде          да
        корень единственный   да
        изломов нет вовсе     да
        корень внутренний     да
        наблюдения ограничены да

    а «доверительное множество — один интервал вокруг корня» всё равно ложь.
    """

    PERIODS = [(Piece(100.0, 131520.0),)] + [(Piece(1.0, 720.0),)] * 24
    HORIZON = 3600.0

    def test_the_root_is_unique_and_interior(self):
        total_b = sum(p[0].b for p in self.PERIODS)
        total_n = sum(p[0].n for p in self.PERIODS)
        self.assertAlmostEqual(total_b / total_n, 1200.0)

    def test_no_period_has_a_kink_at_all(self):
        for pieces in self.PERIODS:
            self.assertEqual(len(pieces), 1, "у аффинной ψ изломов быть не может")

    def test_the_acceptance_set_is_disconnected(self):
        got = acceptance_set(self.PERIODS, z=Z, lo=0.0, hi=self.HORIZON)
        self.assertEqual(len(got), 2, got)
        self.assertAlmostEqual(got[0][0], 0.0)
        self.assertAlmostEqual(got[0][1], 1273.95, places=1)
        self.assertAlmostEqual(got[1][0], 1535.81, places=1)
        self.assertAlmostEqual(got[1][1], self.HORIZON)

    def test_the_hole_really_rejects_and_the_far_piece_really_accepts(self):
        """Проверка против независимого вычисления статистики."""
        import math
        import statistics

        def accepted(lam):
            values = [psi(p, lam) for p in self.PERIODS]
            spread = statistics.stdev(values)
            if spread == 0.0:
                return True
            return abs(math.sqrt(len(values)) * statistics.fmean(values) / spread) <= Z

        for lam in (0.0, 600.0, 1200.0, 1600.0, 2500.0, 3600.0):
            self.assertTrue(accepted(lam), lam)
        for lam in (1300.0, 1400.0, 1500.0):
            self.assertFalse(accepted(lam), lam)

    def test_keeping_only_the_component_around_the_root_loses_a_real_piece(self):
        """Вот эта потеря и есть запрещённый shortcut."""
        got = acceptance_set(self.PERIODS, z=Z, lo=0.0, hi=self.HORIZON)
        around_root = [c for c in got if c[0] <= 1200.0 <= c[1]]
        self.assertEqual(len(around_root), 1)
        self.assertLess(around_root[0][1], self.HORIZON,
                        "компонента вокруг корня НЕ покрывает дальний кусок")
        self.assertEqual(convex_hull_interval(got), (0.0, self.HORIZON))

    def test_the_hull_is_the_only_safe_interval(self):
        got = acceptance_set(self.PERIODS, z=Z, lo=0.0, hi=self.HORIZON)
        low, high = convex_hull_interval(got)
        for component in got:
            self.assertGreaterEqual(component[0], low)
            self.assertLessEqual(component[1], high)


class WellBehavedInversionTests(unittest.TestCase):
    """В приличном случае множество всё-таки одно."""

    def test_a_homogeneous_arm_gives_a_single_component(self):
        periods = [(Piece(1.0, 1200.0 + 10 * (i % 7 - 3)),) for i in range(40)]
        got = acceptance_set(periods, z=Z, lo=0.0, hi=3600.0)
        self.assertEqual(len(got), 1, got)
        low, high = got[0]
        self.assertLess(low, 1200.0)
        self.assertGreater(high, 1200.0)

    def test_a_piecewise_period_is_handled_as_a_minimum(self):
        pieces = (Piece(1.0, 720.0), Piece(2.0, 1500.0))
        self.assertAlmostEqual(psi(pieces, 0.0), 720.0)
        self.assertAlmostEqual(psi(pieces, 1000.0), -500.0)

    def test_zero_variance_is_accepted_not_rejected(self):
        """В истинном λ0 среднее ноль; отвергнуть там из-за нулевого
        разброса значило бы терять покрытие."""
        self.assertTrue(ZERO_VARIANCE_IS_ACCEPTED)
        periods = [(Piece(1.0, 1200.0),)] * 30
        got = acceptance_set(periods, z=Z, lo=0.0, hi=3600.0)
        self.assertEqual(got, [(0.0, 3600.0)])

    def test_an_empty_or_tiny_arm_refuses_to_narrow_anything(self):
        self.assertEqual(acceptance_set([], z=Z, hi=3600.0), [(0.0, 3600.0)])
        self.assertEqual(acceptance_set([(Piece(1.0, 5.0),)], z=Z, hi=3600.0),
                         [(0.0, 3600.0)])


class InversionCoverageTests(unittest.TestCase):
    """Покрытие проверяется ЧЛЕНСТВОМ в множестве, а не попаданием в интервал."""

    def test_the_full_set_covers_the_truth_at_the_nominal_rate(self):
        import random
        rng = random.Random(4)
        true = 600.0
        covered = trials = 0
        for _ in range(200):
            periods = [(Piece(1.0, true + rng.gauss(0.0, 200.0)),) for _ in range(60)]
            got = acceptance_set(periods, z=Z, lo=0.0, hi=3600.0)
            trials += 1
            covered += any(a <= true <= b for a, b in got)
        self.assertGreater(covered / trials, 0.90, covered / trials)
