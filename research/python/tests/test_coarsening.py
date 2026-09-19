"""Быстрая реализация обязана ПОБУКВЕННО совпадать с замороженным движком.

Заморозка запрещает менять движок, а не считать быстрее рядом. Но «рядом» без
доказательства равенства — это ровно тот класс бага, который проект и ловит:
быстрый путь, который чуть-чуть другой. Поэтому здесь property-тест на
случайных потоках с намеренно частыми совпадениями меток.
"""

import random
import unittest

from coarsening import prereg
from coarsening.paired import (
    Stream, ambiguous_stamps, apply_operator, local_density, opportunities,
    order, pair, run_index,
)
from extractor.extract import ambiguous_timestamps, find_opportunities
from extractor.model import NormalizedMessage


def frozen_stream(stream: Stream) -> list[NormalizedMessage]:
    rows = [NormalizedMessage(key, str(actor), stamp, 0, ())
            for stamp, actor, key in
            zip(stream.stamps, stream.actors, stream.keys)]
    rows.sort(key=lambda m: m.sort_key)
    return rows


def random_stream(rng: random.Random, size: int) -> Stream:
    """Метки НАМЕРЕННО грубые: без совпадений тест ничего бы не проверял."""
    resolution = rng.choice((1.0, 5.0, 60.0))
    stamps = sorted(rng.randrange(0, max(2, size)) * resolution for _ in range(size))
    actors = [rng.randrange(2) for _ in range(size)]
    keys = [f"{rng.randrange(10 ** 9):09d}" for _ in range(size)]
    return order(stamps, actors, keys)


class EquivalenceTests(unittest.TestCase):

    def test_ambiguity_matches_the_frozen_engine(self):
        rng = random.Random(20260919)
        for _ in range(200):
            stream = random_stream(rng, rng.randrange(2, 60))
            self.assertEqual(ambiguous_stamps(stream),
                             ambiguous_timestamps(frozen_stream(stream)))

    def test_opportunities_match_the_frozen_engine(self):
        """Тот самый срез `stream[end + 1:]` ищет то, что лежит на end + 1."""
        rng = random.Random(4242)
        checked = 0
        for _ in range(300):
            stream = random_stream(rng, rng.randrange(2, 80))
            rows = frozen_stream(stream)
            for actor in stream.actor_ids:
                mine = opportunities(stream, actor)
                theirs = find_opportunities(rows, str(actor))
                self.assertEqual(len(mine), len(theirs))
                for a, b in zip(mine, theirs):
                    self.assertEqual(a.opened_at, b.opened_at)
                    self.assertEqual(a.run_end_at, b.run_end_at)
                    self.assertEqual(a.reply_at, b.reply_at)
                    self.assertEqual(a.ambiguous, b.ambiguous_order)
                checked += len(mine)
        self.assertGreater(checked, 2000, "тест не дошёл до реальных случаев")


class OperatorTests(unittest.TestCase):

    def test_the_operator_only_moves_time_backwards_and_by_less_than_delta(self):
        rng = random.Random(7)
        for _ in range(2000):
            t = rng.uniform(-10_000, 10_000)
            phase = rng.choice(prereg.PHASE_GRID_SECONDS)
            c = prereg.coarsen(t, 60.0, phase)
            self.assertLessEqual(c, t)
            self.assertLess(t - c, 60.0)

    def test_the_operator_is_idempotent_on_its_own_grid(self):
        for t in (0.0, 1.5, 59.999, 60.0, -0.5):
            once = prereg.coarsen(t, 60.0)
            self.assertEqual(prereg.coarsen(once, 60.0), once)

    def test_coarsening_never_loses_or_invents_a_message(self):
        rng = random.Random(11)
        for _ in range(100):
            stream = random_stream(rng, rng.randrange(1, 50))
            coarse = apply_operator(stream, 60.0)
            self.assertEqual(len(coarse), len(stream))
            self.assertEqual(sorted(coarse.keys), sorted(stream.keys))

    def test_ambiguity_can_only_grow_under_coarsening(self):
        """Две метки, слившись, не расходятся обратно. Инвариант, не надежда."""
        rng = random.Random(13)
        for _ in range(200):
            stream = random_stream(rng, rng.randrange(2, 60))
            coarse = apply_operator(stream, 60.0)
            bad = ambiguous_stamps(coarse)
            for stamp in ambiguous_stamps(stream):
                self.assertIn(prereg.coarsen(stamp, 60.0), bad)

    def test_coarsening_can_INCREASE_the_number_of_runs(self):
        """Интуиция «огрубление только склеивает» неверна, и это надо знать.

        Наблюдатель A внутри корзины порядка не знает, поэтому произвольный
        tie-break способен ПЕРЕМЕШАТЬ актёров и выдумать передачи хода,
        которых в опорном потоке не было. Поэтому знак разности серий
        сообщается как есть и не выдаётся за «слияние».
        """
        stream = order([0.0, 1.0, 2.0, 3.0], [0, 0, 1, 1], ["b", "d", "a", "c"])
        self.assertEqual(max(run_index(stream)) + 1, 2)
        coarse = apply_operator(stream, 60.0)
        self.assertGreater(max(run_index(coarse)) + 1, 2)


class PreregDisciplineTests(unittest.TestCase):

    def test_the_forbidden_predictor_is_not_computed(self):
        """`messages_per_day` протащил бы отказанный Q1a через заднюю дверь."""
        rng = random.Random(3)
        stream = random_stream(rng, 50)
        computed = set(local_density(stream))
        self.assertEqual(computed & set(prereg.FORBIDDEN_PREDICTORS), set())
        self.assertIn(prereg.PRIMARY_PREDICTOR, computed)

    def test_every_predictor_is_window_free(self):
        """Ни один предиктор не должен требовать полного окна наблюдения."""
        rng = random.Random(5)
        short = random_stream(rng, 40)
        half = Stream(short.stamps[:20], short.actors[:20], short.keys[:20])
        # усечение окна меняет ЗНАЧЕНИЕ, но не делает величину невычислимой —
        # в отличие от messages_per_day, которому нужны границы окна
        self.assertEqual(set(local_density(short)), set(local_density(half)))

    def test_the_primary_phase_is_on_the_declared_grid(self):
        self.assertIn(prereg.PRIMARY_PHASE_SECONDS, prereg.PHASE_GRID_SECONDS)

    def test_the_reference_is_not_called_ground_truth(self):
        self.assertTrue(prereg.REFERENCE_IS_NOT_GROUND_TRUTH)
        self.assertEqual(prereg.REFERENCE_TERM, "reference resolution")

    def test_the_poisson_null_is_forbidden_by_name(self):
        self.assertEqual(prereg.POISSON_NULL, "FORBIDDEN")
        self.assertTrue(prereg.NO_NULL_MODEL_NEEDED)

    def test_stage_two_triggers_are_numbers_declared_in_advance(self):
        self.assertEqual(sorted(prereg.STAGE_TWO_TRIGGERS), [
            "density_quartile_gap_pp", "median_added_strict_loss_pp",
            "tie_break_spread_pp"])
        for value in prereg.STAGE_TWO_TRIGGERS.values():
            self.assertIsInstance(value, float)

    def test_rmtr_is_the_only_outcome_that_needs_a_window(self):
        needs = [o.key for o in prereg.OUTCOMES if not o.window_free]
        self.assertEqual(needs, ["rmtr_seconds"])

    def test_the_primary_outcome_is_declared_and_real(self):
        self.assertIn(prereg.PRIMARY_OUTCOME, {o.key for o in prereg.OUTCOMES})


class PairedTests(unittest.TestCase):

    def test_both_arms_share_one_window(self):
        """Иначе часть разницы была бы разницей окон, а не разницей часов."""
        self.assertTrue(prereg.SHARED_WINDOW)
        rng = random.Random(17)
        result = pair("d", random_stream(rng, 60))
        for hours, _, _ in result.reference.rmtr_by_horizon:
            self.assertIn(hours, prereg.HORIZONS_HOURS)

    def test_the_paired_arms_carry_identical_messages(self):
        rng = random.Random(19)
        stream = random_stream(rng, 80)
        result = pair("d", stream)
        self.assertEqual(result.reference.messages, result.observed.messages)

    def test_added_loss_is_measured_against_a_nonzero_baseline(self):
        """Опорная рука тоже неоднозначна. Вычитать её обязательно."""
        stream = order([0.0, 0.0, 10.0], [0, 1, 0], ["a", "b", "c"])
        result = pair("d", stream)
        self.assertGreater(result.reference.strict_loss_share, 0.0)
        self.assertEqual(
            result.added_strict_loss,
            result.observed.strict_loss_share - result.reference.strict_loss_share)
