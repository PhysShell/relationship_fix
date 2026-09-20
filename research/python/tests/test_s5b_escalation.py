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


class TheControlArmGapIsRecordedTests(unittest.TestCase):
    """Какая рука есть `K`, prereg не говорит. Это записано, а не решено."""

    def test_the_pairing_is_flagged_as_unspecified(self):
        self.assertIn("не определяет", E.CONTROL_ARM_IS_UNSPECIFIED)
        self.assertIn("R0", E.CONTROL_ARM_READING)

    def test_no_cell_contrast_is_computed_on_an_assumed_pairing(self):
        self.assertFalse(hasattr(E, "cell_contrast"),
                         "контраст нельзя считать по угаданной паре")
