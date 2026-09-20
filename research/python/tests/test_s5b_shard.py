"""Гейты шардинга. Главный: раскладка не имеет права менять результат.

Этот слой вычислительный. Если он хоть где-то меняет ЧТО получается, а не
КТО считает, он не ускорение, а подлог — поэтому здесь проверяется
`serial == sharded == reordered`, а не «результаты похожи».
"""

from __future__ import annotations

import random
import unittest

from simulation import s5b_escalation as E
from simulation import s5b_precision as PR
from simulation import s5b_shard as S

ARM = dict(rate=6.0, shift=0.40, ratio=0.75, c_rate=1.10, c_shift=-0.10)
TAG = "golden"
#: игрушечная лестница: свойства слияния от абсолютных чисел не зависят,
#: а гонять 64000 периодов в наборе тестов было бы издевательством
LADDER = (12, 30, 48)


def _units(ladder=LADDER, rate=6.0):
    return S.plan([(TAG, rate)], ladder=ladder)


def _run(units):
    return [(u, S.run_unit(u, **ARM)) for u in units]


class TaskIdentityIsScientificOnlyTests(unittest.TestCase):
    """Имя задания — функция координат, не раскладки."""

    def test_the_id_does_not_move_with_the_number_of_shards(self):
        units = _units()
        names = {u.task_id for u in units}
        for shards in (1, 3, 7, 64):
            flat = [u for bucket in S.assign(units, shards) for u in bucket]
            self.assertEqual({u.task_id for u in flat}, names, shards)
            self.assertEqual(len(flat), len(units), shards)

    def test_the_id_is_stable_across_calls_and_distinct_per_range(self):
        first, second = _units(), _units()
        self.assertEqual([u.task_id for u in first],
                         [u.task_id for u in second])
        self.assertEqual(len({u.task_id for u in first}), len(first))

    def test_the_id_ignores_everything_computational(self):
        """Имя — функция ТОЛЬКО (рука, начало, конец).

        Диверсия «имя задания зависит от раскладки» прошла незамеченной:
        прежние тесты проверяли стабильность имени ВНУТРИ прогона, а не
        независимость от вычислительного слоя. Подмешать в имя `weight`
        можно было бесследно — и тогда любая перенастройка модели
        стоимости переименовала бы все задания разом, то есть убила бы
        идемпотентность и чекпойнты между прогонами.
        """
        base = S.Unit(arm=TAG, start=0, stop=12, look=12, weight=1.0)
        for other in (S.Unit(arm=TAG, start=0, stop=12, look=12, weight=999.0),
                      S.Unit(arm=TAG, start=0, stop=12, look=48, weight=0.0),
                      S.Unit(arm=TAG, start=0, stop=12, look=12, weight=1e-9)):
            self.assertEqual(base.task_id, other.task_id,
                             f"имя сдвинулось от {other}")
        for other in (S.Unit(arm="другая", start=0, stop=12, look=12, weight=1.0),
                      S.Unit(arm=TAG, start=1, stop=12, look=12, weight=1.0),
                      S.Unit(arm=TAG, start=0, stop=13, look=12, weight=1.0)):
            self.assertNotEqual(base.task_id, other.task_id,
                                f"имя НЕ сдвинулось от {other}")

    def test_the_cost_model_can_be_retuned_without_renaming_anything(self):
        """Стоимость — оценка для балансировки. Науки в ней нет."""
        before = [u.task_id for u in _units()]
        saved = S.SECONDS_PER_PERIOD_AT_REFERENCE
        try:
            S.SECONDS_PER_PERIOD_AT_REFERENCE = saved * 7.0
            after = [u.task_id for u in _units()]
        finally:
            S.SECONDS_PER_PERIOD_AT_REFERENCE = saved
        self.assertEqual(before, after)

    def test_the_manifest_is_a_function_of_its_input_only(self):
        self.assertEqual(_units(), _units())
        self.assertNotEqual(_units(rate=6.0), _units(rate=96.0))


class UnitsRespectTheLadderTests(unittest.TestCase):
    """Юнит НИКОГДА не пересекает ступень лестницы."""

    def test_no_unit_straddles_a_look(self):
        for unit in _units():
            for look in LADDER:
                self.assertFalse(unit.start < look < unit.stop,
                                 f"{unit} пересекает {look}")

    def test_units_tile_every_step_without_gap_or_overlap(self):
        units = _units()
        previous = 0
        for look in LADDER:
            step = sorted((u for u in units if u.look == look),
                          key=lambda u: u.start)
            self.assertTrue(step, look)
            cursor = previous
            for unit in step:
                self.assertEqual(unit.start, cursor)
                cursor = unit.stop
            self.assertEqual(cursor, look)
            previous = look

    def test_the_production_manifest_also_respects_the_real_ladder(self):
        units = S.plan([(TAG, 96.0)])
        self.assertEqual({u.look for u in units}, set(PR.LOOKS))
        for unit in units:
            for look in PR.LOOKS:
                self.assertFalse(unit.start < look < unit.stop)


class ShardingDoesNotMoveTheResultTests(unittest.TestCase):
    """serial == sharded == reordered. Побитово, а не «примерно»."""

    def test_merged_equals_serial_and_order_does_not_matter(self):
        units = _units()
        parts = _run(units)
        serial = E.accumulate(TAG, 0, LADDER[-1], **ARM)

        merged = S.merge(TAG, parts, look=LADDER[-1], expected=units)
        self.assertEqual(S.store_digest(merged), S.store_digest(serial))
        self.assertEqual(set(merged), set(serial))
        for key in serial:
            self.assertEqual(merged[key], serial[key], key)

        shuffled = list(parts)
        random.Random(17).shuffle(shuffled)
        reordered = S.merge(TAG, shuffled, look=LADDER[-1], expected=units)
        self.assertEqual(S.store_digest(reordered), S.store_digest(serial))

    def test_every_intermediate_look_also_matches_serial(self):
        units = _units()
        parts = _run(units)
        for look in LADDER:
            merged = S.store_for_look(TAG, parts, look=look, expected=units)
            serial = E.accumulate(TAG, 0, look, **ARM)
            self.assertEqual(S.store_digest(merged), S.store_digest(serial),
                             look)

    def test_the_endpoints_themselves_are_identical(self):
        """Сверка на уровне НАУЧНОГО выхода, а не только склада."""
        units = _units()
        merged = S.merge(TAG, _run(units), look=LADDER[-1], expected=units)
        serial = E.accumulate(TAG, 0, LADDER[-1], **ARM)
        self.assertEqual(E.roots_from(merged), E.roots_from(serial))


class EarlyComputationIsNotEarlyLookingTests(unittest.TestCase):
    """Посчитать заранее можно. Посмотреть заранее — нет."""

    def test_future_units_are_invisible_to_an_earlier_look(self):
        units = _units()
        parts = _run(units)                      # посчитано ВСЁ, включая будущее
        early = S.store_for_look(TAG, parts, look=LADDER[0], expected=units)
        serial = E.accumulate(TAG, 0, LADDER[0], **ARM)
        self.assertEqual(S.store_digest(early), S.store_digest(serial))
        for key, pieces in early.items():
            self.assertLessEqual(len(pieces), LADDER[0])


class MergeFailsClosedTests(unittest.TestCase):
    """Недосчитанный склад внешне неотличим от досчитанного: он короче."""

    def setUp(self):
        self.units = _units()
        self.parts = _run(self.units)
        self.look = LADDER[-1]

    def _refuse(self, parts, expected=None):
        with self.assertRaises(S.MergeRefused):
            S.merge(TAG, parts, look=self.look,
                    expected=expected or self.units)

    def test_a_missing_unit_refuses(self):
        self._refuse(self.parts[:-1])
        self._refuse(self.parts[1:])

    def test_a_duplicated_unit_refuses(self):
        self._refuse(self.parts + [self.parts[0]])

    def test_an_unexpected_unit_refuses(self):
        stranger = S.Unit(arm=TAG, start=0, stop=3, look=LADDER[0], weight=1.0)
        self._refuse(self.parts + [(stranger, {})])

    def test_a_gap_refuses(self):
        thinned = [u for u in self.units if u.start != 0]
        self._refuse([p for p in self.parts if p[0].start != 0], thinned)

    def test_an_overlap_refuses(self):
        overlap = S.Unit(arm=TAG, start=0, stop=LADDER[-1], look=LADDER[-1],
                         weight=1.0)
        self._refuse(self.parts + [(overlap, {})], self.units + (overlap,))

    def test_the_empty_merge_refuses_rather_than_returning_nothing(self):
        with self.assertRaises(S.MergeRefused):
            S.merge(TAG, [], look=self.look, expected=self.units)


class BalancingIsGreedyNotContiguousTests(unittest.TestCase):
    """Непрерывная нарезка перекашивает: дорогие руки собираются вместе."""

    def _arms(self):
        from simulation import s5b_prereg as P
        return [(f"r{rate}:{i}", rate)
                for rate in P.OPPORTUNITY_RATE_GRID for i in range(4)]

    def test_lpt_beats_contiguous_slicing_on_the_real_rate_grid(self):
        units = S.plan(self._arms())
        shards = 8
        greedy = S.assign(units, shards)
        greedy_max = max(sum(u.weight for u in b) for b in greedy)

        size = -(-len(units) // shards)
        chunks = [units[i:i + size] for i in range(0, len(units), size)]
        contiguous_max = max(sum(u.weight for u in c) for c in chunks)

        self.assertLess(greedy_max, contiguous_max,
                        "жадная раскладка обязана быть не хуже нарезки")

    def test_every_unit_is_placed_exactly_once(self):
        units = S.plan(self._arms())
        for shards in (1, 5, 13):
            placed = [u for b in S.assign(units, shards) for u in b]
            self.assertEqual(sorted(u.task_id for u in placed),
                             sorted(u.task_id for u in units))

    def test_a_nonsense_shard_count_refuses(self):
        with self.assertRaises(ValueError):
            S.assign(_units(), 0)
