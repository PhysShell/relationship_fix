"""PREREG S5b: заморожено до прогона, и тесты следят, чтобы так и осталось.

Здесь нет ни одного прогона. Проверяется дисциплина: сетки объявлены,
STRICT не может стать primary, два гейта не сливаются в один, и pilot N не
выходит одним числом.
"""

import unittest

from simulation import s5b_prereg as prereg
from simulation.s5b_prereg import Admissibility, Gate, Verdict, verdict


class PurposeTests(unittest.TestCase):

    def test_c_is_a_constraint_not_a_contrast(self):
        """Руки без C нет, и сам C не заморожен — оценивать его эффект нечем."""
        self.assertTrue(prereg.C_IS_A_CONSTRAINT_NOT_A_CONTRAST)
        self.assertIn("оценить эффект пакета C на поведение", prereg.NOT_PURPOSE)

    def test_c_reactivity_axis_is_about_measurability(self):
        """C сокращается в контрасте; он портит не оценку, а ИЗМЕРИМОСТЬ."""
        self.assertTrue(prereg.C_REACTIVITY_IS_ABOUT_MEASURABILITY_NOT_BIAS)
        self.assertEqual(prereg.C_REACTIVITY_RATE_MULTIPLIERS[0], 1.0)

    def test_pilot_n_is_not_a_purpose(self):
        self.assertIn("выбрать pilot N одним числом", prereg.NOT_PURPOSE)


class FrozenGridTests(unittest.TestCase):

    def test_the_rate_grid_follows_a_rule_not_a_taste(self):
        """Узлы — множители 1/4, 1, 4, 16 от дефолта генератора."""
        base = prereg.GENERATOR_DEFAULT_RATE
        self.assertEqual(prereg.OPPORTUNITY_RATE_GRID,
                         (base / 4, base, base * 4, base * 16))
        self.assertTrue(prereg.OPPORTUNITY_RATE_IS_SENSITIVITY_ONLY)

    def test_resolutions_stop_at_the_coarsest_real_source(self):
        """Грубее 60 с нет ни одного кандидата — рисовать там было бы фантазией."""
        self.assertEqual(max(prereg.ACQUISITION_RESOLUTIONS_SECONDS), 60.0)
        self.assertIn(1.0, prereg.ACQUISITION_RESOLUTIONS_SECONDS)
        self.assertGreaterEqual(len(prereg.ACQUISITION_RESOLUTIONS_SECONDS), 4)

    def test_delta_and_horizon_are_axes_not_decisions(self):
        self.assertGreater(len(prereg.DELTA_FRACTIONS_OF_HORIZON), 1)
        self.assertGreater(len(prereg.HORIZONS_SECONDS), 1)
        self.assertIn("выбрать δ по тому, где график красивее", prereg.NOT_PURPOSE)
        self.assertIn("выбрать H по тому, где график красивее", prereg.NOT_PURPOSE)

    def test_delta_is_dimensionless(self):
        """Абсолютное δ потребовало бы основания, которого пока нет."""
        for fraction in prereg.DELTA_FRACTIONS_OF_HORIZON:
            self.assertLess(fraction, 1.0)
            self.assertGreater(fraction, 0.0)

    def test_the_nodes_are_declared_frozen(self):
        self.assertTrue(prereg.GRID_NODES_ARE_FROZEN)

    def test_the_cost_is_visible_before_the_run(self):
        self.assertEqual(prereg.FULL_GRID_CELLS, prereg.cells())
        self.assertEqual(prereg.MEASUREMENT_SURFACE_CELLS, 144)
        self.assertLess(prereg.MEASUREMENT_SURFACE_CELLS, prereg.FULL_GRID_CELLS)

    def test_the_reduction_rule_is_declared_not_tasted(self):
        self.assertEqual(len(prereg.STAGED_SWEEP), 3)
        self.assertTrue(prereg.MEASUREMENT_GATE_IS_INDEPENDENT_OF_N)
        self.assertIn("effect_regime", prereg.REFERENCE_CELL)


class StrictIsNotACompetitorTests(unittest.TestCase):

    def test_strict_is_a_diagnostic_only(self):
        self.assertEqual(prereg.STRICT_ROLE, "diagnostic negative control")
        self.assertEqual(prereg.BOUNDED_ROLE, "allowed measurement policy")

    def test_no_estimator_beauty_contest(self):
        """Таблица «какой лучше» позволила бы выбрать STRICT в удобной области."""
        self.assertTrue(prereg.NO_ESTIMATOR_BEAUTY_CONTEST)
        self.assertIn("STRICT в этой области работает лучше",
                      prereg.FORBIDDEN_INTERPRETATIONS)


class TwoGatesTests(unittest.TestCase):
    """Разделение куплено дорого; в дизайне мощности его легче всего потерять."""

    def test_the_gates_are_two_not_one(self):
        self.assertEqual({Gate.MEASUREMENT, Gate.SAMPLING}, set(Gate))

    def test_the_verdict_distinguishes_curable_from_structural(self):
        self.assertIs(verdict(True, True), Verdict.IDENTIFIED_AND_DECISIVE)
        self.assertIs(verdict(True, False), Verdict.SAMPLING_INCONCLUSIVE)
        self.assertIs(verdict(False, True), Verdict.MEASUREMENT_AMBIGUOUS)
        self.assertIs(verdict(False, False), Verdict.BOTH_AMBIGUOUS)

    def test_measurement_ambiguity_is_never_called_low_power(self):
        self.assertIn("MEASUREMENT_AMBIGUOUS", prereg.STOP_RULES["more_n_cannot_help"])
        self.assertIn("measurement ambiguity лечится увеличением выборки",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_no_finite_n_is_a_diagnosis(self):
        """«Источник не подходит» и «мощности мало» — разные диагнозы."""
        self.assertTrue(prereg.NO_FINITE_N_IS_A_DIAGNOSIS_NOT_A_POWER_PROBLEM)
        self.assertIn("NO_FINITE_N", prereg.NO_FINITE_N)


class OutputShapeTests(unittest.TestCase):

    def test_the_output_is_an_admissibility_region_not_only_power(self):
        self.assertEqual({a.value for a in Admissibility},
                         {"usable", "borderline / structurally ambiguous",
                          "unusable for this endpoint"})

    def test_burden_budget_is_a_constraint_with_numbers(self):
        self.assertGreater(prereg.BUDGET.prompts_per_day, 0)
        self.assertGreater(prereg.BUDGET.manual_minutes_per_week, 0)
        self.assertLess(prereg.BUDGET.missing_periods_share, 1.0)

    def test_c_is_redesigned_rather_than_the_criterion(self):
        self.assertIn("переделывается C, а не критерий",
                      prereg.STOP_RULES["c_must_be_redesigned"])

    def test_a_blocked_s6_is_a_result(self):
        self.assertIn("результат, а не неудача", prereg.STOP_RULES["s6_stays_blocked"])


class ForbiddenInterpretationTests(unittest.TestCase):

    def test_the_forbidden_list_is_verbatim(self):
        for sentence in ("S5b показал, что нужно N участников",
                         "opportunity_rate_per_day теперь известен",
                         "S5b оценил бремя пакета C"):
            self.assertIn(sentence, prereg.FORBIDDEN_INTERPRETATIONS)

    def test_it_agrees_with_the_s4_closure(self):
        """Два запретных списка не должны расходиться."""
        from coarsening import s4_closure
        self.assertTrue(s4_closure.OPPORTUNITY_RATE_IS_A_SENSITIVITY_AXIS)
        self.assertTrue(prereg.OPPORTUNITY_RATE_IS_SENSITIVITY_ONLY)
