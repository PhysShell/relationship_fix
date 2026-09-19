"""BOUNDED проверяется тремя способами, и ни один не верит DP на слово.

    1. ПЕРЕБОРНЫЙ ОРАКУЛ на микротрассах: перечислить ВСЕ допустимые порядки
       и сравнить экстремумы. Оракул независим от DP: он не знает ни про
       сжатые шаблоны, ни про состояния.

    2. МОНОТОННОСТЬ ПО ИЗМЕЛЬЧЕНИЮ: identified_set(1 с) ⊆ identified_set(60 с).
       Эта проверка лучше сравнения с «истинной» секундной последовательностью
       именно потому, что 1 с у нас тоже не истина — там свои 1.9%
       неоднозначных возможностей.

    3. СХЛОПЫВАНИЕ: где хронология однозначна, low == high == обычный
       экстрактор. BOUNDED обязан деградировать в существующий движок, а не
       стать вторым определением метрики.
"""

import itertools
import math
import pathlib
import random
import unittest

from coarsening.bounded import (
    Bin, Bracket, Definedness, Identified, Interval, NoCrossing,
    RATIO_TOLERANCE_SECONDS, _count, _optimise, achievable_frontier,
    arm_ratio_bounds, burden_bounds, count_bounds, definedness,
    dinkelbach_slope_bound, generalized_inverse, hull_of, identified,
    lower_hull, moves, patterns, ratio_bounds, to_bins)
from coarsening.paired import Stream, apply_operator, opportunities, order, rmtr
from coarsening.prereg import coarsen

DELTA = 60.0
HORIZON = 3600.0
FAR = 10.0 ** 9


# ---------------------------------------------------------------------------
# 1. Переборный оракул
# ---------------------------------------------------------------------------

def _arrangements(bucket: Bin):
    """Все РАЗЛИЧНЫЕ расстановки актёров внутри одной корзины."""
    letters = "P" * bucket.partner + "Q" * bucket.participant
    return sorted(set(itertools.permutations(letters)))


def oracle(bins: list[Bin], *, horizon: float, window_end: float,
           delta: float = DELTA, time_layer: bool = True,
           initiation_end: float | None = None):
    """(N, B_lo, B_hi) по каждому допустимому порядку. Ничего не оптимизирует.

    Правило вклада здесь повторено НАМЕРЕННО, а не импортировано: оракул
    проверяет, что DP находит истинный экстремум ПО ПОРЯДКАМ, а не что оба
    одинаково считают вклад.
    """
    out = []
    for combination in itertools.product(*[_arrangements(b) for b in bins]):
        sequence = []
        for bucket, arrangement in zip(bins, combination):
            sequence.extend((bucket.start, actor) for actor in arrangement)
        count = 0
        low = high = 0.0
        inside: dict[float, int] = {}
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
            if initiation_end is None:
                if start + horizon > window_end:
                    continue                   # не eligible — как в экстракторе
            elif start >= initiation_end:
                continue                       # вне области инициации
            count += 1
            if reply is None:
                low += horizon
                high += horizon
            elif reply[0] == start:
                inside[start] = inside.get(start, 0) + 1
            else:
                gap = reply[0] - start
                if time_layer:
                    low += min(max(0.0, gap - delta), horizon)
                    high += min(gap + delta, horizon)
                else:
                    low += min(gap, horizon)
                    high += min(gap, horizon)
        if time_layer:
            for bucket_start, many in inside.items():
                high += min(delta, many * horizon)
        out.append((count, low, high))
    return out


def random_bins(rng: random.Random, many: int, *, biggest: int = 3):
    bins, cursor = [], 0.0
    for _ in range(many):
        cursor += DELTA * rng.randint(1, 3)
        partner = rng.randint(0, biggest)
        participant = rng.randint(0 if partner else 1, biggest)
        bins.append(Bin(cursor, partner, participant))
    return bins


class OracleAgreementTests(unittest.TestCase):

    def _check(self, bins, *, time_layer):
        rows = oracle(bins, horizon=HORIZON, window_end=FAR,
                      time_layer=time_layer)
        counts = count_bounds(bins, horizon=HORIZON, window_end=FAR)
        self.assertEqual(counts.low, float(min(n for n, _, _ in rows)), bins)
        self.assertEqual(counts.high, float(max(n for n, _, _ in rows)), bins)

        burden = burden_bounds(bins, horizon=HORIZON, window_end=FAR,
                               time_layer=time_layer)
        self.assertAlmostEqual(burden.low, min(lo for _, lo, _ in rows), 6)
        self.assertAlmostEqual(burden.high, max(hi for _, _, hi in rows), 6)

        ratios = [(lo / n, hi / n) for n, lo, hi in rows if n]
        got = ratio_bounds(bins, horizon=HORIZON, window_end=FAR,
                           time_layer=time_layer)
        if not ratios:
            self.assertIsNone(got)
            return
        # точность сверяется с ОБЪЯВЛЕННЫМ допуском дробной оптимизации, а
        # не с произвольным числом знаков: иначе тест молча требовал бы от
        # движка точности, которой тот не обещал
        self.assertLessEqual(abs(got.low - min(lo for lo, _ in ratios)),
                             RATIO_TOLERANCE_SECONDS)
        self.assertLessEqual(abs(got.high - max(hi for _, hi in ratios)),
                             RATIO_TOLERANCE_SECONDS)

    def test_the_dp_matches_brute_force_on_micro_traces(self):
        rng = random.Random(20260919)
        for _ in range(120):
            bins = random_bins(rng, rng.randint(1, 4))
            self._check(bins, time_layer=True)

    def test_the_order_layer_alone_also_matches_brute_force(self):
        rng = random.Random(777)
        for _ in range(120):
            bins = random_bins(rng, rng.randint(1, 4))
            self._check(bins, time_layer=False)

    def test_the_hardest_shape_is_covered(self):
        """Плотная смешанная корзина — там, где вариантов больше всего."""
        self._check([Bin(0.0, 3, 3), Bin(60.0, 2, 2)], time_layer=True)

    def test_within_bin_spans_share_one_budget(self):
        """Ловушка, ради которой границы считаются на целом порядке.

        Две возможности, закрывшиеся внутри одной корзины, не могут обе
        растянуться на её полную ширину: их спаны не пересекаются, поэтому
        сумма латентностей не больше delta. Наивная сумма поопортунитных
        максимумов дала бы 2·delta — значение, которого не даёт НИ ОДИН
        допустимый порядок.
        """
        from coarsening.bounded import Move, contribution
        pair_inside = Move(opened=2, closed_carried=False, closed_inside=2,
                           state=None)
        _, low, high = contribution(pair_inside, Bin(0.0, 2, 2), None,
                                    delta=DELTA, horizon=HORIZON,
                                    window_end=FAR, time_layer=True)
        self.assertEqual(low, 0.0)
        self.assertEqual(high, DELTA)
        self.assertLess(high, 2 * min(DELTA, HORIZON))


# ---------------------------------------------------------------------------
# 2. Монотонность по измельчению
# ---------------------------------------------------------------------------

def random_stream(rng: random.Random, size: int) -> Stream:
    stamps = sorted(float(rng.randrange(0, 40 * size)) for _ in range(size))
    actors = [rng.randrange(2) for _ in range(size)]
    keys = [f"{rng.randrange(10 ** 9):09d}" for _ in range(size)]
    return order(stamps, actors, keys)


class RefinementTests(unittest.TestCase):
    """Вложение — ТЕОРЕМА для резкого слоя и ДИАГНОСТИКА для оболочки.

    Разделение не педантское. `N` зависит только от допустимой топологии
    порядка: временной бюджет `min(Δ, c·H)` в него не входит вообще, а
    огрубление лишь СТИРАЕТ ограничения порядка, поэтому любая хронология,
    допустимая при 1 с, допустима и при 60 с. Нарушение здесь — баг, и
    секунды в нём не виноваты.

    Полная временная ОБОЛОЧКА — другое: `outer(1 с)` сама содержит значения,
    физически недостижимые, а `outer(60 с)` обязана содержать РЕЗКОЕ
    множество при 60 с, а не все ложноположительные точки мелкой
    аппроксимации. Её вложение наблюдается, но теоремой не является.
    """

    def _pairs(self, rng, many=60):
        for _ in range(many):
            stream = random_stream(rng, rng.randint(4, 30))
            horizon = 300.0
            # окно берётся так, чтобы eligible были ВСЕ корзины: иначе тест
            # молча проверял бы пустое множество
            window = stream.stamps[-1] + horizon
            yield (to_bins(stream, 0, delta=1.0),
                   to_bins(stream, 0, delta=DELTA), horizon, window)

    def test_the_sharp_count_set_can_only_widen(self):
        """ТЕОРЕМА. N не зависит от времени вовсе — только от порядка."""
        for fine, coarse, horizon, window in self._pairs(random.Random(4242)):
            inner = count_bounds(fine, horizon=horizon, window_end=window)
            outer = count_bounds(coarse, horizon=horizon, window_end=window)
            self.assertIn(inner, outer, f"N {inner} not inside {outer}")

    def test_the_order_layer_is_not_comparable_across_resolutions(self):
        """НЕ инвариант, и это выяснилось здесь, а не в отчёте.

        При `time_layer=False` латентность равна разности НАЧАЛ КОРЗИН — та
        самая подстановка одной точки интервала. Она зависит от разрешения:
        при 60 с латентность кратна 60, поэтому значение 103 с там просто не
        существует. Значит два слоя порядка на разных разрешениях — это не
        одно множество, посчитанное точнее, а две разные величины, и
        требовать вложения не на чем.
        """
        from coarsening import verdict
        stamps = [4, 175, 197, 199, 202, 267, 302, 344, 353, 363, 388, 426,
                  655, 672, 680, 683, 683, 711]
        actors = [0, 1, 1, 1, 0, 0, 0, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0]
        stream = order([float(s) for s in stamps], actors,
                       [f"{index:06d}" for index in range(len(stamps))])
        horizon, window = 300.0, stream.stamps[-1] + 300.0
        fine = to_bins(stream, 0, delta=1.0)
        coarse = to_bins(stream, 0, delta=DELTA)
        inner = burden_bounds(fine, horizon=horizon, window_end=window,
                              delta=1.0, time_layer=False)
        outer = burden_bounds(coarse, horizon=horizon, window_end=window,
                              delta=DELTA, time_layer=False)
        self.assertNotIn(inner, outer)          # 103 < 120: не вложено
        # а два утверждения, которые ДЕЙСТВИТЕЛЬНО обязаны держаться, держатся
        self.assertIn(burden_bounds(fine, horizon=horizon, window_end=window,
                                    delta=1.0),
                      burden_bounds(coarse, horizon=horizon, window_end=window,
                                    delta=DELTA))
        self.assertIn(count_bounds(fine, horizon=horizon, window_end=window),
                      count_bounds(coarse, horizon=horizon, window_end=window))
        self.assertTrue(verdict.ORDER_LAYER_IS_WITHIN_RESOLUTION_ONLY)
        self.assertIn("NOT COMPARABLE",
                      verdict.REFINEMENT_STATUS["R_order_only"])

    def test_the_conservative_envelope_nesting_is_only_a_diagnostic(self):
        """НЕ теорема. Наблюдается — сообщаем; сломается — расследуем слой.

        `outer(1 с)` содержит физически недостижимые значения, поэтому
        требовать от `outer(60 с)` включать их все — требование не к
        математике движка, а к консервативности аппроксимации.
        """
        from coarsening import verdict
        self.assertIn("DIAGNOSTIC", verdict.REFINEMENT_STATUS["R_outer_envelope"])
        self.assertIn("theorem", verdict.REFINEMENT_STATUS["N"])
        held = total = 0
        for fine, coarse, horizon, window in self._pairs(random.Random(4242)):
            inner = burden_bounds(fine, horizon=horizon, window_end=window,
                                  delta=1.0)
            outer = burden_bounds(coarse, horizon=horizon, window_end=window,
                                  delta=DELTA)
            held += inner in outer
            total += 1
        self.assertEqual(held, total, "оболочка не вложилась — расследовать "
                                      "временной слой, не движок порядка")


# ---------------------------------------------------------------------------
# 3. Схлопывание в обычный экстрактор
# ---------------------------------------------------------------------------

class CollapseTests(unittest.TestCase):

    def _unambiguous(self, rng, size):
        """Поток, у которого ни одна корзина не смешанная."""
        stamps, actors, slot = [], [], 0
        for _ in range(size):
            slot += rng.randint(1, 3)
            actor = rng.randrange(2)
            for _ in range(rng.randint(1, 3)):
                stamps.append(slot * DELTA + len(stamps) * 0.001)
                actors.append(actor)
        keys = [f"{index:06d}" for index in range(len(stamps))]
        return order(stamps, actors, keys)

    def test_bounded_degrades_into_the_ordinary_extractor(self):
        rng = random.Random(31337)
        for _ in range(40):
            stream = self._unambiguous(rng, rng.randint(2, 12))
            coarse = apply_operator(stream, DELTA)
            window = coarse.stamps[-1] + 1.0
            bins = to_bins(stream, 0, delta=DELTA)
            counts = count_bounds(bins, horizon=HORIZON, window_end=window)
            burden = burden_bounds(bins, horizon=HORIZON, window_end=window,
                                   time_layer=False)
            self.assertEqual(counts.low, counts.high)
            self.assertAlmostEqual(burden.low, burden.high, 6)
            n, mean = rmtr(opportunities(coarse, 0), HORIZON / 3600.0, window)
            self.assertEqual(int(counts.low), n)
            if n:
                self.assertAlmostEqual(burden.low, mean * n, 5)

    def test_a_single_actor_bin_offers_no_choice(self):
        self.assertEqual(len(moves(Bin(0.0, 3, 0), False)), 1)
        self.assertEqual(len(moves(Bin(0.0, 0, 3), True)), 1)
        self.assertGreater(len(moves(Bin(0.0, 2, 2), False)), 1)


# ---------------------------------------------------------------------------
# Решение
# ---------------------------------------------------------------------------

class DecisionTests(unittest.TestCase):

    def test_an_interval_straddling_the_gate_is_not_called_inconclusive(self):
        """Неидентифицированность — не шум выборки, и имя у неё своё."""
        self.assertIs(identified(Interval(-240.0, 2220.0), 300.0),
                      Identified.ORDER_AMBIGUOUS)

    def test_a_fully_separated_interval_identifies_the_signal(self):
        self.assertIs(identified(Interval(400.0, 900.0), 300.0),
                      Identified.REACTIVITY_SIGNAL)
        self.assertIs(identified(Interval(-900.0, -400.0), 300.0),
                      Identified.REACTIVITY_SIGNAL)

    def test_a_contained_interval_identifies_negligibility(self):
        self.assertIs(identified(Interval(-100.0, 100.0), 300.0),
                      Identified.PRACTICALLY_NEGLIGIBLE)

    def test_a_missing_estimand_is_undefined_not_negligible(self):
        self.assertIs(identified(None, 300.0), Identified.UNDEFINED)

    def test_a_wider_interval_can_only_lose_identification(self):
        """Больше неопределённости не делает вывод сильнее. Инвариант."""
        strong = identified(Interval(400.0, 900.0), 300.0)
        weaker = identified(Interval(-50.0, 900.0), 300.0)
        self.assertIs(strong, Identified.REACTIVITY_SIGNAL)
        self.assertIs(weaker, Identified.ORDER_AMBIGUOUS)


class PatternTests(unittest.TestCase):

    def test_patterns_are_alternating_and_within_the_counts(self):
        for a in range(1, 5):
            for b in range(1, 5):
                for first, p, q in patterns(a, b):
                    self.assertLessEqual(p, a)
                    self.assertLessEqual(q, b)
                    self.assertLessEqual(abs(p - q), 1)
                    if p == q + 1:
                        self.assertTrue(first)
                    if q == p + 1:
                        self.assertFalse(first)

    def test_patterns_are_fewer_than_permutations(self):
        """Ради этого и сжимаем: перестановок факториально, шаблонов — линейно."""
        import math
        for a, b in ((4, 4), (5, 5), (6, 6)):
            arrangements = math.comb(a + b, a)
            self.assertLess(len(patterns(a, b)), arrangements)


class TerminologyAndAggregationTests(unittest.TestCase):
    """Правила счёта объявлены до просмотра распределений — и проверяются."""

    def test_the_two_estimands_are_not_described_with_one_word(self):
        from coarsening import verdict
        self.assertTrue(verdict.N_IS_SHARP)
        self.assertTrue(verdict.RMTR_IS_OUTER_ENVELOPE)
        self.assertIn("outer", verdict.RMTR_TERM)
        self.assertIn("envelope", verdict.WIDTH_TERM)

    def test_a_hair_outside_is_not_counted_as_outside(self):
        """11.0001 против 11.0000 формально снаружи, практически нет."""
        from coarsening import verdict
        self.assertFalse(verdict.violation(11.0001, 1.0, 11.0).outside)
        self.assertTrue(verdict.violation(660.0, 111.0, 525.6).outside)

    def test_violation_is_reported_in_widths_as_well_as_units(self):
        from coarsening import verdict
        hit = verdict.violation(660.0, 111.0, 525.6)
        self.assertAlmostEqual(hit.absolute_seconds, 134.4, 6)
        self.assertAlmostEqual(hit.relative_to_width, 134.4 / 414.6, 6)
        self.assertTrue(hit.above)

    def test_a_point_inside_yields_no_violation(self):
        from coarsening import verdict
        self.assertEqual(verdict.violation(5.0, 1.0, 9.0).absolute_seconds, 0.0)

    def test_the_sharpening_trigger_is_a_number_declared_in_advance(self):
        from coarsening import verdict
        self.assertIsInstance(verdict.SHARPEN_TIME_IF_ORDER_SHARE_BELOW, float)
        self.assertEqual(verdict.order_share(3.0, 6.0), 0.5)
        self.assertTrue(verdict.SHARP_TIME_LAYER.startswith("DEFERRED"))

    def test_multiplicative_width_is_used_for_a_positive_ratio(self):
        from coarsening import verdict
        self.assertAlmostEqual(verdict.multiplicative_width(1.85, 8.76),
                               8.76 / 1.85, 6)
        self.assertEqual(verdict.multiplicative_width(0.0, 5.0), float("inf"))


class EligibilityBoundaryTests(unittest.TestCase):
    """Граница eligibility — единственное место, где «теорема про N» не теорема.

    Найдено разбором, а не тестом: property-тест этого не ловил, потому что
    брал `window = stamps[-1] + horizon`, то есть НИКОГДА не заходил в
    область, где утверждение ложно. Тест, который не может упасть, ничего и
    не проверяет.
    """

    def test_coarsening_can_make_an_ineligible_opportunity_eligible(self):
        """Одно сообщение в t=119, H=60, окно до 120. {0} не вложено в {1}."""
        from coarsening import verdict
        stream = order([119.0], [0], ["a"])
        fine = to_bins(stream, 1, delta=1.0)
        coarse = to_bins(stream, 1, delta=DELTA)
        inner = count_bounds(fine, horizon=60.0, window_end=120.0)
        outer = count_bounds(coarse, horizon=60.0, window_end=120.0)
        self.assertEqual((inner.low, inner.high), (0.0, 0.0))
        self.assertEqual((outer.low, outer.high), (1.0, 1.0))
        self.assertNotIn(inner, outer)
        self.assertIn("stable eligibility", verdict.N_REFINEMENT_SCOPE)

    def test_stable_eligibility_restores_the_invariant(self):
        """`window = last + horizon` — ровно то, что делает прогон Q1c."""
        stream = order([119.0], [0], ["a"])
        window = stream.stamps[-1] + 60.0
        inner = count_bounds(to_bins(stream, 1, delta=1.0),
                             horizon=60.0, window_end=window)
        outer = count_bounds(to_bins(stream, 1, delta=DELTA),
                             horizon=60.0, window_end=window)
        self.assertIn(inner, outer)

    def test_the_corpus_run_uses_the_stable_window(self):
        """Иначе результат по 517 диадам опирался бы на неверную область."""
        from coarsening import verdict
        source = pathlib.Path(__file__).resolve().parent.parent / "tools" / "bounded_q1c.py"
        self.assertIn("window = last + horizon", source.read_text(encoding="utf-8"))
        self.assertTrue(verdict.STABLE_ELIGIBILITY_HOLDS_IN_Q1C)
        self.assertTrue(verdict.ELIGIBILITY_BOUNDARY_SEMANTICS.startswith("DEFERRED"))


class Q1cIsClosedTests(unittest.TestCase):
    """Результат запечатан: цифры, дайджесты и запрет продолжать."""

    def test_the_result_carries_its_inputs_and_outputs(self):
        from coarsening import q1c_result as q
        self.assertEqual(q.STATUS, "CLOSED")
        self.assertEqual(q.CORPUS_ARCHIVE_MD5, "dd3dce055158e70a891e8db49dd2678f")
        self.assertTrue(q.ROWS_SHA256_16 and q.LOG_SHA256_16)
        self.assertEqual(q.DYADS_ANALYSED, 517)

    def test_the_declared_trigger_decided_against_more_work(self):
        from coarsening import q1c_result as q, verdict
        self.assertEqual(q.SHARP_TIME_LAYER, "NOT_WORTH_BUILDING")
        for share in q.ORDER_SHARE_MEDIAN.values():
            self.assertGreater(share, verdict.SHARPEN_TIME_IF_ORDER_SHARE_BELOW)

    def test_the_violation_is_one_directional(self):
        """N всегда ниже, RMTR почти всегда выше — это не шум."""
        from coarsening import q1c_result as q
        self.assertEqual(q.STRICT_N_ABOVE, 0)
        self.assertGreater(q.STRICT_N_BELOW, 500)
        for horizon, above in q.STRICT_RMTR_ABOVE.items():
            self.assertGreater(above, q.STRICT_RMTR_BELOW[horizon])

    def test_the_theorem_applies_because_eligibility_is_stable(self):
        from coarsening import q1c_result as q
        self.assertTrue(q.ELIGIBILITY_IS_STABLE_HERE)

    def test_reopening_is_forbidden_by_name(self):
        from coarsening import q1c_result as q
        self.assertIn("sharper temporal bounds", q.DO_NOT_REOPEN)


class DefinednessTests(unittest.TestCase):
    """Найдено враждебным чтением prereg S5b: существует ли эстиманд вообще."""

    def test_the_three_statuses_are_distinguished(self):
        self.assertIs(definedness(Interval(1.0, 3.0)), Definedness.DEFINED)
        self.assertIs(definedness(Interval(0.0, 0.0)),
                      Definedness.UNDEFINED_EVERYWHERE)
        self.assertIs(definedness(Interval(0.0, 3.0)), Definedness.AMBIGUOUS)

    def test_n_zero_is_order_invariant(self):
        """ТЕОРЕМА, на которой стоит сложение поячеечных границ:

            N_min = 0  =>  N_max = 0

        Eligibility монотонна по времени, а ожидающее возвращение создаётся
        только открытием; значит в первую корзину с сообщением партнёра любой
        порядок входит с пустым состоянием и открывает. Середины нет.

        Исчерпывающий перебор, а не выборочная проверка: случай `low = 0 <
        high` — тот самый, ради которого затевался плавающий знаменатель.
        """
        sizes = [(p, q) for p in range(4) for q in range(4) if p or q]
        seen_zero = 0
        for nbins in (1, 2):
            for combo in itertools.product(sizes, repeat=nbins):
                bins = [Bin(i * 60.0, p, q) for i, (p, q) in enumerate(combo)]
                for horizon in (30.0, 60.0, 150.0):
                    for window in (60.0, 120.0, 900.0):
                        counts = count_bounds(bins, horizon=horizon,
                                              window_end=window)
                        if counts.low == 0.0:
                            seen_zero += 1
                            self.assertEqual(counts.high, 0.0, (combo, horizon, window))
        self.assertGreater(seen_zero, 100, "случай N_min = 0 не встретился вовсе")

    def test_the_ambiguous_status_is_unreachable_today(self):
        """Растяжка: статус существует и обязан НЕ срабатывать. В тот день,
        когда eligibility перестанет быть монотонной, этот тест упадёт —
        что и требуется, потому что правила для латентного знаменателя нет.
        """
        rng = random.Random(4242)
        for _ in range(4000):
            bins = [Bin(i * 60.0, rng.randint(0, 3), rng.randint(0, 3))
                    for i in range(rng.randint(1, 4))]
            bins = [b for b in bins if b.size]
            if not bins:
                continue
            counts = count_bounds(bins, horizon=rng.choice([30.0, 60.0, 120.0]),
                                  window_end=rng.choice([60.0, 180.0, 600.0]))
            self.assertIsNot(definedness(counts), Definedness.AMBIGUOUS, bins)


class ArmRatioTests(unittest.TestCase):
    """ΣB/ΣN по всей руке: Динкельбах этажом выше, а не сумма концов."""

    def _periods(self, rng, count):
        sizes = [(p, q) for p in range(3) for q in range(3) if p or q]
        return [[Bin(i * DELTA, *rng.choice(sizes))
                 for i in range(rng.randint(1, 2))] for _ in range(count)]

    def _brute(self, periods, horizon, window):
        rows = [oracle(b, horizon=horizon, window_end=window, time_layer=False)
                for b in periods]
        low = high = None
        for combo in itertools.product(*rows):
            total = sum(r[0] for r in combo)
            if not total:
                continue
            lo = sum(r[1] for r in combo) / total
            hi = sum(r[2] for r in combo) / total
            low = lo if low is None else min(low, lo)
            high = hi if high is None else max(high, hi)
        return low, high

    def test_it_agrees_with_full_enumeration_of_joint_orders(self):
        """Оракул перебирает совместные порядки; DP не должен их угадывать."""
        rng = random.Random(11)
        horizon, window = 90.0, 600.0
        checked = 0
        for _ in range(60):
            periods = self._periods(rng, rng.randint(2, 3))
            low, high = self._brute(periods, horizon, window)
            if low is None:
                continue
            checked += 1
            got = arm_ratio_bounds(periods, horizon=horizon, window_end=window,
                                   time_layer=False)
            self.assertAlmostEqual(got.low, low, delta=RATIO_TOLERANCE_SECONDS)
            self.assertAlmostEqual(got.high, high, delta=RATIO_TOLERANCE_SECONDS)
        self.assertGreater(checked, 40)

    def test_the_naive_sum_envelope_is_not_bounds(self):
        """ΣB_lo/ΣN_hi .. ΣB_hi/ΣN_lo — ловушка B_min/N_max этажом выше.
        Она не «иногда неточна»: на случайных руках врёт чаще, чем нет.
        """
        rng = random.Random(11)
        horizon, window = 90.0, 600.0
        wrong = total = 0
        for _ in range(60):
            periods = self._periods(rng, rng.randint(2, 3))
            low, high = self._brute(periods, horizon, window)
            if low is None:
                continue
            counts = [count_bounds(b, horizon=horizon, window_end=window)
                      for b in periods]
            burdens = [burden_bounds(b, horizon=horizon, window_end=window,
                                     time_layer=False) for b in periods]
            n_lo, n_hi = sum(c.low for c in counts), sum(c.high for c in counts)
            b_lo, b_hi = sum(x.low for x in burdens), sum(x.high for x in burdens)
            if not n_lo or not n_hi:
                continue
            total += 1
            if abs(b_lo / n_hi - low) > 1e-6 or abs(b_hi / n_lo - high) > 1e-6:
                wrong += 1
        self.assertGreater(total, 30)
        self.assertGreater(wrong, total // 3, "наивная оболочка подозрительно точна")

    def test_an_arm_with_no_opportunity_anywhere_has_no_estimand(self):
        bins = [[Bin(0.0, 0, 2)], [Bin(0.0, 0, 1)]]
        self.assertIsNone(arm_ratio_bounds(bins, horizon=60.0, window_end=600.0))


class InitiationCutoffTests(unittest.TestCase):
    """Конец НАБЛЮДЕНИЯ и конец ОБЛАСТИ ИНИЦИАЦИИ — разные границы.
    Найдено третьим враждебным чтением prereg S5b."""

    def test_the_legacy_rule_is_bit_identical(self):
        """Q1c запечатан; отсутствие отсечки обязано считать ровно как раньше."""
        rng = random.Random(9)
        for _ in range(40):
            bins = random_bins(rng, rng.randint(1, 4))
            for horizon in (60.0, 300.0):
                window = 4 * DELTA
                self.assertEqual(
                    count_bounds(bins, horizon=horizon, window_end=window),
                    count_bounds(bins, horizon=horizon, window_end=window,
                                 initiation_end=None))

    def test_the_t119_counterexample_dies_at_every_resolution(self):
        """Старое правило признавало t = 119 допустимым при 60 с и
        недопустимым при 1 с. Отсечка по опорной корзине убивает его в обеих."""
        stream = Stream((119.0, 400.0), (0, 1), ("a", "b"))
        for delta in (1.0, 5.0, 15.0, 60.0):
            bins = to_bins(stream, 1, delta=delta)
            counts = count_bounds(bins, horizon=60.0, window_end=120.0,
                                  initiation_end=60.0)
            self.assertEqual((counts.low, counts.high), (0.0, 0.0), delta)

    def test_a_reply_after_the_cutoff_still_closes_an_earlier_opening(self):
        """САМЫЙ ВАЖНЫЙ СЛУЧАЙ. Возможность открылась до отсечки, ответ пришёл
        после неё. Если поздние корзины просто отрезать, завершённая
        возможность станет цензурированной и получит полный горизонт —
        ошибка тихая и ровно в ту сторону, которая красивее выглядит.
        """
        bins = [Bin(0.0, 1, 0), Bin(120.0, 0, 1)]
        counts = count_bounds(bins, horizon=300.0, window_end=600.0,
                              initiation_end=60.0)
        self.assertEqual((counts.low, counts.high), (1.0, 1.0))

        burden = burden_bounds(bins, horizon=300.0, window_end=600.0,
                               time_layer=False, initiation_end=60.0)
        self.assertEqual((burden.low, burden.high), (120.0, 120.0))
        self.assertNotEqual(burden.high, 300.0, "возможность стала цензурированной")

    def test_openings_after_the_cutoff_are_not_counted_but_still_transition(self):
        """Позднее открытие не в N, но состояние оно менять обязано."""
        bins = [Bin(0.0, 1, 0), Bin(120.0, 1, 0), Bin(180.0, 0, 1)]
        counts = count_bounds(bins, horizon=300.0, window_end=600.0,
                              initiation_end=60.0)
        self.assertEqual((counts.low, counts.high), (1.0, 1.0))

    def test_it_agrees_with_the_oracle_under_a_cutoff(self):
        """DP и независимый перебор должны согласиться и с отсечкой."""
        rng = random.Random(21)
        checked = 0
        for _ in range(120):
            bins = random_bins(rng, rng.randint(1, 3))
            horizon, window = 300.0, 10 * DELTA
            cutoff = rng.choice([DELTA, 2 * DELTA, 3 * DELTA])
            rows = oracle(bins, horizon=horizon, window_end=window,
                          time_layer=False, initiation_end=cutoff)
            counts = count_bounds(bins, horizon=horizon, window_end=window,
                                  initiation_end=cutoff)
            self.assertEqual(counts.low, float(min(n for n, _, _ in rows)), bins)
            self.assertEqual(counts.high, float(max(n for n, _, _ in rows)), bins)
            burden = burden_bounds(bins, horizon=horizon, window_end=window,
                                   time_layer=False, initiation_end=cutoff)
            self.assertAlmostEqual(burden.low, min(lo for _, lo, _ in rows), 6)
            self.assertAlmostEqual(burden.high, max(hi for _, _, hi in rows), 6)
            checked += 1
        self.assertGreater(checked, 100)

    def test_n_zero_invariance_survives_the_new_cutoff(self):
        """Теорема стоит на префиксности; отсечка обязана её сохранить."""
        rng = random.Random(33)
        seen = 0
        for _ in range(3000):
            bins = random_bins(rng, rng.randint(1, 3))
            counts = count_bounds(bins, horizon=300.0, window_end=10 * DELTA,
                                  initiation_end=rng.choice([DELTA, 2 * DELTA]))
            if counts.low == 0.0:
                seen += 1
                self.assertEqual(counts.high, 0.0, bins)
        self.assertGreater(seen, 50)


class GeneralizedInverseTests(unittest.TestCase):
    """«Монотонность => единственный корень» — неверно. Найдено четвёртым
    враждебным чтением, и проверяется независимо от движка."""

    def test_a_strictly_decreasing_function_gives_its_root(self):
        got = generalized_inverse(lambda x: 10.0 - x, 0.0, 100.0)
        self.assertLessEqual(got.low, 10.0)
        self.assertGreaterEqual(got.high, 10.0)
        self.assertLessEqual(got.width, RATIO_TOLERANCE_SECONDS)

    def test_the_bracket_always_straddles_the_true_value(self):
        """Контракт: low <= λ* <= high при любом бюджете итераций."""
        for iterations in (5, 10, 20, 60):
            got = generalized_inverse(lambda x: 10.0 - x, 0.0, 100.0,
                                      iterations=iterations)
            self.assertLessEqual(got.low, 10.0, iterations)
            self.assertGreaterEqual(got.high, 10.0, iterations)

    def test_a_flat_zero_interval_gives_its_LEFT_edge(self):
        """Вот он, случай, ради которого всё переписано: обычная дихотомия
        вернула бы точку внутри [3, 7], зависящую от числа итераций."""
        def g(x):
            if x < 3.0:
                return 1.0
            if x <= 7.0:
                return 0.0
            return -1.0

        got = generalized_inverse(g, 0.0, 100.0)
        self.assertLessEqual(got.low, 3.0)
        self.assertGreaterEqual(got.high, 3.0)
        self.assertLess(got.high, 7.0, "ушли на ПРАВЫЙ край плато")

    def test_the_left_edge_does_not_depend_on_the_iteration_budget(self):
        """Детерминизм должен быть свойством ОПРЕДЕЛЕНИЯ, а не бюджета."""
        def g(x):
            return 1.0 if x < 3.0 else (0.0 if x <= 7.0 else -1.0)

        for n in (20, 40, 60, 200):
            got = generalized_inverse(g, 0.0, 100.0, iterations=n)
            self.assertLessEqual(got.low, 3.0, n)
            self.assertLess(got.high, 7.0, n)

    def test_non_positive_everywhere_gives_a_degenerate_bracket_at_the_left(self):
        got = generalized_inverse(lambda x: -1.0, 2.0, 100.0)
        self.assertEqual((got.low, got.high), (2.0, 2.0))

    def test_no_crossing_inside_the_bracket_is_an_explicit_refusal(self):
        """Дихотомия не обязана героически искать корень, которого нет."""
        with self.assertRaises(NoCrossing):
            generalized_inverse(lambda x: 1.0, 0.0, 50.0)

    def test_a_none_or_nan_anywhere_is_an_explicit_refusal(self):
        with self.assertRaises(NoCrossing):
            generalized_inverse(lambda x: None, 0.0, 1.0)
        with self.assertRaises(NoCrossing):
            generalized_inverse(lambda x: math.nan, 0.0, 1.0)
        with self.assertRaises(NoCrossing):
            generalized_inverse(lambda x: math.inf, 0.0, 1.0)


class RootUniquenessTests(unittest.TestCase):
    """Уникальность куплена НЕ монотонностью, а теоремой про N = 0."""

    def test_every_non_empty_period_has_slope_at_most_minus_one(self):
        """Механизм: min аффинных функций с наклонами −N_h, а N >= 1 при
        каждой истории непустого периода. Отсюда строгое убывание."""
        rng = random.Random(5)
        checked = 0
        for _ in range(300):
            bins = random_bins(rng, rng.randint(1, 3))
            horizon, window = 300.0, 10 * DELTA
            if _count(bins, horizon, window, True) == 0:
                continue
            checked += 1
            for maximise in (False, True):
                a = _optimise(bins, delta=DELTA, horizon=horizon,
                              window_end=window, time_layer=False, lam=10.0,
                              maximise=maximise, require_any=False)
                b = _optimise(bins, delta=DELTA, horizon=horizon,
                              window_end=window, time_layer=False, lam=11.0,
                              maximise=maximise, require_any=False)
                self.assertLessEqual(b - a, -1.0 + 1e-9, bins)
        self.assertGreater(checked, 100)

    def test_the_slope_bound_counts_non_empty_periods(self):
        periods = [[Bin(0.0, 1, 1)], [Bin(0.0, 0, 2)], [Bin(0.0, 2, 1)]]
        kw = dict(horizon=300.0, window_end=600.0)
        self.assertEqual(dinkelbach_slope_bound(periods, **kw), 2)

    def test_a_zero_slope_bound_means_there_is_no_estimand(self):
        periods = [[Bin(0.0, 0, 2)], [Bin(0.0, 0, 1)]]
        kw = dict(horizon=300.0, window_end=600.0)
        self.assertEqual(dinkelbach_slope_bound(periods, **kw), 0)
        self.assertIsNone(arm_ratio_bounds(periods, **kw))

    def test_an_arm_mixing_empty_and_non_empty_periods_is_fine(self):
        """Смесь на уровне РУКИ законна; запрещена она внутри периода."""
        periods = [[Bin(0.0, 0, 3)], [Bin(0.0, 1, 0), Bin(60.0, 0, 1)]]
        kw = dict(horizon=300.0, window_end=600.0, time_layer=False)
        self.assertEqual(dinkelbach_slope_bound(periods, horizon=300.0,
                                                window_end=600.0), 1)
        got = arm_ratio_bounds(periods, **kw)
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got.low, 60.0, delta=RATIO_TOLERANCE_SECONDS)

    def test_the_smallest_possible_denominator_still_gives_a_finite_root(self):
        """ΣN = 1 — наименьший непустой знаменатель."""
        periods = [[Bin(0.0, 1, 0), Bin(120.0, 0, 1)]]
        kw = dict(horizon=300.0, window_end=600.0, time_layer=False)
        self.assertEqual(dinkelbach_slope_bound(periods, horizon=300.0,
                                                window_end=600.0), 1)
        got = arm_ratio_bounds(periods, **kw)
        self.assertAlmostEqual(got.low, 120.0, delta=RATIO_TOLERANCE_SECONDS)
        self.assertAlmostEqual(got.high, 120.0, delta=RATIO_TOLERANCE_SECONDS)

    def test_no_period_admits_both_an_empty_and_a_non_empty_history(self):
        """Предусловие уникальности — то же, что закрыло плавающий знаменатель.
        Одно предусловие держит оба ответа и сломается сразу для обоих."""
        rng = random.Random(77)
        for _ in range(2000):
            bins = random_bins(rng, rng.randint(1, 3))
            counts = count_bounds(bins, horizon=300.0, window_end=10 * DELTA)
            if counts.low == 0.0:
                self.assertEqual(counts.high, 0.0, bins)


class NumericalConservativenessTests(unittest.TestCase):
    """Численная ошибка обязана РАСШИРЯТЬ идентифицированное множество.

    Иначе компьютер ради красивой цифры выбросит допустимые значения — а это
    ровно то, чего частичная идентификация не делает по определению."""

    #: НЕ подмена модульной константы: она в сигнатуре разрешалась при
    #: импорте, и «высокоточный» прогон был грубым. Точность передаётся явно.
    def _high_precision(self, periods, **kw):
        return arm_ratio_bounds(periods, tolerance=1e-7, **kw)

    def test_the_precision_knob_actually_changes_the_answer(self):
        """Иначе весь этот класс тестов сравнивает грубое само с собой."""
        rng = random.Random(606)
        periods = [random_bins(rng, 2) for _ in range(3)]
        kw = dict(horizon=300.0, window_end=10 * DELTA, time_layer=False)
        coarse = arm_ratio_bounds(periods, tolerance=5.0, **kw)
        fine = arm_ratio_bounds(periods, tolerance=1e-7, **kw)
        self.assertNotEqual((coarse.low, coarse.high), (fine.low, fine.high))
        self.assertGreater((coarse.high - coarse.low) - (fine.high - fine.low), 1.0)

    def test_the_reported_set_contains_the_high_precision_set(self):
        rng = random.Random(404)
        horizon, window = 300.0, 10 * DELTA
        checked = 0
        for _ in range(120):
            periods = [random_bins(rng, rng.randint(1, 2))
                       for _ in range(rng.randint(1, 3))]
            kw = dict(horizon=horizon, window_end=window, time_layer=False)
            coarse = arm_ratio_bounds(periods, **kw)
            if coarse is None:
                continue
            fine = self._high_precision(periods, **kw)
            checked += 1
            self.assertLessEqual(coarse.low, fine.low + 1e-9, periods)
            self.assertGreaterEqual(coarse.high, fine.high - 1e-9, periods)
        self.assertGreater(checked, 80)

    def test_a_smaller_iteration_budget_never_shrinks_the_set(self):
        """Бюджет итераций меняет ШИРИНУ, но не может отрезать допустимое."""
        rng = random.Random(505)
        periods = [random_bins(rng, 2) for _ in range(3)]
        kw = dict(horizon=300.0, window_end=10 * DELTA, time_layer=False)
        fine = self._high_precision(periods, **kw)
        for tolerance in (5.0, 1.0, 0.05):
            coarse = arm_ratio_bounds(periods, tolerance=tolerance, **kw)
            self.assertLessEqual(coarse.low, fine.low + 1e-9, tolerance)
            self.assertGreaterEqual(coarse.high, fine.high - 1e-9, tolerance)

    def test_per_period_bounds_round_outward_too(self):
        """Найдено `tools/diversion.py` на первом запуске: контейнмент-тесты
        покрывали только арм-уровень, и разворот округления в поячеечных
        границах проходил незамеченным. Q1c считался именно ими."""
        rng = random.Random(707)
        horizon, window = 300.0, 10 * DELTA
        checked = 0
        for _ in range(150):
            bins = random_bins(rng, rng.randint(1, 3))
            kw = dict(horizon=horizon, window_end=window, time_layer=False)
            coarse = ratio_bounds(bins, tolerance=5.0, **kw)
            if coarse is None:
                continue
            fine = ratio_bounds(bins, tolerance=1e-7, **kw)
            checked += 1
            self.assertLessEqual(coarse.low, fine.low + 1e-9, bins)
            self.assertGreaterEqual(coarse.high, fine.high - 1e-9, bins)
        self.assertGreater(checked, 80)

    def test_the_per_period_precision_knob_actually_bites(self):
        rng = random.Random(808)
        for _ in range(60):
            bins = random_bins(rng, 2)
            kw = dict(horizon=300.0, window_end=10 * DELTA, time_layer=False)
            coarse = ratio_bounds(bins, tolerance=5.0, **kw)
            fine = ratio_bounds(bins, tolerance=1e-7, **kw)
            if coarse is None or fine is None:
                continue
            if (coarse.high - coarse.low) - (fine.high - fine.low) > 1.0:
                return
        self.fail("точность не влияет на поячеечные границы — тест пустой")

    def test_an_arm_without_an_estimand_refuses_rather_than_returns_a_number(self):
        periods = [[Bin(0.0, 0, 2)], [Bin(0.0, 0, 1)]]
        self.assertIsNone(arm_ratio_bounds(periods, horizon=300.0,
                                           window_end=600.0))


class DomainInvariantTests(unittest.TestCase):
    """[0, H] — граница задачи, а не потолок поиска. Иначе компоненту
    доверительного множества, упирающуюся в H, нельзя читать как конечную."""

    def test_burden_never_exceeds_horizon_times_count(self):
        rng = random.Random(21)
        worst = 0.0
        for _ in range(600):
            bins = random_bins(rng, rng.randint(1, 4))
            for horizon in (60.0, 300.0, 3600.0):
                window = 10 * DELTA
                for layer in (False, True):
                    n = count_bounds(bins, horizon=horizon, window_end=window).high
                    b = burden_bounds(bins, horizon=horizon, window_end=window,
                                      time_layer=layer).high
                    if n:
                        worst = max(worst, b / (horizon * n))
                        self.assertLessEqual(b, horizon * n + 1e-9, (bins, horizon))
        self.assertGreater(worst, 0.99, "граница обязана быть ДОСТИЖИМОЙ, иначе "
                                        "инвариант проверяет не то")

    def test_every_ratio_bound_lies_in_the_domain(self):
        rng = random.Random(22)
        for _ in range(400):
            bins = random_bins(rng, rng.randint(1, 3))
            horizon, window = 300.0, 10 * DELTA
            got = ratio_bounds(bins, horizon=horizon, window_end=window)
            if got is None:
                continue
            self.assertGreaterEqual(got.low, -1e-9, bins)
            self.assertLessEqual(got.high, horizon + 1e-6, bins)


class AchievableFrontierTests(unittest.TestCase):
    """Оболочка достижимых (N, B) — несущая машинерия инверсии теста:
    ψ(λ) = экстремум (B − λN) обязан совпасть с прямым DP при любом λ."""

    def _check(self, bins, *, maximise, time_layer):
        kw = dict(horizon=300.0, window_end=10 * DELTA, delta=DELTA,
                  time_layer=time_layer)
        hull = hull_of(achievable_frontier(bins, maximise=maximise, **kw),
                       upper=maximise)
        picked = max if maximise else min
        for lam in (0.0, 13.7, 60.0, 150.0, 299.0):
            direct = _optimise(bins, lam=lam, maximise=maximise,
                               require_any=False, **kw)
            self.assertAlmostEqual(picked(b - lam * n for n, b in hull), direct,
                                   places=9, msg=(bins, lam, maximise, time_layer))

    def test_the_hull_reproduces_the_dp_in_both_directions(self):
        rng = random.Random(6)
        for _ in range(150):
            bins = random_bins(rng, rng.randint(1, 4))
            for maximise in (False, True):
                for layer in (False, True):
                    self._check(bins, maximise=maximise, time_layer=layer)

    def test_the_hull_is_a_subset_of_the_frontier(self):
        rng = random.Random(7)
        for _ in range(100):
            bins = random_bins(rng, rng.randint(1, 3))
            front = achievable_frontier(bins, horizon=300.0,
                                        window_end=10 * DELTA, delta=DELTA)
            hull = hull_of(front)
            for n, b in hull:
                self.assertIn(n, front)
                self.assertAlmostEqual(front[n], b, places=9)

    def test_the_frontier_agrees_with_the_count_bounds(self):
        """Ключи фронта — это в точности достижимые N."""
        rng = random.Random(8)
        for _ in range(100):
            bins = random_bins(rng, rng.randint(1, 3))
            kw = dict(horizon=300.0, window_end=10 * DELTA)
            front = achievable_frontier(bins, delta=DELTA, **kw)
            counts = count_bounds(bins, **kw)
            self.assertEqual(min(front), counts.low)
            self.assertEqual(max(front), counts.high)

    def test_every_hull_vertex_is_optimal_for_some_lambda(self):
        """Иначе тест не отличал бы оболочку от произвольного подмножества.

        Проба идёт ШИРОКИМ диапазоном, включая отрицательные λ и λ за
        горизонтом: вершина оптимальна на СВОЁМ интервале, и он вполне может
        лежать вне [0, H]. Первая редакция пробовала пять точек внутри
        домена и падала именно на этом.
        """
        rng = random.Random(9)
        examined = 0
        probes = [-200.0 + 5.0 * k for k in range(200)]
        for _ in range(200):
            bins = random_bins(rng, rng.randint(2, 4))
            kw = dict(horizon=300.0, window_end=10 * DELTA, delta=DELTA,
                      time_layer=False)
            hull = hull_of(achievable_frontier(bins, **kw))
            if len(hull) < 2:
                continue
            examined += 1
            for drop in range(len(hull)):
                trimmed = hull[:drop] + hull[drop + 1:]
                differs = any(
                    abs(min(b - lam * n for n, b in trimmed)
                        - min(b - lam * n for n, b in hull)) > 1e-9
                    for lam in probes)
                self.assertTrue(differs, (bins, hull, drop))
            if examined >= 5:
                break
        self.assertGreaterEqual(examined, 5, "не нашлось оболочек с двумя вершинами")
