"""PREREG S5b: заморожено до прогона, и тесты следят, чтобы так и осталось.

Здесь нет ни одного прогона. Проверяется дисциплина: сетки объявлены,
STRICT не может стать primary, два гейта не сливаются в один, и pilot N не
выходит одним числом.
"""

import unittest

from simulation import s5b_prereg as prereg
from simulation.s5b_prereg import Admissibility, Gate, Verdict, verdict


class PurposeTests(unittest.TestCase):

    def test_c_has_no_separately_identifiable_effect(self):
        """Руки без C нет, и сам C не заморожен — оценивать его эффект нечем."""
        self.assertTrue(prereg.C_HAS_NO_SEPARATELY_IDENTIFIABLE_EFFECT)
        self.assertIn("оценить эффект пакета C на поведение", prereg.NOT_PURPOSE)

    def test_c_is_not_claimed_to_cancel_in_the_contrast(self):
        """ПОПРАВКА: генератор нелинеен, поэтому возможно C × T взаимодействие.

        Прежняя редакция объявляла движение контраста по оси C-reactivity
        «тем, чего ждать неоткуда». А оно вполне законно — просто это другой
        эстиманд при другом общем пакете, а не смещение.
        """
        self.assertTrue(prereg.C_MAY_ALTER_BOTH_MEASURABILITY_AND_CONDITIONAL_ITT)
        self.assertTrue(prereg.NEITHER_CHANGE_IS_AN_ESTIMATE_OF_C_VS_NO_C)
        self.assertIn("C сокращается в контрасте", prereg.FORBIDDEN_INTERPRETATIONS)

    def test_c_reactivity_is_three_pairs_not_a_cartesian_product(self):
        """Два независимых кортежа допускали три сценария ИЛИ девять."""
        self.assertEqual(len(prereg.C_REACTIVITY_POINTS), 3)
        for point in prereg.C_REACTIVITY_POINTS:
            self.assertEqual(len(point), 2)
        self.assertEqual(prereg.C_REACTIVITY_POINTS[0], (1.00, 0.00))

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
        self.assertEqual(prereg.LATENT_SIMULATIONS, prereg.latent_simulations())
        self.assertEqual(prereg.MEASUREMENT_CELLS, prereg.measurement_cells())
        self.assertLess(prereg.LATENT_SIMULATIONS, prereg.MEASUREMENT_CELLS)

    def test_r0_is_counted_once(self):
        """Три «разных» нуля соврали бы о размере сетки."""
        self.assertIn("R0", prereg.MAGNITUDE_NOT_APPLICABLE_TO)
        expected = len(prereg.OPPORTUNITY_RATE_GRID) * (1 + 4 * 3) * 3
        self.assertEqual(prereg.LATENT_SIMULATIONS, expected)

    def test_effect_scaling_is_declared(self):
        """«Половина эффекта» имеет минимум три естественных смысла."""
        self.assertIn("logarithmic", prereg.EFFECT_SCALING)

    def test_stage_one_includes_every_topology_changing_axis(self):
        """Измеримость зависит от поведения, поведение — от режима эффекта.

        Прежнее правило отсекало лестницу N по одному R1. «R1 прошёл» не
        означает «R2/R3/R4 прошли»: это буквально главный результат S4.
        """
        for axis in ("effect_regime", "effect_magnitude", "c_reactivity_point"):
            self.assertIn(axis, prereg.STAGE_ONE_AXES)

    def test_the_saving_is_computational_not_scientific(self):
        self.assertTrue(prereg.RESOLUTION_IS_PAIRED_ON_ONE_LATENT_STREAM)
        self.assertTrue(prereg.HORIZON_AND_DELTA_ARE_POST_HOC)
        self.assertIn("§4a", prereg.DURATION_EXCLUDED_FROM_STAGE_ONE_BECAUSE)


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

    def test_the_aggregation_chain_is_frozen_end_to_end(self):
        """Главный блокер прежней редакции: как из интервалов выходит решение."""
        self.assertEqual(len(prereg.AGGREGATION_CHAIN), 6)
        self.assertIn("mean", prereg.ARM_BOUNDS)
        self.assertIn("meanL_T", prereg.CONTRAST_BOUNDS)
        self.assertIn("outer union", prereg.SAMPLING_INTERVAL)
        self.assertTrue(prereg.SAMPLING_INTERVAL_IS_CONSERVATIVE)
        self.assertTrue(prereg.SHARPER_PARTIAL_IDENTIFICATION_CI.startswith("DEFERRED"))

    def test_the_measurement_gate_is_structural_not_sample_free(self):
        """«Не зависит от N вовсе» было слишком сильно: реализованный
        интервал зависит, а структурная ширина — нет."""
        self.assertTrue(prereg.STRUCTURAL_AMBIGUITY_IS_NOT_CURED_BY_N)
        self.assertTrue(prereg.REALIZED_INTERVAL_DOES_DEPEND_ON_N)
        self.assertGreater(prereg.MEASUREMENT_GATE_REFERENCE_DYADS, 0)
        self.assertIn("reference N", prereg.MEASUREMENT_GATE)

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

    def test_no_finite_n_is_structural_not_bad_luck(self):
        self.assertTrue(prereg.NO_FINITE_N_IS_STRUCTURAL_NOT_A_REALIZATION)


class EligibilityBoundaryTests(unittest.TestCase):
    """Правая граница решена ЗДЕСЬ: fixed окна появились в этой же сетке."""

    def test_eligibility_is_resolution_invariant_by_construction(self):
        self.assertTrue(prereg.ELIGIBILITY_IS_RESOLUTION_INVARIANT_BY_CONSTRUCTION)
        self.assertEqual(prereg.ELIGIBILITY_REFERENCE_RESOLUTION_SECONDS,
                         max(prereg.ACQUISITION_RESOLUTIONS_SECONDS))

    def test_the_same_eligible_set_is_used_for_every_arm(self):
        self.assertIn("same eligible set", prereg.ELIGIBILITY_RULE)
        self.assertGreaterEqual(prereg.ELIGIBILITY_GUARD_BINS, 1)


class AdmissibilityRuleTests(unittest.TestCase):
    """BORDERLINE — правило, а не слово."""

    def test_an_interval_clear_of_the_gate_is_usable(self):
        self.assertIs(prereg.admissibility(100.0, 200.0, 50.0),
                      Admissibility.USABLE)

    def test_an_interval_straddling_the_gate_is_unusable(self):
        self.assertIs(prereg.admissibility(-100.0, 200.0, 50.0),
                      Admissibility.UNUSABLE)

    def test_an_interval_hugging_the_gate_is_borderline(self):
        self.assertIs(prereg.admissibility(51.0, 200.0, 50.0),
                      Admissibility.BORDERLINE)

    def test_the_two_borderline_cells_are_chosen_deterministically(self):
        """При сорока семи пограничных «две» — это degree of freedom."""
        self.assertIn("лексикографически", prereg.BORDERLINE_SELECTION)
        self.assertEqual(prereg.BORDERLINE_TIE_BREAK[0], "rate")


class OutputShapeTests(unittest.TestCase):

    def test_the_output_is_an_admissibility_region_not_only_power(self):
        self.assertEqual({a.value for a in Admissibility},
                         {"usable", "borderline / structurally ambiguous",
                          "unusable for this endpoint"})

    def test_operational_feasibility_is_not_an_s5b_output(self):
        """В S5b нет модели, связывающей reactivity с prompts и минутами."""
        self.assertTrue(prereg.OPERATIONAL_FEASIBILITY_IS_NOT_AN_S5B_OUTPUT)
        self.assertEqual(prereg.BUDGET_APPLIES_AT, "C freeze, not S5b")
        self.assertIn("S5b показал, что пакет C выполним",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_c_is_redesigned_rather_than_the_criterion(self):
        self.assertIn("переделывается C, а не критерий",
                      prereg.STOP_RULES["c_must_be_redesigned"])

    def test_s5b_does_not_unblock_s6_itself(self):
        """Иначе после поверхности можно выбрать удобную «целевую» точку."""
        self.assertTrue(prereg.S5B_DOES_NOT_UNBLOCK_S6)
        self.assertIsInstance(prereg.TARGET_WORKING_POINT_COMES_FROM, str)
        self.assertIn("AFTER S5b", prereg.TARGET_WORKING_POINT_COMES_FROM)
        self.assertIn("S5b разблокировал S6", prereg.FORBIDDEN_INTERPRETATIONS)

    def test_q4_is_narrowed_to_resolution_under_complete_coverage(self):
        """Оси покрытия в сетке нет; S4 на capture-window и упёрся."""
        self.assertIn("COMPLETE COVERAGE", prereg.Q4_SCOPE)
        self.assertIn("NOT MODELLED", prereg.COVERAGE_AXIS)


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
