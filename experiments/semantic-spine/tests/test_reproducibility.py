"""Зафиксированные результаты обязаны пересчитываться побайтно.

До Phase 2.5 это было невозможно в принципе: стратегии читали рабочее дерево,
поэтому любой новый файл в основном репозитории двигал числа. Теперь subject
приколочен к `base_commit`, и снимок в eval/results/ обязан совпадать.

Если этот тест покраснел — либо изменился harness (тогда обновите снимок и
объясните, почему числа поехали), либо кто-то правил результаты руками.
"""

import json
import sys
import unittest
from pathlib import Path

from ._harness import SPINE_ROOT

sys.path.insert(0, str(SPINE_ROOT / "eval"))
from score import aggregate, score  # noqa: E402

FROZEN_BUDGET = 8000


class FrozenResults(unittest.TestCase):
    def setUp(self) -> None:
        path = SPINE_ROOT / "eval/results" / f"selection-{FROZEN_BUDGET}.json"
        self.committed = json.loads(path.read_text(encoding="utf-8"))
        self.rows, self.subjects = score(FROZEN_BUDGET)

    def test_summary_reproduces_exactly(self) -> None:
        self.assertEqual(aggregate(self.rows), self.committed["summary"])

    def test_subject_commits_are_the_committed_ones(self) -> None:
        self.assertEqual(self.subjects, self.committed["subject_commits"])

    def test_scoring_twice_gives_the_same_numbers(self) -> None:
        again, _ = score(FROZEN_BUDGET)
        self.assertEqual(aggregate(self.rows), aggregate(again))

    def test_results_declare_the_second_generation_schema(self) -> None:
        # v1 не знал ни pinned subject, ни anchor-level метрик; смешивать
        # снимки двух поколений в одной папке нельзя.
        for path in sorted((SPINE_ROOT / "eval/results").glob("*.json")):
            with self.subTest(result=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["schema_version"], "rf.spine-selection-result.v2")
                self.assertIn("subject_commits", payload)


if __name__ == "__main__":
    unittest.main()


class ExactArithmetic(unittest.TestCase):
    """Агрегаты не имеют права зависеть от порядка и от версии Python.

    Исходный дефект: round() поверх уже округлённых float'ов. CPython 3.12
    добавил компенсированное суммирование в sum() для float'ов, поэтому 3.11 и
    3.13 расходились в четвёртом знаке на значениях у десятичной границы
    (5/6 -> 0.83335). CI краснел, локально было зелено, и «побайтная
    воспроизводимость» держалась на том, с какой стороны границы легло
    двоичное представление.
    """

    def setUp(self) -> None:
        self.rows, _ = score(FROZEN_BUDGET)

    def test_aggregate_is_independent_of_row_order(self) -> None:
        import random

        baseline = aggregate(self.rows)
        for seed in (1, 7, 42):
            with self.subTest(seed=seed):
                shuffled = list(self.rows)
                random.Random(seed).shuffle(shuffled)
                self.assertEqual(
                    {item["strategy"]: item for item in aggregate(shuffled)},
                    {item["strategy"]: item for item in baseline},
                )

    def test_means_come_from_exact_ratios(self) -> None:
        from fractions import Fraction

        from score import quantize, ratio

        # 5/6 лежит ровно на границе четвёртого знака; float-путь давал 0.8333
        # или 0.8334 в зависимости от платформы, точный путь — всегда одно.
        self.assertEqual(quantize(Fraction(5, 6)), 0.8333)
        self.assertEqual(quantize(Fraction(1, 2)), 0.5)
        self.assertEqual(quantize(ratio(0, 0)), 0.0)
        # HALF_UP, а не банковское округление: 0.00005 -> 0.0001, всегда.
        self.assertEqual(quantize(Fraction(1, 20000)), 0.0001)

    def test_no_summary_value_sits_on_a_rounding_tie(self) -> None:
        """Диагностика: если значение точно на границе, ищите его в снимке."""

        from decimal import Decimal
        from fractions import Fraction

        for item in aggregate(self.rows):
            for key, value in item.items():
                if not key.startswith("mean_") or key == "mean_context_tokens":
                    continue
                with self.subTest(strategy=item["strategy"], metric=key):
                    scaled = Decimal(str(value)) * 10000
                    self.assertEqual(scaled, scaled.to_integral_value())
