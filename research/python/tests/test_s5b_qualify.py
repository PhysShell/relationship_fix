"""Гейты самой квалификации: быстрый путь обязан БЫТЬ производственным.

Быстрый путь введён потому, что производственный `acceptance_set` на
`M = 64000` x 4000 реплик считается часами. Подменить проверяемую функцию
её же переписанной версией и не сказать об этом — ровно тот способ, которым
проверки перестают что-либо проверять. Поэтому эквивалентность здесь
ПРОВЕРЯЕТСЯ, и на РАБОЧИХ `M`, а не только на игрушечных.
"""

from __future__ import annotations

import random
import unittest
from fractions import Fraction
from statistics import NormalDist

from coarsening.inversion import Piece, acceptance_set
from simulation import s5b_precision as PR
from tools import s5b_qualify as Q


class Recorder:
    """Накопитель, который ДОПОЛНИТЕЛЬНО хранит развёрнутые периоды."""

    def __init__(self, inner, catalogue=None):
        self.inner = inner
        self.catalogue = catalogue
        self.periods = []

    def add(self, n, b):
        self.inner.add(n, b)
        self.periods.append((Piece(float(n), b),))

    def add_type(self, index):
        self.inner.add_type(index)
        self.periods.append(self.catalogue[index])


def record(scenario, size, seed=0):
    inner = scenario.new_sample()
    catalogue = getattr(inner, "catalogue", None)
    keeper = Recorder(inner, catalogue)
    rng = random.Random(f"{scenario.name}:{seed}")
    for _ in range(size):
        scenario.draw(rng, keeper)
    return keeper


class FastPathIsTheProductionPathTests(unittest.TestCase):
    """Быстрый путь — та же математика и ТОТ ЖЕ `_solve`, но от агрегатов."""

    #: домен 3600 секунд: 1e-6 это 3e-10 относительной ошибки
    TOLERANCE = 1e-6

    def _compare(self, scenario, size, z):
        keeper = record(scenario, size)
        want = acceptance_set(keeper.periods, z=z, lo=Q.LO, hi=Q.HI)
        got = Q.accept_from_segments(keeper.inner.segments(Q.LO, Q.HI),
                                     z=z, lo=Q.LO, hi=Q.HI)
        self.assertEqual(len(want), len(got),
                         f"{scenario.name} M={size}: {want} != {got}")
        worst = 0.0
        for (wa, wb), (ga, gb) in zip(want, got):
            worst = max(worst, abs(wa - ga), abs(wb - gb))
        self.assertLessEqual(worst, self.TOLERANCE,
                             f"{scenario.name} M={size}: расхождение {worst}")
        return worst

    def test_every_scenario_agrees_at_small_and_working_sizes(self):
        worst = 0.0
        for scenario in Q.SCENARIOS:
            for size in (5, 17, 100, 4_000):
                worst = max(worst, self._compare(scenario, size,
                                                 Q.Z_DECLARED))
        self.assertLess(worst, self.TOLERANCE)

    def test_agreement_holds_at_the_top_of_the_production_ladder(self):
        """16000 и 64000 — те самые `M`, на которых и будет считаться."""
        for name in ("fieller", "degenerate_variance"):
            scenario = next(s for s in Q.SCENARIOS if s.name == name)
            for size in (16_000, 64_000):
                self._compare(scenario, size, Q.Z_DECLARED)

    def test_agreement_holds_for_every_declared_z(self):
        for _, z in Q.CONFIGS:
            for scenario in Q.SCENARIOS:
                self._compare(scenario, 300, z)

    def test_the_root_matches_a_bisection_on_the_expanded_sample(self):
        for scenario in Q.SCENARIOS:
            keeper = record(scenario, 500)
            segments = keeper.inner.segments(Q.LO, Q.HI)
            got = Q.root_from_segments(segments, Q.LO, Q.HI)
            lo, hi = Q.LO, Q.HI
            for _ in range(80):
                mid = (lo + hi) / 2.0
                total = sum(min(p.b - mid * p.n for p in period)
                            for period in keeper.periods)
                if total > 0.0:
                    lo = mid
                else:
                    hi = mid
            self.assertAlmostEqual(got, hi, places=6, msg=scenario.name)


class ScenarioTruthIsAnalyticTests(unittest.TestCase):
    """λ0 объявлен в закрытой форме. Проверяется, а не обещается."""

    def test_catalogue_scenarios_have_an_exact_population_root(self):
        """Точная арифметика: E[ψ(λ)] по каталогу, корень в рациональных."""
        cases = ((Q.KINK_CATALOGUE, (Fraction(1, 2), Fraction(1, 4), Fraction(1, 4)),
                  Fraction(1200)),
                 (Q.BOUNDARY_SIGNED_CATALOGUE, (Fraction(1, 2), Fraction(1, 2)),
                  Fraction(0)),
                 (Q.DEGENERATE_CATALOGUE, (Fraction(1, 2), Fraction(1, 2)),
                  Fraction(1200)))
        for catalogue, weights, root in cases:
            def expectation(lam):
                return sum(w * min(Fraction(int(p.b * 100), 100)
                                   - lam * Fraction(int(p.n * 100), 100)
                                   for p in pieces)
                           for w, pieces in zip(weights, catalogue))
            self.assertEqual(expectation(root), 0,
                             f"{catalogue}: E[psi({root})] != 0")
            self.assertGreater(expectation(root - Fraction(1, 1000)), 0)
            self.assertLess(expectation(root + Fraction(1, 1000)), 0)

    def test_moment_scenarios_are_exactly_b_equals_truth_times_n_plus_noise(self):
        """Шум аддитивен и центрирован, значит E[B] = λ0·E[N] ТОЧНО."""
        checks = {"regular": (lambda r: (r.randint(1, 9), r.gauss(0.0, 400.0))),
                  "heavy_tail": (lambda r: (100 if r.random() < 0.04 else 1,
                                            r.gauss(0.0, 200.0))),
                  "zero_heavy": None}
        checks.pop("zero_heavy")
        for name, replay in checks.items():
            scenario = next(s for s in Q.SCENARIOS if s.name == name)
            keeper = record(scenario, 200)
            mirror = random.Random(f"{name}:0")
            for period in keeper.periods:
                n, noise = replay(mirror)
                self.assertEqual(period[0].n, float(n), name)
                #: 1e-6 на значениях до 1.2e7 — это 1e-13 относительной
                #: ошибки, то есть представимость double, а не смещение
                self.assertAlmostEqual(period[0].b - scenario.truth * n, noise,
                                       delta=1e-6, msg=name)

    def test_the_zero_boundary_scenario_puts_the_truth_on_the_domain_edge(self):
        scenario = next(s for s in Q.SCENARIOS if s.name == "boundary_zero")
        self.assertEqual(scenario.truth, Q.LO)
        keeper = record(scenario, 400)
        self.assertTrue(all(p[0].b == 0.0 for p in keeper.periods))
        self.assertGreater(len({p[0].n for p in keeper.periods}), 1)


class AdversarialGeometryIsReachedTests(unittest.TestCase):
    """Набор B-7 обязан ДОСТИГАТЬ геометрии, ради которой он написан."""

    def test_the_fieller_scenario_really_produces_disconnected_sets(self):
        seen = 0
        for seed in range(40):
            keeper = record(next(s for s in Q.SCENARIOS if s.name == "fieller"),
                            4_000, seed)
            got = Q.accept_from_segments(keeper.inner.segments(Q.LO, Q.HI),
                                         z=Q.Z_DECLARED)
            seen += len(got) > 1
        self.assertGreater(seen, 20, "несвязность не достигается — сценарий пуст")

    def test_the_kink_scenario_puts_a_breakpoint_exactly_at_the_truth(self):
        scenario = next(s for s in Q.SCENARIOS if s.name == "kink_at_root")
        keeper = record(scenario, 1_000)
        edges = [s.left for s in keeper.inner.segments(Q.LO, Q.HI)]
        self.assertIn(scenario.truth, edges)

    def test_the_degenerate_scenario_really_has_zero_variance_at_the_truth(self):
        scenario = next(s for s in Q.SCENARIOS if s.name == "degenerate_variance")
        keeper = record(scenario, 1_000)
        holding = [s for s in keeper.inner.segments(Q.LO, Q.HI)
                   if s.left <= scenario.truth <= s.right]
        self.assertTrue(holding)
        for segment in holding:
            self.assertEqual((segment.s_bb, segment.s_nn, segment.s_bn),
                             (0.0, 0.0, 0.0))

    def test_the_zero_boundary_scenario_is_an_exact_double_root(self):
        """`b ≡ 0` => форма вырождается в `a·λ² <= 0`, `a > 0`: корень ДВОЙНОЙ."""
        scenario = next(s for s in Q.SCENARIOS if s.name == "boundary_zero")
        keeper = record(scenario, 2_000)
        got = Q.accept_from_segments(keeper.inner.segments(Q.LO, Q.HI),
                                     z=Q.Z_DECLARED)
        self.assertEqual(len(got), 1)
        self.assertLessEqual(got[0][0], scenario.truth)
        self.assertLessEqual(got[0][1] - got[0][0], 1e-3)
        self.assertEqual(acceptance_set(keeper.periods, z=Q.Z_DECLARED,
                                        lo=Q.LO, hi=Q.HI)[0][0], got[0][0])

    def test_the_narrow_control_expectation_is_declared_with_a_reason(self):
        """Какие сценарии контроль уронить НЕ МОЖЕТ — сказано до прогона."""
        immune = {s.name for s in Q.SCENARIOS if not s.narrow_control_must_fail}
        self.assertEqual(immune, {"boundary_zero", "degenerate_variance"})
        for scenario in Q.SCENARIOS:
            self.assertTrue(scenario.why.strip(), scenario.name)

    def test_the_narrow_control_cannot_move_the_immune_scenarios(self):
        """Объявленный иммунитет — вывод, и он проверяется вычислением."""
        for name in ("boundary_zero", "degenerate_variance"):
            scenario = next(s for s in Q.SCENARIOS if s.name == name)
            keeper = record(scenario, 1_000)
            segments = keeper.inner.segments(Q.LO, Q.HI)
            wide = Q.accept_from_segments(segments, z=Q.Z_DECLARED)
            narrow = Q.accept_from_segments(segments, z=Q.Z_NARROW)
            self.assertTrue(any(a <= scenario.truth <= b for a, b in wide), name)
            self.assertTrue(any(a <= scenario.truth <= b for a, b in narrow), name)


class ControlFlowAtSmallSizesTests(unittest.TestCase):
    """«Малое M» из B-7: процедура обязана не падать и не врать."""

    def test_a_single_period_yields_the_whole_domain(self):
        for scenario in Q.SCENARIOS:
            keeper = record(scenario, 1)
            got = Q.accept_from_segments(keeper.inner.segments(Q.LO, Q.HI),
                                         z=Q.Z_DECLARED)
            self.assertEqual(got, [(Q.LO, Q.HI)], scenario.name)
            self.assertEqual(PR.radius(got, 0.0), Q.HI)
            self.assertFalse(PR.is_precise(PR.radius(got, 0.0), Q.DELTA))

    def test_an_empty_sample_is_the_whole_domain_too(self):
        self.assertEqual(Q.accept_from_segments((), z=Q.Z_DECLARED),
                         [(Q.LO, Q.HI)])

    def test_a_tiny_ladder_exhausts_and_reports_insufficient(self):
        scenario = next(s for s in Q.SCENARIOS if s.name == "zero_heavy")
        _, outcome = Q.replicate(scenario, 0, ladder=(2, 4, 8))
        #: ТОЛЬКО объявленный `z`: контроль `z = 0.5` строит множество вчетверо
        #: уже цели и на восьми периодах способен объявить точность — это его
        #: работа, ровно поэтому он и контроль
        got = outcome["объявленный alpha/12"]
        self.assertIs(got.status, PR.PrecisionStatus.INSUFFICIENT)
        self.assertEqual(got.look, 8)
        self.assertEqual(Q.replicate(scenario, 0, ladder=(2,))[1]
                         ["объявленный alpha/12"].look, 2)

    def test_the_harness_loop_reproduces_the_production_run_nested(self):
        """Общий поток на три `z` не должен менять исход ни для одного."""
        for scenario in Q.SCENARIOS[:5]:
            for index in range(3):
                _, outcome = Q.replicate(scenario, index)
                for label, z in Q.CONFIGS:
                    def evaluate(size, scenario=scenario, index=index):
                        rng = random.Random(f"{scenario.name}:{index}")
                        sample = scenario.new_sample()
                        for _ in range(size):
                            scenario.draw(rng, sample)
                        segments = sample.segments(Q.LO, Q.HI)
                        return (Q.accept_from_segments(segments, z=z,
                                                       lo=Q.LO, hi=Q.HI),
                                Q.root_from_segments(segments, Q.LO, Q.HI))
                    want = PR.run_nested(evaluate, Q.DELTA, z=z)
                    self.assertIs(outcome[label].status, want.status,
                                  (scenario.name, index, label))
                    self.assertEqual(outcome[label].look, want.look,
                                     (scenario.name, index, label))


class TheFiellerGoldenIsReproducedExactlyTests(unittest.TestCase):
    """Собственный контрпример проекта — обязательный член набора B-7."""

    PERIODS = [(Piece(100.0, 131520.0),)] + [(Piece(1.0, 720.0),)] * 24

    def test_the_golden_is_still_disconnected_and_the_radius_uses_all_of_it(self):
        got = acceptance_set(self.PERIODS, z=NormalDist().inv_cdf(0.975),
                             lo=0.0, hi=3600.0)
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(got[0][1], 1273.95, places=1)
        self.assertAlmostEqual(got[1][0], 1535.81, places=1)
        self.assertEqual(PR.radius(got, 1200.0), 2400.0)
        self.assertEqual(PR.radius([got[0]], 1200.0), 1200.0)

    def test_the_golden_root_is_the_declared_twelve_hundred(self):
        total = sum(p.b for q in self.PERIODS for p in q)
        denominator = sum(p.n for q in self.PERIODS for p in q)
        self.assertEqual(total / denominator, 1200.0)


class QualificationGatesAreDeclaredTests(unittest.TestCase):
    """Пороги объявлены ДО прогона и взяты из уже существующего правила."""

    def test_the_floor_is_the_project_floor_not_a_new_one(self):
        from simulation import s5b_prereg as prereg
        self.assertEqual(prereg.COVERAGE_ACCEPTANCE_FLOOR, 0.93)
        self.assertEqual(Q.REPLICATES, prereg.COVERAGE_REPLICATES)

    def test_the_family_z_matches_this_suite_not_a_smaller_one(self):
        from simulation import s5b_prereg as prereg
        want = NormalDist().inv_cdf(1.0 - prereg.SIMULTANEOUS_ALPHA
                                    / len(Q.SCENARIOS))
        self.assertAlmostEqual(Q.SUITE_Z, want)
        self.assertGreater(Q.SUITE_Z, prereg.COVERAGE_Z,
                           "десять сценариев не могут делить поправку семи")

    def test_acceptance_requires_both_family_corrections(self):
        """Ни один из двух порогов не должен пропускать то, что валит другой."""
        tight = Q.Tally(covered=3_735, trials=4_000)
        self.assertFalse(Q.accepted(tight))
        self.assertTrue(Q.accepted(Q.Tally(covered=3_900, trials=4_000)))

    def test_the_delta_is_the_tightest_on_the_declared_grid(self):
        from simulation import s5b_prereg as prereg
        self.assertEqual(Q.DELTA, min(prereg.DELTA_FRACTIONS_OF_HORIZON) * Q.HI)

    def test_the_declared_z_is_the_twelve_comparison_one(self):
        self.assertAlmostEqual(Q.Z_DECLARED, PR.Z_PER_COMPARISON)
        self.assertGreater(Q.Z_DECLARED, 2.86)
        self.assertLess(Q.Z_DECLARED, 2.87)
