"""Стратегии отбора: одинаковый бюджет, одинаковый счётчик, честный бенчмарк.

Самый важный тест здесь — не про recall. Он про то, что ни один oracle-файл не
принадлежит самому harness'у: иначе spine выигрывает по построению, и таблица
измеряет только нашу способность подкрутить бенчмарк.
"""

import unittest
from pathlib import Path

from spine.budget import ContextBudget, approx_tokens
from spine.compiler import compile_spec_dir
from spine.selector import (
    FILL_BACKFILL,
    FILL_PREFIX,
    STRATEGIES,
    SpineSelector,
    TaskSpec,
)
from spine.subject import subject_worktree

from ._harness import REPO_ROOT, SPEC_DIR, SPINE_ROOT

TASKS_DIR = SPINE_ROOT / "eval" / "tasks"
BUDGETS = (1000, 4000, 8000)
HARNESS_PREFIX = "experiments/semantic-spine"


def load_tasks() -> list[TaskSpec]:
    return [TaskSpec.load(path) for path in sorted(TASKS_DIR.glob("*.json"))]


def subject_for(task: TaskSpec) -> Path:
    """Стратегии читают worktree на base_commit, а не рабочее дерево."""

    return subject_worktree(REPO_ROOT, task.base_commit)


class BenchmarkIntegrity(unittest.TestCase):
    def test_tasks_exist(self) -> None:
        self.assertGreaterEqual(len(load_tasks()), 4)

    def test_no_oracle_file_belongs_to_the_harness(self) -> None:
        for task in load_tasks():
            for path in task.oracle_files:
                with self.subTest(task=task.id, path=path):
                    self.assertFalse(
                        path.startswith(HARNESS_PREFIX),
                        "an oracle file inside the harness rigs the benchmark",
                    )

    def test_every_oracle_file_exists_in_its_subject(self) -> None:
        for task in load_tasks():
            subject = subject_for(task)
            for path in task.oracle_files:
                with self.subTest(task=task.id, path=path):
                    self.assertTrue((subject / path).is_file())

    def test_seeds_are_parseable_references(self) -> None:
        from spine.refs import parse_ref

        for task in load_tasks():
            for seed in task.seeds:
                with self.subTest(task=task.id, seed=seed):
                    parse_ref(seed)


class BudgetFairness(unittest.TestCase):
    def setUp(self) -> None:
        self.compilation = compile_spec_dir(SPEC_DIR)
        self.tasks = load_tasks()

    def test_no_strategy_ever_exceeds_the_budget(self) -> None:
        for budget_tokens in BUDGETS:
            budget = ContextBudget(budget_tokens)
            for name, cls in STRATEGIES.items():
                for task in self.tasks:
                    with self.subTest(strategy=name, budget=budget_tokens, task=task.id):
                        bundle = cls(subject_for(task), self.compilation).select(task, budget)
                        self.assertLessEqual(bundle.tokens, budget_tokens)

    def test_every_strategy_counts_tokens_with_the_same_function(self) -> None:
        budget = ContextBudget(4000)
        task = self.tasks[0]
        subject = subject_for(task)
        for name, cls in STRATEGIES.items():
            with self.subTest(strategy=name):
                bundle = cls(subject, self.compilation).select(task, budget)
                self.assertEqual(
                    bundle.tokens,
                    sum(approx_tokens(chunk.text) for chunk in bundle.chunks),
                )

    def test_prefix_fill_never_beats_backfill_on_tokens_used(self) -> None:
        budget = ContextBudget(4000)
        task = self.tasks[0]
        for name, cls in STRATEGIES.items():
            with self.subTest(strategy=name):
                prefix = cls(subject_for(task), self.compilation, FILL_PREFIX).select(task, budget)
                backfill = cls(subject_for(task), self.compilation, FILL_BACKFILL).select(task, budget)
                self.assertLessEqual(prefix.tokens, backfill.tokens)

    def test_selection_is_deterministic(self) -> None:
        budget = ContextBudget(4000)
        task = self.tasks[0]
        for name, cls in STRATEGIES.items():
            with self.subTest(strategy=name):
                first = cls(subject_for(task), self.compilation).select(task, budget)
                second = cls(subject_for(task), self.compilation).select(task, budget)
                self.assertEqual(first.files(), second.files())
                self.assertEqual(first.render(), second.render())


class SpineBehaviour(unittest.TestCase):
    def setUp(self) -> None:
        self.compilation = compile_spec_dir(SPEC_DIR)
        self.tasks = {task.id: task for task in load_tasks()}

    def _bundle(self, task_id: str, budget_tokens: int = 8000, cls=SpineSelector):
        task = self.tasks[task_id]
        return cls(subject_for(task), self.compilation).select(task, ContextBudget(budget_tokens))

    def test_spine_reaches_production_files_not_only_its_own_spec(self) -> None:
        bundle = self._bundle("confusable-drift")
        outside = [f for f in bundle.files() if not f.startswith(HARNESS_PREFIX)]
        self.assertTrue(outside, "the spine only retrieved its own spec; it proves nothing")

    def test_confusable_neighbour_is_pulled_in_first(self) -> None:
        bundle = self._bundle("confusable-drift")
        origins = [chunk.origin for chunk in bundle.chunks]
        self.assertIn("label:B.VALIDATION", origins)
        self.assertIn("label:B.REPAIR_ATTEMPT", origins)
        self.assertLess(
            origins.index("label:B.REPAIR_ATTEMPT"),
            len(origins),
            "the confusable pair must be adjacent in the bundle, not at the far end",
        )

    def test_rationale_ablation_actually_removes_rationales(self) -> None:
        from spine.selector import SpineNoRationaleSelector

        full = self._bundle("confusable-drift")
        stripped = self._bundle("confusable-drift", cls=SpineNoRationaleSelector)
        self.assertIn("rationale:", full.render())
        self.assertNotIn("rationale:", stripped.render())

    def test_noise_ablation_actually_injects_noise(self) -> None:
        from spine.selector import SpineNoisySelector

        noisy = self._bundle("confusable-drift", cls=SpineNoisySelector)
        self.assertTrue(any(chunk.reason == "injected noise" for chunk in noisy.chunks))

    def test_excerpts_are_excerpts_not_whole_files(self) -> None:
        bundle = self._bundle("naturalness-register-leak")
        gate = "docs/research/dialogue-naturalness-gate.md"
        chunks = [c for c in bundle.chunks if c.path == gate]
        self.assertTrue(chunks, "the spine did not reach the naturalness gate at all")
        whole = (subject_for(self.tasks["naturalness-register-leak"]) / gate).read_text(encoding="utf-8")
        self.assertLess(
            sum(approx_tokens(c.text) for c in chunks),
            approx_tokens(whole) // 4,
            "the spine pulled the whole document; that is retrieval, not a spine",
        )


if __name__ == "__main__":
    unittest.main()


class CorpusIntegrity(unittest.TestCase):
    """Стратегии ищут по production-репозиторию, а не по файлам эксперимента."""

    def test_harness_files_are_not_in_the_searched_corpus(self) -> None:
        from spine.selector import repo_text_files

        # Двойная защита: subject на base_commit harness'а не содержит вовсе,
        # а исключение по префиксу держит инвариант и для будущих коммитов.
        root = REPO_ROOT
        inside = [
            p for p in repo_text_files(root)
            if str(p.relative_to(root)).startswith(HARNESS_PREFIX)
        ]
        self.assertEqual(
            inside,
            [],
            "the harness is searching its own spec; lexical and raw would find the "
            "ontology restated there and score for the wrong reason",
        )

    def test_baselines_never_retrieve_harness_files(self) -> None:
        from spine.selector import DocsSelector, LexicalSelector, RawSelector, SymbolGraphSelector

        compilation = compile_spec_dir(SPEC_DIR)
        task = load_tasks()[0]
        for cls in (RawSelector, DocsSelector, LexicalSelector, SymbolGraphSelector):
            with self.subTest(strategy=cls.name):
                bundle = cls(subject_for(task), compilation).select(task, ContextBudget(8000))
                self.assertFalse(
                    [f for f in bundle.files() if f.startswith(HARNESS_PREFIX)]
                )


class OracleSections(unittest.TestCase):
    """Anchor-level верхняя граница обязана быть и точной, и полной."""

    def setUp(self) -> None:
        from spine.selector import OracleSectionsSelector

        self.cls = OracleSectionsSelector
        self.compilation = compile_spec_dir(SPEC_DIR)

    def test_it_retrieves_every_declared_anchor(self) -> None:
        from spine.targets import covers, locate_all

        for task in load_tasks():
            subject = subject_for(task)
            locations = locate_all(subject, list(task.oracle_targets))
            bundle = self.cls(subject, self.compilation).select(task, ContextBudget(16000))
            for location in locations:
                with self.subTest(task=task.id, target=location.target.raw):
                    self.assertTrue(
                        any(covers(location, c.path, c.text) for c in bundle.chunks)
                    )

    def test_it_is_an_excerpt_strategy_not_a_whole_file_one(self) -> None:
        task = next(t for t in load_tasks() if t.id == "naturalness-register-leak")
        subject = subject_for(task)
        bundle = self.cls(subject, self.compilation).select(task, ContextBudget(16000))
        whole = sum(
            approx_tokens((subject / f).read_text(encoding="utf-8")) for f in task.oracle_files
        )
        self.assertLess(bundle.tokens, whole // 2)
