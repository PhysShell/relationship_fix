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


def _reference_set(periods, z, lo, hi):
    """Эталон на Decimal(60): те же сегменты, НО без наружного расширения.

    Правило вклада повторено намеренно, а не импортировано: эталон проверяет,
    что быстрый путь не теряет допустимые λ, а не что оба считают одинаково.
    """
    from decimal import Decimal, getcontext
    getcontext().prec = 60
    D = Decimal
    count = len(periods)
    edges = {D(repr(lo)), D(repr(hi))}
    for pieces in periods:
        for i, a in enumerate(pieces):
            for b in pieces[i + 1:]:
                if a.n != b.n:
                    lam = (D(repr(a.b)) - D(repr(b.b))) / (D(repr(a.n)) - D(repr(b.n)))
                    if D(repr(lo)) < lam < D(repr(hi)):
                        edges.add(lam)
    edges = sorted(edges)
    out = []
    for left, right in zip(edges, edges[1:]):
        if right - left <= 0:
            continue
        middle = (left + right) / 2
        active = [min(pieces, key=lambda p: D(repr(p.b)) - middle * D(repr(p.n)))
                  for pieces in periods]
        mb = sum(D(repr(p.b)) for p in active) / count
        mn = sum(D(repr(p.n)) for p in active) / count
        s_bb = sum((D(repr(p.b)) - mb) ** 2 for p in active)
        s_bn = sum((D(repr(p.b)) - mb) * (D(repr(p.n)) - mn) for p in active)
        s_nn = sum((D(repr(p.n)) - mn) ** 2 for p in active)
        scale = D(repr(z)) ** 2 / (count - 1)
        a = count * mn * mn - scale * s_nn
        b = -2 * count * mb * mn + 2 * scale * s_bn
        c = count * mb * mb - scale * s_bb
        if s_nn == 0 and s_bb == 0:
            out.append((float(left), float(right)))
            continue
        if a == 0:
            if b == 0:
                if c <= 0:
                    out.append((float(left), float(right)))
                continue
            edge = -c / b
            piece = (left, min(right, edge)) if b > 0 else (max(left, edge), right)
            if piece[0] <= piece[1]:
                out.append((float(piece[0]), float(piece[1])))
            continue
        disc = b * b - 4 * a * c
        if disc < 0:
            if a < 0:
                out.append((float(left), float(right)))
            continue
        root = disc.sqrt()
        r1, r2 = (-b - root) / (2 * a), (-b + root) / (2 * a)
        low, high = (min(r1, r2), max(r1, r2))
        if a > 0:
            piece = (max(left, low), min(right, high))
            if piece[0] <= piece[1]:
                out.append((float(piece[0]), float(piece[1])))
        else:
            if left < low:
                out.append((float(left), float(min(right, low))))
            if high < right:
                out.append((float(max(left, high)), float(right)))
    return out


class NumericalEnclosureTests(unittest.TestCase):
    """Вся статистика может быть верной, а покрытие уехать на sqrt()."""

    def _contains(self, computed, point):
        return any(a - 1e-6 <= point <= b + 1e-6 for a, b in computed)

    def test_the_computed_set_contains_the_high_precision_set(self):
        import random
        rng = random.Random(99)
        checked = 0
        for _ in range(120):
            count = rng.randint(3, 12)
            periods = []
            for _ in range(count):
                n_pieces = rng.randint(1, 2)
                pieces = tuple(Piece(float(rng.randint(1, 8)),
                                     float(rng.randint(0, 40) * 60))
                               for _ in range(n_pieces))
                periods.append(pieces)
            computed = acceptance_set(periods, z=Z, lo=0.0, hi=3600.0)
            reference = _reference_set(periods, Z, 0.0, 3600.0)
            checked += 1
            for a, b in reference:
                for point in (a, b, (a + b) / 2):
                    self.assertTrue(self._contains(computed, point),
                                    (periods, (a, b), point, computed))
        self.assertGreater(checked, 100)

    def test_a_double_root_is_not_lost_to_two_ulp(self):
        """disc == 0 и disc чуть отрицательный обязаны дать область, а не пустоту."""
        from coarsening.inversion import _solve
        # (λ − 100)² <= 0: единственная точка 100
        self.assertTrue(_solve((1.0, -200.0, 10000.0), 0.0, 3600.0))
        # тот же корень, сдвинутый в отрицательный дискриминант на ulp
        self.assertTrue(_solve((1.0, -200.0, 10000.0 + 1e-10), 0.0, 3600.0))

    def test_a_genuinely_empty_quadratic_stays_empty(self):
        """Расширение не должно выдумывать область там, где её нет."""
        from coarsening.inversion import _solve
        self.assertEqual(_solve((1.0, 0.0, 1.0e6), 0.0, 3600.0), [])

    def test_the_stable_formula_survives_severe_cancellation(self):
        """b² >> 4ac: прямая формула здесь теряет один корень."""
        from coarsening.inversion import _roots
        low, high = _roots(1.0, -1e8, 1.0)
        self.assertAlmostEqual(low, 1e-8, delta=1e-12)
        self.assertAlmostEqual(high / 1e8, 1.0, places=9)

    def test_constant_quadratics_are_handled(self):
        from coarsening.inversion import _solve
        self.assertEqual(_solve((0.0, 0.0, -1.0), 5.0, 9.0), [(5.0, 9.0)])
        self.assertEqual(_solve((0.0, 0.0, 1.0), 5.0, 9.0), [])
