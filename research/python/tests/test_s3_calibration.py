"""S3-гарнесс проверяется тем же, чем всё остальное: попыткой его сломать.

Инструмент сравнения опаснее обычного кода: он выдаёт вердикт о том, верен ли
генератор, и ошибка в нём выглядит как открытие. Поэтому правило решения
(`classify_distance`) проверяется отдельно от любой симуляции и любого корпуса —
пятью числами, как `recovery.classify`.
"""

import math
import unittest

from extractor.model import RawMessage
from simulation import corpus_compare as cal
from simulation import manifest
from simulation.manifest import RunManifest, trace_digest
from simulation.process import DyadParameters, Population, TrueEffect

H = (1 / 60, 24.0)


def message(mid, actor, at, *, offset=0):
    return RawMessage(message_id=mid, actor=actor, local_time=at,
                      utc_offset_minutes=offset, char_count=10,
                      device_id="t", deleted=False, synced_at=None)


class CoarsenTests(unittest.TestCase):
    """Огрубление часов — то, без чего MaiChat на наш вопрос не отвечает."""

    def test_it_floors_onto_the_grid(self):
        got = cal.coarsen([message("a", "p", 1234.87)], 1.0)
        self.assertEqual(got[0].timestamp, 1234.0)

    def test_a_coarser_grid_collapses_more(self):
        stream = [message("a", "p", 70.0), message("b", "q", 100.0)]
        self.assertEqual(len({m.timestamp for m in cal.coarsen(stream, 1.0)}), 2)
        self.assertEqual(len({m.timestamp for m in cal.coarsen(stream, 60.0)}), 1)

    def test_resolution_zero_changes_nothing(self):
        stream = [message("a", "p", 1234.87)]
        self.assertEqual(cal.coarsen(stream, 0.0), stream)

    def test_the_grid_is_on_the_event_axis_not_the_local_clock(self):
        """Иначе смещение зоны двигало бы сетку, и две записи одного момента
        из разных зон попадали бы в разные секунды."""
        utc = cal.coarsen([message("a", "p", 3600.5, offset=0)], 1.0)[0]
        plus_one = cal.coarsen([message("b", "p", 7200.5, offset=60)], 1.0)[0]
        self.assertEqual(utc.timestamp, plus_one.timestamp)

    def test_flooring_never_reorders_two_moments(self):
        stream = [message("a", "p", 10.9), message("b", "q", 11.1)]
        coarse = cal.coarsen(stream, 1.0)
        self.assertLessEqual(coarse[0].timestamp, coarse[1].timestamp)


class QuantileTests(unittest.TestCase):

    def test_it_interpolates_between_order_statistics(self):
        self.assertEqual(cal.quantile([0.0, 1.0, 2.0, 3.0, 4.0], 0.5), 2.0)
        self.assertEqual(cal.quantile([0.0, 1.0, 2.0, 3.0, 4.0], 0.25), 1.0)

    def test_too_few_observations_give_nothing_rather_than_a_guess(self):
        self.assertIsNone(cal.quantile([1.0, 2.0, 3.0, 4.0], 0.5))
        self.assertIsNone(cal.quantile([], 0.5))

    def test_the_ends_are_the_extremes(self):
        self.assertEqual(cal.quantile([5.0, 1.0, 3.0, 2.0, 4.0], 0.0), 1.0)
        self.assertEqual(cal.quantile([5.0, 1.0, 3.0, 2.0, 4.0], 1.0), 5.0)


class ClassifyDistanceTests(unittest.TestCase):
    """Правило решения из prereg §3, назначенное ДО просмотра корпуса."""

    FULL = cal.Comparability.FULL

    def test_within_a_factor_of_two_everywhere_is_in_range(self):
        self.assertIs(cal.classify_distance(0.0, self.FULL), cal.Verdict.IN_RANGE)
        self.assertIs(cal.classify_distance(1.0, self.FULL), cal.Verdict.IN_RANGE)

    def test_between_two_and_four_is_marginal(self):
        self.assertIs(cal.classify_distance(1.001, self.FULL), cal.Verdict.MARGINAL)
        self.assertIs(cal.classify_distance(2.0, self.FULL), cal.Verdict.MARGINAL)

    def test_beyond_a_factor_of_four_is_out_of_range(self):
        self.assertIs(cal.classify_distance(2.001, self.FULL), cal.Verdict.OUT_OF_RANGE)

    def test_structural_mismatch_outranks_any_distance(self):
        """NOT COMPARABLE идёт первым: иначе структурное несоответствие
        превращается в «расхождение», а потом в повод подкрутить генератор под
        корпус, который на этот вопрос не отвечает."""
        for distance in (0.0, 1.0, 9.0, None):
            self.assertIs(cal.classify_distance(distance, cal.Comparability.NONE),
                          cal.Verdict.NOT_COMPARABLE)

    def test_a_missing_distance_is_insufficient_and_not_a_pass(self):
        self.assertIs(cal.classify_distance(None, self.FULL), cal.Verdict.INSUFFICIENT)
        self.assertIs(cal.classify_distance(None, cal.Comparability.SHORT_RANGE),
                      cal.Verdict.INSUFFICIENT)

    def test_the_verdict_grid_narrows_with_comparability(self):
        grids = {q.comparability: q.verdict_grid for q in cal.QUANTITIES}
        self.assertEqual(grids[cal.Comparability.FULL], cal.QUANTILES)
        self.assertEqual(grids[cal.Comparability.SHORT_RANGE], cal.SHORT_GRID)
        self.assertEqual(grids[cal.Comparability.NONE], ())

    def test_every_registered_quantity_carries_a_reason(self):
        for quantity in cal.QUANTITIES:
            self.assertTrue(quantity.why, quantity.name)


class TiePressureTests(unittest.TestCase):

    def pressure(self, **over):
        base = dict(messages=10, timestamp_groups=3, cross_actor_groups=2,
                    opportunities_in_period=8, ambiguous_in_period=2,
                    by_horizon={1.0: (6, 2)})
        return cal.TiePressure(**{**base, **over})

    def test_the_cost_is_ambiguous_over_everything_eligible(self):
        self.assertAlmostEqual(self.pressure().cost(1.0), 2 / 8)

    def test_no_eligible_opportunities_means_no_cost_rather_than_zero(self):
        """Ноль возможностей — это отсутствие данных, а не дешёвая политика.
        Отсутствие не становится свидетельством."""
        self.assertIsNone(self.pressure(by_horizon={1.0: (0, 0)}).cost(1.0))

    def test_merging_adds_every_counter(self):
        merged = self.pressure().merged(self.pressure())
        self.assertEqual(merged.messages, 20)
        self.assertEqual(merged.cross_actor_groups, 4)
        self.assertEqual(merged.by_horizon[1.0], (12, 4))
        self.assertAlmostEqual(merged.cost(1.0), 2 / 8)


class ObserveTests(unittest.TestCase):
    """Наблюдение одного person-period на собранном руками потоке."""

    def setUp(self):
        # партнёр шлёт две штуки, участник отвечает через 10 с
        self.stream = [message("1", "them", 0.0), message("2", "them", 5.0),
                       message("3", "me", 15.0),
                       message("4", "them", 100.0), message("5", "me", 130.0)]

    def test_it_finds_the_hand_overs_and_their_shape(self):
        got = cal.observe(self.stream, "me", 0.0, 1000.0, H)
        self.assertEqual(got.values["run_message_count"], [2.0, 1.0])
        self.assertEqual(got.values["run_span_seconds"], [5.0, 0.0])
        self.assertEqual(got.values["run_start_to_reentry_seconds"], [15.0, 30.0])
        self.assertEqual(got.values["reply_speed_seconds"], [10.0, 30.0])

    def test_one_cross_actor_tie_taints_two_opportunities(self):
        """Группа неоднозначности задевает и ту возможность, что отвечает В неё,
        и ту, что открывается ИЗ неё. Одна секунда — две выброшенные
        возможности, и цена `STRICT` поэтому выше, чем доля самих ties."""
        tied = self.stream + [message("6", "them", 130.0)]
        got = cal.observe(tied, "me", 0.0, 1000.0, H)
        self.assertEqual(got.pressure.timestamp_groups, 1)
        self.assertEqual(got.pressure.cross_actor_groups, 1)
        self.assertEqual(got.pressure.opportunities_in_period, 3)
        self.assertEqual(got.pressure.ambiguous_in_period, 2)

    def test_a_same_actor_tie_is_counted_but_harmless(self):
        tied = self.stream + [message("6", "them", 100.0)]
        got = cal.observe(tied, "me", 0.0, 1000.0, H)
        self.assertEqual(got.pressure.timestamp_groups, 1)
        self.assertEqual(got.pressure.cross_actor_groups, 0)
        self.assertEqual(got.pressure.ambiguous_in_period, 0)

    def test_window_scale_quantities_are_one_number_per_period(self):
        got = cal.observe(self.stream, "me", 0.0, 1000.0, H)
        self.assertEqual(got.values["messages_per_person_period"], [5.0])
        self.assertEqual(got.values["opportunities_per_person_period"], [2.0])
        self.assertEqual(got.values["nonresponse_share"], [0.0])

    def test_samples_accumulate_without_losing_anybody(self):
        sample = cal.Sample.empty(H)
        for _ in range(3):
            sample.absorb(cal.observe(self.stream, "me", 0.0, 1000.0, H))
        self.assertEqual(len(sample.values["run_message_count"]), 6)
        self.assertEqual(sample.pressure.messages, 15)


class TotalVariationTests(unittest.TestCase):

    def test_identical_distributions_are_at_zero(self):
        series = [float(h) for h in range(24)] * 3
        self.assertAlmostEqual(cal.total_variation(series, series), 0.0)

    def test_disjoint_distributions_are_at_one(self):
        self.assertAlmostEqual(cal.total_variation([1.0] * 10, [20.0] * 10), 1.0)

    def test_an_empty_side_gives_nothing(self):
        self.assertIsNone(cal.total_variation([], [1.0]))


class ManifestTests(unittest.TestCase):
    """Манифест — то, без чего таблица через месяц держится на вере."""

    def test_the_digest_matches_the_freeze_and_is_deterministic(self):
        """Замок, а не справка: семантика генератора заморожена до S4.

        Сдвинуть отпечаток можно только вместе с документированной поправкой —
        расхождение, класс, что сделано, новый отпечаток. Иначе калибровочный
        корпус за пару кругов становится дрессировочной площадкой.
        """
        self.assertEqual(trace_digest(), manifest.FROZEN_DIGEST)
        self.assertEqual(trace_digest(), trace_digest())
        self.assertIn("S4", manifest.FROZEN_UNTIL)

    def test_changing_the_process_changes_the_digest(self):
        """Отпечаток обязан умирать демонстративно: манифест со старым
        отпечатком объявляет, что числа относились к другому генератору."""
        moved = DyadParameters(latency_log_mean=math.log(900.0))
        self.assertNotEqual(trace_digest(moved), trace_digest())

    def test_it_carries_everything_the_run_is_defined_by(self):
        manifest = RunManifest.build(
            "t", master_seed=7, replicates=3, dyads=10, days=14.0,
            horizon_hours=24.0, paired=True)
        rendered = manifest.render()
        for expected in ("generator digest", "code commit", "master seed",
                         "pairing policy", "parameter grid"):
            self.assertIn(expected, rendered)
        self.assertEqual(manifest.generator_digest, trace_digest())

    def test_a_planted_effect_is_named_in_the_manifest(self):
        null = RunManifest.build("t", master_seed=1, replicates=2, dyads=1, days=1.0,
                                 horizon_hours=24.0, paired=False)
        self.assertIn("none (null)", null.render())
        planted = RunManifest.build("t", master_seed=1, replicates=2, dyads=1, days=1.0,
                                    horizon_hours=24.0, paired=False,
                                    effect=TrueEffect(latency_log_shift=0.4))
        self.assertIn("latency_log_shift", planted.render())

    def test_it_round_trips_to_plain_data(self):
        manifest = RunManifest.build("t", master_seed=1, replicates=2, dyads=1,
                                     days=1.0, horizon_hours=24.0, paired=False,
                                     population=Population())
        as_dict = manifest.as_dict()
        self.assertEqual(as_dict["population"]["base"]["opportunity_rate_per_day"], 6.0)
        self.assertIn("generator_digest", as_dict)


if __name__ == "__main__":
    unittest.main()
