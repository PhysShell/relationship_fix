"""Заморозка протокола проверяется, а не обещается.

Если правка двигает `surface_digest`, значит она трогает задачи, якоря, граф
или порядок связей — то есть ровно то, что после просмотра результатов трогать
нельзя. Тест не запрещает такую правку; он требует поднять версию протокола и
признать, что это уже другой эксперимент.
"""

import json
import sys
import unittest
from pathlib import Path

from ._harness import SPINE_ROOT

sys.path.insert(0, str(SPINE_ROOT))
from eval.protocol import (  # noqa: E402
    PHASES,
    load,
    phase,
    surface_digest,
    transition_problems,
    treatment_digest,
    version,
)


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

    def test_the_v1_record_is_present(self) -> None:
        """Историческая запись обязана пережить открытие v2.

        Верхнеуровневые дайджесты при переходе законно поедут; v1_record — нет.
        Пока фаза v1_closed, они обязаны совпадать; после — v1_record остаётся
        историей, а постоянная запись результата живёт в снимках и в git.
        """

        record = self.protocol["v1_record"]
        for key in ("surface_digest", "treatment_digest", "tasks"):
            self.assertIn(key, record)
        if phase() == "v1_closed":
            self.assertEqual(record["surface_digest"], surface_digest())
            self.assertEqual(record["treatment_digest"], treatment_digest())
            self.assertEqual(record["tasks"], self.protocol["tasks"])

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


class StagedTransition(unittest.TestCase):
    """Открыть v2 одним монолитным коммитом нельзя.

    Без ступеней можно поднять версию, починить рендеринг и раскрыть held-out
    задачи разом. Человек скажет «порядок соблюдён концептуально», а Git увидит
    одну кашу — и предсказание перестанет быть prospective.

    До этого монолит ловила ровно одна проверка: голое `version() == 1`. Это не
    барьер, а табличка «удали меня при открытии v2» — ровно то, что сделает
    автор такого коммита.
    """

    def test_the_live_protocol_has_no_transition_problems(self) -> None:
        self.assertEqual(transition_problems(), [])

    def test_phase_is_one_of_the_declared_states(self) -> None:
        self.assertIn(phase(), PHASES)

    def test_v1_closed_means_version_one_and_the_original_task_set(self) -> None:
        if phase() != "v1_closed":
            self.skipTest("v1 is no longer the live phase")
        self.assertEqual(version(), 1)
        self.assertEqual(len(list((SPINE_ROOT / "eval/tasks").glob("*.json"))), 8)

    def test_the_v2_phase_machine_is_declared(self) -> None:
        phases = load()["v2_plan"]["phases"]
        self.assertEqual(sorted(phases), ["commit_A", "commit_B", "commit_C"])
        self.assertIn("must_not_contain", phases["commit_A"])
        self.assertIn("invariant", phases["commit_C"])


class StagedTransitionIsSatisfiable(unittest.TestCase):
    """Барьер обязан пропускать легальную последовательность.

    Зеркало мутационного набора: там каждая мутация обязана быть поймана, здесь
    правильный путь обязан пройти. Барьер, который блокирует всё, ошибается
    просто в другую сторону.

    Симуляция строит настоящий git-репозиторий и проходит A -> B -> C, а затем
    пробует «безобидный рефакторинг» после раскрытия задач.
    """

    def _git(self, repo: Path, *args: str) -> str:
        import subprocess

        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, timeout=30
        ).stdout.strip()

    def test_the_three_stage_path_passes_and_a_late_refactor_does_not(self) -> None:
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            spine = repo / "experiments/semantic-spine"
            spine.parent.mkdir(parents=True)
            shutil.copytree(SPINE_ROOT, spine, ignore=shutil.ignore_patterns("__pycache__"))
            repo.mkdir(exist_ok=True)
            self._git(repo, "init", "--quiet")
            self._git(repo, "config", "user.email", "t@t")
            self._git(repo, "config", "user.name", "t")

            protocol_file = spine / "eval/protocol.json"

            def edit(**changes) -> None:
                payload = json.loads(protocol_file.read_text(encoding="utf-8"))
                payload.update(changes)
                protocol_file.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )

            def commit(message: str) -> str:
                self._git(repo, "add", "-A")
                self._git(repo, "commit", "--quiet", "-m", message)
                return self._git(repo, "rev-parse", "HEAD")

            def touch_treatment(note: str) -> None:
                target = spine / "spine/selector.py"
                target.write_text(target.read_text(encoding="utf-8") + f"\n# {note}\n", encoding="utf-8")

            commit("v1")
            self.assertEqual(transition_problems(spine), [], "the copied v1 must be clean")

            # Ступень A: версия 2 и починка, ни одной новой задачи.
            edit(protocol_version=2, phase="v2_implementation_frozen")
            touch_treatment("v2: materialized_in renders the label's own entry")
            commit("A: implementation frozen")
            self.assertEqual(transition_problems(spine), [], "stage A must pass")

            # Ступень B: преригистрация кода воздействия; задач по-прежнему нет.
            edit(preregistered_treatment_digest=treatment_digest(spine))
            stage_b = commit("B: treatment preregistered")
            self.assertEqual(transition_problems(spine), [], "stage B must pass")

            # Ступень C: раскрытие задач; дайджест обязан совпасть с B.
            task = json.loads((spine / "eval/tasks/confusable-drift.json").read_text(encoding="utf-8"))
            task["task_id"] = "heldout-01"
            (spine / "eval/tasks/heldout-01.json").write_text(
                json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            edit(phase="v2_tasks_revealed", preregistered_at_commit=stage_b)
            commit("C: held-out tasks revealed")
            self.assertEqual(transition_problems(spine), [], "the legitimate path must pass")

            # Зеркало: «безобидный рефакторинг» после раскрытия обязан быть отвергнут.
            touch_treatment("innocent refactor")
            commit("D: refactor after the reveal")
            problems = transition_problems(spine)
            self.assertTrue(problems, "a treatment change after the reveal must be refused")
            self.assertIn("innocent refactor", problems[0])

    def test_a_monolithic_v2_commit_is_refused(self) -> None:
        """Всё разом: версия, починка, преригистрация и задачи в одном коммите."""

        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            spine = repo / "experiments/semantic-spine"
            spine.parent.mkdir(parents=True)
            shutil.copytree(SPINE_ROOT, spine, ignore=shutil.ignore_patterns("__pycache__"))
            repo.mkdir(exist_ok=True)
            self._git(repo, "init", "--quiet")
            self._git(repo, "config", "user.email", "t@t")
            self._git(repo, "config", "user.name", "t")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "--quiet", "-m", "v1")

            task = json.loads((spine / "eval/tasks/confusable-drift.json").read_text(encoding="utf-8"))
            task["task_id"] = "heldout-01"
            (spine / "eval/tasks/heldout-01.json").write_text(
                json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            payload = json.loads((spine / "eval/protocol.json").read_text(encoding="utf-8"))
            payload.update(
                protocol_version=2,
                phase="v2_tasks_revealed",
                preregistered_treatment_digest=treatment_digest(spine),
            )
            (spine / "eval/protocol.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "--quiet", "-m", "monolithic v2")

            problems = transition_problems(spine)
            self.assertTrue(problems, "a monolithic v2 commit must be refused")
            self.assertIn("preregistration must name the commit", problems[0])
