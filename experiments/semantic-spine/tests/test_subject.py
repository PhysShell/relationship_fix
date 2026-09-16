"""Subject worktree и anchor-level цели.

`base_commit` обязан управлять тем, что читают стратегии. Пока он лежал в
манифесте и никем не читался, слово «воспроизводимо» было незаслуженным.
"""

import json
import tempfile
import unittest
from pathlib import Path

from spine.selector import TaskSpec
from spine.subject import SubjectUnavailable, resolve_commit, subject_worktree
from spine.targets import TargetUnresolvable, covers, locate, locate_all, parse_target

from ._harness import REPO_ROOT, SPINE_ROOT

TASKS = sorted((SPINE_ROOT / "eval/tasks").glob("*.json"))


def tasks() -> list[TaskSpec]:
    return [TaskSpec.load(path) for path in TASKS]


class PinnedSubject(unittest.TestCase):
    def test_every_task_declares_a_resolvable_base_commit(self) -> None:
        for task in tasks():
            with self.subTest(task=task.id):
                self.assertEqual(len(resolve_commit(REPO_ROOT, task.base_commit)), 40)

    def test_a_manifest_without_base_commit_is_refused(self) -> None:
        payload = json.loads(TASKS[0].read_text(encoding="utf-8"))
        payload.pop("base_commit")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                TaskSpec.load(path)

    def test_unknown_commit_fails_instead_of_falling_back(self) -> None:
        with self.assertRaises(SubjectUnavailable):
            subject_worktree(REPO_ROOT, "0" * 40)

    def test_worktree_is_at_the_declared_commit(self) -> None:
        task = tasks()[0]
        subject = subject_worktree(REPO_ROOT, task.base_commit)
        head = (subject / ".git").read_text(encoding="utf-8") if (subject / ".git").is_file() else ""
        self.assertTrue(subject.is_dir())
        self.assertTrue(head.startswith("gitdir:"))
        self.assertTrue((subject / "data/ontology/behavior-v0.1.json").is_file())

    def test_subject_predates_the_harness(self) -> None:
        """Лучшая защита от self-contamination — subject, в котором harness'а нет."""

        for task in tasks():
            with self.subTest(task=task.id):
                subject = subject_worktree(REPO_ROOT, task.base_commit)
                self.assertFalse((subject / "experiments/semantic-spine").exists())

    def test_the_same_commit_is_reused_not_recreated(self) -> None:
        task = tasks()[0]
        first = subject_worktree(REPO_ROOT, task.base_commit)
        second = subject_worktree(REPO_ROOT, task.base_commit)
        self.assertEqual(first, second)


class AnchorTargets(unittest.TestCase):
    def test_every_declared_target_resolves_in_its_subject(self) -> None:
        for task in tasks():
            subject = subject_worktree(REPO_ROOT, task.base_commit)
            self.assertTrue(task.oracle_targets, f"{task.id} declares no oracle_targets")
            for raw in task.oracle_targets:
                with self.subTest(task=task.id, target=raw):
                    locate(subject, parse_target(raw))

    def test_every_target_file_is_also_an_oracle_file(self) -> None:
        for task in tasks():
            for raw in task.oracle_targets:
                with self.subTest(task=task.id, target=raw):
                    self.assertIn(parse_target(raw).path, task.oracle_files)

    def test_malformed_targets_are_refused(self) -> None:
        for raw in ["no-anchor.md", "#only-anchor", "", "../escape.md#x", "x.md#"]:
            with self.subTest(target=raw):
                with self.assertRaises(TargetUnresolvable):
                    parse_target(raw)

    def test_json_anchor_matches_the_defining_line_not_a_mention(self) -> None:
        """`"id": "B.VALIDATION"` — определение; упоминание в confusable_with — нет."""

        task = next(t for t in tasks() if t.id == "confusable-drift")
        subject = subject_worktree(REPO_ROOT, task.base_commit)
        location = locate(subject, parse_target("data/ontology/behavior-v0.1.json#B.VALIDATION"))
        self.assertIn('"id"', location.line_text)

    def test_coverage_needs_the_definition_line_not_just_the_file(self) -> None:
        task = next(t for t in tasks() if t.id == "confusable-drift")
        subject = subject_worktree(REPO_ROOT, task.base_commit)
        location = locate_all(subject, ["data/ontology/behavior-v0.1.json#B.VALIDATION"])[0]
        self.assertTrue(covers(location, location.target.path, location.line_text))
        self.assertFalse(covers(location, location.target.path, "some unrelated text"))
        self.assertFalse(covers(location, "another/file.json", location.line_text))


if __name__ == "__main__":
    unittest.main()
