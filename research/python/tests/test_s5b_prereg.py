"""PREREG S5b: заморожено до прогона, и тесты следят, чтобы так и осталось.

Здесь нет ни одного прогона. Проверяется дисциплина: сетки объявлены,
STRICT не может стать primary, два гейта не сливаются в один, и pilot N не
выходит одним числом.
"""

import itertools
import math
import pathlib
import random
import unittest

from coarsening.bounded import Bin, burden_bounds, count_bounds
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
        self.assertTrue(prereg.DURATIONS_ARE_NESTED_PREFIXES)

    def test_duration_is_back_in_stage_one(self):
        """«Единственным каналом была правая граница» — неверно: длина
        периода меняет число и состав возможностей и P(N = 0)."""
        self.assertIn("observation_days", prereg.STAGE_ONE_AXES)
        self.assertIn("P(N = 0)", prereg.DURATION_IS_IN_STAGE_ONE_BECAUSE)
        self.assertFalse(hasattr(prereg, "DURATION_EXCLUDED_FROM_STAGE_ONE_BECAUSE"))

    def test_duration_costs_no_extra_latent_simulations(self):
        """Возвращение оси не должно быть оплачено симуляциями."""
        self.assertEqual(prereg.LONGEST_DURATION_DAYS,
                         max(prereg.OBSERVATION_DAYS))
        self.assertEqual(prereg.LATENT_SIMULATIONS, 156)
        self.assertEqual(prereg.MEASUREMENT_CELLS, 16_848)
        self.assertEqual(prereg.MEASUREMENT_CELLS,
                         156 * 4 * 3 * 3 * len(prereg.OBSERVATION_DAYS))

    def test_the_prefix_trick_names_its_precondition(self):
        """Префикс распределён как короткий прогон только при однородности."""
        self.assertIn("time-homogeneous", prereg.PREFIX_NESTING_REQUIRES)
        self.assertTrue(prereg.PREFIX_NESTING_IS_TESTED_PATHWISE)


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
        self.assertIn("Dinkelbach", prereg.ARM_BOUNDS)
        self.assertIn("λ⁻T", prereg.CONTRAST_BOUNDS)
        self.assertIn("outer union", prereg.SAMPLING_INTERVAL)
        self.assertTrue(prereg.SAMPLING_INTERVAL_IS_CONSERVATIVE)
        self.assertTrue(prereg.SHARPER_PARTIAL_IDENTIFICATION_CI.startswith("DEFERRED"))

    def test_the_measurement_gate_is_a_population_object(self):
        """Одна выборка из 500 — всё ещё реализация. Гейт определён через
        ожидания, а симуляция их лишь численно интегрирует."""
        self.assertTrue(prereg.MEASUREMENT_GATE_IS_A_POPULATION_OBJECT)
        self.assertTrue(prereg.STRUCTURAL_AMBIGUITY_IS_NOT_CURED_BY_N)
        self.assertTrue(prereg.REALIZED_INTERVAL_DOES_DEPEND_ON_N)
        self.assertIn("POPULATION", prereg.MEASUREMENT_GATE)
        self.assertFalse(hasattr(prereg, "MEASUREMENT_GATE_REFERENCE_DYADS"))
        self.assertIn("λ⁻_T", prereg.POPULATION_MEASUREMENT_BOUNDS)

    def test_monte_carlo_stops_on_precision_never_on_result(self):
        """Остановка по точности — не то же, что остановка по ответу."""
        self.assertTrue(prereg.MC_STOPPING_IS_ON_PRECISION_NOT_ON_RESULT)
        self.assertLess(prereg.MEASUREMENT_MC_START_PERIODS_PER_ARM,
                        prereg.MEASUREMENT_MC_MAX_PERIODS_PER_ARM)
        self.assertGreater(prereg.MEASUREMENT_MC_ESCALATION_FACTOR, 1)

    def test_compute_limits_never_become_scientific_verdicts(self):
        self.assertTrue(prereg.MC_NOISE_IS_NOT_A_SCIENTIFIC_VERDICT)
        self.assertIn("MC_PRECISION_INSUFFICIENT", prereg.STOP_RULES["mc_precision"])
        self.assertTrue(prereg.TIMING_PILOT_MEASURES_WALL_CLOCK_ONLY)

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

    def test_eligibility_is_a_time_region_not_an_opportunity_set(self):
        """Общего множества возможностей между разрешениями НЕТ — за тем
        огрубление и существует."""
        self.assertTrue(prereg.ELIGIBILITY_IS_A_TIME_REGION_NOT_AN_OPPORTUNITY_SET)
        self.assertIn("initiation region", prereg.ELIGIBILITY_RULE)
        self.assertNotIn("same eligible set", prereg.ELIGIBILITY_RULE)
        self.assertEqual(prereg.ELIGIBILITY_REFERENCE_RESOLUTION_SECONDS,
                         max(prereg.ACQUISITION_RESOLUTIONS_SECONDS))

    def test_the_guard_bin_is_inside_the_formula(self):
        """Прежняя пара строк противоречила себе: формула без запаса всё ещё
        признавала t = 119 допустимым, ради которого всё и затевалось."""
        self.assertIn("ELIGIBILITY_GUARD_BINS", prereg.ELIGIBILITY_RULE)
        self.assertGreaterEqual(prereg.ELIGIBILITY_GUARD_BINS, 1)
        self.assertFalse(prereg.is_eligible(119.0, window_end=120.0, horizon=60.0))
        self.assertTrue(prereg.is_eligible(59.0, window_end=120.0, horizon=60.0))

    def test_eligibility_agrees_across_every_resolution_on_the_axis(self):
        """Тот же момент, огрублённый по-разному, получает тот же вердикт."""
        window, horizon = 7200.0, 600.0
        for t in range(0, 7200, 37):
            verdicts = set()
            for delta in prereg.ACQUISITION_RESOLUTIONS_SECONDS:
                observed = delta * math.floor(t / delta)
                verdicts.add(prereg.is_eligible(observed, window_end=window,
                                                horizon=horizon))
            self.assertEqual(len(verdicts), 1, t)

    def test_every_resolution_nests_in_the_reference_bin(self):
        """Без вложенности «родительская корзина» — пустые слова."""
        self.assertTrue(prereg.RESOLUTIONS_MUST_NEST_IN_THE_REFERENCE_BIN)
        for delta in prereg.ACQUISITION_RESOLUTIONS_SECONDS:
            self.assertAlmostEqual(
                prereg.ELIGIBILITY_REFERENCE_RESOLUTION_SECONDS % delta, 0.0)

    def test_the_initiation_region_is_a_prefix_in_time(self):
        """На этой монотонности стоит теорема N_min = 0 => N_max = 0."""
        self.assertTrue(prereg.INITIATION_REGION_IS_A_TIME_PREFIX)
        window, horizon = 3600.0, 300.0
        seen_false = False
        for t in range(0, 3600, 13):
            ok = prereg.is_eligible(float(t), window_end=window, horizon=horizon)
            if not ok:
                seen_false = True
            elif seen_false:
                self.fail("допустимость вернулась после запрета: не префикс")
        self.assertTrue(seen_false)


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

    def test_the_selection_is_executable_not_prose(self):
        """Проза оставляла runner'у решать, что такое «ближайшая изнутри»."""
        cells = [prereg.Cell(("b",), 1.05, 3.0, 1.0),    # изнутри, 0.05
                 prereg.Cell(("a",), 2.0, 3.0, 1.0),     # изнутри, но не погранич.
                 prereg.Cell(("c",), -1.02, 0.5, 1.0),   # снаружи, 0.02
                 prereg.Cell(("d",), -5.0, 5.0, 1.0)]    # снаружи, далеко
        inside, outside = prereg.select_borderline_cells(cells)
        self.assertEqual(inside.axes, ("b",))
        self.assertEqual(outside.axes, ("c",))

    def test_only_genuinely_borderline_cells_are_eligible(self):
        """Мой баг, благословлённый моим же тестом: фильтр шёл только по
        base_admissibility, поэтому при отсутствии пограничных на стороне
        возвращалась ближайшая НЕПОГРАНИЧНАЯ и называлась пограничной."""
        far = [prereg.Cell(("a",), 2.0, 3.0, 1.0),       # изнутри, 1.0 >> 0.1
               prereg.Cell(("d",), -5.0, 5.0, 1.0)]      # снаружи, 4.0 >> 0.1
        for cell in far:
            self.assertIsNot(prereg.admissibility(cell.low, cell.high, cell.delta),
                             Admissibility.BORDERLINE)
        self.assertEqual(prereg.select_borderline_cells(far), (None, None))

    def test_ties_are_broken_lexicographically_not_by_input_order(self):
        """Иначе порядок обхода сетки становится научным решением."""
        cells = [prereg.Cell(("z", 2), 1.05, 3.0, 1.0),
                 prereg.Cell(("a", 1), 1.05, 3.0, 1.0)]
        inside, _ = prereg.select_borderline_cells(cells)
        self.assertEqual(inside.axes, ("a", 1))
        inside_again, _ = prereg.select_borderline_cells(list(reversed(cells)))
        self.assertEqual(inside_again.axes, ("a", 1))

    def test_an_empty_side_yields_none_rather_than_a_substitute(self):
        """«Пограничных нет» — результат, а не повод подставить ближайшую."""
        self.assertTrue(prereg.BORDERLINE_SIDE_MAY_BE_EMPTY)
        cells = [prereg.Cell(("a",), 1.05, 3.0, 1.0)]
        inside, outside = prereg.select_borderline_cells(cells)
        self.assertIsNotNone(inside)
        self.assertIsNone(outside)


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


class PrimaryFunctionalTests(unittest.TestCase):
    """Смена первичного эстиманда — главная поправка второго чтения."""

    def test_the_primary_is_the_ratio_of_totals(self):
        self.assertIn("ΣB/ΣN", prereg.PRIMARY_ARM_FUNCTIONAL)
        self.assertTrue(prereg.PRIMARY_IS_A_RATIO_OF_ITTS_NOT_A_CONDITIONAL_MEAN)

    def test_the_person_period_version_is_demoted_for_a_named_reason(self):
        """Проект это уже знал и записал в extractor/estimands.py."""
        self.assertTrue(prereg.PERSON_PERIOD_WEIGHTED_CONDITIONS_ON_POST_TREATMENT)
        self.assertTrue(any("person-period" in f
                            for f in prereg.DIAGNOSTIC_ARM_FUNCTIONALS))

    def test_the_replacement_is_not_sold_without_its_caveat(self):
        """ΣB/ΣN — отношение двух ITT, а не среднее по «возникшим всё равно»."""
        self.assertIn("mix changed", prereg.COMPOSITION_CAVEAT)
        self.assertIn("ΣB/ΣN — это среднее время возврата среди возникших "
                      "возможностей", prereg.FORBIDDEN_INTERPRETATIONS)

    def test_the_thing_that_makes_it_conditional_is_reported(self):
        self.assertTrue(prereg.ZERO_INCIDENCE_SHARE_IS_REPORTED_PER_ARM)

    def test_the_naive_sum_envelope_is_refused_by_name(self):
        self.assertTrue(prereg.NAIVE_SUM_ENVELOPE_IS_NOT_BOUNDS)
        self.assertTrue(prereg.ARM_BOUNDS_ARE_SHARP_ON_THE_ORDER_LAYER_ONLY)


class DefinednessTripwireTests(unittest.TestCase):
    """Претензия «плавающий знаменатель» в этом движке не проходит —
    но предусловия названы, и на них стоит растяжка."""

    def test_the_invariance_names_what_it_rests_on(self):
        self.assertTrue(prereg.N_ZERO_IS_ORDER_INVARIANT)
        self.assertEqual(len(prereg.N_ZERO_INVARIANCE_RESTS_ON), 2)

    def test_the_tripwire_has_declared_behaviour_not_just_existence(self):
        self.assertTrue(prereg.DEFINEDNESS_AMBIGUOUS_IS_A_TRIPWIRE)
        self.assertIn("STOPS", prereg.IF_DEFINEDNESS_AMBIGUOUS_EVER_FIRES)
        self.assertTrue(prereg.FLOATING_DENOMINATOR_BOUNDS.startswith("DEFERRED"))
        self.assertIn("Definedness.AMBIGUOUS",
                      prereg.STOP_RULES["definedness_tripwire"])


class OperatingCharacteristicTests(unittest.TestCase):
    """Порог решающего исхода не выбирается — выдаётся объект."""

    def test_no_threshold_is_chosen_here(self):
        self.assertTrue(prereg.MINIMAL_N_IS_NOT_AN_S5B_OUTPUT)
        self.assertIn("AFTER", prereg.REQUIRED_OPERATING_CHARACTERISTIC_COMES_FROM)
        self.assertIn("all four verdicts", prereg.OPERATING_CHARACTERISTIC)
        self.assertGreater(prereg.SAMPLING_REPLICATES, 0)

    def test_the_two_no_n_labels_are_different_claims(self):
        """Из пяти точек до 400 бесконечность не выводится."""
        self.assertNotEqual(prereg.NO_FINITE_N, prereg.NO_PREDECLARED_N)
        self.assertIn("population measurement gate",
                      prereg.THE_INFINITE_CLAIM_IS_LICENSED_ONLY_BY)
        self.assertIn("NO_PREDECLARED_N", prereg.STOP_RULES["ladder_is_not_infinity"])
        self.assertIn("лестница N исчерпана, значит никакой N не поможет",
                      prereg.FORBIDDEN_INTERPRETATIONS)


class SamplingEnvelopeTests(unittest.TestCase):
    """Пережившая атаку конструкция записывается так же, как провалившаяся."""

    def test_the_coverage_argument_is_recorded_not_assumed(self):
        self.assertTrue(prereg.SAMPLING_ENVELOPE_SURVIVED_ATTACK)
        self.assertIn("Bonferroni", prereg.SAMPLING_ENVELOPE_COVERAGE)
        self.assertIn("97.5", prereg.SAMPLING_ENVELOPE_COVERAGE)


class PrefixNestingTests(unittest.TestCase):
    """Длительность вернулась в этап 1 бесплатно — но только если префикс
    длинного потока ДЕЙСТВИТЕЛЬНО совпадает с коротким прогоном."""

    def test_a_short_run_is_a_pathwise_prefix_of_a_long_one(self):
        """Проверка, а не рассуждение. `days` входит в генератор ровно одной
        строкой (`end`), поэтому совпадение должно быть ПОТРАЕКТОРНЫМ, а не
        только распределительным — и это сильнее, чем нужно, что хорошо.
        """
        from simulation.process import DAY, DyadParameters, generate_dyad

        params = DyadParameters()
        for seed in ("a", "b", "c"):
            long = generate_dyad(random.Random(seed), params,
                                 days=prereg.LONGEST_DURATION_DAYS)
            for days in prereg.OBSERVATION_DAYS:
                short = generate_dyad(random.Random(seed), params, days=days)
                cut = [(m.actor, m.local_time) for m in long
                       if m.local_time < days * DAY]
                self.assertEqual(cut, [(m.actor, m.local_time) for m in short],
                                 (seed, days))

    def test_the_longest_duration_covers_the_axis(self):
        self.assertEqual(prereg.LONGEST_DURATION_DAYS,
                         max(prereg.OBSERVATION_DAYS))


class PopulationFunctionalTests(unittest.TestCase):
    """После смены эстиманда популяционный объект стал другим."""

    def test_the_population_object_is_a_dinkelbach_root_not_a_mean(self):
        """«Сначала границы, потом среднее» не коммутирует с отношением —
        доказано на конечной руке, и на популяционном слое то же самое."""
        self.assertTrue(prereg.MEAN_OF_ENDPOINTS_IS_THE_WRONG_POPULATION_OBJECT)
        self.assertIn("roots of", prereg.POPULATION_ARM_BOUNDS)
        self.assertIn("E[extremum", prereg.POPULATION_ARM_BOUNDS)
        self.assertIn("λ⁻_T", prereg.POPULATION_MEASUREMENT_BOUNDS)
        self.assertIn("границы руки — это среднее поячеечных границ",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_the_finite_engine_is_named_as_the_approximation_it_is(self):
        self.assertTrue(prereg.ARM_RATIO_BOUNDS_IS_THE_SAA_OF_THE_POPULATION_FUNCTIONAL)
        self.assertIn("SAA", prereg.AGGREGATION_CHAIN[2])


class SamplingInferenceTests(unittest.TestCase):
    """Бонферрони не доказывает валидность компонентных интервалов."""

    def test_welch_is_retired_with_a_named_reason(self):
        self.assertTrue(prereg.BONFERRONI_DOES_NOT_PROVE_COMPONENT_VALIDITY)
        self.assertIn("root of a whole-arm", prereg.WELCH_NO_LONGER_APPLIES_BECAUSE)
        self.assertIn("outer union", prereg.SAMPLING_INTERVAL)

    def test_the_primary_is_test_inversion(self):
        """Последний P0 снят не починкой сертификата, а отказом от допущения."""
        self.assertIn("test inversion", prereg.PRIMARY_INFERENCE)
        self.assertTrue(prereg.TEST_INVERSION_NEEDS_NO_DIFFERENTIABILITY)
        self.assertTrue(prereg.TEST_INVERSION_NEEDS_NO_INTERIORITY)
        self.assertIn("sqrt(n)", prereg.TEST_INVERSION_SET)
        self.assertEqual(prereg.SANDWICH_ROLE, "diagnostic cross-check")

    def test_the_uniqueness_theorem_defines_the_parameter_and_nothing_more(self):
        """Она делает λ0 корректно определённым — и только. Связности
        множества принятия она НЕ даёт: тестируется стьюдентизованная
        статистика, у которой знаменатель тоже зависит от λ."""
        self.assertTrue(prereg.UNIQUENESS_THEOREM_MAKES_lambda0_WELL_DEFINED)
        self.assertTrue(prereg.UNIQUENESS_DOES_NOT_MAKE_THE_ACCEPTANCE_SET_CONNECTED)
        self.assertFalse(hasattr(prereg,
            "UNIQUENESS_THEOREM_IS_WHAT_MAKES_C_AN_INTERVAL_FOR_lambda0"))
        self.assertTrue(prereg.N_ZERO_IS_ORDER_INVARIANT)

    def test_the_switch_does_not_claim_a_failure_it_did_not_observe(self):
        """Сэндвич на контрпримере НЕ сломался, и это записано."""
        self.assertTrue(prereg.SANDWICH_DID_NOT_VISIBLY_FAIL_ON_THE_COUNTEREXAMPLE)
        self.assertTrue(prereg.SWITCH_IS_JUSTIFIED_BY_A_MISSING_ASSUMPTION_NOT_BY_A_DEMONSTRATED_FAILURE)

    def test_the_withdrawn_radius_claim_is_named(self):
        """Две соседние цифры в отчёте спорили друг с другом: 1 с против 2.3 с."""
        self.assertIn("smaller than the", prereg.REGULARITY_RADIUS_CLAIM_IS_WITHDRAWN)
        self.assertFalse(prereg.REGULARITY_GATE_IS_BLOCKING_IN_S5A_RATIO)
        self.assertTrue(prereg.REGULARITY_GATES_ARE_DIAGNOSTIC_NOW)
        self.assertIn("радиус сертификата можно взять меньше ошибки самой оценки",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_zero_observations_are_not_zero_mass(self):
        """Для дифференцируемости различие БИНАРНО, и граница его не закрывает."""
        self.assertIn("изломов не найдено, значит их нет",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_the_hull_machinery_is_named_as_required(self):
        self.assertIn("convex hull", prereg.INFERENCE_REQUIRES_MACHINERY)
        self.assertLess(prereg.TEST_INVERSION_COVERAGE_STUDY_HOURS,
                        prereg.COVERAGE_GATE_COMPUTE_BUDGET_HOURS)

    def test_the_sandwich_spec_survives_as_diagnostic(self):
        self.assertEqual(len(prereg.SANDWICH_INFERENCE), 5)
        self.assertIn("envelope theorem", prereg.ANALYTIC_INFERENCE[1])
        self.assertIn("no differencing", prereg.ANALYTIC_INFERENCE[1])
        self.assertIn("smaller N", prereg.ARGEXTREMUM_TIE_BREAK)
        self.assertIn("carry N", prereg.ANALYTIC_REQUIRES_MACHINERY)

    def test_the_jacobian_bound_is_the_same_theorem_a_third_time(self):
        """Уникальность, фиксированный знаменатель и CLT — одно предусловие."""
        self.assertTrue(prereg.ANALYTIC_JACOBIAN_IS_BOUNDED_BY_THE_SAME_THEOREM)
        self.assertTrue(prereg.N_ZERO_IS_ORDER_INVARIANT)

    def test_degenerate_replicates_are_counted_not_dropped(self):
        self.assertTrue(prereg.DEGENERATE_SHARE_IS_REPORTED)
        self.assertGreater(prereg.DEGENERATE_REPLICATE_LIMIT, 0.0)

    def test_coverage_is_checked_not_assumed(self):
        """Иначе метод снова выбирается после того, как видно, какой нравится."""
        self.assertTrue(prereg.SAMPLING_METHOD_COVERAGE_STUDY)
        self.assertTrue(prereg.COVERAGE_IS_OF_THE_SET_NOT_OF_A_POINT)
        self.assertIn("⊇", prereg.COVERAGE_TARGET)
        self.assertIn("SAMPLING_METHOD_INVALID", prereg.SAMPLING_METHOD_LADDER[2])
        self.assertTrue(prereg.NO_SHOPPING_FOR_A_METHOD_THAT_COVERS)
        self.assertIn("STOP", prereg.STOP_RULES["coverage_failure"])


class EstimandTradeTests(unittest.TestCase):
    """Смена эстиманда — размен, а не починка смещения."""

    def test_the_trade_is_stated_not_hidden(self):
        self.assertTrue(prereg.ESTIMAND_SWITCH_IS_A_TRADE_NOT_A_BIAS_FIX)
        self.assertTrue(prereg.PRIMARY_IS_NOT_ONE_VOTE_PER_RANDOMISED_UNIT)
        self.assertTrue(prereg.OPPORTUNITY_WEIGHTS_ARE_THEMSELVES_TREATMENT_DEPENDENT)

    def test_the_target_parameter_is_written_as_a_formula(self):
        self.assertIn("E[B(z)] / E[N(z)]", prereg.TARGET_PARAMETER)
        self.assertIn("θ_1 − θ_0", prereg.TARGET_PARAMETER)

    def test_the_two_tempting_misreadings_are_forbidden(self):
        self.assertIn("контраст θ — средний индивидуальный эффект лечения",
                      prereg.FORBIDDEN_INTERPRETATIONS)
        self.assertIn("θ_1 и θ_0 считаются на общем наборе возможностей",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_the_caveat_is_auditable_through_the_identity(self):
        """Тождество ΣB/M = (ΣN/M)(ΣB/ΣN) уже доказано в estimands.py."""
        self.assertEqual(len(prereg.REPORTED_TRIPLE), 3)
        self.assertTrue(prereg.IDENTITY_IS_AUDITED_PER_ARM)

    def test_the_tripwire_now_guards_the_arm_denominator(self):
        self.assertIn("ΣN = 0", prereg.TRIPWIRE_GUARDS_THE_ARM_DENOMINATOR)


class S5aRatioAmendmentTests(unittest.TestCase):
    """Сертификат от другого эстиманда не наследуется."""

    def test_the_amendment_is_blocking(self):
        self.assertTrue(prereg.S5A_QUALIFIED_A_DIFFERENT_PRIMARY)
        self.assertTrue(prereg.S5A_RATIO_IS_BLOCKING_FOR_S5B)
        self.assertEqual(len(prereg.S5A_RATIO_CHECKS), 6)
        self.assertIn("sampling-CI coverage", prereg.S5A_RATIO_CHECKS)
        self.assertIn("S5a-RATIO", prereg.STOP_RULES["s5a_ratio_is_blocking"])

    def test_history_is_annotated_not_rewritten(self):
        self.assertTrue(prereg.HISTORICAL_S5A_STAYS_CLOSED_FOR_THE_OLD_PRIMARY)
        self.assertTrue(prereg.OLD_ARTIFACTS_ARE_ANNOTATED_NOT_REWRITTEN)
        self.assertTrue(prereg.FROZEN_FILES_ARE_NOT_EDITED_FOR_CROSS_REFERENCES)
        self.assertTrue(prereg.THE_FREEZE_REFUSED_A_DOCUMENTATION_EDIT_AND_WAS_OBEYED)
        self.assertIn("S5a уже квалифицировал этот анализ",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_the_run_order_puts_machinery_first(self):
        self.assertEqual(len(prereg.RUN_ORDER), 4)
        self.assertIn("S5a-RATIO", prereg.RUN_ORDER[0])


class InitiationBridgeTests(unittest.TestCase):
    """Мост «предикат prereg -> скаляр движка» гниёт молча, поэтому проверен."""

    def test_the_scalar_cutoff_agrees_with_the_predicate(self):
        for window in (120.0, 600.0, 3600.0, 86_400.0):
            for horizon in prereg.HORIZONS_SECONDS:
                cutoff = prereg.initiation_cutoff(window, horizon)
                for t in range(0, int(window) + 1, max(1, int(window) // 200)):
                    self.assertEqual(
                        prereg.is_eligible(float(t), window_end=window,
                                           horizon=horizon),
                        float(t) < cutoff, (window, horizon, t))

    def test_a_window_too_short_for_any_horizon_admits_nothing(self):
        self.assertEqual(prereg.initiation_cutoff(100.0, 60.0), 0.0)
        self.assertFalse(prereg.is_eligible(0.0, window_end=100.0, horizon=60.0))

    def test_the_engine_takes_the_cutoff_separately_from_the_window(self):
        """Конец наблюдения и отсечка инициации — разные аргументы."""
        from coarsening.bounded import opens_here
        self.assertTrue(opens_here(0.0, horizon=300.0, window_end=600.0,
                                   initiation_end=60.0))
        self.assertFalse(opens_here(120.0, horizon=300.0, window_end=600.0,
                                    initiation_end=60.0))


def _reference(bins, *, horizon, window_end, eligible, time_layer=False):
    """МЕДЛЕННАЯ эталонная реализация: ЯВНЫЙ предикат и ЯВНЫЕ истории.

    Предикат здесь — функция, а не скаляр, и в этом весь смысл проверки:
    оптимизированный путь сворачивает область инициации в одно число, и если
    свёртка неверна, сравнение со скаляром этого не покажет. Правило вклада
    повторено НАМЕРЕННО, а не импортировано.

    Возвращает (N_min, N_max, B_min, B_max) по всем допустимым историям.
    """
    def arrangements(bucket):
        letters = "P" * bucket.partner + "A" * bucket.participant
        return sorted(set(itertools.permutations(letters)))

    rows = []
    for combination in itertools.product(*[arrangements(b) for b in bins]):
        sequence = []
        for bucket, arrangement in zip(bins, combination):
            sequence.extend((bucket.start, actor) for actor in arrangement)
        count, low, high = 0, 0.0, 0.0
        index = 0
        while index < len(sequence):
            start, actor = sequence[index]
            if actor != "P" or (index > 0 and sequence[index - 1][1] == "P"):
                index += 1
                continue
            end = index
            while end + 1 < len(sequence) and sequence[end + 1][1] == "P":
                end += 1
            reply = sequence[end + 1] if end + 1 < len(sequence) else None
            index = end + 1
            if not eligible(start):
                continue
            count += 1
            if reply is None:
                low += horizon
                high += horizon
            elif reply[0] != start:
                gap = reply[0] - start
                low += min(gap, horizon)
                high += min(gap, horizon)
        rows.append((count, low, high))
    return (min(r[0] for r in rows), max(r[0] for r in rows),
            min(r[1] for r in rows), max(r[2] for r in rows))


class InitiationDifferentialOracleTests(unittest.TestCase):
    """Урок №6 прошлого чтения: детерминированно неправильный тест всё ещё
    неправильный. Поэтому шести регрессий мало — нужен эталон и генератор."""

    HORIZON = 300.0

    def _compare(self, bins, window_end):
        cutoff = prereg.initiation_cutoff(window_end, self.HORIZON)
        predicate = lambda t: prereg.is_eligible(t, window_end=window_end,
                                                 horizon=self.HORIZON)
        want = _reference(bins, horizon=self.HORIZON, window_end=window_end,
                          eligible=predicate)
        counts = count_bounds(bins, horizon=self.HORIZON, window_end=window_end,
                              initiation_end=cutoff)
        burden = burden_bounds(bins, horizon=self.HORIZON, window_end=window_end,
                               time_layer=False, initiation_end=cutoff)
        self.assertEqual((counts.low, counts.high), (float(want[0]), float(want[1])),
                         (bins, window_end))
        self.assertAlmostEqual(burden.low, want[2], 6, (bins, window_end))
        self.assertAlmostEqual(burden.high, want[3], 6, (bins, window_end))

    def test_the_scalar_path_matches_the_explicit_predicate_on_random_timelines(self):
        rng = random.Random(1234)
        sizes = [(p, q) for p in range(3) for q in range(3) if p or q]
        for _ in range(250):
            window = rng.choice([600.0, 900.0, 1200.0, 1800.0])
            step = prereg.ELIGIBILITY_REFERENCE_RESOLUTION_SECONDS
            bins = [Bin(i * step, *rng.choice(sizes))
                    for i in range(rng.randint(1, 4))]
            self._compare(bins, window)

    def test_the_named_edge_cases_are_forced_not_hoped_for(self):
        """Сгенерированное может не попасть в край; эти попадают всегда."""
        window = 900.0
        cutoff = prereg.initiation_cutoff(window, self.HORIZON)
        self.assertGreater(cutoff, 0.0)
        step = prereg.ELIGIBILITY_REFERENCE_RESOLUTION_SECONDS
        for at in (cutoff - step, cutoff, cutoff + step):
            with self.subTest(at=at):
                self._compare([Bin(at, 1, 0), Bin(at + step, 0, 1)], window)

    def test_an_opening_before_the_cutoff_closed_after_it(self):
        """Открытие внутри области, ответ — за отсечкой, но В ПРЕДЕЛАХ
        горизонта. Именно здесь наивная обрезка корзин дала бы полный H.

        Первая редакция этого теста ставила ответ ДАЛЬШЕ горизонта и падала:
        там min(gap, H) = H законно, и падал тест, а не движок. Эталон при
        этом соглашался с движком в обоих вариантах — то есть дифференциальная
        часть работала, а моё дополнительное утверждение было просто неверным.
        """
        window = 1800.0
        cutoff = prereg.initiation_cutoff(window, self.HORIZON)
        step = prereg.ELIGIBILITY_REFERENCE_RESOLUTION_SECONDS
        bins = [Bin(cutoff - step, 1, 0), Bin(cutoff + step, 0, 1)]
        self._compare(bins, window)
        burden = burden_bounds(bins, horizon=self.HORIZON, window_end=window,
                               time_layer=False, initiation_end=cutoff)
        self.assertEqual(burden.high, 2 * step)
        self.assertLess(burden.high, self.HORIZON,
                        "возможность стала цензурированной, хотя ответ был")

    def test_a_window_admitting_nothing_agrees_with_the_reference(self):
        self._compare([Bin(0.0, 1, 1)], 100.0)

    def test_the_legacy_semantics_still_agrees_with_its_own_reference(self):
        """initiation_end=None — историческое правило; эталон тот же, предикат
        другой. Иначе «совместимость» проверялась бы сама собой."""
        rng = random.Random(99)
        sizes = [(p, q) for p in range(3) for q in range(3) if p or q]
        horizon, window = 300.0, 900.0
        for _ in range(120):
            step = 60.0
            bins = [Bin(i * step, *rng.choice(sizes))
                    for i in range(rng.randint(1, 4))]
            want = _reference(bins, horizon=horizon, window_end=window,
                              eligible=lambda t: t + horizon <= window)
            counts = count_bounds(bins, horizon=horizon, window_end=window)
            self.assertEqual((counts.low, counts.high),
                             (float(want[0]), float(want[1])), bins)


class RootDefinitionTests(unittest.TestCase):
    """Монотонность не покупает уникальность. Определение не должно на неё
    опираться, а уникальность — быть отдельным проверяемым свойством."""

    def test_the_endpoint_is_defined_by_generalized_inverse(self):
        self.assertTrue(prereg.MONOTONICITY_DOES_NOT_BUY_UNIQUENESS)
        self.assertIn("inf{λ", prereg.ARM_ENDPOINT_DEFINITION)
        self.assertIn("not 'the root'", prereg.ARM_ENDPOINT_DEFINITION)
        self.assertIn("left edge", prereg.PLATEAU_RESOLVES_TO)
        self.assertIn("монотонность g даёт единственный корень",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_uniqueness_has_a_named_sufficient_condition(self):
        self.assertIn("slope <= -1", prereg.UNIQUENESS_SUFFICIENT_CONDITION)
        self.assertIn("E[N] > 0", prereg.POPULATION_UNIQUENESS_CONDITION)
        self.assertTrue(prereg.MONOTONICITY_ALONE_IS_NOT_THE_ARGUMENT)

    def test_uniqueness_and_the_denominator_share_one_precondition(self):
        """Одно предусловие держит оба ответа и сломается сразу для обоих."""
        self.assertTrue(prereg.UNIQUENESS_RESTS_ON_THE_SAME_THEOREM_AS_THE_DENOMINATOR)
        self.assertTrue(prereg.N_ZERO_IS_ORDER_INVARIANT)


class ResamplingUnitTests(unittest.TestCase):
    """Единица рандомизации и независимый кластер — разные причины."""

    def test_the_cluster_is_named_and_justified_by_the_design(self):
        self.assertEqual(prereg.RANDOMISATION_UNIT, prereg.INDEPENDENT_SAMPLING_CLUSTER)
        self.assertIn("one person-period per dyad",
                      prereg.RESAMPLING_UNIT_COINCIDES_BECAUSE)

    def test_the_design_claim_is_checked_against_the_code(self):
        """Если этот факт изменится, prereg обязан узнать об этом здесь."""
        import inspect
        from simulation import recovery
        source = inspect.getsource(recovery.run_arm)
        self.assertIn("по одному person-period на пару", source)

    def test_several_periods_per_unit_is_a_tripwire_not_a_footnote(self):
        self.assertTrue(prereg.MULTI_PERIOD_PER_UNIT_IS_A_TRIPWIRE)
        self.assertIn("STOPS", prereg.IF_A_DYAD_EVER_YIELDS_SEVERAL_PERIODS)
        self.assertIn("кластерный", prereg.STOP_RULES["multi_period_unit"])


class CoverageGateTests(unittest.TestCase):
    """Провал покрытия должен иметь заранее замороженное продолжение."""

    def test_the_fallback_ladder_is_frozen_with_a_named_method_b(self):
        self.assertEqual(len(prereg.SAMPLING_METHOD_LADDER), 3)
        self.assertTrue(prereg.METHOD_B_IS_NAMED_IN_ADVANCE)
        self.assertIn("subsampling", prereg.SAMPLING_METHOD_LADDER[1])
        self.assertIn("non-smooth extremal", prereg.WHY_SUBSAMPLING)
        for field in ("draw", "scaling", "centering", "interval", "seeds",
                      "degenerate_subsample", "statistic", "subsamples"):
            self.assertIn(field, prereg.SUBSAMPLING_SPEC)
        self.assertIn("without replacement", prereg.SUBSAMPLING_SPEC["draw"])
        self.assertIn("sqrt(m / n)", prereg.SUBSAMPLING_SPEC["scaling"])
        self.assertTrue(prereg.SUBSAMPLING_RATE_IS_ASSUMED_NOT_ESTIMATED)
        self.assertTrue(prereg.SAMPLING_METHOD_LADDER[2].startswith("STOP"))

    def test_each_rung_re_earns_its_certificate(self):
        """Иначе B унаследует сертификат A — болезнь §4b этажом ниже."""
        self.assertTrue(prereg.EACH_RUNG_REPEATS_S5A_RATIO_IN_FULL)
        self.assertTrue(prereg.NO_THIRD_ATTEMPT)

    def test_coverage_is_checked_where_it_is_hard_not_only_where_it_is_easy(self):
        self.assertGreaterEqual(len(prereg.COVERAGE_DGP_SUITE), 6)
        joined = " ".join(prereg.COVERAGE_DGP_SUITE)
        for edge in ("near-zero denominator", "tied extrema", "weak identification",
                     "heavy censoring", "boundary", "flat-root"):
            self.assertIn(edge, joined)
        self.assertTrue(prereg.WORST_SCENARIO_DECIDES)
        self.assertIn("покрытие проверено — в опорной ячейке",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_acceptance_is_executable_and_accounts_for_mc_error(self):
        """95% на 1000 репликах проходит; 95% на 20 — нет, и это верно."""
        self.assertTrue(prereg.COVERAGE_ACCEPTANCE_ACCOUNTS_FOR_MC_ERROR)
        self.assertTrue(prereg.coverage_is_accepted(950, 1000))
        self.assertFalse(prereg.coverage_is_accepted(940, 1000))
        self.assertFalse(prereg.coverage_is_accepted(19, 20))
        self.assertEqual(prereg.wilson_lower(0, 0), 0.0)

    def test_the_wilson_limit_is_below_the_point_estimate(self):
        for k, n in ((950, 1000), (500, 1000), (990, 1000)):
            self.assertLess(prereg.wilson_lower(k, n), k / n)


class NumericalContractTests(unittest.TestCase):
    """Численная ошибка обязана расширять множество, а не сужать."""

    def test_the_engine_returns_a_bracket_and_rounds_outward(self):
        from coarsening.bounded import Bracket, generalized_inverse
        got = generalized_inverse(lambda x: 10.0 - x, 0.0, 100.0)
        self.assertIsInstance(got, Bracket)
        self.assertLessEqual(got.low, 10.0)
        self.assertGreaterEqual(got.high, 10.0)

    def test_shrinking_the_identified_set_is_a_forbidden_reading(self):
        self.assertIn("численная скобка сузила интервал — зато точнее",
                      prereg.FORBIDDEN_INTERPRETATIONS)


class SimultaneousCoverageTests(unittest.TestCase):
    """Семь утверждений уровня 95% не составляют одного уровня 95%."""

    def test_the_criterion_is_family_wise(self):
        self.assertTrue(prereg.COVERAGE_CRITERION_IS_SIMULTANEOUS)
        self.assertAlmostEqual(prereg.COVERAGE_ALPHA_EACH,
                               prereg.SIMULTANEOUS_ALPHA / len(prereg.COVERAGE_DGP_SUITE))
        self.assertGreater(prereg.COVERAGE_Z, 2.4)
        self.assertIn("покрытие 95% на семи сценариях — это 95%",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_the_replicate_count_follows_from_a_power_rule(self):
        """R=1000 отвергал бы валидный метод в 69 случаях из 70."""
        self.assertIn("union bound", prereg.GATE_POWER_RULE)
        self.assertTrue(prereg.GATE_POWER_USES_UNION_BOUND_NOT_INDEPENDENCE)
        self.assertAlmostEqual(prereg.GATE_POWER_PER_CELL_REQUIRED,
                               1 - prereg.GATE_POWER_FAMILY_BUDGET / 7)
        self.assertEqual(prereg.COVERAGE_REPLICATES, 4_000)
        self.assertIn("not by taste", prereg.COVERAGE_REPLICATES_CHOSEN_BY)

    def test_the_gate_actually_passes_a_nominal_method_at_the_chosen_R(self):
        """Проверка правила, а не веры в него: k* при R и вероятность пройти."""
        R = prereg.COVERAGE_REPLICATES
        kstar = next(k for k in range(R + 1) if prereg.coverage_is_accepted(k, R))
        self.assertLessEqual(kstar / R, 0.95,
                             "порог выше номинального: валидный метод не пройдёт")

    def test_the_worst_scenario_decides_not_the_average(self):
        self.assertTrue(prereg.WORST_SCENARIO_DECIDES)
        good, bad = (3980, 4000), (3600, 4000)
        self.assertTrue(prereg.suite_is_accepted([good, good]))
        self.assertFalse(prereg.suite_is_accepted([good, bad]))
        self.assertFalse(prereg.suite_is_accepted([]))


class ComputeBudgetTests(unittest.TestCase):
    """Метод, покрытие которого нельзя проверить, не используется."""

    def test_the_ladder_is_ordered_by_a_measured_budget(self):
        self.assertTrue(prereg.BUDGET_DECIDES_THE_LADDER_ORDER)
        self.assertGreater(prereg.MEASURED_MS_PER_PERIOD_RECOMPUTE, 0.0)
        self.assertIn("test inversion", prereg.SAMPLING_METHOD_LADDER[0])
        self.assertIn("OVER BUDGET", prereg.SAMPLING_METHOD_LADDER[1])

    def test_the_n_out_of_n_bootstrap_is_dropped_for_two_reasons(self):
        self.assertIn("known failure case", prereg.N_OUT_OF_N_BOOTSTRAP_IS_DROPPED)
        self.assertIn("unvalidatable", prereg.N_OUT_OF_N_BOOTSTRAP_IS_DROPPED)

    def test_an_unvalidatable_fallback_is_never_used(self):
        self.assertIn("never used", prereg.IF_METHOD_A_FAILS)
        self.assertIn("DESIGN changes", prereg.IF_METHOD_A_FAILS)
        self.assertIn("НЕ используется", prereg.STOP_RULES["unvalidatable_method"])

    def test_the_budget_arithmetic_reproduces(self):
        """Числа в prereg должны СЛЕДОВАТЬ из замера, а не стоять рядом с ним.

        Сценарии идут на крайних точках лестницы диад (25 и 400), поэтому
        стоимость усредняется по ним — как и при выборе порядка лестницы.
        """
        ms = prereg.MEASURED_MS_PER_PERIOD_RECOMPUTE
        arms, boot, R = 2, 2_000, prereg.COVERAGE_REPLICATES
        scenarios = len(prereg.COVERAGE_DGP_SUITE)
        recompute = lambda n: ms * n / 1000.0

        boot_days = (sum(recompute(n) * boot * arms for n in (25, 400)) / 2
                     * R * scenarios / 86_400)
        self.assertGreater(boot_days, 100, "бутстрап обязан выходить за бюджет")

        analytic_hours = (sum(recompute(n) * arms * 2 for n in (25, 400)) / 2
                          * R * scenarios / 3_600)
        self.assertLess(analytic_hours, prereg.COVERAGE_GATE_COMPUTE_BUDGET_HOURS)


class DiversionProtocolTests(unittest.TestCase):
    """Протокол, проверяющий гейты, сам нуждался в гейте."""

    def test_the_protocol_is_executable_and_isolated(self):
        self.assertTrue(prereg.DIVERSION_PROTOCOL_REQUIRES_BYTECODE_ISOLATION)
        path = pathlib.Path(prereg.DIVERSION_PROTOCOL_IS_EXECUTABLE)
        self.assertTrue((pathlib.Path(__file__).resolve().parents[3] / path).exists())

    def test_every_declared_diversion_has_a_unique_anchor(self):
        """Иначе протокол падает на якоре, а не на гейте."""
        from tools import diversion
        root = pathlib.Path(diversion.__file__).resolve().parent.parent
        for name, rel, old, _new, _mods in diversion.DIVERSIONS:
            self.assertEqual((root / rel).read_text().count(old), 1, name)

    def test_the_declared_diversions_cover_the_new_gates(self):
        from tools import diversion
        names = " ".join(d[0] for d in diversion.DIVERSIONS)
        for gate in ("наружу", "плато", "отказ", "поправка", "реплик", "отсечка"):
            self.assertIn(gate, names)


class RegularityGateTests(unittest.TestCase):
    """После отказа от бутстрапа производная стала несущей балкой."""

    KW = dict(delta=60.0, horizon=300.0, window_end=900.0, time_layer=False)
    #: излом при λ = 60: наклон −1 -> −2
    KINKED = [Bin(0.0, 2, 1), Bin(60.0, 0, 1)]
    #: гладкая, корень 120
    SMOOTH = [Bin(0.0, 1, 0), Bin(120.0, 0, 1)]

    def _psi(self, bins):
        from coarsening.bounded import _optimise
        return lambda lam: _optimise(bins, lam=lam, maximise=False,
                                     require_any=False, **self.KW)

    def test_the_envelope_claim_is_narrowed_to_where_it_holds(self):
        self.assertTrue(prereg.ENVELOPE_GIVES_THE_DERIVATIVE_ONLY_WHERE_THE_ARGMIN_IS_UNIQUE)
        self.assertTrue(prereg.SLOPE_NEVER_ZERO_IS_NOT_SLOPE_CONTINUOUS)
        self.assertIn("E[ψ] stays smooth", prereg.REGULARITY_IS_ABOUT_g_NOT_ABOUT_EVERY_psi)

    def test_the_sample_level_check_is_recorded_as_blind(self):
        """Оно не «не там реализовано», оно слепнет С РОСТОМ n."""
        self.assertTrue(prereg.SAMPLE_LEVEL_REGULARITY_CHECK_IS_ASYMPTOTICALLY_BLIND)
        self.assertIn("59/60 at n = 1600", prereg.BLINDNESS_MEASURED)
        self.assertTrue(prereg.REGULARITY_GATE_CHECKS_THE_POPULATION_NOT_THE_SAMPLE)

    def test_the_blindness_reproduces(self):
        """Не верим записи — воспроизводим: популяционный разрыв 0.5, а
        выборочная проверка в выборочном корне его не видит."""
        from coarsening.bounded import generalized_inverse, one_sided_slopes
        rng = random.Random(1)
        periods = [self.KINKED if rng.random() < 0.5 else self.SMOOTH
                   for _ in range(400)]
        G = lambda lam: sum(self._psi(b)(lam) for b in periods)
        root = generalized_inverse(G, 0.0, 300.0 + 1e-9, tolerance=1e-9)
        lam = (root.low + root.high) / 2
        left, right = one_sided_slopes(G, lam)
        self.assertEqual(left, right, "выборочная проверка обязана СКАЗАТЬ regular")
        h = 1e-5
        below = sum((self._psi(b)(60.0) - self._psi(b)(60.0 - h)) / h for b in periods)
        above = sum((self._psi(b)(60.0 + h) - self._psi(b)(60.0)) / h for b in periods)
        self.assertGreater(abs(below - above) / len(periods), 0.1,
                           "а популяционный разрыв при этом есть")

    def test_the_population_certificate_fires_on_the_counterexample(self):
        from coarsening.bounded import count_near_breakpoints
        periods = [self.KINKED] * 100 + [self.SMOOTH] * 100
        hits, nearest = count_near_breakpoints(periods, 60.0, 10.0, **self.KW)
        self.assertEqual(hits, 100)
        self.assertEqual(nearest, 0.0, "излом РОВНО в корне обязан ловиться")
        self.assertFalse(prereg.regularity_is_accepted(hits, len(periods), 1.0, 1.0))

    def test_the_population_certificate_stays_quiet_on_smooth_periods(self):
        from coarsening.bounded import count_near_breakpoints
        periods = [self.SMOOTH] * 50
        hits, nearest = count_near_breakpoints(periods, 60.0, 10.0, **self.KW)
        self.assertEqual((hits, nearest), (0, None))

    def test_zero_observations_become_a_bound_not_a_zero(self):
        """«Изломов не найдено» не равно «изломов нет»."""
        self.assertGreater(prereg.wilson_upper(0, 4_000), 0.0)
        self.assertLess(prereg.wilson_upper(0, 4_000), 0.01)
        self.assertTrue(prereg.regularity_is_accepted(0, 4_000, 3.0, 1.5))
        self.assertIn("Wilson", prereg.REGULARITY_RESIDUAL_BOUND)

    def test_the_radius_is_tied_to_the_uncertainty_of_the_root(self):
        self.assertGreaterEqual(prereg.REGULARITY_RADIUS_SE_MULTIPLE, 2.0)
        self.assertIn("standard errors", prereg.REGULARITY_GATE)

    def test_the_denominator_heuristic_is_withdrawn(self):
        """Как интуиция сгодится, как заверение — опасна."""
        self.assertTrue(prereg.DENOMINATOR_HEURISTIC_IS_WITHDRAWN_AS_ASSURANCE)
        self.assertFalse(hasattr(prereg, "WHY_THE_ROOT_IS_USUALLY_REGULAR"))

    def test_interiority_is_a_second_independent_gate(self):
        self.assertEqual(len(prereg.REGULARITY_GATES_ARE_TWO), 2)
        self.assertTrue(prereg.interiority_is_accepted(1200.0, 2.3, 3600.0))
        self.assertFalse(prereg.interiority_is_accepted(0.0, 2.3, 3600.0))
        self.assertFalse(prereg.interiority_is_accepted(3599.0, 2.3, 3600.0))
        self.assertTrue(prereg.BOUNDARY_CELLS_GET_NO_SYMMETRIC_INTERVAL)

    def test_the_boundary_is_shown_to_be_genuine(self):
        """Если бы её можно было перешагнуть, это была бы граница поиска."""
        self.assertIn("no crossing exists there",
                      prereg.BOUNDARY_IS_GENUINE_NOT_A_SEARCH_ARTEFACT)
        for lam in (-1.0, -60.0, -1000.0):
            self.assertGreaterEqual(self._psi(self.KINKED)(lam), 0.0, lam)


class DiversionSelfTestTests(unittest.TestCase):
    """Harness обязан доказать, что исполняет испорченный им файл."""

    def test_the_harness_has_a_self_test_and_a_cache_contract(self):
        from tools import diversion
        source = pathlib.Path(diversion.__file__).read_text()
        self.assertIn("PYTHONPYCACHEPREFIX", source)
        self.assertTrue(hasattr(diversion, "self_test"))
        self.assertIn("self_test()", source)

    def test_minus_B_alone_is_named_as_insufficient(self):
        from tools import diversion
        self.assertIn("НЕ КОНТРАКТ", diversion.run_tests.__doc__)


class BlindGateGoldenTests(unittest.TestCase):
    """ПОСТОЯННЫЙ СВИДЕТЕЛЬ, а не тест текущей реализации.

    Он фиксирует, почему ЦЕЛЫЙ КЛАСС процедур запрещён:

        никогда не определять популяционную регулярность вопросом
        «попал ли выборочный корень ровно в выборочный излом»

    Если когда-нибудь кто-то снова предложит такую проверку, этот тест
    показывает, что она становится тем зеленее, чем больше данных.
    """

    KW = dict(delta=60.0, horizon=300.0, window_end=900.0, time_layer=False)
    KINKED = [Bin(0.0, 2, 1), Bin(60.0, 0, 1)]
    SMOOTH = [Bin(0.0, 1, 0), Bin(120.0, 0, 1)]
    TRUE_ROOT = 60.0

    def _psi(self, bins, lam):
        from coarsening.bounded import _optimise
        return _optimise(bins, lam=lam, maximise=False, require_any=False, **self.KW)

    def test_the_population_really_has_a_kink_at_the_root(self):
        h = 1e-5
        mix = [self.KINKED] * 100 + [self.SMOOTH] * 100
        below = sum((self._psi(b, self.TRUE_ROOT) - self._psi(b, self.TRUE_ROOT - h)) / h
                    for b in mix) / len(mix)
        above = sum((self._psi(b, self.TRUE_ROOT + h) - self._psi(b, self.TRUE_ROOT)) / h
                    for b in mix) / len(mix)
        self.assertAlmostEqual(below, -1.0, places=3)
        self.assertAlmostEqual(above, -1.5, places=3)
        self.assertAlmostEqual(sum(self._psi(b, self.TRUE_ROOT) for b in mix), 0.0,
                               places=6, msg="корень обязан быть РОВНО в изломе")

    def test_a_sample_root_check_calls_it_regular_and_gets_worse_with_n(self):
        from coarsening.bounded import generalized_inverse, one_sided_slopes
        rng = random.Random(17)
        verdicts = {}
        for n in (50, 800):
            regular = 0
            for _ in range(20):
                periods = [self.KINKED if rng.random() < 0.5 else self.SMOOTH
                           for _ in range(n)]
                G = lambda lam: sum(self._psi(b, lam) for b in periods)
                root = generalized_inverse(G, 0.0, 300.0 + 1e-9, tolerance=1e-9)
                left, right = one_sided_slopes(G, (root.low + root.high) / 2)
                regular += left == right
            verdicts[n] = regular / 20
        self.assertGreaterEqual(verdicts[50], 0.8, verdicts)
        self.assertGreaterEqual(verdicts[800], 0.8, verdicts)

    def test_the_population_certificate_sees_what_the_sample_check_cannot(self):
        from coarsening.bounded import count_near_breakpoints
        mix = [self.KINKED] * 100 + [self.SMOOTH] * 100
        hits, nearest = count_near_breakpoints(mix, self.TRUE_ROOT, 5.0, **self.KW)
        self.assertEqual(hits, 100)
        self.assertEqual(nearest, 0.0)


class BreakpointLocalisationTests(unittest.TestCase):
    """Дихотомия внутри nearest_breakpoint набором не исполнялась —
    NameError нашёлся вручную, а не тестом. Больше нет."""

    KW = dict(delta=60.0, horizon=300.0, window_end=900.0, time_layer=False)

    def test_the_distance_is_located_not_just_detected(self):
        from coarsening.bounded import Bin as B, _optimise, nearest_breakpoint
        kinked = [B(0.0, 2, 1), B(60.0, 0, 1)]
        psi = lambda lam: _optimise(kinked, lam=lam, maximise=False,
                                    require_any=False, **self.KW)
        for probe, want in ((63.0, 3.0), (60.25, 0.25), (57.5, 2.5), (60.0, 0.0)):
            got = nearest_breakpoint(psi, probe, 10.0)
            self.assertIsNotNone(got, probe)
            self.assertAlmostEqual(got, want, places=5, msg=probe)

    def test_the_affine_threshold_is_tied_to_the_minimum_possible_sag(self):
        from coarsening import bounded
        self.assertLess(bounded.AFFINE_SAG_FRACTION, 1e-4)
        self.assertFalse(hasattr(bounded, "AFFINE_TOLERANCE"))


class AcceptanceSetGeometryTests(unittest.TestCase):
    """Связность множества принятия не следует из единственности корня."""

    def test_the_full_set_is_required_and_the_shortcut_forbidden(self):
        self.assertTrue(prereg.FULL_ACCEPTANCE_SET_IS_REQUIRED)
        self.assertTrue(prereg.TWO_BISECTIONS_AROUND_THE_ROOT_ARE_FORBIDDEN)
        self.assertTrue(prereg.ACCEPTANCE_SET_NEED_NOT_BE_CONNECTED)
        self.assertIn("корень единственный, значит доверительное множество — интервал",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_the_golden_counterexample_is_named_and_reproduces(self):
        from coarsening.inversion import Piece, acceptance_set
        self.assertIn("N=100", prereg.FIELLER_GOLDEN)
        periods = [(Piece(100.0, 131520.0),)] + [(Piece(1.0, 720.0),)] * 24
        got = acceptance_set(periods, z=1.959963984540054, lo=0.0, hi=3600.0)
        self.assertEqual(len(got), 2, got)

    def test_only_the_convex_hull_may_become_an_interval(self):
        self.assertIn("convex hull", prereg.INTERVAL_CONVERSION)
        self.assertTrue(prereg.UGLY_SETS_ARE_REPORTED_AS_IS)
        self.assertIn("вторая компонента выглядит странно, уберём её",
                      prereg.FORBIDDEN_INTERPRETATIONS)

    def test_the_exact_computation_is_named(self):
        self.assertIn("quadratic", prereg.ACCEPTANCE_SET_IS_COMPUTED_EXACTLY)

    def test_zero_variance_has_a_declared_semantics(self):
        """И обоснование правильное: это соглашение теста, а не вывод о
        покрытии. Из E[ψ(λ0)] = 0 не следует нулевое ВЫБОРОЧНОЕ среднее."""
        from coarsening import inversion
        self.assertIn("do not reject", prereg.ZERO_VARIANCE_RULE)
        self.assertIn("costs power, not coverage", prereg.ZERO_VARIANCE_RULE)
        self.assertTrue(prereg.ZERO_VARIANCE_COSTS_POWER_NOT_COVERAGE)
        self.assertTrue(prereg.ZERO_VARIANCE_FREQUENCY_IS_REPORTED)
        self.assertTrue(inversion.ZERO_VARIANCE_IS_ACCEPTED)
        self.assertTrue(inversion.ZERO_VARIANCE_COSTS_POWER_NOT_COVERAGE)

    def test_the_domain_is_structural_not_a_search_cap(self):
        """Иначе компоненту, упирающуюся в H, нельзя читать как конечную."""
        self.assertIn("B <= H·N", prereg.DOMAIN_IS_STRUCTURAL)
        self.assertTrue(prereg.DOMAIN_UPPER_END_IS_NOT_A_SEARCH_CAP)
        self.assertTrue(prereg.DOMAIN_INVARIANT_IS_TESTED)

    def test_no_multiplicity_correction_over_lambda(self):
        """Покрытие определяется поведением теста в истинном λ0."""
        self.assertTrue(prereg.NO_MULTIPLICITY_CORRECTION_OVER_lambda)


class Stage1RunnerTests(unittest.TestCase):
    """Entrypoint этапа 1 восстановлен из /tmp в tracked source.

    Модуль НАМЕРЕННО не реализует лестницу M и статусы точности: prereg
    замораживает правило, но не оценщик MCSE. См.
    docs/research/s5b-mcse-specification-gap.md.
    """

    def test_the_entrypoint_is_tracked_now(self):
        from simulation import s5b_stage1
        path = pathlib.Path(s5b_stage1.__file__)
        self.assertTrue(path.exists())
        self.assertIn("simulation", str(path))

    def test_the_arm_tag_is_scientific_identity_only(self):
        """Сид не должен зависеть от worker, shard, порядка и их количества."""
        from simulation import s5b_stage1 as S
        tag = S.arm_tag(6.0, 1.1, "R2", 2.0)
        self.assertEqual(tag, "r6.0:c1.1:R2:m2.0")
        for forbidden in ("shard", "worker", "index", "rank", "job"):
            self.assertNotIn(forbidden, tag)

    def test_the_arm_grid_matches_the_prereg_count(self):
        from simulation import s5b_stage1 as S
        self.assertEqual(len(S.REGIMES), 13)
        arms = len(S.REGIMES) * len(prereg.C_REACTIVITY_POINTS) * \
            len(prereg.OPPORTUNITY_RATE_GRID)
        self.assertEqual(arms, prereg.LATENT_SIMULATIONS)

    def test_the_effect_scale_is_logarithmic_as_declared(self):
        """m·shift и ratio**m, и R0 не масштабируется."""
        from simulation import s5b_stage1 as S
        self.assertEqual(S.effect("R0", 2.0), (0.0, 1.0))
        shift_one, ratio_one = S.effect("R2", 1.0)
        shift_two, ratio_two = S.effect("R2", 2.0)
        self.assertAlmostEqual(ratio_two, ratio_one ** 2)
        shift_a, _ = S.effect("R1", 0.5)
        shift_b, _ = S.effect("R1", 1.0)
        self.assertAlmostEqual(shift_a, shift_b * 0.5)

    def test_the_runner_does_not_pretend_to_implement_the_ladder(self):
        """Реализовать произвольную формулу SE и назвать это исполнением
        замороженного правила — дописать prereg задним числом."""
        from simulation import s5b_stage1 as S
        source = pathlib.Path(S.__file__).read_text()
        for absent in ("MEASUREMENT_MC_ESCALATION_FACTOR",
                       "MEASUREMENT_MC_MAX_PERIODS_PER_ARM",
                       "MC_PRECISION_INSUFFICIENT"):
            self.assertNotIn(f"P.{absent}", source, absent)
        self.assertIn("НЕ реализованы", source)

    def test_the_specification_gap_is_documented_not_silently_filled(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        note = root / "docs/research/s5b-mcse-specification-gap.md"
        self.assertTrue(note.exists())
        text = note.read_text()
        self.assertIn("ПРЕДЛАГАЕМЫЙ АМЕНДМЕНТ", text)
        self.assertIn("NOT_EVALUATED_MC_PRECISION", text)
        self.assertIn("MC_PRECISION_PREDICTED_INSUFFICIENT", text)

    def test_the_baseline_has_no_futility_rule_to_appeal_to(self):
        """Ранний пропуск ячеек не может ссылаться на prereg, которого нет."""
        for absent in ("FUTILITY", "EARLY_STOP", "PREDICTED_INSUFFICIENT"):
            self.assertFalse(hasattr(prereg, absent), absent)

    def test_the_aborted_run_is_recorded_as_invalid(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        record = root / "docs/research/s5b-stage1-aborted-serial-run.md"
        self.assertTrue(record.exists())
        text = record.read_text()
        self.assertIn("ABORTED_INVALID_IMPLEMENTATION", text)
        self.assertIn("EQUIVALENCE ORACLE", text)


class PrecisionRadiusTests(unittest.TestCase):
    """Правило точности — fixed-width по ПОЛНОМУ множеству, а не MCSE.

    Тождество «ширина = 2z·SE» принадлежит вальдову интервалу; инверсия
    теста выбиралась ровно за то, что вальдовой геометрии у неё нет.
    """

    def test_the_ladder_comes_from_the_frozen_constants(self):
        from simulation import s5b_precision as PR
        self.assertEqual(PR.LOOKS, (4_000, 16_000, 64_000))
        self.assertEqual(PR.LOOKS[0], prereg.MEASUREMENT_MC_START_PERIODS_PER_ARM)
        self.assertEqual(PR.LOOKS[-1], prereg.MEASUREMENT_MC_MAX_PERIODS_PER_ARM)

    def test_the_radius_uses_the_whole_set_not_the_component(self):
        """Собственный Филлер-golden: компонента вокруг корня вдвое уже."""
        from simulation import s5b_precision as PR
        full = [(0.0, 1273.95), (1535.81, 3600.0)]
        self.assertEqual(PR.radius(full, 1200.0), 2400.0)
        self.assertEqual(PR.radius([(0.0, 1273.95)], 1200.0), 1200.0)

    def test_the_criterion_reduces_to_the_frozen_one_in_the_wald_case(self):
        """A = λ̂ ± z·SE  =>  r = z·SE  =>  критерий это SE <= target."""
        from simulation import s5b_precision as PR
        delta = 36.0
        target = PR.target(delta)
        for se in (target * 0.5, target * 0.999, target * 1.001, target * 2):
            point = 1200.0
            wald = [(point - PR.Z_PER_LOOK * se, point + PR.Z_PER_LOOK * se)]
            self.assertEqual(PR.is_precise(PR.radius(wald, point), delta),
                             se <= target, se)

    def test_the_multiplicity_counts_endpoints_as_well_as_looks(self):
        """Сертификат ЯЧЕЙКИ — 4 конца x 3 просмотра, а не 3 просмотра.

        Первая редакция делила уровень только по просмотрам и молча
        считала, что четыре конца ячейки — одно утверждение.
        """
        from simulation import s5b_precision as PR
        self.assertEqual(PR.ENDPOINTS_PER_CELL, 4)
        self.assertEqual(len(PR.LOOKS), 3)
        self.assertEqual(PR.COMPARISONS, 12)
        self.assertAlmostEqual(PR.ALPHA_PER_COMPARISON,
                               (1 - prereg.CONFIDENCE_LEVEL) / 12)
        self.assertGreater(PR.Z_PER_COMPARISON, 2.86)
        self.assertLess(PR.Z_PER_COMPARISON, 2.87)

    def test_the_first_edition_name_cannot_carry_the_first_edition_value(self):
        """`Z_PER_LOOK` оставлено как имя, но указывает на ТЕКУЩЕЕ значение."""
        from simulation import s5b_precision as PR
        self.assertEqual(PR.Z_PER_LOOK, PR.Z_PER_COMPARISON)
        self.assertFalse(hasattr(PR, "ALPHA_PER_LOOK"),
                         "имя с прежней арифметикой обязано исчезнуть")

    def test_the_threshold_itself_does_not_move_with_z(self):
        """r <= z·target  <=>  SE <= target в вальдовом случае при ЛЮБОМ z."""
        from simulation import s5b_precision as PR
        delta, point = 36.0, 1200.0
        limit = PR.target(delta)
        for z in (1.96, 2.394, PR.Z_PER_COMPARISON, 4.0):
            for se in (limit * 0.5, limit * 0.999, limit * 1.001, limit * 2):
                wald = [(point - z * se, point + z * se)]
                self.assertEqual(
                    PR.is_precise(PR.radius(wald, point), delta, z=z),
                    se <= limit, (z, se))

    def test_an_empty_set_is_infinitely_imprecise(self):
        from simulation import s5b_precision as PR
        self.assertEqual(PR.radius([], 100.0), float("inf"))
        self.assertFalse(PR.is_precise(PR.radius([], 100.0), 36.0))

    def test_the_nested_procedure_stops_and_escalates_as_declared(self):
        from simulation import s5b_precision as PR
        seen = []

        def wide(size):
            seen.append(size)
            return [(0.0, 3600.0)], 1200.0

        outcome = PR.run_nested(wide, 36.0)
        self.assertEqual(seen, list(PR.LOOKS), "обязана пройти всю лестницу")
        self.assertIs(outcome.status, PR.PrecisionStatus.INSUFFICIENT)

        seen.clear()

        def narrow(size):
            seen.append(size)
            return [(1199.9, 1200.1)], 1200.0

        outcome = PR.run_nested(narrow, 36.0)
        self.assertEqual(seen, [PR.LOOKS[0]], "обязана остановиться на первом")
        self.assertIs(outcome.status, PR.PrecisionStatus.ACHIEVED)

    def test_the_surface_status_is_separate_from_every_verdict(self):
        from simulation import s5b_precision as PR
        self.assertEqual(PR.NOT_EVALUATED_MC_PRECISION, "NOT_EVALUATED_MC_PRECISION")
        for verdict in Verdict:
            self.assertNotEqual(PR.NOT_EVALUATED_MC_PRECISION, verdict.value)
        for state in Admissibility:
            self.assertNotEqual(PR.NOT_EVALUATED_MC_PRECISION, state.value)

    def test_prediction_is_not_a_verdict(self):
        from simulation import s5b_precision as PR
        self.assertNotEqual(PR.PrecisionStatus.PREDICTED_INSUFFICIENT,
                            PR.PrecisionStatus.INSUFFICIENT)
        self.assertIn("PREDICTED", PR.PrecisionStatus.PREDICTED_INSUFFICIENT.value)

    def test_the_retracted_claims_are_marked_not_erased(self):
        """Проект ошибки не стирает, а помечает — значит проверяется
        КОНТЕКСТ, а не отсутствие фразы. Первая редакция этого теста
        требовала отсутствия и падала на собственном опровержении."""
        root = pathlib.Path(__file__).resolve().parents[3]
        raw = (root / "docs/research/s5b-mcse-specification-gap.md").read_text()
        #: перенос строки не должен прятать фразу от проверки
        flat = " ".join(raw.replace(">", " ").split())
        self.assertIn("Это неверно", flat)
        self.assertIn("MC precision radius", flat)
        for claim, marker in (("ближе к перцентилю", "удалено"),
                              ("(sup A − inf A) / (2z)", "Это неверно")):
            self.assertIn(claim, flat, claim)
            paragraph = next(part for part in raw.split("\n\n") if claim in part)
            self.assertIn(marker, paragraph, (claim, marker))

class PrecisionQualificationDeclarationTests(unittest.TestCase):
    """Амендмент вступает в силу только после квалификации (B-7).

    Здесь проверяется ОБЪЯВЛЕНИЕ, а не результат: набор, пороги и лестница
    записаны раньше, чем получены числа. Порядок коммитов — часть
    доказательства, что суита не подгонялась под исход.
    """

    def _note(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        return (root / "docs/research/s5b-mcse-specification-gap.md").read_text()

    def test_the_declaration_says_it_precedes_the_numbers(self):
        note = self._note()
        self.assertIn("## 6. Квалификация: ЧТО ОБЪЯВЛЕНО ДО ПРОГОНА", note)
        self.assertIn("до того, как получены числа", note)

    def test_the_ladder_declared_is_the_production_one(self):
        """Масштабированная лестница квалифицирует не ту процедуру.

        Требуется отсутствие не СТРОКИ, а УПОТРЕБЛЕНИЯ: проект ошибки не
        стирает, а помечает, поэтому прежнюю лестницу называть можно —
        но только в абзаце, который её отзывает. Первая редакция этого
        теста запрещала строку и падала на собственном отзыве.
        """
        note = self._note()
        self.assertIn("ПРОИЗВОДСТВЕННАЯ", note)
        self.assertIn("`4000 → 16000 → 64000`", note)
        for paragraph in note.split("\n\n"):
            if "400 → 1600 → 6400" in paragraph:
                self.assertIn("отозвана", paragraph,
                              "прежняя лестница названа вне отзыва")

    def test_the_declared_suite_matches_the_executable_one(self):
        """Таблица в документе и код обязаны называть ОДНИ И ТЕ ЖЕ сценарии."""
        from tools import s5b_qualify as Q
        note = self._note()
        for scenario in Q.SCENARIOS:
            self.assertIn(f"`{scenario.name}`", note, scenario.name)
        self.assertEqual(len(Q.SCENARIOS), 9)
        flat = " ".join(note.replace(">", " ").split())
        for required in ("Филлер-golden с несвязным множеством",
                         "излом в корне", "граничный корень `λ0 = 0`",
                         "вырожденная дисперсия", "тяжёлым `N = 0`",
                         "малое `M`", "намеренно заниженное множество"):
            self.assertIn(required, flat, required)

    def test_the_acceptance_rule_is_the_existing_one_not_a_new_one(self):
        from tools import s5b_qualify as Q
        self.assertIn("уже существующий", self._note())
        self.assertEqual(prereg.COVERAGE_ACCEPTANCE_FLOOR, 0.93)
        self.assertEqual(Q.REPLICATES, prereg.COVERAGE_REPLICATES)
        self.assertEqual(Q.DELTA, min(prereg.DELTA_FRACTIONS_OF_HORIZON) * 3600.0)

    def test_the_family_correction_is_not_borrowed_from_a_smaller_family(self):
        from tools import s5b_qualify as Q
        self.assertGreater(Q.SUITE_Z, prereg.COVERAGE_Z)
        self.assertIn("одалживать поправку на меньшее семейство",
                      " ".join(self._note().split()))

    def test_the_secondary_quantity_is_declared_as_not_gating(self):
        """Покрытие на остановке названо заранее и заранее объявлено вторичным."""
        flat = " ".join(self._note().split())
        self.assertIn("как вторичное и не гейтящее число", flat)
        self.assertIn("Гейт стоит НЕ на нём", flat)

    def test_the_declared_immunity_of_two_scenarios_is_argued_in_advance(self):
        from tools import s5b_qualify as Q
        self.assertIn("уронить **не может**", " ".join(self._note().split()))
        immune = {s.name for s in Q.SCENARIOS if not s.narrow_control_must_fail}
        self.assertEqual(immune, {"boundary_zero", "degenerate_variance"})

    def test_the_fast_path_substitution_is_disclosed_not_silent(self):
        flat = " ".join(self._note().split())
        self.assertIn("не дублируется", flat)
        self.assertIn("РАБОЧИХ `M` (4000, 16000, 64000)", flat)

    def test_the_pilot_peek_is_disclosed(self):
        """Подсматривание было; оно записано, а не забыто."""
        self.assertIn("был сделан до объявления** и здесь раскрыт",
                      " ".join(self._note().split()))

    def test_the_harness_is_versioned_code_not_a_run_artifact(self):
        """ADR-0003 §6: гейтящие числа — только из версионированных скриптов."""
        root = pathlib.Path(__file__).resolve().parents[3]
        self.assertTrue((root / "research/python/tools/s5b_qualify.py").exists())
        self.assertIn("ADR-0003 §6", self._note())


class PrecisionQualificationResultTests(unittest.TestCase):
    """Результат квалификации. Суита НЕ пройдена, и это записано так."""

    def _note(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        return (root / "docs/research/s5b-mcse-specification-gap.md").read_text()

    def _flat(self):
        return " ".join(self._note().split())

    def test_the_verdict_is_a_failure_and_says_so_in_the_heading(self):
        note = self._note()
        self.assertIn("## 7. Квалификация: РЕЗУЛЬТАТ — СУИТА НЕ ПРОЙДЕНА", note)
        self.assertIn("`fieller` отклонён", self._flat())
        self.assertIn("0.9036", note)          # нижняя граница провала
        self.assertIn("0.9150", note)          # точечная оценка провала

    def test_the_amendment_did_not_become_active(self):
        flat = self._flat()
        self.assertIn("Амендмент остаётся ПРЕДЛОЖЕНИЕМ", flat)
        self.assertIn("Шардинг не начинается", flat)
        self.assertIn("Реализация Stage 1 escalation не начинается", flat)
        self.assertIn("ПРЕДЛАГАЕМЫЙ амендмент", flat)

    def test_the_multiplicity_claim_is_about_the_suite_not_about_necessity(self):
        """Не «Бонферрони необходим», а «без поправки суиту не прошли».

        Первая формулировка утверждает свойство метода, которого замер не
        устанавливает: измерено, что НЕОТКОРРЕКТИРОВАННАЯ процедура не
        прошла ОБЪЯВЛЕННУЮ суиту, а не что никакая другая поправка не
        справилась бы.
        """
        flat = self._flat()
        self.assertIn("не прошла объявленную квалификационную суиту", flat)
        self.assertIn("прошла в восьми сценариях из девяти", flat)
        for retired in ("поправка на три просмотра **необходима**",
                        "ПОПРАВКА НА ТРИ ПРОСМОТРА НЕОБХОДИМА",
                        "Бонферрони его возвращает"):
            self.assertNotIn(retired, flat, retired)

    def test_passing_is_stated_as_clearing_the_floor_not_as_proof(self):
        flat = self._flat()
        self.assertIn("превысила объявленный пол `0.93`", flat)
        self.assertNotIn("Номинал `0.95` доказан", flat)
        self.assertIn("Номинал `0.9875` не установлен нигде", flat)

    def test_the_failure_mechanism_is_localised_not_hand_waved(self):
        flat = self._flat()
        self.assertIn("CV(N)² > M/z²", flat)
        self.assertIn("промахов 307", flat)
        self.assertIn("промахов   0 = 0.0000", self._note())
        self.assertIn("ни одна из 4000 реплик не могла остановиться", flat)

    def test_the_diagnostic_is_marked_as_following_the_verdict(self):
        """Диагностика объясняет вердикт, а не пересматривает его."""
        self.assertIn("посчитана **после** вердикта и вердикта не меняет",
                      self._flat())

    def test_the_obvious_repair_is_proposed_and_explicitly_not_applied(self):
        """Уточнённый критерий прошёл бы — и ровно поэтому не берётся."""
        flat = self._flat()
        self.assertIn("ПРЕДЛОЖЕНИЕ, которое здесь НЕ вводится", flat)
        self.assertIn("выбор критерия по результату", flat)
        self.assertIn("редакцией 4 со СВОИМ объявлением и СВОИМ прогоном", flat)

    def test_the_secondary_number_is_reported_because_it_was_declared(self):
        flat = self._flat()
        self.assertIn("0.9942", flat)
        self.assertIn("названа вторичной заранее и вторичной остаётся", flat)

    def test_both_ladder_branches_and_the_geometry_were_actually_reached(self):
        flat = self._flat()
        self.assertIn("3723 несвязных множества из 12000 построений", flat)
        self.assertIn("задевает ВСЕ четыре исхода сразу", flat)

    def test_the_negative_controls_behaved_as_declared(self):
        flat = self._flat()
        self.assertIn("отклонено ровно в тех семи сценариях, для которых это "
                      "было объявлено до прогона", flat)
        self.assertIn("Объявленное ожидание исполнено без правок", flat)

