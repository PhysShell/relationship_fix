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
    treatment_digest_at,
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
        """Обязательна граница B/C. Отдельность A и B — нет: разделять «написали
        код» и «записали его хеш» не добавляет независимости, пока и то и другое
        скрыто от curator'а."""

        plan = load()["v2_plan"]
        phases = plan["phases"]
        self.assertEqual(sorted(k for k in phases if k != "note"), ["A_and_B", "C"])
        self.assertIn("must_not_contain", phases["A_and_B"])
        self.assertIn("enforced_boundary", phases["C"])
        self.assertGreaterEqual(len(plan["closed_bypasses"]), 5)


class TransitionBarrier(unittest.TestCase):
    """Барьер проверяется попыткой построить неправильную историю.

    Метод, который уже несколько раз спасал этот harness: не спрашивать «есть
    ли проверка?», а попробовать пройти мимо неё. Каждая симуляция строит
    настоящий git-репозиторий.

    Зеркало обязательно: барьер, который блокирует всё, ошибается просто в
    другую сторону, поэтому легальный путь обязан проходить.
    """

    def _git(self, repo: Path, *args: str) -> str:
        import subprocess

        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, timeout=30
        ).stdout.strip()

    def _fresh(self, tmp: str):
        import shutil

        repo = Path(tmp) / "repo"
        spine = repo / "experiments/semantic-spine"
        spine.parent.mkdir(parents=True)
        shutil.copytree(SPINE_ROOT, spine, ignore=shutil.ignore_patterns("__pycache__"))
        self._git(repo.parent, "init", "--quiet", str(repo))
        self._git(repo, "config", "user.email", "t@t")
        self._git(repo, "config", "user.name", "t")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "--quiet", "-m", "v1")
        return repo, spine

    def _edit(self, spine: Path, **changes) -> None:
        path = spine / "eval/protocol.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(changes)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _add_held_out_task(self, spine: Path) -> None:
        task = json.loads((spine / "eval/tasks/confusable-drift.json").read_text(encoding="utf-8"))
        task["task_id"] = "heldout-01"
        (spine / "eval/tasks/heldout-01.json").write_text(
            json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def _touch_treatment(self, spine: Path, note: str) -> None:
        target = spine / "spine/selector.py"
        target.write_text(target.read_text(encoding="utf-8") + f"\n# {note}\n", encoding="utf-8")

    def _commit(self, repo: Path, message: str) -> str:
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "--quiet", "-m", message)
        return self._git(repo, "rev-parse", "HEAD")

    def _walk_to_reveal(self, repo: Path, spine: Path) -> str:
        """Легальный путь до раскрытия задач включительно."""

        self._edit(spine, protocol_version=2, phase="v2_implementation_frozen")
        self._touch_treatment(spine, "v2: materialized_in renders the label's own entry")
        self._commit(repo, "A: implementation frozen")
        self.assertEqual(transition_problems(spine), [], "stage A must pass")

        self._edit(spine, preregistered_treatment_digest=treatment_digest(spine))
        stage_b = self._commit(repo, "B: treatment preregistered")
        self.assertEqual(transition_problems(spine), [], "stage B must pass")

        self._add_held_out_task(spine)
        self._edit(spine, phase="v2_tasks_revealed", preregistered_at_commit=stage_b)
        self._commit(repo, "C: held-out tasks revealed")
        return stage_b

    def test_the_legitimate_path_passes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo, spine = self._fresh(tmp)
            self._walk_to_reveal(repo, spine)
            self.assertEqual(transition_problems(spine), [], "the legitimate path must pass")

    def test_a_late_refactor_is_refused(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo, spine = self._fresh(tmp)
            self._walk_to_reveal(repo, spine)
            self._touch_treatment(spine, "innocent refactor")
            self._commit(repo, "D: refactor after the reveal")
            problems = transition_problems(spine)
            self.assertTrue(problems)
            self.assertIn("innocent refactor", problems[0])

    def test_completing_the_experiment_does_not_lift_the_freeze(self) -> None:
        """Иначе provenance уничтожается ровно после того, как потратили деньги."""

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo, spine = self._fresh(tmp)
            self._walk_to_reveal(repo, spine)
            self._touch_treatment(spine, "late change")
            self._edit(spine, phase="v2_experiment_complete")
            self._commit(repo, "escape via experiment_complete")
            problems = transition_problems(spine)
            self.assertTrue(problems, "the freeze must be monotonic across v2 phases")
            self.assertIn("changed after the held-out tasks were revealed", problems[0])

    def test_a_naive_monolith_is_refused(self) -> None:
        """Всё разом и без указания преригистрационного коммита."""

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo, spine = self._fresh(tmp)
            self._add_held_out_task(spine)
            self._edit(
                spine,
                protocol_version=2,
                phase="v2_tasks_revealed",
                preregistered_treatment_digest=treatment_digest(spine),
            )
            self._commit(repo, "monolithic v2")
            problems = transition_problems(spine)
            self.assertTrue(problems)
            self.assertIn("preregistration must name the commit", problems[0])

    def test_a_sneaky_monolith_pointing_at_an_older_commit_is_refused(self) -> None:
        """Самый интересный нарушитель.

        Меняет treatment, добавляет задачи, записывает хеш НОВОГО кода и
        указывает на любой старый коммит, в котором задач ещё не было. Все
        прежние проверки он проходил: коммит существует, не равен HEAD, задач в
        нём восемь, текущий дайджест совпадает с записанным. Не совпадало
        только одно — treatment в самом названном коммите.
        """

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo, spine = self._fresh(tmp)
            old = self._git(repo, "rev-parse", "HEAD")
            self._touch_treatment(spine, "v2 rendering change")
            self._add_held_out_task(spine)
            self._edit(
                spine,
                protocol_version=2,
                phase="v2_tasks_revealed",
                preregistered_treatment_digest=treatment_digest(spine),
                preregistered_at_commit=old,
            )
            self._commit(repo, "sneaky monolith")
            problems = transition_problems(spine)
            self.assertTrue(problems, "pointing at an older commit must not be enough")
            self.assertIn("treatment at the preregistration commit", problems[0])

    def test_a_v2_phase_requires_version_two(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo, spine = self._fresh(tmp)
            self._edit(spine, phase="v2_implementation_frozen")
            self._commit(repo, "phase without a version bump")
            problems = transition_problems(spine)
            self.assertTrue(problems)
            self.assertIn("protocol_version is 1, not 2", problems[0])

    def test_the_tree_digest_matches_the_working_tree_digest(self) -> None:
        """Обе раскладки байт обязаны совпадать, иначе сравнение бессмысленно."""

        import subprocess

        head = subprocess.run(
            ["git", "-C", str(SPINE_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        self.assertEqual(treatment_digest(), treatment_digest_at(SPINE_ROOT, head))
