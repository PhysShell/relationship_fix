"""PREREG S5b: заморожено до прогона, и тесты следят, чтобы так и осталось.

Здесь нет ни одного прогона. Проверяется дисциплина: сетки объявлены,
STRICT не может стать primary, два гейта не сливаются в один, и pilot N не
выходит одним числом.
"""

import math
import random
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
        self.assertIn("bootstrap", prereg.SAMPLING_INTERVAL)

    def test_the_bootstrap_is_frozen_end_to_end(self):
        self.assertEqual(len(prereg.SAMPLING_INFERENCE), 5)
        self.assertIn("no linearisation", prereg.SAMPLING_INFERENCE[1])
        self.assertTrue(prereg.BOOTSTRAP_RESAMPLES_RANDOMISED_UNITS)
        self.assertGreater(prereg.BOOTSTRAP_REPLICATES, 0)

    def test_degenerate_replicates_are_counted_not_dropped(self):
        self.assertTrue(prereg.BOOTSTRAP_DEGENERATE_SHARE_IS_REPORTED)
        self.assertGreater(prereg.BOOTSTRAP_DEGENERATE_REPLICATE_LIMIT, 0.0)

    def test_coverage_is_checked_not_assumed(self):
        """Иначе метод снова выбирается после того, как видно, какой нравится."""
        self.assertTrue(prereg.SAMPLING_METHOD_COVERAGE_STUDY)
        self.assertTrue(prereg.COVERAGE_IS_OF_THE_SET_NOT_OF_A_POINT)
        self.assertIn("⊇", prereg.COVERAGE_TARGET)
        self.assertIn("SAMPLING_METHOD_INVALID", prereg.COVERAGE_FAILURE_RULE)
        self.assertTrue(prereg.NO_SHOPPING_FOR_A_BOOTSTRAP_THAT_COVERS)
        self.assertIn("SAMPLING_METHOD_INVALID", prereg.STOP_RULES["coverage_failure"])


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
