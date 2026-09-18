"""S5a: проверяется АНАЛИЗ, а порождение данных ему стенд.

Правило решения живёт здесь отдельно от всякой симуляции — четырьмя числами,
как `recovery.classify` и `corpus_compare.classify_distance`. Гейт решает,
объявлен ли сигнал; ошибка в нём выглядит как научный результат.
"""

import random
import unittest

from extractor.model import HorizonAggregate, LengthSummary, PeriodAggregate
from simulation import experiment as ex
from simulation.process import Population, TrueEffect

H = 24.0
HOUR = 3600.0


def cell(n, burden, *, replied=None, window=14 * 24 * HOUR):
    return PeriodAggregate(
        participant_id="p", period_id="w",
        horizons=(HorizonAggregate(
            horizon_hours=H, opportunities_eligible=n,
            sum_min_latency_seconds=burden,
            replied_within=n if replied is None else replied),),
        own_messages=LengthSummary(count=0, total_chars=0),
        own_episode_returns=0, cross_actor_tie_groups=0,
        ambiguous_opportunities=0, observation_window_seconds=window)


class DecisionGateTests(unittest.TestCase):
    """Таблица истинности гейта эквивалентности."""

    def test_an_interval_wholly_outside_the_region_is_a_signal(self):
        self.assertIs(ex.decide(120.0, 300.0, 100.0), ex.Decision.REACTIVITY_SIGNAL)
        self.assertIs(ex.decide(-300.0, -120.0, 100.0), ex.Decision.REACTIVITY_SIGNAL)

    def test_an_interval_wholly_inside_the_region_is_practically_negligible(self):
        self.assertIs(ex.decide(-80.0, 80.0, 100.0), ex.Decision.PRACTICALLY_NEGLIGIBLE)

    def test_an_interval_straddling_the_boundary_is_inconclusive(self):
        self.assertIs(ex.decide(-50.0, 150.0, 100.0), ex.Decision.INCONCLUSIVE)
        self.assertIs(ex.decide(50.0, 150.0, 100.0), ex.Decision.INCONCLUSIVE)

    def test_the_boundaries_are_pinned_where_they_flip(self):
        # ровно на границе интервал ещё ВНУТРИ области
        self.assertIs(ex.decide(-100.0, 100.0, 100.0), ex.Decision.PRACTICALLY_NEGLIGIBLE)
        self.assertIs(ex.decide(-100.001, 100.0, 100.0), ex.Decision.INCONCLUSIVE)
        # ровно на границе снаружи сигнала ещё нет
        self.assertIs(ex.decide(100.0, 300.0, 100.0), ex.Decision.INCONCLUSIVE)
        self.assertIs(ex.decide(100.001, 300.0, 100.0), ex.Decision.REACTIVITY_SIGNAL)

    def test_a_signal_always_excludes_zero(self):
        """Отдельной проверки на ноль нет, потому что она была бы слабее."""
        for low, high in ((120.0, 300.0), (-300.0, -120.0)):
            self.assertIs(ex.decide(low, high, 100.0), ex.Decision.REACTIVITY_SIGNAL)
            self.assertFalse(low <= 0 <= high)

    def test_a_missing_interval_is_inconclusive_and_not_absence_of_effect(self):
        """Отсутствие не становится свидетельством."""
        self.assertIs(ex.decide(None, 1.0, 10.0), ex.Decision.INCONCLUSIVE)
        self.assertIs(ex.decide(1.0, None, 10.0), ex.Decision.INCONCLUSIVE)
        self.assertIs(ex.decide(None, None, 10.0), ex.Decision.INCONCLUSIVE)

    def test_delta_zero_reduces_the_gate_to_a_significance_test(self):
        self.assertIs(ex.decide(10.0, 300.0, 0.0), ex.Decision.REACTIVITY_SIGNAL)
        self.assertIs(ex.decide(-10.0, 300.0, 0.0), ex.Decision.INCONCLUSIVE)
        # при delta = 0 «практически ноль» недостижим, и это правильно:
        # точечное равенство нулю не доказуемо интервалом
        self.assertIs(ex.decide(-0.001, 0.001, 0.0), ex.Decision.INCONCLUSIVE)

    def test_a_negative_region_is_refused_rather_than_interpreted(self):
        self.assertIs(ex.decide(1.0, 2.0, -5.0), ex.Decision.INCONCLUSIVE)


class RegimeTests(unittest.TestCase):

    def test_every_regime_is_declared_with_a_description(self):
        self.assertEqual(set(ex.REGIMES), {"R0", "R1", "R2", "R3", "R4"})
        for name, regime in ex.REGIMES.items():
            self.assertEqual(regime.name, name)
            self.assertTrue(regime.description)

    def test_the_null_regime_applies_nothing(self):
        self.assertTrue(ex.REGIMES["R0"].effect(random.Random(1)).is_null)

    def test_each_regime_touches_the_channel_it_names(self):
        rng = random.Random(1)
        self.assertEqual(ex.REGIMES["R1"].effect(rng).opportunity_rate_ratio, 1.0)
        self.assertGreater(ex.REGIMES["R1"].effect(rng).latency_log_shift, 0.0)
        self.assertEqual(ex.REGIMES["R2"].effect(rng).latency_log_shift, 0.0)
        self.assertLess(ex.REGIMES["R2"].effect(rng).opportunity_rate_ratio, 1.0)
        mixed = ex.REGIMES["R3"].effect(rng)
        self.assertGreater(mixed.latency_log_shift, 0.0)
        self.assertLess(mixed.opportunity_rate_ratio, 1.0)

    def test_the_heterogeneous_regime_keeps_the_average_and_spreads_the_effect(self):
        rng = random.Random(4)
        shifts = [ex.REGIMES["R4"].effect(rng).latency_log_shift for _ in range(4000)]
        self.assertAlmostEqual(sum(shifts) / len(shifts), ex.LATENCY_SHIFT, delta=0.02)
        self.assertEqual(set(shifts), {0.0, 2 * ex.LATENCY_SHIFT})
        self.assertTrue(ex.REGIMES["R4"].heterogeneous)

    def test_r1_is_not_advertised_as_incidence_neutral(self):
        """S3a: сдвиг латентности двигает incidence эмерджентно. Описание режима
        обязано это говорить, иначе через месяц его процитируют как «чистый»."""
        self.assertIn("эмерджентно", ex.REGIMES["R1"].description)


class AssignmentTests(unittest.TestCase):

    def test_full_compliance_means_assignment_equals_receipt(self):
        got = ex.randomise(200, 3, compliance=1.0)
        self.assertEqual(got.assigned_treated, got.received_treated)
        self.assertEqual(got.compliance_rate, 1.0)

    def test_controls_never_receive_the_treatment(self):
        got = ex.randomise(200, 3, compliance=0.5)
        for assigned, received in zip(got.assigned_treated, got.received_treated):
            if not assigned:
                self.assertFalse(received)

    def test_partial_compliance_lands_near_the_declared_rate(self):
        got = ex.randomise(600, 5, compliance=0.6)
        self.assertAlmostEqual(got.compliance_rate, 0.6, delta=0.08)

    def test_selective_non_compliance_is_lower_than_uniform(self):
        """Иначе проверка ITT проверяет пустое место."""
        uniform = ex.randomise(600, 5, compliance=0.6, selective=False)
        selective = ex.randomise(600, 5, compliance=0.6, selective=True)
        self.assertLess(selective.compliance_rate, uniform.compliance_rate)

    def test_the_arm_share_is_respected(self):
        got = ex.randomise(800, 9, treated_share=0.25)
        self.assertAlmostEqual(sum(got.assigned_treated) / 800, 0.25, delta=0.05)


class AnalysisTests(unittest.TestCase):
    """Анализ видит мир только через `PeriodAggregate`, как и в поле."""

    def setUp(self):
        self.assignment = ex.Assignment((True,) * 6 + (False,) * 6,
                                        (True,) * 6 + (False,) * 6)

    def aggregates(self, treated_burden, control_burden, n=4):
        return ([cell(n, treated_burden) for _ in range(6)]
                + [cell(n, control_burden) for _ in range(6)])

    def test_it_reports_the_difference_in_the_direction_treated_minus_control(self):
        got = ex.analyse(self.assignment, self.aggregates(4000.0, 2000.0), delta=0.0)
        self.assertGreater(got.difference, 0.0)

    def test_identical_arms_give_a_zero_difference_and_no_signal(self):
        got = ex.analyse(self.assignment, self.aggregates(2000.0, 2000.0), delta=100.0)
        self.assertEqual(got.difference, 0.0)
        self.assertIs(got.decision, ex.Decision.PRACTICALLY_NEGLIGIBLE)

    def test_cells_with_no_opportunities_are_counted_and_dropped_from_rmtr(self):
        """N = 0: burden определён, RMTR нет. Ноль не подставляется."""
        mixed = [cell(0, 0.0) for _ in range(6)] + [cell(4, 2000.0) for _ in range(6)]
        got = ex.analyse(self.assignment, mixed, delta=0.0)
        self.assertEqual(got.treated.cells_zero_incidence, 6)
        self.assertEqual(got.treated.cells_contributing, 0)
        self.assertIs(got.decision, ex.Decision.INCONCLUSIVE)
        self.assertFalse(got.estimable)

    def test_burden_still_exists_where_rmtr_does_not(self):
        mixed = [cell(0, 0.0) for _ in range(6)] + [cell(4, 2000.0) for _ in range(6)]
        got = ex.analyse(self.assignment, mixed, estimand="mean_burden", delta=0.0)
        self.assertEqual(got.treated.cells_contributing, 6)
        self.assertEqual(got.treated.mean, 0.0)

    def test_missing_periods_are_counted_rather_than_silently_absent(self):
        with_gaps = list(self.aggregates(4000.0, 2000.0))
        with_gaps[0] = None
        with_gaps[6] = None
        got = ex.analyse(self.assignment, with_gaps, delta=0.0)
        self.assertEqual(got.treated.cells_missing, 1)
        self.assertEqual(got.control.cells_missing, 1)
        self.assertEqual(got.treated.cells_assigned, 6)

    def test_itt_analyses_by_assignment_and_per_protocol_by_receipt(self):
        crossed = ex.Assignment((True,) * 6 + (False,) * 6,
                                (False,) * 6 + (False,) * 6)
        data = self.aggregates(4000.0, 2000.0)
        itt = ex.analyse(crossed, data, delta=0.0)
        pp = ex.analyse(crossed, data, delta=0.0, by_receipt=True)
        self.assertEqual(itt.analysis, "ITT")
        self.assertEqual(pp.analysis, "per-protocol")
        self.assertEqual(itt.treated.cells_contributing, 6)
        self.assertEqual(pp.treated.cells_contributing, 0)

    def test_a_single_cell_per_arm_cannot_form_an_interval(self):
        thin = ex.Assignment((True, False), (True, False))
        got = ex.analyse(thin, [cell(4, 4000.0), cell(4, 2000.0)], delta=0.0)
        self.assertFalse(got.estimable)
        self.assertIs(got.decision, ex.Decision.INCONCLUSIVE)

    def test_the_opportunity_weighted_ratio_is_not_offered_as_a_cell_estimand(self):
        """Роли не сливать: это отношение сумм, у него нет ячеечного распределения."""
        self.assertNotIn("opportunity_rmtr", ex.CELL_VALUES)
        self.assertEqual(ex.PRIMARY, "person_period_rmtr")


class TrialTests(unittest.TestCase):

    def test_each_dyad_lives_once_in_its_own_arm(self):
        assignment, aggregates = ex.run_trial(ex.REGIMES["R1"], 2, dyads=20, days=7)
        self.assertEqual(len(aggregates), 20)
        self.assertEqual(assignment.n, 20)
        self.assertEqual(len({a.period_id for a in aggregates if a}), 20)

    def test_a_trial_is_reproducible_from_its_seed(self):
        first = ex.run_trial(ex.REGIMES["R3"], 5, dyads=12, days=7)
        second = ex.run_trial(ex.REGIMES["R3"], 5, dyads=12, days=7)
        self.assertEqual(first, second)

    def test_missing_periods_leave_a_hole_rather_than_shrinking_the_trial(self):
        _, aggregates = ex.run_trial(ex.REGIMES["R0"], 6, dyads=40, days=7,
                                     missing_share=0.5)
        self.assertEqual(len(aggregates), 40)
        self.assertTrue(any(a is None for a in aggregates))

    def test_the_null_regime_leaves_both_arms_from_the_same_process(self):
        assignment, aggregates = ex.run_trial(ex.REGIMES["R0"], 8, dyads=30, days=7)
        got = ex.analyse(assignment, aggregates, estimand="mean_incidence", delta=0.0)
        self.assertIs(got.decision, ex.Decision.INCONCLUSIVE)


class OperatingCharacteristicsTests(unittest.TestCase):

    def test_shares_are_reported_over_the_trials_run(self):
        oc = ex.OperatingCharacteristics(
            regime="R0", estimand="x", delta=0.0, trials=20,
            counts={ex.Decision.INCONCLUSIVE: 19, ex.Decision.REACTIVITY_SIGNAL: 1})
        self.assertAlmostEqual(oc.share(ex.Decision.REACTIVITY_SIGNAL), 0.05)
        self.assertAlmostEqual(oc.share(ex.Decision.PRACTICALLY_NEGLIGIBLE), 0.0)

    def test_no_trials_does_not_divide_by_zero(self):
        oc = ex.OperatingCharacteristics(regime="R0", estimand="x", delta=0.0, trials=0)
        self.assertEqual(oc.share(ex.Decision.INCONCLUSIVE), 0.0)


if __name__ == "__main__":
    unittest.main()
