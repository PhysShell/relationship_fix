"""Гейты слоя эскалации. Первый из них — что рефакторинг ничего не сдвинул.

Восстановленный runner объявлен EQUIVALENCE ORACLE, поэтому любая правка в
нём обязана доказывать, что выход не изменился. Золотые значения сняты ДО
рефакторинга и вписаны сюда числами, а не пересчитываются тем же кодом,
который проверяется.
"""

from __future__ import annotations

import hashlib
import json
import unittest

from simulation import s5b_escalation as E
from simulation import s5b_precision as PR
from simulation import s5b_stage1 as S

GOLDEN_ARM = dict(rate=6.0, shift=0.40, ratio=0.75, c_rate=1.10, c_shift=-0.10)
GOLDEN_SEED = "golden"
GOLDEN_PERIODS = 50
#: дайджест всех 72 концов, округлённых до 9 знаков, снят до рефакторинга
GOLDEN_DIGEST = "444d383c91b85507"
GOLDEN_SAMPLE = {
    "1.0|14.0|300.0|0": 274.940586091,
    "1.0|14.0|300.0|1": 274.940657617,
    "1.0|14.0|3600.0|0": 1413.719308377,
    "1.0|14.0|3600.0|1": 1413.719362021,
    "1.0|14.0|86400.0|0": 6675.494349003,
    "1.0|14.0|86400.0|1": 6675.494429469,
}


def _digest(encoded):
    return hashlib.sha256(json.dumps(
        {k: round(v, 9) for k, v in sorted(encoded.items())},
        sort_keys=True).encode()).hexdigest()[:16]


class TheOracleDidNotMoveTests(unittest.TestCase):
    """Рефакторинг ради эскалации не имеет права сдвинуть ни один конец."""

    def test_the_recovered_runner_still_produces_the_golden(self):
        encoded = S.encode(S.arm_endpoints(GOLDEN_SEED, periods=GOLDEN_PERIODS,
                                           **GOLDEN_ARM))
        self.assertEqual(len(encoded), 72)
        for key, want in GOLDEN_SAMPLE.items():
            self.assertAlmostEqual(encoded[key], want, places=9, msg=key)
        self.assertEqual(_digest(encoded), GOLDEN_DIGEST)

    def test_the_escalation_layer_reproduces_the_runner_exactly(self):
        """Эскалация обязана давать ТЕ ЖЕ точки, а не «примерно те же».

        Иначе слой точности молча поменял бы сам эстиманд, и это была бы
        худшая из возможных правок — незаметная.
        """
        store = E.accumulate(GOLDEN_SEED, 0, GOLDEN_PERIODS, **GOLDEN_ARM)
        self.assertEqual(_digest(S.encode(E.roots_from(store))), GOLDEN_DIGEST)


class NestingIsAStrictPrefixTests(unittest.TestCase):
    """`16000` продолжает `4000`, а не строит новую выборку."""

    def test_accumulating_in_two_steps_equals_one_step(self):
        whole = E.accumulate(GOLDEN_SEED, 0, 40, **GOLDEN_ARM)
        split = E.accumulate(GOLDEN_SEED, 0, 17, **GOLDEN_ARM)
        split = E.accumulate(GOLDEN_SEED, 17, 40, store=split, **GOLDEN_ARM)
        self.assertEqual(set(whole), set(split))
        for key in whole:
            self.assertEqual(whole[key], split[key], key)

    def test_a_prefix_is_a_prefix_of_the_longer_store(self):
        short = E.accumulate(GOLDEN_SEED, 0, 17, **GOLDEN_ARM)
        long = E.accumulate(GOLDEN_SEED, 0, 40, **GOLDEN_ARM)
        for key, pieces in short.items():
            self.assertEqual(long[key][:len(pieces)], pieces, key)

    def test_the_stream_does_not_depend_on_where_the_chunk_starts(self):
        """Сид периода — функция только (tag, i). Ни shard, ни порядок."""
        middle = E.accumulate(GOLDEN_SEED, 17, 40, **GOLDEN_ARM)
        whole = E.accumulate(GOLDEN_SEED, 0, 40, **GOLDEN_ARM)
        for key, pieces in middle.items():
            self.assertEqual(whole[key][-len(pieces):], pieces, key)


class PrecisionLayerTests(unittest.TestCase):
    """Статусы, лестница и запрет на управление прогнозом."""

    def test_every_endpoint_gets_a_status_and_a_delta_fraction(self):
        from simulation import s5b_prereg as P
        store = E.accumulate(GOLDEN_SEED, 0, 30, **GOLDEN_ARM)
        got = E.endpoints_from(store, look=30)
        self.assertEqual(len(got), 72 * len(P.DELTA_FRACTIONS_OF_HORIZON))
        for (key, fraction), endpoint in got.items():
            self.assertIn(fraction, P.DELTA_FRACTIONS_OF_HORIZON)
            self.assertIsInstance(endpoint.status, PR.PrecisionStatus)
            self.assertGreaterEqual(endpoint.radius, 0.0)

    def test_thirty_periods_cannot_reach_precision(self):
        """Тридцать периодов заведомо грубы; статус обязан это сказать."""
        store = E.accumulate(GOLDEN_SEED, 0, 30, **GOLDEN_ARM)
        got = E.endpoints_from(store, look=30)
        self.assertTrue(all(e.status is PR.PrecisionStatus.INSUFFICIENT
                            for e in got.values()))

    def test_the_cell_needs_all_four_endpoints(self):
        A = PR.PrecisionStatus.ACHIEVED
        I = PR.PrecisionStatus.INSUFFICIENT
        self.assertTrue(E.cell_is_evaluable([A, A, A, A]))
        self.assertFalse(E.cell_is_evaluable([A, A, A, I]))
        self.assertFalse(E.cell_is_evaluable([A, A, A]))
        self.assertFalse(E.cell_is_evaluable([A, A, A, A, A]))

    def test_an_unevaluable_cell_gets_the_surface_status(self):
        A = PR.PrecisionStatus.ACHIEVED
        I = PR.PrecisionStatus.INSUFFICIENT
        self.assertEqual(E.cell_status([A, A, A, I]),
                         PR.NOT_EVALUATED_MC_PRECISION)
        self.assertIsNone(E.cell_status([A, A, A, A]))

    def test_prediction_never_reaches_control_flow(self):
        """PREDICTED — только провенанс. В лестницу он не входит."""
        import inspect
        source = inspect.getsource(E)
        body = source.split("PREDICTED_NEVER_DRIVES_CONTROL_FLOW")[-1]
        self.assertNotIn("PREDICTED_INSUFFICIENT", body.split("def ", 1)[-1]
                         .split("PROVENANCE")[0])
        A = PR.PrecisionStatus.ACHIEVED
        P_ = PR.PrecisionStatus.PREDICTED_INSUFFICIENT
        self.assertFalse(E.cell_is_evaluable([A, A, A, P_]),
                         "прогноз не заменяет достигнутую точность")
        self.assertTrue(E.PREDICTED_NEVER_DRIVES_CONTROL_FLOW)

    def test_the_h300_cells_are_not_skipped(self):
        """Futility-правила нет; H = 300 идёт обычной лестницей."""
        from simulation import s5b_prereg as P
        self.assertIn(300.0, P.HORIZONS_SECONDS)
        self.assertFalse(E.SKIPPED_HORIZONS)
        store = E.accumulate(GOLDEN_SEED, 0, 20, **GOLDEN_ARM)
        horizons = {key[2] for key, _ in E.endpoints_from(store, look=20)}
        self.assertIn(300.0, horizons)


class TheGoldenCanonisedTheComputationNotTheSemanticsTests(unittest.TestCase):
    """Золотой дайджест доказывает «то же, что раньше», и не более.

    Область действия оракула — ВЫЧИСЛЕНИЕ. Прав ли старый runner в смысле
    режимов, он не говорит вовсе, и R4 это показал.
    """

    def test_the_regime_path_reproduces_the_golden_for_R3(self):
        """Золотой снят при (0.40, 0.75), то есть это R3 при m = 1."""
        store = E.accumulate(GOLDEN_SEED, 0, GOLDEN_PERIODS, rate=6.0,
                             c_rate=1.10, c_shift=-0.10,
                             regime="R3", magnitude=1.0)
        self.assertEqual(_digest(S.encode(E.roots_from(store))), GOLDEN_DIGEST)

    def test_the_legacy_effect_is_marked_wrong_rather_than_quietly_fixed(self):
        self.assertTrue(S.LEGACY_EFFECT_IS_WRONG_FOR_R4)
        self.assertEqual(S.effect("R4", 1.0), (0.2, 0.87),
                         "оракул обязан остаться записью того, ЧТО БЫЛО")
        self.assertIn("не трогается", E.R4_SEMANTICS_MISMATCH)


class RegimeSemanticsComeFromTheFrozenSourceTests(unittest.TestCase):
    """Числа не переписываются руками — именно это и породило расхождение."""

    def test_R0_to_R3_agree_with_the_legacy_effect_exactly(self):
        for regime in ("R0", "R1", "R2", "R3"):
            for magnitude in (0.5, 1.0, 2.0):
                got = E.regime_effect("tag", 0, regime, magnitude)
                want = S.effect(regime, magnitude)
                self.assertAlmostEqual(got[0], want[0], places=12,
                                       msg=(regime, magnitude))
                self.assertAlmostEqual(got[1], want[1], places=12,
                                       msg=(regime, magnitude))

    def test_R4_deliberately_disagrees_with_the_legacy_effect(self):
        legacy = S.effect("R4", 1.0)
        drawn = {E.regime_effect("tag", i, "R4", 1.0) for i in range(50)}
        self.assertNotIn(legacy, drawn)
        self.assertEqual({r for _, r in drawn}, {1.0},
                         "у R4 нет канала incidence вовсе")

    def test_R4_is_a_fair_coin_over_periods(self):
        from simulation.experiment import LATENCY_SHIFT
        draws = [E.regime_effect("tag", i, "R4", 1.0)[0] for i in range(4_000)]
        self.assertEqual(set(draws), {2 * LATENCY_SHIFT, 0.0})
        treated = sum(x > 0 for x in draws) / len(draws)
        self.assertGreater(treated, 0.46, treated)
        self.assertLess(treated, 0.54, treated)

    def test_R4_keeps_the_declared_mean_itt(self):
        from simulation.experiment import LATENCY_SHIFT
        for magnitude in (0.5, 1.0, 2.0):
            draws = [E.regime_effect("tag", i, "R4", magnitude)[0]
                     for i in range(4_000)]
            mean = sum(draws) / len(draws)
            self.assertAlmostEqual(mean, magnitude * LATENCY_SHIFT, delta=0.03,
                                   msg=magnitude)

    def test_the_multiplier_applies_before_the_split(self):
        """`2·(m·L) = m·(2·L)`: буквальное чтение prereg и реализация сходятся.

        Проверяется, а не объявляется — именно на этом месте prereg и
        настаивает, что структура гетерогенности обязана сохраниться.
        """
        from simulation.experiment import LATENCY_SHIFT
        for magnitude in (0.5, 1.0, 2.0):
            for index in range(40):
                got = E.regime_effect("tag", index, "R4", magnitude)[0]
                literal = (2 * (magnitude * LATENCY_SHIFT)
                           if got > 0 else 0.0)
                self.assertAlmostEqual(got, literal, places=12)


class TheEffectDrawIsItsOwnSubstreamTests(unittest.TestCase):
    """Тип периода — функция только (tag, i). Ни шарда, ни порядка."""

    def test_the_draw_does_not_touch_the_message_stream(self):
        import random as _random
        message = _random.Random(f"tag:{7}").random()
        effect = _random.Random(f"tag:{E.EFFECT_SUBSTREAM}:{7}").random()
        self.assertNotEqual(message, effect)

    def test_the_period_type_is_the_same_whatever_the_chunk(self):
        whole = [E.regime_effect("tag", i, "R4", 1.0) for i in range(60)]
        pieces = ([E.regime_effect("tag", i, "R4", 1.0) for i in range(17)]
                  + [E.regime_effect("tag", i, "R4", 1.0) for i in range(17, 60)])
        self.assertEqual(whole, pieces)

    def test_two_arms_do_not_share_the_heterogeneity_pattern(self):
        left = [E.regime_effect("a", i, "R4", 1.0) for i in range(60)]
        right = [E.regime_effect("b", i, "R4", 1.0) for i in range(60)]
        self.assertNotEqual(left, right)

    def test_the_store_built_from_chunks_matches_for_R4_too(self):
        kw = dict(rate=6.0, c_rate=1.10, c_shift=-0.10,
                  regime="R4", magnitude=1.0)
        whole = E.accumulate(GOLDEN_SEED, 0, 24, **kw)
        split = E.accumulate(GOLDEN_SEED, 0, 9, **kw)
        split = E.accumulate(GOLDEN_SEED, 9, 24, store=split, **kw)
        self.assertEqual(whole, split)

    def test_the_draw_is_pinned_to_its_own_substream(self):
        """Не упоминание имени потока, а ТОЖДЕСТВО с ним.

        Слить поток эффекта с потоком сообщений значит скоррелировать, кто
        пролечен, с тем, какая диада выпала. Детерминизм при этом
        сохранится, поэтому поймать подмену можно только равенством.
        """
        import random as _random
        from simulation.experiment import LATENCY_SHIFT
        for index in range(30):
            stream = _random.Random(f"{GOLDEN_SEED}:{E.EFFECT_SUBSTREAM}:{index}")
            want = 2 * LATENCY_SHIFT if stream.random() < 0.5 else 0.0
            got = E.regime_effect(GOLDEN_SEED, index, "R4", 1.0)[0]
            self.assertEqual(got, want, index)

    def test_R4_is_drawn_PER_PERIOD_not_once_for_the_arm(self):
        """Розыгрыш, поднятый из цикла, дал бы однородную руку.

        Тогда склад совпал бы с одним из двух постоянных вариантов, и
        гетерогенность исчезла бы, не оставив следа в числах.
        """
        from simulation.experiment import LATENCY_SHIFT
        kw = dict(rate=6.0, c_rate=1.10, c_shift=-0.10)
        mixed = E.accumulate(GOLDEN_SEED, 0, 30, regime="R4",
                             magnitude=1.0, **kw)
        for constant in (2 * LATENCY_SHIFT, 0.0):
            homogeneous = E.accumulate(GOLDEN_SEED, 0, 30, shift=constant,
                                       ratio=1.0, **kw)
            self.assertNotEqual(mixed, homogeneous, constant)

    def test_R4_really_moves_the_endpoints(self):
        """Иначе «исправили» означало бы «ничего не поменяли»."""
        kw = dict(rate=6.0, c_rate=1.10, c_shift=-0.10)
        fixed = E.roots_from(E.accumulate(GOLDEN_SEED, 0, 40,
                                          regime="R4", magnitude=1.0, **kw))
        legacy_shift, legacy_ratio = S.effect("R4", 1.0)
        legacy = E.roots_from(E.accumulate(GOLDEN_SEED, 0, 40,
                                           shift=legacy_shift,
                                           ratio=legacy_ratio, **kw))
        self.assertNotEqual(fixed, legacy)


class TheControlArmMappingTests(unittest.TestCase):
    """K = R0 той же (rate, C). Перескочить координаты нельзя."""

    def test_only_the_regime_changes(self):
        got = E.control_arm_for(24.0, 1.25, "R2", 2.0)
        self.assertEqual(got, (24.0, 1.25, "R0", 1.0))

    def test_R0_maps_to_itself(self):
        self.assertEqual(E.control_arm_for(6.0, 1.10, "R0", 1.0),
                         (6.0, 1.10, "R0", 1.0))

    def test_the_rate_and_the_reactivity_point_are_carried_over(self):
        from simulation import s5b_prereg as P
        for rate in P.OPPORTUNITY_RATE_GRID:
            for c_rate, _ in P.C_REACTIVITY_POINTS:
                arm_rate, arm_c, regime, magnitude = E.control_arm_for(
                    rate, c_rate, "R4", 0.5)
                self.assertEqual((arm_rate, arm_c), (rate, c_rate))
                self.assertEqual((regime, magnitude), ("R0", 1.0))

    def test_the_completion_is_marked_as_post_freeze(self):
        self.assertTrue(E.CONTROL_ARM_WAS_UNSPECIFIED_IN_BASELINE)
        self.assertIn("T = (rate, C, Ri, magnitude)", E.CONTROL_ARM_MAPPING)
        self.assertIn("R0", E.CONTROL_ARM_MAPPING)

    def test_a_contrast_is_still_not_computed_here(self):
        """Отображение есть; контраст — следующий шаг, не этот."""
        self.assertFalse(hasattr(E, "cell_contrast"))


class BothFindingsAreRecordedTests(unittest.TestCase):
    """Находки записаны в документ, а не только в код."""

    def _note(self):
        import pathlib as _p
        root = _p.Path(__file__).resolve().parents[3]
        return (root / "docs/research/s5b-r4-semantics-and-control-arm.md"
                ).read_text()

    def test_the_r4_mismatch_is_written_down_with_both_defects(self):
        note = " ".join(self._note().split())
        self.assertIn("R4_SEMANTICS_MISMATCH", note)
        self.assertIn("(0.20, 0.87)", note)
        self.assertIn("Канала incidence у `R4` **нет вовсе**", note)
        self.assertIn("Исправляется **реализация**, не prereg", note)

    def test_the_scope_of_the_oracle_is_stated(self):
        """Золотой дайджест доказывает «то же», а не «верно»."""
        note = " ".join(self._note().split())
        self.assertIn("область действия оракула — ВЫЧИСЛЕНИЕ, а не семантика",
                      note)
        self.assertIn("**не канонизировал** этот баг", note)

    def test_the_control_arm_completion_is_marked_post_freeze(self):
        note = " ".join(self._note().split())
        self.assertIn("post-freeze specification completion", note)
        self.assertIn("не делает вид, что существовала всегда", note)
        self.assertIn("не обязательно `[0, 0]`", note)

    def test_the_prereg_was_not_touched_by_either(self):
        note = self._note()
        self.assertIn("Prereg `2224eb8` не изменён ни одной из них", note)

