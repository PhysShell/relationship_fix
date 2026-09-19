"""Мост между формальной моделью (Lean) и рабочим кодом (Python).

Lean доказывает теоремы о МОДЕЛИ. Эти тесты проверяют, что рабочий код —
та же самая модель, а не похожая. Без них «доказано в Lean» означало бы
ровно столько же, сколько «доказано на салфетке рядом с кодом».

Два утверждения моста, и оба нужны:

    1. `to_bins` при делящихся разрешениях действительно СКЛЕИВАЕТ ПОДРЯД
       ИДУЩИЕ корзины — именно это `coarsen` в Lean и называет огрублением;

    2. число возможностей в рабочем коде совпадает с `opps` из Lean-модели
       на тех же последовательностях актёров.

Формальная сторона живёт в `formal/`, статус каждого утверждения — в
`docs/formal-model.md`.
"""

import random
import unittest

from coarsening.bounded import Bin, to_bins
from coarsening.paired import Stream, opportunities, order

#: Ровно определение из `RelationshipFix/Opportunities.lean`, переписанное на
#: Python БЕЗ подглядывания в `find_opportunities`: возможность открывается на
#: первом сообщении партнёрской серии.
def opps_as_in_lean(actors, participant) -> int:
    total = 0
    previous = None
    for actor in actors:
        if actor != participant and previous != _PARTNER_MARK:
            total += 1
        previous = _PARTNER_MARK if actor != participant else _SELF_MARK
    return total


_PARTNER_MARK, _SELF_MARK = object(), object()


def random_stream(rng: random.Random, size: int) -> Stream:
    stamps = sorted(float(rng.randrange(0, 40 * size)) for _ in range(size))
    actors = [rng.randrange(2) for _ in range(size)]
    keys = [f"{rng.randrange(10 ** 9):09d}" for _ in range(size)]
    return order(stamps, actors, keys)


def as_multiset(bucket: Bin) -> tuple[int, int]:
    return bucket.partner, bucket.participant


class CoarseningIsAConsecutiveMergeTests(unittest.TestCase):
    """Мост к `coarsen` из `RelationshipFix/Coarsening.lean`.

    Lean определяет огрубление абстрактно — как склейку подряд идущих корзин,
    и доказывает монотонность именно для него. Арифметическая часть («грубый
    ключ есть функция от мелкого») тоже доказана, а вот то, что `to_bins`
    реализует ровно эту склейку, — утверждение о РЕАЛИЗАЦИИ, и его место
    здесь.
    """

    def _check(self, stream: Stream, fine: float, coarse: float):
        fine_bins = to_bins(stream, 0, delta=fine)
        coarse_bins = to_bins(stream, 0, delta=coarse)
        merged, index = [], 0
        for bucket in coarse_bins:
            partner = participant = 0
            taken = 0
            while index < len(fine_bins) and \
                    fine_bins[index].start < bucket.start + coarse:
                partner += fine_bins[index].partner
                participant += fine_bins[index].participant
                index += 1
                taken += 1
            self.assertGreater(taken, 0, "грубая корзина без мелких")
            merged.append((partner, participant))
        self.assertEqual(index, len(fine_bins), "мелкие корзины остались лишними")
        self.assertEqual(merged, [as_multiset(b) for b in coarse_bins])

    def test_minute_bins_are_merged_second_bins(self):
        rng = random.Random(20260919)
        for _ in range(200):
            self._check(random_stream(rng, rng.randint(1, 40)), 1.0, 60.0)

    def test_it_holds_for_other_dividing_resolutions(self):
        rng = random.Random(7)
        for fine, coarse in ((1.0, 5.0), (5.0, 60.0), (2.0, 60.0), (1.0, 3600.0)):
            for _ in range(40):
                self._check(random_stream(rng, rng.randint(1, 40)), fine, coarse)


class OpportunityDefinitionsAgreeTests(unittest.TestCase):
    """Мост к `opps` из `RelationshipFix/Opportunities.lean`.

    Рабочая функция доказанно совпадает с замороженным движком
    (`tests/test_coarsening.py`), а здесь — что она же совпадает с тем
    определением, о котором доказываются теоремы. Иначе теоремы были бы про
    чужую величину.
    """

    def test_the_counts_coincide_on_random_streams(self):
        rng = random.Random(4242)
        checked = 0
        for _ in range(400):
            stream = random_stream(rng, rng.randint(1, 50))
            for participant in stream.actor_ids:
                mine = len(opportunities(stream, participant))
                theirs = opps_as_in_lean(stream.actors, participant)
                self.assertEqual(mine, theirs, list(stream.actors))
                checked += mine
        self.assertGreater(checked, 2000, "тест не дошёл до реальных случаев")

    def test_a_partner_run_is_one_opportunity_not_three(self):
        """То самое место, где определение легко испортить."""
        self.assertEqual(opps_as_in_lean([1, 0, 0, 0, 1, 0], 1), 2)
        self.assertEqual(opps_as_in_lean([0, 0, 0], 1), 1)
        self.assertEqual(opps_as_in_lean([1, 1, 1], 1), 0)
        self.assertEqual(opps_as_in_lean([], 1), 0)
