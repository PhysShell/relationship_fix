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
