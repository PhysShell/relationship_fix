"""Гейты самой квалификации: быстрый путь обязан БЫТЬ производственным.

Быстрый путь введён потому, что производственный `acceptance_set` на
`M = 64000` x 4000 реплик считается часами. Подменить проверяемую функцию
её же переписанной версией и не сказать об этом — ровно тот способ, которым
проверки перестают что-либо проверять. Поэтому эквивалентность здесь
ПРОВЕРЯЕТСЯ, и на РАБОЧИХ `M`, а не только на игрушечных.
"""

from __future__ import annotations

import pathlib
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

    #: ДОПУСК ОТНОСИТЕЛЬНЫЙ, и это правка редакции 4. Прежний абсолютный
    #: `1e-6` пережил девять сценариев и споткнулся о десятый:
    #: `fieller_certifying` несёт `B = 12 000 499.5` при разбросе `psi`
    #: порядка 500, поэтому центрированные суммы теряют значащие цифры В
    #: ОБОИХ путях, а не в одном. Наблюдённое расхождение 6.2e-06 — это
    #: 1.7e-09 домена, при полуширине множества порядка 0.03.
    #:
    #: Допуск поднят ДО прогона и вместе с ним добавлена проверка, которая
    #: и есть содержательная: совпадение РЕШЕНИЙ, а не цифр. Число может
    #: разойтись в тринадцатом знаке; вердикт разойтись не имеет права.
    TOLERANCE = 1e-8 * (3600.0 - 0.0)

    def _compare(self, scenario, size, z, maximise=False):
        keeper = record(scenario, size)
        want = acceptance_set(keeper.periods, z=z, lo=Q.LO, hi=Q.HI,
                              maximise=maximise)
        got = Q.accept_from_segments(
            keeper.inner.segments(Q.LO, Q.HI, maximise=maximise),
            z=z, lo=Q.LO, hi=Q.HI)
        self.assertEqual(len(want), len(got),
                         f"{scenario.name} M={size}: {want} != {got}")
        worst = 0.0
        for (wa, wb), (ga, gb) in zip(want, got):
            worst = max(worst, abs(wa - ga), abs(wb - gb))
        self.assertLessEqual(worst, self.TOLERANCE,
                             f"{scenario.name} M={size}: расхождение {worst}")
        #: СОДЕРЖАТЕЛЬНАЯ проверка: ни одно решение не расходится
        point = Q.root_from_segments(
            keeper.inner.segments(Q.LO, Q.HI, maximise=maximise), Q.LO, Q.HI)
        for delta in Q.DELTAS:
            self.assertEqual(PR.is_precise(PR.radius(want, point), delta, z=z),
                             PR.is_precise(PR.radius(got, point), delta, z=z),
                             f"{scenario.name} M={size}: разошлась точность")
        self.assertEqual(
            any(a <= scenario.truth <= b for a, b in want),
            any(a <= scenario.truth <= b for a, b in got),
            f"{scenario.name} M={size}: разошлось покрытие")
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

    def test_agreement_holds_for_the_upper_endpoint_too(self):
        """Верхний конец берёт max по кускам — это другая выборка сегментов.

        Четвёрка концов ячейки состоит из λ⁻ И λ⁺, значит быстрый путь
        обязан совпадать с производственным и при `maximise=True`.
        """
        for scenario in Q.SCENARIOS:
            for size in (5, 100, 4_000):
                self._compare(scenario, size, Q.Z_DECLARED, maximise=True)

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
        cases = ((Q.FIELLER_CATALOGUE, (Fraction(1, 1000), Fraction(999, 1000)),
                  Fraction(1200)),
                 (Q.KINK_CATALOGUE, (Fraction(1, 2), Fraction(1, 4), Fraction(1, 4)),
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

    def test_the_failing_scenario_has_the_most_exact_truth_of_all(self):
        """`fieller` провалил гейт, значит его `λ0` обязан быть вне сомнений.

        Целыми числами, без плавающей точки: 10999 · 1200 = 13198800.
        """
        heavy, light = Q.FIELLER_CATALOGUE
        self.assertEqual((heavy[0].n, heavy[0].b), (10_000.0, 12_479_520.0))
        self.assertEqual((light[0].n, light[0].b), (1.0, 720.0))
        total_n = 10_000 + 999 * 1
        total_b = 12_479_520 + 999 * 720
        self.assertEqual(total_n, 10_999)
        self.assertEqual(total_b, 13_198_800)
        self.assertEqual(total_b, 1200 * total_n)
        #: физическая допустимость: B <= N·H при H = 3600
        self.assertLessEqual(heavy[0].b, heavy[0].n * Q.HI)
        self.assertLessEqual(light[0].b, light[0].n * Q.HI)

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
        result = Q.replicate(scenario, 0, namespace=Q.TEST_NAMESPACE,
                             ladder=(2, 4, 8))
        #: ТОЛЬКО объявленный `z`: контроль `z = 0.5` строит множество вчетверо
        #: уже цели и на восьми периодах способен объявить точность — это его
        #: работа, ровно поэтому он и контроль
        certified, covered, look = result[(Q.DELTA, "объявленный alpha/12")]
        self.assertFalse(certified, "восьми периодов не хватает на точность")
        self.assertIsNone(look)
        self.assertIsNone(covered)

    def test_the_harness_loop_reproduces_the_production_run_nested(self):
        """Общий поток на все δ и все `z` не меняет исход ни для одного.

        `run_nested` — производственная вложенная процедура. Harness гоняет
        девять конфигураций на ОДНОМ потоке ради скорости; если общий поток
        хоть где-то сдвинул момент остановки, экономия куплена подлогом.
        """
        for scenario in Q.SCENARIOS[:4]:
            for index in range(2):
                shared = Q.replicate(scenario, index,
                                     namespace=Q.TEST_NAMESPACE)
                for label, z in Q.CONFIGS:
                    for delta in Q.DELTAS:
                        def evaluate(size, scenario=scenario, index=index, z=z):
                            rng = random.Random(
                                f"{Q.TEST_NAMESPACE}:{scenario.name}:{index}")
                            sample = scenario.new_sample()
                            for _ in range(size):
                                scenario.draw(rng, sample)
                            segments = sample.segments(Q.LO, Q.HI)
                            return (Q.accept_from_segments(segments, z=z,
                                                           lo=Q.LO, hi=Q.HI),
                                    Q.root_from_segments(segments, Q.LO, Q.HI))
                        want = PR.run_nested(evaluate, delta, z=z)
                        certified, _, look = shared[(delta, label)]
                        where = (scenario.name, index, label, delta)
                        self.assertEqual(
                            certified,
                            want.status is PR.PrecisionStatus.ACHIEVED, where)
                        if certified:
                            self.assertEqual(look, want.look, where)


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
    """Пороги редакции 4 ВЫВЕДЕНЫ из правил проекта, а не выбраны."""

    def test_the_gated_quantity_is_false_certification_not_per_look_coverage(self):
        """Редакция 3 гейтила покрытие каждого просмотра и была сильнее задачи."""
        self.assertAlmostEqual(Q.NOMINAL_FALSE_CERT,
                               len(PR.LOOKS) * PR.ALPHA_PER_COMPARISON)
        self.assertAlmostEqual(Q.NOMINAL_FALSE_CERT, 0.0125)
        self.assertIn("p_false_cert", Q.main.__doc__ or Q.__doc__ or "")

    def test_the_floor_is_a_declared_transport_convention(self):
        """Пол не выводится из prereg — он ПЕРЕНОСИТ его относительный допуск.

        Пара проекта «0.93 при 0.95» задаёт допустимое превышение промаха
        в 1.4 раза. Конвенция: сохранить этот множитель. Альтернатива
        (сохранить абсолютный отступ 0.02) дала бы 0.9675 и тоже была бы
        разумна — поэтому это выбор, объявленный до прогона, а не теорема.
        """
        from simulation import s5b_prereg as prereg
        self.assertAlmostEqual(Q.FLOOR_RATIO, 1.4)
        self.assertAlmostEqual(
            Q.FLOOR_RATIO,
            (1 - prereg.COVERAGE_ACCEPTANCE_FLOOR) / (1 - prereg.CONFIDENCE_LEVEL))
        self.assertAlmostEqual(Q.FALSE_CERT_FLOOR, 0.9825)

    def test_the_chosen_floor_discriminates_secondary_check(self):
        """ВТОРИЧНАЯ проверка различающей силы, НЕ основание выбора порога.

        Конвенция переноса выбрана в `test_the_floor_is_a_declared_transport
        _convention`; здесь лишь констатируется её следствие: буквальный
        0.93 пропустил бы α-процедуру (около 0.95), выведенный из конвенции
        пол её отвергает. Выбирать порог ПО этому следствию значило бы
        назначать проходной балл под конкретного двоечника.
        """
        from simulation import s5b_prereg as prereg
        unadjusted = int(round(0.05 * Q.REPLICATES))
        good = Q.REPLICATES - unadjusted
        self.assertTrue(prereg.coverage_is_accepted(good, Q.REPLICATES),
                        "буквальный пол 0.93 пропустил бы α-процедуру")
        self.assertFalse(Q.accepted(unadjusted, Q.REPLICATES),
                         "выведенный пол обязан её отвергнуть")

    def test_the_replicate_count_is_set_by_the_power_rule_not_by_taste(self):
        """То же правило, что однажды подняло R с 1000 до 4000."""
        self.assertGreaterEqual(Q.power_of(Q.REPLICATES), Q.GATE_POWER_REQUIRED)
        self.assertLess(Q.power_of(Q.REPLICATES // 2), Q.GATE_POWER_REQUIRED,
                        "R взят с запасом, которого правило не требует")

    def test_the_power_is_measured_against_the_worst_ADMISSIBLE_method(self):
        """Гейт, отвергающий метод, который сам же разрешает, сломан."""
        self.assertTrue(Q.accepted(int(Q.NOMINAL_FALSE_CERT * Q.REPLICATES),
                                   Q.REPLICATES))

    def test_the_family_correction_covers_every_gated_statement(self):
        from simulation import s5b_prereg as prereg
        self.assertEqual(Q.STATEMENTS, (len(Q.SCENARIOS) + 1) * len(Q.DELTAS))
        self.assertEqual(Q.STATEMENTS, 33)
        self.assertAlmostEqual(
            Q.SUITE_Z,
            NormalDist().inv_cdf(1 - prereg.SIMULTANEOUS_ALPHA / Q.STATEMENTS))
        self.assertGreater(Q.SUITE_Z, prereg.COVERAGE_Z)

    def test_the_delta_axis_is_covered_whole_not_sampled(self):
        from simulation import s5b_prereg as prereg
        self.assertEqual(Q.DELTAS,
                         tuple(f * Q.HI for f in prereg.DELTA_FRACTIONS_OF_HORIZON))
        self.assertEqual(Q.DELTA, min(Q.DELTAS))

    def test_the_critical_value_did_not_move_with_the_target(self):
        """Редакция 4 меняет ЦЕЛЬ квалификации, а не `z`."""
        self.assertAlmostEqual(Q.Z_DECLARED, PR.Z_PER_COMPARISON)
        self.assertAlmostEqual(Q.Z_DECLARED, 2.8653, places=4)

    def test_the_seed_namespaces_are_separated(self):
        """Тестовый поток и гейтящий поток обязаны НЕ пересекаться."""
        names = {Q.TEST_NAMESPACE, Q.CALIBRATION_NAMESPACE,
                 Q.QUALIFICATION_NAMESPACE}
        self.assertEqual(len(names), 3)
        self.assertNotIn("r4", names, "голое `r4` было общим на всё")

    def test_the_namespace_cannot_be_omitted_by_accident(self):
        """Защита СТРУКТУРНАЯ, а не рекомендательная: параметр обязателен."""
        import inspect
        for function in (Q.replicate, Q.replicate_cell):
            parameter = inspect.signature(function).parameters["namespace"]
            self.assertIs(parameter.default, inspect.Parameter.empty,
                          f"{function.__name__}: namespace получил умолчание")
            self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        scenario = Q.SCENARIOS[0]
        with self.assertRaises(TypeError):
            Q.replicate(scenario, 0)
        with self.assertRaises(TypeError):
            Q.replicate_cell(0)

    def test_no_test_may_run_replicates_on_the_qualification_stream(self):
        """Ни один тест не имеет права ЗАПУСТИТЬ реплику гейтящего потока.

        Проверяется УПОТРЕБЛЕНИЕ, а не упоминание, и это третья попытка:
        поиск подстроки падал на собственной докстроке, поиск имени — на
        честной проверке «три пространства различны». Запрещено ровно одно:
        передать гейтящий поток в `namespace=`. Называть константу можно.

        Тот же класс, что уже ловил проект дважды (фраза про перцентиль,
        отозванная лестница): отсутствие ИМЕНИ и отсутствие ДЕЙСТВИЯ — разные
        требования, и проверять надо второе.
        """
        import ast
        tree = ast.parse(pathlib.Path(__file__).read_text())
        forbidden = getattr(Q, "QUALIFICATION" + "_NAMESPACE")
        passed, seen_test_stream = [], False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "namespace":
                    continue
                value = keyword.value
                if isinstance(value, ast.Attribute):
                    passed.append(value.attr)
                    seen_test_stream |= value.attr == "TEST_NAMESPACE"
                elif isinstance(value, ast.Constant):
                    passed.append(value.value)
        self.assertNotIn("QUALIFICATION_NAMESPACE", passed,
                         "тест гоняет реплики гейтящего потока")
        self.assertNotIn(forbidden, passed,
                         "поток гейта вписан строкой в обход имени")
        self.assertTrue(seen_test_stream,
                        "ни один тест не назвал тестовый поток — проверка пуста")



class StoppingProcedureIsTheObjectTests(unittest.TestCase):
    """Квалифицируется момент остановки и ВОЗВРАЩЁННОЕ множество."""

    def test_an_endpoint_that_never_certifies_produces_no_false_certification(self):
        """tau = inf -> MC_PRECISION_INSUFFICIENT -> научного вердикта нет."""
        scenario = next(s for s in Q.SCENARIOS if s.name == "degenerate_variance")
        result = Q.replicate(scenario, 0, namespace=Q.TEST_NAMESPACE)
        for (delta, label), (certified, covered, look) in result.items():
            self.assertFalse(certified, (delta, label))
            self.assertIsNone(look)
            self.assertIsNone(covered)

    def test_the_tally_counts_only_misses_that_came_with_a_certificate(self):
        """Промах БЕЗ сертификата в гейт не входит — в этом вся редакция 4.

        `degenerate_variance` не сертифицирует никогда, поэтому его
        `false_cert` обязан быть нулём при любом числе реплик; а `fieller`
        промахивается на фиксированных просмотрах и всё равно даёт ноль.
        """
        for name in ("degenerate_variance", "fieller"):
            scenario = next(s for s in Q.SCENARIOS if s.name == name)
            tallies = {(d, l): Q.Tally() for d in Q.DELTAS
                       for l, _ in Q.CONFIGS}
            for index in range(20):
                Q.replicate(scenario, index, tallies,
                            namespace=Q.TEST_NAMESPACE)
            for key, tally in tallies.items():
                self.assertEqual(tally.achieved, 0, (name, key))
                self.assertEqual(tally.false_cert, 0, (name, key))
            fixed = tallies[(Q.DELTA, Q.CONFIGS[0][0])]
            if name == "fieller":
                self.assertGreater(sum(fixed.fixed_look_miss.values()), 0,
                                   "фиксированные промахи обязаны быть видны")

    def test_a_certifying_endpoint_reports_the_set_it_actually_returned(self):
        scenario = next(s for s in Q.SCENARIOS if s.name == "regular")
        result = Q.replicate(scenario, 0, namespace=Q.TEST_NAMESPACE)
        certified = [(d, l) for (d, l), (c, _, _) in result.items() if c]
        self.assertTrue(certified, "сценарий обязан доходить до сертификата")
        for key in certified:
            self.assertIn(result[key][2], PR.LOOKS)
            self.assertIsInstance(result[key][1], bool)

    def test_the_certifying_fieller_actually_certifies(self):
        """Иначе гейт редакции 4 на филлеровской геометрии ВАКУУМЕН."""
        scenario = next(s for s in Q.SCENARIOS
                        if s.name == "fieller_certifying")
        stops = [Q.replicate(scenario, i, namespace=Q.TEST_NAMESPACE)
                 [(Q.DELTA, Q.CONFIGS[0][0])]
                 for i in range(40)]
        self.assertGreater(sum(c for c, _, _ in stops), 30,
                           "сценарий не доходит до сертификата — гейт пуст")

    def test_the_original_fieller_is_declared_vacuous_not_quietly_dropped(self):
        """Исходный `fieller` остаётся в суите и не ослабляется."""
        names = [s.name for s in Q.SCENARIOS]
        self.assertIn("fieller", names)
        self.assertIn("fieller_certifying", names)
        scenario = next(s for s in Q.SCENARIOS if s.name == "fieller")
        self.assertEqual(scenario.truth, 1200.0)
        self.assertEqual(Q.FIELLER_CATALOGUE,
                         ((Piece(10_000.0, 12_479_520.0),), (Piece(1.0, 720.0),)))

    def test_the_certifying_fieller_has_the_same_exact_truth(self):
        heavy, light = Q.FIELLER_CERTIFYING_CATALOGUE
        total_n = 10_000 + 999
        total_b = Fraction(120004995, 10) + 999 * Fraction(11995, 10)
        self.assertEqual(Fraction(int(heavy[0].b * 10), 10), Fraction(120004995, 10))
        self.assertEqual(Fraction(int(light[0].b * 10), 10), Fraction(11995, 10))
        self.assertEqual(total_b, 1200 * total_n)
        self.assertLessEqual(heavy[0].b, heavy[0].n * Q.HI)


class FourEndpointOrchestrationTests(unittest.TestCase):
    """Одна ошибка в `all(...)` переживает тысячу теорем."""

    def test_the_cell_needs_all_four_endpoints_not_any(self):
        self.assertTrue(Q.cell_gets_verdict([True, True, True, True]))
        self.assertFalse(Q.cell_gets_verdict([True, True, True, False]))
        self.assertFalse(Q.cell_gets_verdict([False, False, False, False]))
        self.assertFalse(Q.cell_gets_verdict([True, True, True]),
                         "трёх концов мало — их обязано быть четыре")

    def test_the_two_arms_have_different_truths_so_a_swap_cannot_hide(self):
        self.assertNotEqual(Q.CELL_TREATED_TRUTH, Q.CELL_CONTROL_TRUTH)
        self.assertEqual(Q.CELL_TREATED_TRUTH, (1200.0, 1600.0))
        self.assertEqual(Q.CELL_CONTROL_TRUTH, (900.0, 1300.0))

    def test_each_arm_truth_is_exact_for_both_directions(self):
        """λ⁻ по min, λ⁺ по max — это РАЗНЫЕ корни одной выборки."""
        for catalogue, weights, (low, high) in (
                (Q.CELL_TREATED, (Fraction(1, 2), Fraction(1, 2)),
                 Q.CELL_TREATED_TRUTH),
                (Q.CELL_CONTROL, (Fraction(1, 2), Fraction(1, 2)),
                 Q.CELL_CONTROL_TRUTH)):
            for truth, picker in ((low, min), (high, max)):
                value = sum(w * picker(Fraction(int(p.b)) - Fraction(int(truth))
                                       * Fraction(int(p.n)) for p in pieces)
                            for w, pieces in zip(weights, catalogue))
                self.assertEqual(value, 0, (truth, picker))

    def test_all_four_endpoints_run_the_real_nested_procedure(self):
        result = Q.replicate_cell(0, namespace=Q.TEST_NAMESPACE)
        key = (Q.DELTA, Q.CONFIGS[0][0])
        self.assertIn(key, result)
        verdict, ok, _ = result[key]
        self.assertIsInstance(verdict, bool)
        if verdict:
            self.assertIsInstance(ok, bool)

    def test_the_cell_scenario_is_not_vacuous(self):
        got = [Q.replicate_cell(i, namespace=Q.TEST_NAMESPACE)
               [(Q.DELTA, Q.CONFIGS[0][0])][0]
               for i in range(30)]
        self.assertGreater(sum(got), 20, "ячейка не доходит до вердикта")
