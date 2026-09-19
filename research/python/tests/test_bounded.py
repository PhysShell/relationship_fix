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
import pathlib
import random
import unittest

from coarsening.bounded import (
    Bin, Definedness, Identified, Interval, RATIO_TOLERANCE_SECONDS,
    arm_ratio_bounds, burden_bounds, count_bounds, definedness, identified,
    moves, patterns, ratio_bounds, to_bins)
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
           delta: float = DELTA, time_layer: bool = True):
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
            if start + horizon > window_end:
                continue                       # не eligible — как в экстракторе
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
