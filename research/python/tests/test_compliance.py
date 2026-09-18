"""Смещение по конструкции: known potential outcomes, никакого генератора.

Прошлая попытка крутила параметры процесса в надежде, что per-protocol
испортится, и получила |t| = 0.70 — то есть доказала только, что
избирательность была слабой. Здесь смещение заложено в конструкцию, поэтому
проверка либо ловит его, либо не работает.
"""

import statistics
import unittest

from simulation import compliance as co
from simulation.compliance import ComplianceRule


def outcomes(baseline, effect):
    return co.PotentialOutcomes(tuple(baseline), tuple(effect))


class PotentialOutcomeTests(unittest.TestCase):

    def test_the_population_effect_is_the_mean_of_the_individual_ones(self):
        got = outcomes([100.0, 200.0], [10.0, -30.0])
        self.assertEqual(got.n, 2)
        self.assertAlmostEqual(got.ate, -10.0)

    def test_the_observed_value_switches_on_receipt_not_assignment(self):
        got = outcomes([100.0, 200.0], [10.0, -30.0])
        self.assertEqual(got.observed(False, 0), 100.0)
        self.assertEqual(got.observed(True, 0), 110.0)
        self.assertEqual(got.observed(True, 1), 170.0)

    def test_an_outcome_cannot_go_negative(self):
        """RMTR — время; отрицательного времени ответа не бывает."""
        self.assertEqual(outcomes([10.0], [-500.0]).observed(True, 0), 0.0)

    def test_the_default_draw_plants_a_zero_average_effect(self):
        """Ноль не украшение: любой знак у PP тогда порождён ТОЛЬКО отбором."""
        drawn = co.draw_potential_outcomes(4000, 1)
        self.assertAlmostEqual(drawn.ate, 0.0, delta=40.0)
        self.assertGreater(statistics.stdev(drawn.effect), 500.0)

    def test_the_draw_is_reproducible(self):
        self.assertEqual(co.draw_potential_outcomes(50, 7),
                         co.draw_potential_outcomes(50, 7))
        self.assertNotEqual(co.draw_potential_outcomes(50, 7),
                            co.draw_potential_outcomes(50, 8))


class ComplierSelectionTests(unittest.TestCase):

    def setUp(self):
        self.outcomes = co.draw_potential_outcomes(400, 3)
        self.assigned = [i % 2 == 0 for i in range(400)]

    def compliers(self, rule, rate=0.5):
        import random
        return co._compliers(self.outcomes, self.assigned, rule, rate,
                             random.Random(11))

    def test_every_rule_yields_the_same_number_of_compliers(self):
        """Доля соблюдения фиксирована: иначе расхождение объяснялось бы ею."""
        sizes = {rule: len(self.compliers(rule)) for rule in ComplianceRule}
        self.assertEqual(len(set(sizes.values())), 1, sizes)

    def test_select_high_takes_those_the_treatment_helps(self):
        chosen = self.compliers(ComplianceRule.SELECT_HIGH)
        rest = [i for i, z in enumerate(self.assigned) if z and i not in chosen]
        self.assertGreater(min(self.outcomes.effect[i] for i in chosen),
                           max(self.outcomes.effect[i] for i in rest))

    def test_select_low_takes_those_it_harms(self):
        chosen = self.compliers(ComplianceRule.SELECT_LOW)
        rest = [i for i, z in enumerate(self.assigned) if z and i not in chosen]
        self.assertLess(max(self.outcomes.effect[i] for i in chosen),
                        min(self.outcomes.effect[i] for i in rest))

    def test_random_selection_lands_between_the_two(self):
        mean = lambda ids: statistics.fmean(self.outcomes.effect[i] for i in ids)
        low = mean(self.compliers(ComplianceRule.SELECT_LOW))
        rnd = mean(self.compliers(ComplianceRule.RANDOM))
        high = mean(self.compliers(ComplianceRule.SELECT_HIGH))
        self.assertLess(low, rnd)
        self.assertLess(rnd, high)

    def test_only_the_assigned_can_comply(self):
        for rule in ComplianceRule:
            for index in self.compliers(rule):
                self.assertTrue(self.assigned[index], rule)


class TrialTests(unittest.TestCase):

    def test_controls_never_receive_and_the_rate_is_honoured(self):
        drawn = co.draw_potential_outcomes(600, 5)
        assignment, cells = co.compliance_trial(
            drawn, 5, rule=ComplianceRule.SELECT_HIGH, compliance_rate=0.4)
        self.assertEqual(len(cells), 600)
        for assigned, received in zip(assignment.assigned_treated,
                                      assignment.received_treated):
            if not assigned:
                self.assertFalse(received)
        self.assertAlmostEqual(assignment.compliance_rate, 0.4, delta=0.02)

    def test_the_planted_value_arrives_as_the_cell_rmtr(self):
        """Анализ прогоняется настоящий, поэтому величина обязана дойти до него
        ровно как ячеечный RMTR."""
        cell = co._cell(1234.0).horizon(co.HORIZON_HOURS)
        self.assertEqual(cell.rmtr_seconds, 1234.0)
        self.assertEqual(cell.opportunities_eligible, 1)


class VerdictTests(unittest.TestCase):
    """Чистая часть: знак и |t|, без единого прогона."""

    def check(self, rule, gap, se=1.0):
        return co.ComplianceCheck(rule=rule, trials=40, true_ate=0.0,
                                  mean_itt=0.0, mean_pp=gap, mean_gap=gap,
                                  se_gap=se, mean_compliance=0.5)

    def test_select_high_passes_only_on_a_clear_positive_gap(self):
        self.assertTrue(self.check(ComplianceRule.SELECT_HIGH, 10.0).passes)
        self.assertFalse(self.check(ComplianceRule.SELECT_HIGH, -10.0).passes)
        self.assertFalse(self.check(ComplianceRule.SELECT_HIGH, 1.0).passes)

    def test_select_low_passes_only_on_a_clear_negative_gap(self):
        self.assertTrue(self.check(ComplianceRule.SELECT_LOW, -10.0).passes)
        self.assertFalse(self.check(ComplianceRule.SELECT_LOW, 10.0).passes)

    def test_random_passes_only_when_nothing_systematic_happens(self):
        self.assertTrue(self.check(ComplianceRule.RANDOM, 1.0).passes)
        self.assertFalse(self.check(ComplianceRule.RANDOM, 10.0).passes)

    def test_a_zero_spread_does_not_divide_by_zero(self):
        self.assertEqual(self.check(ComplianceRule.RANDOM, 1.0, se=0.0).t_gap,
                         float("inf"))


class MirrorTests(unittest.TestCase):
    """Зеркальность — то, что отделяет ИЗБИРАТЕЛЬНОСТЬ от разбавления."""

    @classmethod
    def setUpClass(cls):
        cls.checks = {rule: co.run_compliance_check(rule, participants=200,
                                                    trials=12, base_seed=880_000)
                      for rule in ComplianceRule}

    def test_the_true_population_effect_is_zero_in_every_arm(self):
        for rule, check in self.checks.items():
            self.assertAlmostEqual(check.true_ate, 0.0, delta=120.0, msg=rule)

    def test_the_compliance_rate_is_identical_across_rules(self):
        rates = [round(c.mean_compliance, 2) for c in self.checks.values()]
        self.assertEqual(len(set(rates)), 1, rates)

    def test_selecting_the_helped_pushes_per_protocol_above_itt(self):
        check = self.checks[ComplianceRule.SELECT_HIGH]
        self.assertGreater(check.mean_gap, 0.0)
        self.assertGreater(check.t_gap, 3.0)
        self.assertTrue(check.passes)

    def test_selecting_the_harmed_pushes_it_below(self):
        check = self.checks[ComplianceRule.SELECT_LOW]
        self.assertLess(check.mean_gap, 0.0)
        self.assertGreater(check.t_gap, 3.0)
        self.assertTrue(check.passes)

    def test_random_compliance_produces_no_systematic_drift(self):
        self.assertTrue(self.checks[ComplianceRule.RANDOM].passes)

    def test_the_two_selective_rules_are_mirror_images(self):
        high = self.checks[ComplianceRule.SELECT_HIGH].mean_gap
        low = self.checks[ComplianceRule.SELECT_LOW].mean_gap
        self.assertAlmostEqual(high, -low, delta=0.35 * abs(high))

    def test_itt_is_not_a_cure_for_selective_compliance_either(self):
        """Важная тонкость: при избирательном соблюдении ITT САМ не равен нулю,
        хотя истинный средний эффект по популяции нулевой. И это верно —
        назначение действительно производит эффект, когда именно оно приводит
        к лечению тех, кому оно помогает. ITT несмещён для эффекта НАЗНАЧЕНИЯ,
        а не для популяционного ATE.
        """
        high = self.checks[ComplianceRule.SELECT_HIGH]
        self.assertGreater(high.mean_itt, 0.0)
        self.assertLess(self.checks[ComplianceRule.SELECT_LOW].mean_itt, 0.0)
        self.assertAlmostEqual(self.checks[ComplianceRule.RANDOM].mean_itt,
                               0.0, delta=abs(high.mean_itt) / 2)


if __name__ == "__main__":
    unittest.main()
