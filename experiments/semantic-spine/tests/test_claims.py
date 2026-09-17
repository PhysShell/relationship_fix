"""Утверждения, которые делает README, проверяются как тесты.

Прогон идёт против worktree на `base_commit`, как и eval/score.py: тест,
который мерит рабочее дерево, охраняет не тот эксперимент.

Здесь же зафиксирован главный отрицательный результат Phase 2.5: на уровне
файлов spine ведёт, на уровне якорей — проигрывает whole-file oracle'у.
Инверсия заявлена в README и обязана падать, если перестанет держаться.
"""

import unittest
from functools import lru_cache

from spine.budget import ContextBudget
from spine.compiler import compile_spec_dir
from spine.selector import STRATEGIES, TaskSpec
from spine.subject import subject_worktree
from spine.targets import covers, locate_all

from ._harness import REPO_ROOT, SPEC_DIR, SPINE_ROOT

import sys

sys.path.insert(0, str(SPINE_ROOT))
from eval.protocol import version as protocol_version  # noqa: E402

BUDGET = 8000


@lru_cache(maxsize=1)
def measure() -> dict[str, dict[str, float]]:
    compilation = compile_spec_dir(SPEC_DIR)
    budget = ContextBudget(BUDGET)
    tasks = [TaskSpec.load(p) for p in sorted((SPINE_ROOT / "eval/tasks").glob("*.json"))]

    totals = {name: {"file": 0.0, "target": 0.0} for name in STRATEGIES}
    for task in tasks:
        subject = subject_worktree(REPO_ROOT, task.base_commit)
        locations = locate_all(subject, list(task.oracle_targets))
        for name, cls in STRATEGIES.items():
            bundle = cls(subject, compilation).select(task, budget)
            selected = set(bundle.files())
            totals[name]["file"] += sum(
                1 for path in task.oracle_files if path in selected
            ) / len(task.oracle_files)
            totals[name]["target"] += sum(
                1
                for location in locations
                if any(covers(location, c.path, c.text) for c in bundle.chunks)
            ) / len(locations)
    return {
        name: {key: value / len(tasks) for key, value in scores.items()}
        for name, scores in totals.items()
    }


class ReadmeClaims(unittest.TestCase):
    def setUp(self) -> None:
        self.score = measure()

    def test_spine_beats_every_retrieval_baseline_on_targets(self) -> None:
        for baseline in ("raw", "docs", "lexical", "bm25", "symbol-graph"):
            with self.subTest(baseline=baseline):
                self.assertGreater(
                    self.score["semantic-spine"]["target"], self.score[baseline]["target"]
                )

    def test_bm25_is_the_stronger_sparse_baseline(self) -> None:
        # Обгонять tf-idf несложно. Если бы BM25 обгонял spine, заявлять
        # преимущество над retrieval'ом было бы нельзя.
        self.assertGreater(self.score["bm25"]["target"], self.score["lexical"]["target"])

    def test_oracle_sections_is_the_upper_bound(self) -> None:
        for name in STRATEGIES:
            if name == "oracle-sections":
                continue
            with self.subTest(strategy=name):
                self.assertGreaterEqual(
                    self.score["oracle-sections"]["target"], self.score[name]["target"]
                )

    def test_spine_loses_to_whole_file_oracle_on_targets(self) -> None:
        """Инверсия v1: файл находит лучше, нужное место — хуже.

        Свойство ИМЕННО протокола v1, а не вечная истина. В v2 рендеринг
        `materialized_in` чинится легально, и тогда этот тест АРХИВИРУЕТСЯ
        вместе с протоколом, а не правится до зелёного: иначе CI станет
        требовать сохранять известный retrieval-баг на том основании, что
        когда-то мы честно доказали его существование. Машины тоже умеют
        цепляться за прошлое.

        Постоянная запись отрицательного результата — побайтно замороженные
        снимки в eval/results/ и eval/protocol.json, а не этот тест.
        """

        if protocol_version() != 1:
            self.skipTest(
                "archived with selection protocol v1; the permanent record is "
                "eval/results/selection-8000.json and eval/protocol.json"
            )

        self.assertGreater(
            self.score["semantic-spine"]["file"], self.score["oracle"]["file"]
        )
        self.assertLess(
            self.score["semantic-spine"]["target"], self.score["oracle"]["target"]
        )

    def test_typed_edges_actually_bind(self) -> None:
        self.assertGreater(
            self.score["semantic-spine"]["target"],
            self.score["semantic-spine/-typed-edges"]["target"],
        )

    def test_injected_noise_never_helps(self) -> None:
        self.assertLessEqual(
            self.score["semantic-spine/+irrelevant-docs"]["target"],
            self.score["semantic-spine"]["target"],
        )

    def test_rationale_does_not_improve_retrieval(self) -> None:
        self.assertGreaterEqual(
            self.score["semantic-spine/-rationale"]["target"],
            self.score["semantic-spine"]["target"],
        )


if __name__ == "__main__":
    unittest.main()
