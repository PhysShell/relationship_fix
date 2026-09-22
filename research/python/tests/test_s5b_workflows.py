"""Гейты на сами workflow-файлы.

Свойства, за которые платят часами CI, проверяются здесь, а не глазами:
таймаут ниже платформенного потолка, упавший шард не отменяет остальные, и
версии действий — те, что сверены со страницами релизов, а не взятые по
памяти. Мажоры у GitHub разошлись (upload v7, download v8), и написать
везде `v4` было бы естественной ошибкой.
"""

from __future__ import annotations

import pathlib
import unittest

from simulation import s5b_shard as S

#: Проект держится на стандартной библиотеке. PyYAML тут единственная
#: посторонняя зависимость, и она нужна только чтобы читать workflow —
#: научного кода не касается. Если её нет, гейты пропускаются, а не
#: ломают набор: иначе stdlib-only перестал бы быть правдой.
try:
    import yaml
except ImportError:                                # pragma: no cover
    yaml = None

ROOT = pathlib.Path(__file__).resolve().parents[3]
SMOKE = ROOT / ".github/workflows/s5b-smoke.yml"
STAGE1 = ROOT / ".github/workflows/s5b-stage1.yml"

#: сверено со страницами релизов, а не по памяти
VERIFIED = {"actions/checkout": "v7", "actions/setup-python": "v7",
            "actions/upload-artifact": "v7", "actions/download-artifact": "v8"}


def _load(path):
    return yaml.safe_load(path.read_text())


needs_yaml = unittest.skipIf(yaml is None, "PyYAML не установлен")


def _uses(spec):
    for job in spec["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step:
                yield step["uses"]


@needs_yaml
class ActionVersionsAreTheVerifiedOnesTests(unittest.TestCase):

    def test_every_action_is_pinned_to_the_verified_major(self):
        for path in (SMOKE, STAGE1):
            for used in _uses(_load(path)):
                name, _, version = used.partition("@")
                self.assertIn(name, VERIFIED, f"{path.name}: {used}")
                self.assertEqual(version, VERIFIED[name],
                                 f"{path.name}: {used}")

    def test_the_artifact_majors_are_not_assumed_equal(self):
        """Ровно та ошибка, которую память и подсказывает."""
        self.assertNotEqual(VERIFIED["actions/upload-artifact"],
                            VERIFIED["actions/download-artifact"])


@needs_yaml
class TimeoutsStayUnderThePlatformCapTests(unittest.TestCase):

    def test_every_computing_job_times_out_before_the_platform_kills_it(self):
        """Упереться в потолок значит потерять ВСЮ работу без диагностики."""
        cap = S.GITHUB_JOB_MAX_HOURS * 60
        for path in (SMOKE, STAGE1):
            for name, job in _load(path)["jobs"].items():
                if name in ("plan", "merge"):
                    continue
                timeout = job.get("timeout-minutes")
                self.assertIsNotNone(timeout, f"{path.name}:{name}")
                self.assertLess(timeout, cap, f"{path.name}:{name}")

    def test_the_shard_budget_leaves_room_under_the_cap(self):
        self.assertLess(S.SHARD_BUDGET_HOURS, S.GITHUB_JOB_MAX_HOURS)


@needs_yaml
class TheMatrixIsShapedByTheDocumentedLimitsTests(unittest.TestCase):

    def test_a_failed_shard_does_not_cancel_the_others(self):
        """Слияние fail-closed и само скажет, чего не хватает."""
        compute = _load(STAGE1)["jobs"]["compute"]
        self.assertIs(compute["strategy"]["fail-fast"], False)

    def test_the_matrix_is_built_from_the_plan_not_hardcoded(self):
        compute = _load(STAGE1)["jobs"]["compute"]
        self.assertIn("fromJSON", str(compute["strategy"]["matrix"]["shard"]))
        self.assertIn("plan", compute["needs"])

    def test_every_planned_step_fits_the_matrix_ceiling(self):
        from simulation import s5b_precision as PR
        units = S.plan([(a["tag"], a["effective_rate"])
                        for a in S.production_arms()])
        for look in PR.LOOKS:
            step = [u for u in units if u.look == look]
            self.assertLessEqual(S.shards_needed(step),
                                 S.GITHUB_MATRIX_MAX_JOBS, look)

    def test_shard_results_travel_as_artifacts_not_job_outputs(self):
        """Поведение `outputs` у матричных заданий не документировано.

        Поэтому конструкция на него не опирается вовсе: дешевле, чем
        полагаться на неописанное и выяснять на двухстах CPU-часах.
        """
        compute = _load(STAGE1)["jobs"]["compute"]
        self.assertNotIn("outputs", compute)
        names = [s["with"]["name"] for s in compute["steps"]
                 if s.get("uses", "").startswith("actions/upload-artifact")]
        self.assertTrue(names)
        for name in names:
            self.assertIn("matrix.shard", name,
                          "имя артефакта обязано нести значение матрицы")

    def test_the_merge_runs_even_when_a_shard_failed(self):
        merge = _load(STAGE1)["jobs"]["merge"]
        self.assertIn("cancelled()", str(merge["if"]))
        download = [s for s in merge["steps"]
                    if s.get("uses", "").startswith("actions/download-artifact")]
        self.assertTrue(any(s["with"].get("merge-multiple") for s in download))


@needs_yaml
class TheSmokeJobIsTheWorstCaseTests(unittest.TestCase):

    def test_the_smoke_job_runs_the_most_expensive_unit_of_the_grid(self):
        arms = S.production_arms()
        worst = max(arms, key=lambda a: a["effective_rate"])
        self.assertEqual(worst["effective_rate"], 120.0)
        self.assertGreater(
            S.cost_of(worst["effective_rate"], 64_000, 1.0) / 3600,
            S.GITHUB_JOB_MAX_HOURS,
            "одна группа ключей обязана НЕ влезать — иначе проба не худшая")

    def test_the_cost_model_uses_the_effective_rate_not_the_grid_rate(self):
        """Ставка сетки недооценивает ровно самые тяжёлые руки."""
        arms = {a["tag"]: a for a in S.production_arms()}
        heavy = arms["r96.0:c1.25:R0:m1.0"]
        self.assertGreater(heavy["effective_rate"], heavy["rate"])
        self.assertAlmostEqual(heavy["effective_rate"], 96.0 * 1.25)
