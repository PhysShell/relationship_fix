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

PLACEHOLDER = "0" * 40


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


@needs_yaml
class TheSmokeResultIsRecordedTests(unittest.TestCase):
    """Калибровка взята из прогона на настоящем раннере, а не с машины."""

    def _note(self):
        return " ".join((ROOT / "docs/research/s5b-smoke-record.md")
                        .read_text().split())

    def test_the_cost_model_is_calibrated_from_the_smoke_run(self):
        self.assertAlmostEqual(S.SECONDS_PER_PERIOD_AT_REFERENCE, 0.0238626)
        self.assertIn("35769710129", S.SECONDS_PER_PERIOD_MEASURED_ON)
        self.assertGreater(S.SECONDS_PER_PERIOD_AT_REFERENCE,
                           S.SECONDS_PER_PERIOD_BEFORE_SMOKE,
                           "замер обязан был УВЕЛИЧИТЬ оценку, а не наоборот")

    def test_the_calibration_matches_the_measured_seconds(self):
        """Число выведено из замера, а не домножено на коэффициент."""
        want = 16035.7 / (64_000 * (120.0 / 6.0) * (0.05 + 0.95 * 0.5))
        self.assertAlmostEqual(S.SECONDS_PER_PERIOD_AT_REFERENCE, want,
                               places=6)

    def test_the_operational_budget_stays_under_the_platform_timeout(self):
        """Свойство СИСТЕМЫ: бюджет строго ниже платформенного потолка.

        Прежняя редакция этого теста требовала, чтобы измеренное время
        ПРЕВЫШАЛО бюджет. Это был исторический факт конкретной пробы, а не
        свойство корректной системы: раннер побыстрее — и «правильная»
        конфигурация валила бы тест. Тот же класс, что уже ловился трижды:
        проверять надо требование, а не совпадение.

        Само число 4.454 ч против 4.0 ч осталось в исследовательской
        записи, где ему и место.
        """
        self.assertLess(S.SHARD_BUDGET_HOURS, S.GITHUB_JOB_MAX_HOURS)

    def test_the_recalibrated_plan_still_fits_every_documented_limit(self):
        from simulation import s5b_precision as PR
        units = S.plan([(a["tag"], a["effective_rate"])
                        for a in S.production_arms()])
        for look in PR.LOOKS:
            step = [u for u in units if u.look == look]
            count = S.shards_needed(step)
            S.check_platform_limits(S.assign(step, count))
            self.assertLessEqual(count, S.GITHUB_MATRIX_MAX_JOBS, look)

    def test_the_record_states_what_the_single_point_does_not_prove(self):
        note = self._note()
        self.assertIn("одна точка", note)
        self.assertIn("Форма квалифицирована", note)
        self.assertIn("Бюджет шарда `4.0 ч` пробит фактом", note)
        self.assertIn("b3d80674ae23c419", note)
        self.assertIn("поймано ТОЛЬКО прогоном", note)


@needs_yaml
class ScienceShaIsPinnedNotInheritedTests(unittest.TestCase):
    """Триггерный коммит — сигнал запуска, а не версия научного кода.

    Заявка меняется чаще кода: ступени 4000/16000/64000 заказываются в
    разные дни. Если каждая считает тем, что лежало на ветке в момент
    заказа, вложенность лестницы становится утверждением о репозитории, а
    не о выборке.
    """

    def _stage1(self):
        return _load(STAGE1)

    def test_the_science_sha_is_a_full_quoted_hex_sha(self):
        value = self._stage1()["env"]["SCIENCE_SHA"]
        self.assertIsInstance(value, str,
                              "YAML разобрал SHA как число — нужны кавычки")
        self.assertRegex(value, r"^[0-9a-f]{40}$")

    def test_a_requested_run_may_not_point_at_the_placeholder(self):
        """Связка правильная: запрещено ЗАКАЗЫВАТЬ прогон без закрепления.

        Плейсхолдер сам по себе не дефект — он живёт ровно между тем, как
        научный код закоммичен, и тем, как его SHA вписан. Дефектом он
        становится в момент, когда появляется заявка.
        """
        if not (ROOT / ".github/s5b-stage1-request.txt").exists():
            self.skipTest("заявки нет — закреплять пока нечего")
        self.assertNotEqual(self._stage1()["env"]["SCIENCE_SHA"], PLACEHOLDER,
                            "заявка есть, а закреплён плейсхолдер")

    def test_every_computing_job_checks_out_the_pinned_sha(self):
        for name in ("compute", "merge"):
            job = self._stage1()["jobs"][name]
            refs = [step["with"]["ref"] for step in job["steps"]
                    if step.get("uses", "").startswith("actions/checkout")]
            self.assertTrue(refs, name)
            for ref in refs:
                self.assertIn("SCIENCE_SHA", ref, (name, ref))

    def test_the_plan_reads_the_request_from_the_branch_and_code_from_the_pin(self):
        """Два checkout'а, и они РАЗНЫЕ по назначению."""
        steps = [s for s in self._stage1()["jobs"]["plan"]["steps"]
                 if s.get("uses", "").startswith("actions/checkout")]
        self.assertEqual(len(steps), 2)
        refs = {s["with"]["ref"]: s["with"]["path"] for s in steps}
        self.assertIn("${{ github.sha }}", refs, "заявка не читается с ветки")
        pinned = [r for r in refs if "SCIENCE_SHA" in r]
        self.assertEqual(len(pinned), 1, "научный код не закреплён")
        self.assertNotEqual(refs["${{ github.sha }}"], refs[pinned[0]],
                            "оба checkout'а в один каталог — затрут друг друга")


@needs_yaml
class Stage1LaunchesByRequestFileTests(unittest.TestCase):
    """`workflow_dispatch` на рабочей ветке не срабатывает — documented."""

    def test_stage1_triggers_on_push_to_its_request_file(self):
        spec = _load(STAGE1)
        trigger = spec[True] if True in spec else spec["on"]
        self.assertIn("push", trigger)
        self.assertEqual(trigger["push"]["paths"],
                         [".github/s5b-stage1-request.txt"])

    def test_stage1_does_not_pretend_dispatch_works_here(self):
        spec = _load(STAGE1)
        trigger = spec[True] if True in spec else spec["on"]
        self.assertNotIn("workflow_dispatch", trigger)

    def test_a_request_if_present_names_a_ladder_step(self):
        import re
        request = ROOT / ".github/s5b-stage1-request.txt"
        if not request.exists():
            self.skipTest("заявки нет")
        found = re.search(r"^look:\s*(\d+)", request.read_text(),
                          re.MULTILINE)
        self.assertIsNotNone(found, "заявка не называет ступень")
        from simulation import s5b_precision as PR
        self.assertIn(int(found.group(1)), PR.LOOKS)

