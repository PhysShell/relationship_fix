"""Гейты шардинга. Главный: раскладка не имеет права менять результат.

Ось разреза — КЛЮЧИ. Они разделимы ВЫЧИСЛИТЕЛЬНО: конец ключа считается
без состояния, выведенного из другого ключа. Статистической независимости
между ключами нет и не требуется — они считаются по одним и тем же диадам.
"""

from __future__ import annotations

import random
import unittest

from simulation import s5b_escalation as E
from simulation import s5b_precision as PR
from simulation import s5b_shard as S

ARM = dict(rate=6.0, c_rate=1.10, c_shift=-0.10, regime="R3", magnitude=1.0)
TAG = "golden"
LADDER = (12, 30)


def _units(ladder=LADDER, rate=6.0):
    return S.plan([(TAG, rate)], ladder=ladder)


class TaskIdentityIsScientificOnlyTests(unittest.TestCase):

    def test_the_id_is_a_function_of_arm_look_and_keys_only(self):
        base = S.Unit(arm=TAG, look=12, keys=E.KEYS[:4], weight=1.0)
        same = S.Unit(arm=TAG, look=12, keys=E.KEYS[:4], weight=999.0)
        self.assertEqual(base.task_id, same.task_id, "вес попал в имя")
        for other in (S.Unit(arm="иная", look=12, keys=E.KEYS[:4], weight=1.0),
                      S.Unit(arm=TAG, look=30, keys=E.KEYS[:4], weight=1.0),
                      S.Unit(arm=TAG, look=12, keys=E.KEYS[:5], weight=1.0)):
            self.assertNotEqual(base.task_id, other.task_id, other)

    def test_the_cost_model_can_be_retuned_without_renaming_anything(self):
        before = [u.task_id for u in _units()]
        saved = S.SECONDS_PER_PERIOD_AT_REFERENCE
        try:
            S.SECONDS_PER_PERIOD_AT_REFERENCE = saved * 7.0
            after = [u.task_id for u in _units()]
        finally:
            S.SECONDS_PER_PERIOD_AT_REFERENCE = saved
        self.assertEqual(before, after)

    def test_the_id_does_not_move_with_the_number_of_shards(self):
        units = _units()
        names = {u.task_id for u in units}
        for shards in (1, 3, 9):
            flat = [u for bucket in S.assign(units, shards) for u in bucket]
            self.assertEqual({u.task_id for u in flat}, names, shards)


class UnitsTileTheKeySpaceTests(unittest.TestCase):

    def test_each_arm_and_look_covers_every_key_exactly_once(self):
        for look in LADDER:
            keys = []
            for unit in _units():
                if unit.look == look:
                    keys.extend(unit.keys)
            self.assertEqual(len(keys), len(set(keys)), "ключи пересекаются")
            self.assertEqual(set(keys), set(E.KEYS), "покрытие неполное")

    def test_groups_are_contiguous_in_the_canonical_order(self):
        for unit in _units():
            first = E.KEYS.index(unit.keys[0])
            self.assertEqual(tuple(E.KEYS[first:first + len(unit.keys)]),
                             unit.keys)

    def test_the_heaviest_production_arm_is_split_enough_to_fit(self):
        """rate = 96 на третьей ступени: одна группа не влезает в потолок."""
        self.assertGreater(S.cost_of(96.0, 64_000, 1.0) / 3600,
                           S.SHARD_BUDGET_HOURS)
        groups = S.groups_needed(96.0, 64_000)
        self.assertGreater(groups, 1)
        self.assertLessEqual(S.cost_of(96.0, 64_000, 1.0 / groups) / 3600,
                             S.SHARD_BUDGET_HOURS)


class ShardingDoesNotMoveTheResultTests(unittest.TestCase):
    """Юнит обязан давать ТО ЖЕ, что монолит. Побитово."""

    def _monolith(self, look):
        store = E.accumulate(TAG, 0, look, **ARM)
        return E.endpoints_from(store, look=look)

    def test_a_unit_equals_the_monolith_on_its_own_keys(self):
        look = LADDER[-1]
        whole = self._monolith(look)
        for unit in _units():
            if unit.look != look:
                continue
            got = S.run_unit(unit, **ARM)
            self.assertTrue(got, unit.task_id)
            for name, endpoint in got.items():
                self.assertEqual(endpoint, whole[name], name)

    def test_the_merged_result_equals_the_monolith_entirely(self):
        look = LADDER[-1]
        units = [u for u in _units() if u.look == look]
        parts = [(u, S.run_unit(u, **ARM)) for u in units]
        merged = S.merge(TAG, look, parts, expected=units)
        whole = self._monolith(look)
        self.assertEqual(S.result_digest(merged), S.result_digest(whole))
        self.assertEqual(merged, whole)

    def test_the_order_of_parts_does_not_matter(self):
        look = LADDER[-1]
        units = [u for u in _units() if u.look == look]
        parts = [(u, S.run_unit(u, **ARM)) for u in units]
        shuffled = list(parts)
        random.Random(11).shuffle(shuffled)
        self.assertEqual(S.merge(TAG, look, shuffled, expected=units),
                         S.merge(TAG, look, parts, expected=units))

    def test_the_prefix_is_recomputed_identically_not_resampled(self):
        """Ступень 3, пересчитав 0..M3, обязана увидеть те же 0..M1."""
        short = E.accumulate(TAG, 0, LADDER[0], **ARM)
        long = E.accumulate(TAG, 0, LADDER[-1], **ARM)
        for key, pieces in short.items():
            self.assertEqual(long[key][:len(pieces)], pieces, key)


class MergeFailsClosedTests(unittest.TestCase):
    """Неполный набор концов внешне неотличим от полного: он короче."""

    def setUp(self):
        self.look = LADDER[-1]
        self.units = [u for u in _units() if u.look == self.look]
        self.parts = [(u, S.run_unit(u, **ARM)) for u in self.units]

    def _refuse(self, parts, expected=None):
        with self.assertRaises(S.MergeRefused):
            S.merge(TAG, self.look, parts, expected=expected or self.units)

    def test_a_missing_unit_refuses(self):
        self._refuse(self.parts[:-1])

    def test_a_duplicated_unit_refuses(self):
        self._refuse(self.parts + [self.parts[0]])

    def test_an_unexpected_unit_refuses(self):
        stranger = S.Unit(arm=TAG, look=self.look, keys=E.KEYS[:1], weight=1.0)
        self._refuse(self.parts + [(stranger, {})])

    def test_incomplete_key_coverage_refuses(self):
        half = S.Unit(arm=TAG, look=self.look, keys=E.KEYS[:10], weight=1.0)
        self._refuse([(half, {})], [half])

    def test_a_unit_returning_a_foreign_key_refuses(self):
        """Юнит обязан отдавать СВОИ ключи и только их.

        При одной группе своих ключей — все, поэтому чужой взять неоткуда;
        пара строится явно, чтобы проверка не оказалась пустой.
        """
        half = len(E.KEYS) // 2
        left = S.Unit(arm=TAG, look=self.look, keys=E.KEYS[:half], weight=1.0)
        right = S.Unit(arm=TAG, look=self.look, keys=E.KEYS[half:], weight=1.0)
        whole = S.run_unit(S.Unit(arm=TAG, look=self.look, keys=E.KEYS,
                                  weight=1.0), **ARM)
        mine = {n: e for n, e in whole.items() if n[0] in left.keys}
        theirs = {n: e for n, e in whole.items() if n[0] in right.keys}
        S.merge(TAG, self.look, [(left, mine), (right, theirs)],
                expected=[left, right])            # чистый случай проходит
        alien = next(iter(theirs))
        polluted = dict(mine)
        polluted[alien] = theirs[alien]
        with self.assertRaises(S.MergeRefused):
            S.merge(TAG, self.look, [(left, polluted), (right, theirs)],
                    expected=[left, right])

    def test_an_empty_merge_refuses(self):
        self._refuse([])

    def test_a_look_the_manifest_never_declared_refuses(self):
        with self.assertRaises(S.MergeRefused):
            S.merge(TAG, 99_999, self.parts, expected=self.units)


class PlatformLimitsAreCheckedNotAssumedTests(unittest.TestCase):
    """256 заданий на матрицу и 6 часов на задание — сверено с документацией."""

    def test_the_documented_limits_are_recorded(self):
        self.assertEqual(S.GITHUB_MATRIX_MAX_JOBS, 256)
        self.assertEqual(S.GITHUB_JOB_MAX_HOURS, 6.0)
        self.assertLess(S.SHARD_BUDGET_HOURS, S.GITHUB_JOB_MAX_HOURS,
                        "бюджет обязан иметь запас до потолка")

    def test_too_many_shards_refuses(self):
        units = _units()
        with self.assertRaises(S.PlanRefused):
            S.check_platform_limits([units] * (S.GITHUB_MATRIX_MAX_JOBS + 1))

    def test_an_over_budget_shard_refuses(self):
        heavy = S.Unit(arm=TAG, look=64_000, keys=E.KEYS,
                       weight=S.SHARD_BUDGET_HOURS * 3600 + 1.0)
        with self.assertRaises(S.PlanRefused):
            S.check_platform_limits([[heavy]])

    def test_the_shard_count_is_derived_by_checking_the_real_assignment(self):
        """Формула «сумма делить на бюджет» ошибается в опасную сторону.

        Юнит неделим, идеальной упаковки не бывает, и на второй ступени
        оценка давала 4.12 ч при бюджете 4.0 ч.
        """
        from simulation import s5b_prereg as P
        from simulation import s5b_stage1 as T
        arms = [(T.arm_tag(r, c, reg, m), r) for r in P.OPPORTUNITY_RATE_GRID
                for c, _ in P.C_REACTIVITY_POINTS for reg, m in T.REGIMES]
        units = S.plan(arms)
        for look in PR.LOOKS:
            step = [u for u in units if u.look == look]
            count = S.shards_needed(step)
            S.check_platform_limits(S.assign(step, count))
            self.assertLessEqual(count, S.GITHUB_MATRIX_MAX_JOBS, look)
            if count > 1:
                with self.assertRaises(S.PlanRefused, msg=look):
                    S.check_platform_limits(S.assign(step, count - 1))

    def test_an_indivisible_over_budget_unit_refuses_outright(self):
        huge = S.Unit(arm=TAG, look=64_000, keys=E.KEYS,
                      weight=S.SHARD_BUDGET_HOURS * 3600 * 2)
        with self.assertRaises(S.PlanRefused):
            S.shards_needed([huge])


class BalancingIsGreedyNotContiguousTests(unittest.TestCase):

    def _arms(self):
        from simulation import s5b_prereg as P
        return [(f"r{rate}:{i}", rate)
                for rate in P.OPPORTUNITY_RATE_GRID for i in range(4)]

    def test_lpt_beats_contiguous_slicing_on_the_real_rate_grid(self):
        units = S.plan(self._arms())
        shards = 8
        greedy = max(sum(u.weight for u in b)
                     for b in S.assign(units, shards))
        size = -(-len(units) // shards)
        contiguous = max(sum(u.weight for u in units[i:i + size])
                         for i in range(0, len(units), size))
        self.assertLess(greedy, contiguous)

    def test_every_unit_is_placed_exactly_once(self):
        units = S.plan(self._arms())
        for shards in (1, 5, 13):
            placed = [u for b in S.assign(units, shards) for u in b]
            self.assertEqual(sorted(u.task_id for u in placed),
                             sorted(u.task_id for u in units))

    def test_a_nonsense_shard_count_refuses(self):
        with self.assertRaises(ValueError):
            S.assign(_units(), 0)


class KeysAreSeparableNotIndependentTests(unittest.TestCase):
    """Формулировка существенна: разделимость и независимость — разное."""

    def test_the_claim_is_computational_separability(self):
        self.assertTrue(E.KEYS_ARE_COMPUTATIONALLY_SEPARABLE_NOT_INDEPENDENT)

    def test_keys_share_the_very_same_dyads(self):
        """Раз диады общие, статистическая независимость не утверждается."""
        left = E.accumulate(TAG, 0, 8, wanted=E.KEYS[:2], **ARM)
        right = E.accumulate(TAG, 0, 8, wanted=E.KEYS[2:4], **ARM)
        both = E.accumulate(TAG, 0, 8, wanted=E.KEYS[:4], **ARM)
        self.assertEqual({**left, **right}, both)
