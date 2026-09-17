"""Заморозка протокола проверяется, а не обещается.

Если правка двигает `surface_digest`, значит она трогает задачи, якоря, граф
или порядок связей — то есть ровно то, что после просмотра результатов трогать
нельзя. Тест не запрещает такую правку; он требует поднять версию протокола и
признать, что это уже другой эксперимент.
"""

import json
import sys
import unittest

from ._harness import SPINE_ROOT

sys.path.insert(0, str(SPINE_ROOT))
from eval.protocol import load, surface_digest, version  # noqa: E402


class FrozenSurface(unittest.TestCase):
    def setUp(self) -> None:
        self.protocol = load()

    def test_surface_digest_still_matches(self) -> None:
        self.assertEqual(
            surface_digest(),
            self.protocol["surface_digest"],
            "the protocol surface moved (tasks, anchors, spec graph or relation order). "
            "That is a different experiment: bump protocol_version instead of "
            "re-freezing the digest in place.",
        )

    def test_protocol_is_v1_and_immutable(self) -> None:
        self.assertEqual(version(), 1)
        self.assertEqual(self.protocol["status"], "immutable")

    def test_v0_and_the_freeze_are_different_commits(self) -> None:
        """88f6dfb — harness v0; anchor-level ground truth появился в 2ef1e5c.

        Через четыре месяца придётся доказывать, выбирались ли якоря до или
        после просмотра результатов. Пусть на это отвечает файл, а не память.
        """

        self.assertNotEqual(
            self.protocol["harness_v0_commit"], self.protocol["frozen_at_commit"]
        )
        for key in ("harness_v0_commit", "frozen_at_commit"):
            with self.subTest(key=key):
                self.assertEqual(len(self.protocol[key]), 40)

    def test_recorded_result_matches_the_frozen_snapshot(self) -> None:
        snapshot = json.loads(
            (SPINE_ROOT / "eval/results/selection-8000.json").read_text(encoding="utf-8")
        )
        summary = {row["strategy"]: row for row in snapshot["summary"]}
        for strategy, recorded in self.protocol["recorded_result"].items():
            if strategy == "budget_tokens":
                continue
            with self.subTest(strategy=strategy):
                self.assertEqual(recorded["target_recall"], summary[strategy]["mean_target_recall"])
                self.assertEqual(recorded["file_recall"], summary[strategy]["mean_file_recall"])

    def test_the_negative_result_is_recorded_as_a_v1_property(self) -> None:
        self.assertIn(
            "spine_loses_to_whole_file_oracle_on_targets", self.protocol["properties"]
        )

    def test_subject_commits_agree_with_the_task_manifests(self) -> None:
        from spine.selector import TaskSpec

        declared = {
            TaskSpec.load(path).id: TaskSpec.load(path).base_commit
            for path in sorted((SPINE_ROOT / "eval/tasks").glob("*.json"))
        }
        self.assertEqual(declared, self.protocol["subject_commits"])


if __name__ == "__main__":
    unittest.main()


class BlindBarrier(unittest.TestCase):
    """Порядок Phase 3 обязан быть соблюдаем, а не только описан.

    Правило: сначала чинится рендеринг, потом замораживается код v2, и ТОЛЬКО
    ПОТОМ раскрываются held-out задачи. Если задачи появятся раньше, записанное
    предсказание (0.54 -> 0.85-0.95) перестанет быть prospective.

    Часть порядка стережёт surface_digest: новый файл задачи двигает дайджест.
    Часть — снимки: починка рендеринга двигает числа. Здесь — оставшееся:
    план обязан существовать ДО того, как кто-то откроет v2.
    """

    def setUp(self) -> None:
        self.protocol = load()

    def test_v2_plan_is_declared_before_v2_can_open(self) -> None:
        plan = self.protocol.get("v2_plan")
        self.assertIsNotNone(plan, "v2 cannot open without a declared plan")
        self.assertEqual(plan["status"], "declared, not started")
        self.assertEqual(len(plan["blind_barrier"]), 4)
        self.assertIn("materialized_in", plan["blind_barrier"][0])

    def test_held_out_tasks_are_not_revealed_while_v1_is_live(self) -> None:
        tasks = sorted((SPINE_ROOT / "eval/tasks").glob("*.json"))
        self.assertEqual(
            len(tasks),
            self.protocol["tasks"],
            "the task set changed while protocol_version is 1; held-out tasks must not "
            "appear before the v2 implementation change is frozen",
        )

    def test_the_negative_task_class_is_planned(self) -> None:
        """Агенты обожают улучшать мир до состояния failing tests."""

        classes = self.protocol["v2_plan"]["tasks"]["classes"]
        self.assertTrue(
            any("no change required" in c for c in classes),
            "a benchmark with no 'no change required' class cannot measure restraint",
        )

    def test_conditions_and_the_primary_metric_are_pinned(self) -> None:
        plan = self.protocol["v2_plan"]
        self.assertEqual(sorted(plan["conditions"]) [:5], ["A", "B", "C", "D", "E"])
        self.assertEqual(plan["primary_metric"], "resolved by hidden acceptance")
        self.assertEqual(plan["causal_ladder"][-1], "hidden acceptance")

    def test_run_order_is_randomized_not_blocked_by_strategy(self) -> None:
        self.assertIn("randomized", self.protocol["v2_plan"]["run_order"]["rule"])
