"""Метрики прогона считаются от записанной траектории — их можно проверить
без агента. А ненастроенный адаптер обязан падать, а не отчитываться."""

import unittest
from pathlib import Path

from spine.budget import ContextBudget
from spine.compiler import compile_spec_dir
from spine.selector import SpineSelector, TaskSpec
from spine.subject import subject_worktree

from ._harness import REPO_ROOT, SPEC_DIR, SPINE_ROOT

import sys

sys.path.insert(0, str(SPINE_ROOT / "eval"))
from runner import (  # noqa: E402
    AgentNotConfigured,
    Trajectory,
    UnconfiguredAdapter,
    compute_metrics,
)


class Metrics(unittest.TestCase):
    def setUp(self) -> None:
        self.task = TaskSpec.load(SPINE_ROOT / "eval/tasks/confusable-drift.json")
        subject = subject_worktree(REPO_ROOT, self.task.base_commit)
        self.bundle = SpineSelector(subject, compile_spec_dir(SPEC_DIR)).select(
            self.task, ContextBudget(8000)
        )

    def test_edit_precision_counts_only_oracle_files(self) -> None:
        trajectory = Trajectory(
            files_touched=("data/ontology/behavior-v0.1.json", "README.md"),
            tests_ran=True,
            tests_passed=True,
        )
        metrics = compute_metrics(self.task, self.bundle, trajectory)
        self.assertEqual(metrics.files_touched, 2)
        self.assertEqual(metrics.unexpected_files_touched, 1)
        self.assertEqual(metrics.edit_precision, 0.5)

    def test_repeated_edits_to_one_file_count_once(self) -> None:
        trajectory = Trajectory(
            files_touched=("README.md", "README.md"), tests_ran=True, tests_passed=True
        )
        self.assertEqual(compute_metrics(self.task, self.bundle, trajectory).files_touched, 1)

    def test_passing_tests_that_never_ran_is_not_resolved(self) -> None:
        trajectory = Trajectory(tests_ran=False, tests_passed=True)
        self.assertFalse(compute_metrics(self.task, self.bundle, trajectory).resolved)

    def test_resolved_requires_both_ran_and_passed(self) -> None:
        self.assertTrue(
            compute_metrics(
                self.task, self.bundle, Trajectory(tests_ran=True, tests_passed=True)
            ).resolved
        )
        self.assertFalse(
            compute_metrics(
                self.task, self.bundle, Trajectory(tests_ran=True, tests_passed=False)
            ).resolved
        )

    def test_empty_trajectory_has_zero_precision_not_a_crash(self) -> None:
        metrics = compute_metrics(self.task, self.bundle, Trajectory())
        self.assertEqual(metrics.edit_precision, 0.0)
        self.assertEqual(metrics.files_touched, 0)


class NoSilentZeroes(unittest.TestCase):
    def test_unconfigured_adapter_refuses_to_report(self) -> None:
        task = TaskSpec.load(SPINE_ROOT / "eval/tasks/confusable-drift.json")
        subject = subject_worktree(REPO_ROOT, task.base_commit)
        bundle = SpineSelector(subject, compile_spec_dir(SPEC_DIR)).select(task, ContextBudget(1000))
        with self.assertRaises(AgentNotConfigured):
            UnconfiguredAdapter().run(task, bundle, Path("/nonexistent"))

    def test_no_task_claims_authored_acceptance_tests_yet(self) -> None:
        import json

        for path in sorted((SPINE_ROOT / "eval/tasks").glob("*.json")):
            with self.subTest(task=path.stem):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    payload["acceptance"]["status"],
                    "not_authored",
                    "a task claims acceptance tests exist; wire them into the runner or "
                    "set the status back",
                )


if __name__ == "__main__":
    unittest.main()
