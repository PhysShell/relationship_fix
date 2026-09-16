"""Утверждения, которые делает README, проверяются как тесты.

Числа в таблицах — снимок против конкретного коммита, и они поедут, как только
репозиторий подрастёт: raw, docs и lexical читают его целиком. Поэтому в CI
защищаются не цифры, а ВЫВОДЫ. Если репозиторий изменился настолько, что вывод
перестал держаться, README врёт — и узнать об этом должен тест, а не читатель.
"""

import unittest

from spine.budget import ContextBudget
from spine.compiler import compile_spec_dir
from spine.selector import STRATEGIES, TaskSpec

from ._harness import REPO_ROOT, SPEC_DIR, SPINE_ROOT


def mean_recall(strategy: str, budget_tokens: int) -> float:
    compilation = compile_spec_dir(SPEC_DIR)
    budget = ContextBudget(budget_tokens)
    tasks = [TaskSpec.load(p) for p in sorted((SPINE_ROOT / "eval/tasks").glob("*.json"))]
    total = 0.0
    for task in tasks:
        bundle = STRATEGIES[strategy](REPO_ROOT, compilation).select(task, budget)
        selected = set(bundle.files())
        hit = sum(1 for path in task.oracle_files if path in selected)
        total += hit / len(task.oracle_files)
    return total / len(tasks)


class ReadmeClaims(unittest.TestCase):
    BUDGET = 8000

    def setUp(self) -> None:
        self.recall = {name: mean_recall(name, self.BUDGET) for name in STRATEGIES}

    def test_spine_beats_every_non_oracle_baseline(self) -> None:
        for baseline in ("raw", "docs", "lexical", "symbol-graph"):
            with self.subTest(baseline=baseline):
                self.assertGreater(self.recall["semantic-spine"], self.recall[baseline])

    def test_spine_beats_the_whole_file_oracle_on_recall(self) -> None:
        # Заявленная причина — гранулярность, а не семантика: oracle читает
        # файлы целиком и не помещается в бюджет. Вывод держится, пока держится
        # и эта причина.
        self.assertGreater(self.recall["semantic-spine"], self.recall["oracle"])

    def test_typed_edges_actually_bind(self) -> None:
        self.assertGreater(
            self.recall["semantic-spine"],
            self.recall["semantic-spine/-typed-edges"],
            "typed edge ordering bought nothing; the README claim about typed edges is false",
        )

    def test_injected_noise_never_helps(self) -> None:
        self.assertLessEqual(
            self.recall["semantic-spine/+irrelevant-docs"], self.recall["semantic-spine"]
        )

    def test_rationale_does_not_improve_retrieval(self) -> None:
        # Честный отрицательный результат: rationale стоит бюджета и для ПОИСКА
        # не даёт ничего. Помогает ли он агенту ПОНЯТЬ — вопрос Phase 3, на
        # который эта метрика ответить не может.
        self.assertGreaterEqual(
            self.recall["semantic-spine/-rationale"], self.recall["semantic-spine"]
        )


if __name__ == "__main__":
    unittest.main()
