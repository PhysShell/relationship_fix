"""The weighting fork, the N = 0 boundary, and the direction of B = N x R.

The export ships sums and counts and no ratios, which is correct and also means
the estimand is chosen downstream. These fixtures pin the choices so that a
future analysis cannot take one by accident.
"""

import unittest

from extractor import estimands as es
from extractor.model import HorizonAggregate, LengthSummary, PeriodAggregate

HOUR = 3600.0
H = 6.0


def cell(n, burden, *, window=24 * HOUR, pid="p1"):
    """One person-period carrying exactly the sufficient statistics that matter."""
    return PeriodAggregate(
        participant_id=pid,
        period_id="w1",
        horizons=(HorizonAggregate(
            horizon_hours=H,
            opportunities_eligible=n,
            sum_min_latency_seconds=burden,
            replied_within=n,
        ),),
        own_messages=LengthSummary(count=0, total_chars=0),
        own_episode_returns=0,
        observation_window_seconds=window,
    )


class WeightingForkTests(unittest.TestCase):
    """Same sufficient statistics, two estimands, and they are not close."""

    def setUp(self):
        # one heavy-traffic fast person, one light-traffic slow person
        self.sample = [cell(10, 10 * 60.0), cell(1, 3600.0, pid="p2")]

    def test_opportunity_weighted_pools_across_people(self):
        got = es.opportunity_weighted_rmtr(self.sample, H)
        self.assertEqual(got.value, (600.0 + 3600.0) / 11)   # 381.8s
        self.assertEqual(got.opportunities, 11)

    def test_person_period_weighted_gives_each_period_one_vote(self):
        got = es.person_period_weighted_rmtr(self.sample, H)
        self.assertEqual(got.value, (60.0 + 3600.0) / 2)     # 1830.0s
        self.assertEqual(got.contributing, 2)

    def test_the_two_weightings_disagree_by_a_factor_not_a_rounding(self):
        pooled = es.opportunity_weighted_rmtr(self.sample, H).value
        per_person = es.person_period_weighted_rmtr(self.sample, H).value
        self.assertGreater(per_person / pooled, 4.0)

    def test_they_coincide_only_when_every_cell_carries_the_same_count(self):
        balanced = [cell(3, 900.0), cell(3, 300.0, pid="p2")]
        self.assertEqual(es.opportunity_weighted_rmtr(balanced, H).value,
                         es.person_period_weighted_rmtr(balanced, H).value)


class ZeroIncidenceTests(unittest.TestCase):
    """N = 0: burden is defined, RMTR is not, and 0 is not an allowed stand-in."""

    def setUp(self):
        self.sample = [cell(2, 1200.0), cell(0, 0.0, pid="p2"), cell(1, 300.0, pid="p3")]

    def test_rmtr_is_undefined_not_zero_on_an_empty_cell(self):
        empty = self.sample[1].horizon(H)
        self.assertIsNone(empty.rmtr_seconds)
        self.assertEqual(empty.reentry_burden_seconds, 0.0)

    def test_both_rmtr_weightings_drop_the_empty_cell(self):
        for estimator in (es.opportunity_weighted_rmtr, es.person_period_weighted_rmtr):
            got = estimator(self.sample, H)
            self.assertEqual(got.person_periods, 3)
            self.assertEqual(got.contributing, 2)
            self.assertEqual(got.zero_incidence, 1)
            self.assertTrue(got.conditions_on_occurrence)

    def test_burden_keeps_the_empty_cell_and_conditions_on_nothing(self):
        got = es.mean_burden(self.sample, H)
        self.assertEqual(got.contributing, 3)
        self.assertEqual(got.value, (1200.0 + 0.0 + 300.0) / 3)
        self.assertEqual(got.zero_incidence, 1)   # described, not dropped

    def test_a_sample_of_only_empty_cells_has_a_burden_and_no_rmtr(self):
        empty = [cell(0, 0.0), cell(0, 0.0, pid="p2")]
        self.assertEqual(es.mean_burden(empty, H).value, 0.0)
        self.assertIsNone(es.opportunity_weighted_rmtr(empty, H).value)
        self.assertIsNone(es.person_period_weighted_rmtr(empty, H).value)

    def test_dropping_empty_cells_can_move_the_conditional_estimate_on_its_own(self):
        """Why P(N = 0) is not a nuisance parameter: two arms with identical
        episode durations differ on the conditional mean purely through how
        often a period produced any episode at all."""
        arm_a = [cell(1, 600.0), cell(1, 600.0, pid="p2")]
        arm_b = [cell(1, 600.0), cell(0, 0.0, pid="p2")]
        self.assertEqual(es.person_period_weighted_rmtr(arm_a, H).value,
                         es.person_period_weighted_rmtr(arm_b, H).value)   # blind
        self.assertNotEqual(es.mean_burden(arm_a, H).value,
                            es.mean_burden(arm_b, H).value)                # sees it
        self.assertNotEqual(es.mean_incidence(arm_a, H).value,
                            es.mean_incidence(arm_b, H).value)


class CommonWindowTests(unittest.TestCase):
    def test_burden_refuses_unequal_windows(self):
        mixed = [cell(1, 600.0, window=24 * HOUR),
                 cell(1, 600.0, window=48 * HOUR, pid="p2")]
        with self.assertRaises(es.WindowMismatch):
            es.mean_burden(mixed, H)

    def test_rmtr_survives_unequal_windows_but_says_so(self):
        mixed = [cell(1, 600.0, window=24 * HOUR),
                 cell(1, 900.0, window=48 * HOUR, pid="p2")]
        got = es.person_period_weighted_rmtr(mixed, H)
        self.assertEqual(got.value, 750.0)
        self.assertIsNone(got.window_seconds)

    def test_a_common_window_is_reported_back(self):
        got = es.mean_burden([cell(1, 600.0), cell(2, 600.0, pid="p2")], H)
        self.assertEqual(got.window_seconds, 24 * HOUR)


class IdentityDirectionTests(unittest.TestCase):
    """B = N x R in the reals. B is the primitive; reconstruction is not exact."""

    def test_rmtr_is_the_quotient_of_the_exported_numbers(self):
        agg = cell(4, 1000.0).horizon(H)
        self.assertEqual(agg.rmtr_seconds, 250.0)
        self.assertEqual(agg.reentry_burden_seconds, 1000.0)

    def test_reconstructing_the_burden_from_n_and_r_is_not_exact(self):
        """Pinned from a real MaiChat cell: 1 ulp, harmless as a number and
        fatal as an exact-equality invariant check. Hence B is exported and R
        is derived, never the other way round."""
        agg = cell(41, 909.7609996795654).horizon(H)
        self.assertNotEqual(agg.opportunities_eligible * agg.rmtr_seconds,
                            agg.reentry_burden_seconds)
        self.assertAlmostEqual(agg.opportunities_eligible * agg.rmtr_seconds,
                               agg.reentry_burden_seconds, places=9)


class ArmLevelDecompositionTests(unittest.TestCase):
    """B = N x R survives averaging only under the ratio-of-sums weighting."""

    def setUp(self):
        # incidence and duration deliberately ANTI-correlated: the busy cell is
        # fast, the quiet cell is slow. This is the MaiChat pattern.
        self.sample = [cell(10, 10 * 60.0), cell(1, 3600.0, pid="p2")]

    def test_incidence_times_opportunity_weighted_rmtr_is_the_mean_burden(self):
        got = es.burden_decomposition(self.sample, H)
        self.assertEqual(got.mean_incidence * got.opportunity_weighted_rmtr,
                         got.mean_burden)
        self.assertEqual(got.residual, 0.0)
        self.assertTrue(got.holds_exactly)

    def test_the_naive_product_with_the_person_weighted_rmtr_is_wrong(self):
        """And wrong by a factor, not an epsilon — this is Cov(N, R)."""
        naive = (es.mean_incidence(self.sample, H).value
                 * es.person_period_weighted_rmtr(self.sample, H).value)
        true_mean = es.mean_burden(self.sample, H).value
        self.assertEqual(true_mean, 2100.0)
        self.assertEqual(naive, 5.5 * 1830.0)          # 10065.0
        self.assertGreater(naive / true_mean, 4.0)

    def test_the_two_agree_only_when_incidence_and_duration_are_unassociated(self):
        flat = [cell(2, 600.0), cell(2, 1200.0, pid="p2")]   # equal N, so Cov = 0
        naive = (es.mean_incidence(flat, H).value
                 * es.person_period_weighted_rmtr(flat, H).value)
        self.assertEqual(naive, es.mean_burden(flat, H).value)

    def test_the_identity_is_not_testable_without_a_single_opportunity(self):
        """Three states, not two: the factor does not exist, so neither does a
        verdict on the identity."""
        empty = [cell(0, 0.0), cell(0, 0.0, pid="p2")]
        got = es.burden_decomposition(empty, H)
        self.assertIsNone(got.residual)
        self.assertIsNone(got.holds_exactly)
        self.assertEqual(got.mean_burden, 0.0)

    def test_decomposition_inherits_the_common_window_refusal(self):
        mixed = [cell(1, 600.0), cell(1, 600.0, window=48 * HOUR, pid="p2")]
        with self.assertRaises(es.WindowMismatch):
            es.burden_decomposition(mixed, H)


class StructuralInvariantTests(unittest.TestCase):
    """0 <= B_H <= observation window, because capped opportunity intervals are
    disjoint and clipped inside the period."""

    def test_a_lawful_aggregate_passes(self):
        got = es.burden_fits_window(cell(3, 3 * HOUR), time_axis_total=True)
        self.assertIs(got.status, es.CheckStatus.CHECKED)
        self.assertTrue(got.passed)

    def test_a_burden_larger_than_the_window_is_caught(self):
        """Only reachable through overlapping opportunities, double counting or
        a clock that lied — all four causes want a human."""
        got = es.burden_fits_window(cell(30, 30 * HOUR), time_axis_total=True)
        self.assertFalse(got.passed)
        self.assertIn("exceeds observation window", got.violations[0])

    def test_a_negative_burden_is_caught_separately(self):
        got = es.burden_fits_window(cell(1, -1.0), time_axis_total=True)
        self.assertFalse(got.passed)
        self.assertIn("negative burden", got.violations[0])

    def test_a_coarse_time_axis_returns_not_applicable_and_not_a_pass(self):
        """Silence must not read as a green tick: under a partial order an
        ambiguous tie can manufacture the overlap the invariant looks for, and
        the fault would belong to the timestamps, not the extractor."""
        got = es.burden_fits_window(cell(30, 30 * HOUR), time_axis_total=False)
        self.assertIs(got.status, es.CheckStatus.NOT_APPLICABLE)
        self.assertIsNone(got.passed)
        self.assertEqual(got.violations, ())


if __name__ == "__main__":
    unittest.main()
