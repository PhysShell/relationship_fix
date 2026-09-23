"""Гейты слоя ИСПОЛНЕНИЯ: свой `tau` у каждого конца.

Слой лежит отдельным деревом (`execution/`), потому что в производстве он
приезжает ДРУГИМ checkout'ом, нежели наука. Здесь это дерево кладётся на
путь явно: единственный шов, и он назван вслух, а не спрятан в конфиг.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "execution") not in sys.path:
    sys.path.insert(0, str(ROOT / "execution"))

from s5b_execution import (cli, cost, provenance,       # noqa: E402
                           reduction, scheduler)
from s5b_execution.identity import (ACHIEVED, INSUFFICIENT,        # noqa: E402
                                    ArtifactRefused, EndpointId,
                                    load_unit_payloads)
from s5b_execution.ledger import Ledger, LedgerRefused             # noqa: E402

KEY_LOW = [1.0, 14.0, 300.0, False]
KEY_HIGH = [1.0, 14.0, 300.0, True]


def _end(key, fraction, *, achieved, look, point=100.0, width=1.0):
    return {"key": list(key), "fraction": fraction, "point": point,
            "low": point - width, "high": point + width, "radius": width,
            "status": ACHIEVED if achieved else INSUFFICIENT,
            "look": look if achieved else None}


def _unit(task_id, arm, look, endpoints, keys=(KEY_LOW,)):
    """Часть с ЧЕСТНЫМ отпечатком: он теперь пересчитывается из содержимого."""
    from s5b_execution.identity import recompute_digest
    payload = {"task_id": task_id, "arm": arm, "look": look,
               "keys": [list(k) for k in keys], "endpoints": endpoints}
    payload["digest"] = recompute_digest(payload)
    return payload


def _canonical_parts(where, look=4000, endpoints=None):
    """156 частей с НАСТОЯЩИМИ тегами рук сетки.

    Выдуманная рука отвергается каноническим гейтом — и правильно
    делает. Чтобы проверять то, ради чего тест написан, синтетика обязана
    быть канонической по составу.
    """
    from simulation import s5b_shard as S
    keys = tuple(scheduler.KEYS)
    where = pathlib.Path(where)
    rows = []
    for arm in S.production_arms():
        unit = S.Unit(arm=arm["tag"], look=look, keys=keys, weight=0.0)
        payload = _unit(unit.task_id, arm["tag"], look,
                        list(endpoints or []), keys)
        (where / f"{unit.task_id}.json").write_text(
            json.dumps(payload, sort_keys=True))
        rows.append({"task_id": unit.task_id, "arm": arm["tag"],
                     "look": look, "shard": 0,
                     "keys": [list(k) for k in keys]})
    (where / "manifest.json").write_text(json.dumps(
        {"look": look, "shards": 1, "units": rows,
         # провенанс обязателен: возобновление сверяет по нему SCIENCE_SHA
         "provenance": {"science_sha": "a" * 40, "execution_sha": "b" * 40,
                        "request_sha": "c" * 40, "inputs": {},
                        "manifest_digest": "x"}}))
    return rows


class EarliestTauIsKeptTests(unittest.TestCase):
    """Сценарий из директивы, дословно.

    Конец достиг точности на 4000. Юнит ПЕРЕСЧИТАН на 16000 — потому что
    рядом, в том же юните, остался незакрывшийся сосед. Итог обязан
    сохранить значение и `tau = 4000`.
    """

    def _ledger(self):
        early = _unit("u1", "armT", 4000, [
            _end(KEY_LOW, 0.1, achieved=True, look=4000, point=100.0, width=2.0),
            _end(KEY_LOW, 0.01, achieved=False, look=None),
        ])
        late = _unit("u1", "armT", 16000, [
            # тот же конец, ПЕРЕСЧИТАН: другое значение, другой просмотр
            _end(KEY_LOW, 0.1, achieved=True, look=16000, point=777.0, width=0.5),
            _end(KEY_LOW, 0.01, achieved=True, look=16000, point=50.0, width=0.1),
        ])
        ledger = Ledger()
        ledger.absorb(4000, [early])
        ledger.absorb(16000, [late])
        return ledger

    def test_the_early_endpoint_keeps_its_value_and_tau(self):
        final = self._ledger().finalise(16000)
        kept = final[EndpointId("armT", tuple(KEY_LOW), 0.1)]
        self.assertEqual(kept["look"], 4000, "tau подменён поздним просмотром")
        self.assertEqual(kept["point"], 100.0, "значение подменено")
        self.assertEqual(kept["high"], 102.0)

    def test_the_late_endpoint_settles_at_its_own_look(self):
        """Сосед закрылся на 16000 — у него свой tau, и он именно 16000."""
        final = self._ledger().finalise(16000)
        late = final[EndpointId("armT", tuple(KEY_LOW), 0.01)]
        self.assertEqual(late["look"], 16000)
        self.assertEqual(late["point"], 50.0)

    def test_the_two_endpoints_of_one_unit_may_hold_different_taus(self):
        """Внутри ОДНОГО юнита tau у концов разные. Это норма, не изъян."""
        final = self._ledger().finalise(16000)
        taus = {final[EndpointId("armT", tuple(KEY_LOW), f)]["look"]
                for f in (0.1, 0.01)}
        self.assertEqual(taus, {4000, 16000})

    def test_the_recount_is_counted_not_silently_dropped(self):
        """Проигнорированная копия учитывается: молчание скрыло бы сбой."""
        self.assertEqual(self._ledger().ignored_because_already_settled, 1)

    def test_a_later_loss_of_precision_does_not_unsettle(self):
        """Радиус по M убывать НЕ обязан: множество приёма бывает несвязным.

        Конец, точный на 4000 и неточный на 16000, обязан остаться точным
        со своим ранним tau. Иначе ранний результат исчезал бы именно там,
        где его нельзя восстановить.
        """
        ledger = Ledger()
        ledger.absorb(4000, [_unit("u2", "armT", 4000, [
            _end(KEY_LOW, 0.1, achieved=True, look=4000)])])
        ledger.absorb(16000, [_unit("u2", "armT", 16000, [
            _end(KEY_LOW, 0.1, achieved=False, look=None)])])
        got = ledger.finalise(16000)[EndpointId("armT", tuple(KEY_LOW), 0.1)]
        self.assertEqual(got["status"], ACHIEVED)
        self.assertEqual(got["look"], 4000)


class LedgerRefusesTests(unittest.TestCase):
    """Отказ по умолчанию: сомнительный вход не чинится на лету."""

    def test_looks_must_be_absorbed_in_ascending_order(self):
        """16000 раньше 4000 сделал бы tau не минимумом, а первым пришедшим."""
        ledger = Ledger()
        ledger.absorb(16000, [_unit("u", "a", 16000, [
            _end(KEY_LOW, 0.1, achieved=True, look=16000)])])
        with self.assertRaises(LedgerRefused):
            ledger.absorb(4000, [_unit("u", "a", 4000, [
                _end(KEY_LOW, 0.1, achieved=True, look=4000)])])

    def test_a_payload_from_another_look_is_refused(self):
        ledger = Ledger()
        with self.assertRaises(LedgerRefused):
            ledger.absorb(4000, [_unit("u", "a", 16000, [])])

    def test_an_achieved_endpoint_claiming_another_look_is_refused(self):
        """Происхождение: точный конец обязан нести ступень, с которой приехал."""
        ledger = Ledger()
        with self.assertRaises(LedgerRefused):
            ledger.absorb(4000, [_unit("u", "a", 4000, [
                _end(KEY_LOW, 0.1, achieved=True, look=64000)])])

    def test_an_insufficient_endpoint_carrying_a_look_is_refused(self):
        ledger = Ledger()
        bad = _end(KEY_LOW, 0.1, achieved=False, look=None)
        bad["look"] = 4000
        with self.assertRaises(LedgerRefused):
            ledger.absorb(4000, [_unit("u", "a", 4000, [bad])])

    def test_finalising_an_empty_ledger_is_refused(self):
        with self.assertRaises(LedgerRefused):
            Ledger().finalise(4000)

    def test_finalising_at_a_look_never_absorbed_is_refused(self):
        ledger = Ledger()
        ledger.absorb(4000, [_unit("u", "a", 4000, [
            _end(KEY_LOW, 0.1, achieved=True, look=4000)])])
        with self.assertRaises(LedgerRefused):
            ledger.finalise(16000)


class UnitSelectionTests(unittest.TestCase):
    """Юнит идёт дальше, если внутри остался хоть один незакрытый конец."""

    def test_a_unit_with_one_unsettled_endpoint_is_still_needed(self):
        ledger = Ledger()
        ledger.absorb(4000, [_unit("u", "armT", 4000, [
            _end(KEY_LOW, 0.1, achieved=True, look=4000),
            _end(KEY_LOW, 0.01, achieved=False, look=None)])])
        self.assertTrue(ledger.unit_is_needed("armT", [tuple(KEY_LOW)],
                                              (0.1, 0.01)))

    def test_a_fully_settled_unit_is_not_needed(self):
        ledger = Ledger()
        ledger.absorb(4000, [_unit("u", "armT", 4000, [
            _end(KEY_LOW, 0.1, achieved=True, look=4000),
            _end(KEY_LOW, 0.01, achieved=True, look=4000)])])
        self.assertFalse(ledger.unit_is_needed("armT", [tuple(KEY_LOW)],
                                               (0.1, 0.01)))


class CostLivesOnlyInExecutionTests(unittest.TestCase):
    """Стоимость научного результата не определяет."""

    def test_the_task_id_does_not_depend_on_cost(self):
        """Перераскладка обязана оставлять артефакты теми же."""
        from simulation import s5b_shard as S
        keys = tuple(scheduler.KEYS)
        cheap = S.Unit(arm="a", look=4000, keys=keys, weight=1.0)
        dear = S.Unit(arm="a", look=4000, keys=keys, weight=999999.0)
        self.assertEqual(cheap.task_id, dear.task_id)

    def test_the_envelope_is_the_worst_observed_runner_not_the_typical(self):
        """В потолок упирается худший шард, а его задаёт самый медленный."""
        rate = 120.0
        got = cost.seconds_for(rate, cost.FITTED_AT_LOOK)
        each = [a + b * rate for a, b in cost.RUNNER_FITS]
        self.assertEqual(got, max(each))
        self.assertGreater(got, sum(each) / len(each))

    def test_the_budget_is_checked_in_two_steps_not_against_a_sample_range(self):
        """Прежний критерий сравнивал запас с размахом ШЕСТИ наблюдений.

        1.963 — максимум шести замеров, а не верхняя граница распределения
        скоростей раннеров. Сравнивать с ним значило бы выдавать выборку
        за совокупность. Требование переформулировано: веса от
        консервативной огибающей, а цель — существенно ниже потолка, и
        это объявленный операционный выбор.
        """
        self.assertLess(cost.SHARD_BUDGET_HOURS, 4.0, "пробит фактом 4.188")
        self.assertGreaterEqual(cost.BUDGET_HEADROOM, cost.MIN_BUDGET_HEADROOM)
        self.assertLess(cost.SHARD_BUDGET_HOURS, cost.PLATFORM_CAP_HOURS)

    def test_the_worst_predicted_job_fits_the_target_at_every_runnable_look(self):
        """Проверяется ХУДШЕЕ предсказанное задание, а не среднее."""
        from simulation import s5b_shard as S
        for look in (4000, 16_000):
            units = scheduler.units_for(look)
            count = scheduler.shards_needed(units)
            worst = max(sum(u.weight for u in b)
                        for b in S.assign(units, count))
            self.assertLessEqual(worst, cost.SHARD_BUDGET_HOURS * 3600.0,
                                 f"look {look}")
            self.assertLess(worst, cost.PLATFORM_CAP_HOURS * 3600.0 / 2.0,
                            f"look {look}: худшее задание близко к потолку")

    def test_the_split_economy_is_refused_not_guessed(self):
        """Деление ключей не измерено ни разу — значит отказ, а не константа."""
        self.assertIsNone(cost.UNDIVIDED_SHARE)
        with self.assertRaises(cost.SplitEconomyUnmeasured):
            cost.groups_needed(120.0, 64_000, 72)

    def test_no_split_is_needed_at_the_looks_we_may_run(self):
        """На 4000 и 16000 деления нет: ось ключей не включается."""
        for arm in scheduler.arms().values():
            for look in (4000, 16_000):
                self.assertEqual(
                    cost.groups_needed(arm["effective_rate"], look,
                                       len(scheduler.KEYS)), 1)


class ProvenanceTests(unittest.TestCase):
    """Прогон без происхождения не начинается."""

    def test_a_missing_sha_is_refused(self):
        import os
        keep = {k: os.environ.get(k) for k in provenance.REQUIRED_ENV}
        try:
            for name in provenance.REQUIRED_ENV:
                os.environ.pop(name, None)
            with self.assertRaises(provenance.ProvenanceIncomplete):
                provenance.collect(inputs={}, manifest_digest="x")
        finally:
            for name, value in keep.items():
                if value is not None:
                    os.environ[name] = value

    def test_a_truncated_sha_is_refused(self):
        import os
        keep = {k: os.environ.get(k) for k in provenance.REQUIRED_ENV}
        try:
            for name in provenance.REQUIRED_ENV:
                os.environ[name] = "abc123"
            with self.assertRaises(provenance.ProvenanceIncomplete):
                provenance.collect(inputs={}, manifest_digest="x")
        finally:
            for name, value in keep.items():
                os.environ.pop(name, None)
                if value is not None:
                    os.environ[name] = value


class ArtifactReadingTests(unittest.TestCase):

    def test_a_part_file_missing_a_field_is_refused(self):
        with tempfile.TemporaryDirectory() as where:
            (pathlib.Path(where) / "abc.json").write_text(
                json.dumps({"task_id": "abc", "arm": "a"}))
            with self.assertRaises(ArtifactRefused):
                load_unit_payloads(where)

    def test_a_file_named_other_than_its_task_id_is_refused(self):
        with tempfile.TemporaryDirectory() as where:
            (pathlib.Path(where) / "zzz.json").write_text(
                json.dumps(_unit("abc", "a", 4000, [])))
            with self.assertRaises(ArtifactRefused):
                load_unit_payloads(where)

    def test_an_empty_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as where:
            with self.assertRaises(ArtifactRefused):
                load_unit_payloads(where)


class FrozenScienceIsCalledNotCopiedTests(unittest.TestCase):
    """Слой зовёт науку, а не заводит вторую рядом."""

    def test_the_frozen_merge_is_used_at_every_look(self):
        self.assertTrue(reduction.FROZEN_MERGE_RUNS_AT_EVERY_LOOK)
        source = (ROOT / "execution/s5b_execution/reduction.py").read_text()
        self.assertIn("S.merge(", source)

    def test_the_contrast_comes_from_the_frozen_module(self):
        source = (ROOT / "execution/s5b_execution/reduction.py").read_text()
        self.assertIn("E.cell_contrast(", source)
        self.assertIn("E.cell_is_evaluable(", source)

    def test_the_layer_declares_it_owns_no_science(self):
        import s5b_execution
        self.assertTrue(s5b_execution.EXECUTION_LAYER_OWNS_NO_SCIENCE)


class ManifestIsTheOnlySourceOfLayoutTests(unittest.TestCase):
    """План и исполнение не могут разойтись, потому что вывод один.

    Сегодняшний отказ прогона родился из расхождения двух мест, которые
    обязаны были совпасть. Раскладка пишется планом в манифест, а `run`
    её ЧИТАЕТ, а не выводит заново.
    """

    def _manifest(self, tmp, look=4000):
        import os
        from s5b_execution import cli
        keep = {k: os.environ.get(k) for k in provenance.REQUIRED_ENV}
        try:
            for name in provenance.REQUIRED_ENV:
                os.environ[name] = "a" * 40
            cli.main(["plan", "--look", str(look), "--out", tmp])
        finally:
            for name, value in keep.items():
                os.environ.pop(name, None)
                if value is not None:
                    os.environ[name] = value
        return json.loads((pathlib.Path(tmp) / "manifest.json").read_text())

    def test_every_unit_carries_its_shard(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._manifest(tmp)
            self.assertTrue(all("shard" in u for u in manifest["units"]))
            shards = {u["shard"] for u in manifest["units"]}
            self.assertEqual(shards, set(range(manifest["shards"])))

    def test_a_manifest_row_whose_task_id_lies_is_refused(self):
        """Манифест не верят на слово: состав обязан давать тот же task_id.

        Проверяется ПОВЕДЕНИЕ. Прежняя версия этого гейта искала строку в
        исходнике и потому прошла бы мимо любой подмены, оставившей
        комментарий на месте.
        """
        from s5b_execution import cli
        from simulation import s5b_shard as S
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {"look": 4000, "shards": 1, "units": [
                {"task_id": "0" * 16, "arm": "r6.0:c1.00:R0:m1.0",
                 "look": 4000, "shard": 0,
                 "keys": [list(k) for k in scheduler.KEYS]}]}
            path = pathlib.Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest))
            with self.assertRaises(SystemExit) as caught:
                cli.main(["run", "--look", "4000", "--manifest", str(path),
                          "--shard", "0", "--out", tmp])
            self.assertIn("происхождение нарушено", str(caught.exception))
        # и наоборот: честный состав даёт ровно объявленный task_id
        honest = S.Unit(arm="a", look=4000, keys=tuple(scheduler.KEYS),
                        weight=0.0)
        self.assertNotEqual(honest.task_id, "0" * 16)

    def test_the_manifest_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            got = self._manifest(tmp)["provenance"]
            for field in provenance.REQUIRED:
                self.assertTrue(got[field])
            self.assertIn("manifest_digest", got)
            self.assertIn("inputs", got)

    def test_a_unit_declared_but_never_delivered_is_refused(self):
        """Ожидаемое берётся из МАНИФЕСТА, а не из приехавшего.

        Одна рука, два юнита по половине ключей — приезжает один. Ключи
        руки покрыты наполовину, и замороженное слияние обязано отказать.
        Это ровно тот путь, который впервые заработает на 64000.
        """
        from s5b_execution import cli
        from simulation import s5b_shard as S
        keys = tuple(scheduler.KEYS)
        half = len(keys) // 2
        # настоящий тег сетки: выдуманный отвергнет гейт канонических рук
        tag = sorted(a["tag"] for a in S.production_arms())[0]
        a = S.Unit(arm=tag, look=4000, keys=keys[:half], weight=0.0)
        b = S.Unit(arm=tag, look=4000, keys=keys[half:], weight=0.0)
        with tempfile.TemporaryDirectory() as tmp:
            where = pathlib.Path(tmp)
            (where / "manifest.json").write_text(json.dumps({
                "look": 4000, "shards": 1, "units": [
                    {"task_id": u.task_id, "arm": tag, "look": 4000,
                     "shard": 0, "keys": [list(k) for k in u.keys]}
                    for u in (a, b)]}))
            (where / f"{a.task_id}.json").write_text(json.dumps(
                _unit(a.task_id, tag, 4000, [], a.keys)))
            payloads = load_unit_payloads(where)
            with self.assertRaises(Exception) as caught:
                cli._verify_with_frozen_merge(where, 4000, payloads)
            self.assertIn("не хватает юнитов", str(caught.exception))


class BoundariesAreProvenNotDeclaredTests(unittest.TestCase):
    """Три инварианта, каждый закрывает дыру в том, что выглядело закрытым."""

    def test_science_imported_from_elsewhere_is_refused(self):
        """Execution-checkout — ПОЛНЫЙ репозиторий, там тоже research/python.

        Сегодня коллизии нет лишь потому, что в PYTHONPATH попадает
        `exec/execution`, а не `exec`. Это свойство одной строки, а не
        гарантия: иначе SCIENCE_SHA стал бы табличкой на двери.
        """
        from s5b_execution import guard
        got = guard.assert_science_comes_from(ROOT / "research/python")
        self.assertIn("simulation.s5b_shard", got)
        self.assertTrue(got["simulation.s5b_shard"].endswith("s5b_shard.py"))
        with tempfile.TemporaryDirectory() as elsewhere:
            with self.assertRaises(guard.BoundaryViolated):
                guard.assert_science_comes_from(elsewhere)

    def test_a_commit_touching_more_than_the_request_is_refused(self):
        """Пина EXECUTION_SHA мало: YAML воркфлоу GitHub берёт с triggering ref."""
        from s5b_execution import guard
        guard.assert_request_is_only_a_signal([guard.REQUEST_PATH])
        with self.assertRaises(guard.BoundaryViolated):
            # пусто — тоже отказ: значит запуск случился не тем
            # механизмом, которым мы думаем
            guard.assert_request_is_only_a_signal([])
        with self.assertRaises(guard.BoundaryViolated) as caught:
            guard.assert_request_is_only_a_signal(
                [guard.REQUEST_PATH, ".github/workflows/s5b-stage1.yml"])
        self.assertIn("s5b-stage1.yml", str(caught.exception))

    def test_a_prior_set_with_another_digest_is_refused(self):
        """prior_run якорем не является: task_id кодирует координаты, не байты."""
        from s5b_execution import cli, provenance
        from s5b_execution.identity import load_unit_payloads
        with tempfile.TemporaryDirectory() as tmp:
            _canonical_parts(tmp)
            honest = provenance.digest_of(load_unit_payloads(tmp))
            cli._ledger_from([tmp], honest)          # верный — проходит
            with self.assertRaises(SystemExit) as caught:
                cli._ledger_from([tmp], "deadbeefdeadbeef")
            self.assertIn("приехал не тот прогон", str(caught.exception))

    def test_the_reduced_artifact_carries_the_whole_chain(self):
        """Цепочка провенанса замкнута: вход, выход и чем считали.

        Гейт поведенческий: он ЗАПУСКАЕТ сведение и читает артефакт.
        Текстовая версия искала бы имена полей в исходнике и прошла бы
        мимо подмены, оставившей их на месте, — ровно так сегодня
        проскочила диверсия.
        """
        import os
        from s5b_execution import cli
        env = {"SCIENCE_SHA": "a" * 40, "EXECUTION_SHA": "b" * 40,
               "REQUEST_SHA": "c" * 40}
        keep = {k: os.environ.get(k) for k in env}
        try:
            os.environ.update(env)
            with tempfile.TemporaryDirectory() as tmp:
                _canonical_parts(tmp, endpoints=[
                    _end(KEY_LOW, 0.1, achieved=True, look=4000)])
                cli.main(["reduce", "--look", "4000", "--out", tmp,
                          "--prior-run", "35805206374"])
                got = json.loads((pathlib.Path(tmp) / "reduced.json")
                                 .read_text())["summary"]["provenance"]
        finally:
            for name, value in keep.items():
                os.environ.pop(name, None)
                if value is not None:
                    os.environ[name] = value
        for field in ("science_sha", "execution_sha", "request_sha", "look",
                      "prior_run", "prior_digest", "input_digest",
                      "output_digest"):
            self.assertIn(field, got, field)
        self.assertEqual(got["science_sha"], "a" * 40)
        self.assertEqual(got["prior_run"], "35805206374")
        self.assertTrue(got["input_digest"])
        self.assertTrue(got["output_digest"])


class TheAnchorIsNotSelfReferentialTests(unittest.TestCase):
    """Отпечаток файла X, лежащий в файле Y, петли не образует."""

    def test_a_workflow_that_does_not_match_the_declaration_is_refused(self):
        from s5b_execution import guard
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "wf.yml"
            path.write_text("на: push\n")
            honest = guard.sha256_of(path)
            self.assertEqual(guard.assert_workflow_matches(path, honest),
                             honest)
            path.write_text("на: push\n# правка после объявления\n")
            with self.assertRaises(guard.BoundaryViolated) as caught:
                guard.assert_workflow_matches(path, honest)
            self.assertIn("исполняется не то", str(caught.exception))

    def test_what_the_checks_catch_is_stated_honestly(self):
        """Они закрывают снос по невнимательности, а не злой умысел."""
        from s5b_execution import guard
        self.assertTrue(guard.CATCHES_DRIFT_MAKES_DELIBERATE_CHANGE_VISIBLE)


class TheDigestAnchorsContentNotClaimsTests(unittest.TestCase):
    """`prior_digest` обязан якорить БАЙТЫ, а не чужое слово о байтах."""

    def _part(self, tmp, tamper=False):
        from s5b_execution.identity import recompute_digest
        from simulation import s5b_shard as S
        keys = tuple(scheduler.KEYS)
        unit = S.Unit(arm="armA", look=4000, keys=keys, weight=0.0)
        payload = {"task_id": unit.task_id, "arm": "armA", "look": 4000,
                   "keys": [list(k) for k in keys],
                   "endpoints": [_end(KEY_LOW, 0.1, achieved=True, look=4000)]}
        payload["digest"] = recompute_digest(payload)
        if tamper:
            # содержимое другое, отпечаток — старый правильный
            payload["endpoints"] = [
                _end(KEY_LOW, 0.1, achieved=True, look=4000, point=999.0)]
        payload["seconds"] = 1.0
        payload["peak_rss_mb"] = 1.0
        (pathlib.Path(tmp) / f"{unit.task_id}.json").write_text(
            json.dumps(payload, sort_keys=True))
        return payload

    def test_an_honest_part_recomputes_to_its_stored_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._part(tmp)
            got = load_unit_payloads(tmp)
            self.assertEqual(got[0]["digest"], payload["digest"])

    def test_tampered_endpoints_with_the_old_digest_are_refused(self):
        """Тот самый файл, который прошёл бы обе прежние проверки."""
        with tempfile.TemporaryDirectory() as tmp:
            self._part(tmp, tamper=True)
            with self.assertRaises(ArtifactRefused) as caught:
                load_unit_payloads(tmp)
            self.assertIn("содержимое не то", str(caught.exception))

    def test_runtime_fields_are_outside_the_digest(self):
        """`seconds` и `peak_rss_mb` зависят от раннера, а не от науки."""
        from s5b_execution.identity import CANONICAL_DIGEST_FIELDS
        self.assertNotIn("seconds", CANONICAL_DIGEST_FIELDS)
        self.assertNotIn("peak_rss_mb", CANONICAL_DIGEST_FIELDS)
        self.assertNotIn("digest", CANONICAL_DIGEST_FIELDS)

    def test_the_real_stage1_artifacts_recompute_to_the_declared_digest(self):
        """Заявленный 9e2f5b314e598bb7 проверен ОТ СОДЕРЖИМОГО.

        Прежде и старый CLI, и первая версия `digest_of` складывали
        сохранённые строки `payload["digest"]`. Два пути были независимы
        как функции, но опирались на одни и те же утверждения. Этот гейт
        считает от полей концов.
        """
        import hashlib
        from s5b_execution.identity import recompute_digest
        where = pathlib.Path(
            "/tmp/claude-0/-home-user-relationship-fix/"
            "3a3c202b-1fe4-5131-b65c-c041f8d2cbed/scratchpad/s5b/out")
        if not where.exists():
            self.skipTest("артефакты ступени 4000 недоступны локально")
        parts = load_unit_payloads(where)
        self.assertEqual(len(parts), 156)
        rebuilt = sorted(recompute_digest(p) for p in parts)
        self.assertEqual(
            hashlib.sha256(json.dumps(rebuilt, sort_keys=True)
                           .encode()).hexdigest()[:16],
            "9e2f5b314e598bb7")


class TheScienceNamespaceIsCheckedWholeTests(unittest.TestCase):
    """Две вершины проверять мало: Python соберёт Франкенштейна молча."""

    def test_every_loaded_scientific_module_is_checked(self):
        from s5b_execution import guard
        got = guard.assert_science_comes_from(ROOT / "research/python")
        heads = {name.split(".")[0] for name in got}
        self.assertEqual(heads, set(guard.SCIENCE_NAMESPACES))
        self.assertTrue(any(n.startswith("coarsening.") for n in got),
                        "проверены только simulation.*")
        self.assertGreater(len(got), len(guard.SCIENCE_ENTRY_POINTS))

    def test_a_sibling_prefix_does_not_pass_as_the_root(self):
        """`/tmp/science-evil` начинается с `/tmp/science`.

        Поэтому сравнение идёт через resolve() + is_relative_to, а не
        через строковый префикс.
        """
        from s5b_execution import guard
        src = (ROOT / "execution/s5b_execution/guard.py").read_text()
        self.assertIn("is_relative_to", src)
        self.assertNotIn(".startswith(", src)
        with tempfile.TemporaryDirectory() as tmp:
            sibling = pathlib.Path(tmp) / "research"
            sibling.mkdir()
            with self.assertRaises(guard.BoundaryViolated):
                guard.assert_science_comes_from(sibling)


class TheAncestryIsProvenBeforeTheDiffTests(unittest.TestCase):
    """«Объекта нет» никогда не должно выглядеть как «различий нет»."""

    def _repo(self, tmp):
        import subprocess
        run = lambda *a: subprocess.run(["git", "-C", tmp, *a],
                                        capture_output=True, text=True,
                                        check=True)
        run("init", "-q")
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        (pathlib.Path(tmp) / "a.txt").write_text("1")
        run("add", "-A"); run("commit", "-qm", "first")
        base = run("rev-parse", "HEAD").stdout.strip()
        (pathlib.Path(tmp) / ".github").mkdir(parents=True, exist_ok=True)
        (pathlib.Path(tmp) / "b.txt").write_text("2")
        run("add", "-A"); run("commit", "-qm", "second")
        head = run("rev-parse", "HEAD").stdout.strip()
        return base, head

    def test_a_missing_object_is_refused_not_treated_as_no_difference(self):
        from s5b_execution import guard
        with tempfile.TemporaryDirectory() as tmp:
            self._repo(tmp)
            with self.assertRaises(guard.BoundaryViolated) as caught:
                guard.assert_object_exists(tmp, "0" * 40)
            self.assertIn("история обрезана", str(caught.exception))

    def test_a_non_ancestor_anchor_is_refused(self):
        from s5b_execution import guard
        with tempfile.TemporaryDirectory() as tmp:
            base, head = self._repo(tmp)
            guard.assert_is_ancestor(tmp, base, head)
            with self.assertRaises(guard.BoundaryViolated):
                guard.assert_is_ancestor(tmp, head, base)

    def test_changed_paths_are_read_from_the_real_repository(self):
        from s5b_execution import guard
        with tempfile.TemporaryDirectory() as tmp:
            base, head = self._repo(tmp)
            self.assertEqual(guard.changed_paths(tmp, base, head), ["b.txt"])


class ThreeArmSetsAreNotOneTests(unittest.TestCase):
    """canonical / scheduled / arrived — разные множества."""

    def test_a_scheduled_arm_outside_the_frozen_grid_is_refused(self):
        from s5b_execution import cli
        with self.assertRaises(SystemExit) as caught:
            cli._verify_arms("где-то", [{"arm": "выдуманная"}],
                             {"выдуманная"})
        self.assertIn("вне сетки замороженной науки", str(caught.exception))

    def test_a_scheduled_arm_that_never_arrived_is_refused(self):
        from s5b_execution import cli
        from simulation import s5b_shard as S
        tags = sorted(a["tag"] for a in S.production_arms())[:2]
        with self.assertRaises(SystemExit) as caught:
            cli._verify_arms("где-то", [{"arm": tags[0]}], set(tags))
        self.assertIn("не совпали с запланированными", str(caught.exception))

    def test_an_arm_that_arrived_unscheduled_is_refused(self):
        from s5b_execution import cli
        from simulation import s5b_shard as S
        tags = sorted(a["tag"] for a in S.production_arms())[:2]
        with self.assertRaises(SystemExit) as caught:
            cli._verify_arms("где-то", [{"arm": t} for t in tags], {tags[0]})
        self.assertIn("не совпали с запланированными", str(caught.exception))

    def test_a_settled_arm_absent_from_the_manifest_is_legitimate(self):
        """Рука, все концы которой закрылись, законно не планируется дальше.

        Прежнее требование `arrived == canonical` объявило бы это пропажей.
        После остановки это НОРМАЛЬНАЯ работа реестра, и следующая ступень
        обязана считаться без неё.
        """
        from s5b_execution import cli
        from simulation import s5b_shard as S
        tags = sorted(a["tag"] for a in S.production_arms())
        subset = set(tags[:5])
        cli._verify_arms("где-то", [{"arm": t} for t in subset], subset)


# ---------------------------------------------------------------------------
# Возобновление прерванного прогона
# ---------------------------------------------------------------------------

def _run_manifest(where, units, look=4000, science="a" * 40):
    """Манифест прогона с провенансом, как его пишет `plan`."""
    (pathlib.Path(where) / "manifest.json").write_text(json.dumps({
        "look": look, "shards": 1,
        "units": [{"task_id": u.task_id, "arm": u.arm, "look": look,
                   "shard": 0, "keys": [list(k) for k in u.keys]}
                  for u in units],
        "provenance": {"science_sha": science, "execution_sha": "b" * 40,
                       "request_sha": "c" * 40, "inputs": {},
                       "manifest_digest": "x"}}))


def _two_arms(look=4000):
    from simulation import s5b_shard as S
    keys = tuple(scheduler.KEYS)
    tags = sorted(a["tag"] for a in S.production_arms())[:2]
    return [S.Unit(arm=t, look=look, keys=keys, weight=0.0) for t in tags]


class ResumeIsKeyedByTaskIdTests(unittest.TestCase):
    """Переиспользуется `task_id`, а не номер шарда.

    Номер шарда — решение планировщика: при возобновлении оставшиеся
    юниты перепаковываются как угодно. Привязка к старому номеру сделала
    бы переиспользование заложником раскладки.
    """

    def test_a_complete_part_is_reused(self):
        from s5b_execution import resume
        units = _two_arms()
        with tempfile.TemporaryDirectory() as tmp:
            _run_manifest(tmp, units)
            (pathlib.Path(tmp) / f"{units[0].task_id}.json").write_text(
                json.dumps(_unit(units[0].task_id, units[0].arm, 4000,
                                 [_end(KEY_LOW, 0.1, achieved=True, look=4000)],
                                 units[0].keys)))
            got = resume.completed(tmp, look=4000, science_sha="a" * 40)
            self.assertEqual(set(got), {units[0].task_id})

    def test_a_part_from_another_science_sha_is_refused(self):
        """Склеить два вычисления и выдать за одно нельзя."""
        from s5b_execution import resume
        units = _two_arms()
        with tempfile.TemporaryDirectory() as tmp:
            _run_manifest(tmp, units, science="d" * 40)
            (pathlib.Path(tmp) / f"{units[0].task_id}.json").write_text(
                json.dumps(_unit(units[0].task_id, units[0].arm, 4000, [],
                                 units[0].keys)))
            with self.assertRaises(resume.ResumeRefused) as caught:
                resume.completed(tmp, look=4000, science_sha="a" * 40)
            self.assertIn("разные вычисления", str(caught.exception))

    def test_a_part_not_declared_by_the_manifest_is_refused(self):
        from s5b_execution import resume
        from simulation import s5b_shard as S
        units = _two_arms()
        stray = S.Unit(arm=sorted(a["tag"] for a in S.production_arms())[5],
                       look=4000, keys=tuple(scheduler.KEYS), weight=0.0)
        with tempfile.TemporaryDirectory() as tmp:
            _run_manifest(tmp, units)
            (pathlib.Path(tmp) / f"{stray.task_id}.json").write_text(
                json.dumps(_unit(stray.task_id, stray.arm, 4000, [],
                                 stray.keys)))
            with self.assertRaises(resume.ResumeRefused) as caught:
                resume.completed(tmp, look=4000, science_sha="a" * 40)
            self.assertIn("не объявлена манифестом", str(caught.exception))

    def test_a_part_from_another_look_is_refused(self):
        from s5b_execution import resume
        units = _two_arms()
        with tempfile.TemporaryDirectory() as tmp:
            _run_manifest(tmp, units, look=16_000)
            with self.assertRaises(resume.ResumeRefused):
                resume.completed(tmp, look=4000, science_sha="a" * 40)

    def test_tampered_content_with_the_old_digest_is_refused(self):
        """Диверсия из директивы: payload подменён, отпечаток старый."""
        from s5b_execution import resume
        from s5b_execution.identity import ArtifactRefused, recompute_digest
        units = _two_arms()
        with tempfile.TemporaryDirectory() as tmp:
            _run_manifest(tmp, units)
            good = _unit(units[0].task_id, units[0].arm, 4000,
                         [_end(KEY_LOW, 0.1, achieved=True, look=4000)],
                         units[0].keys)
            keep = good["digest"]
            good["endpoints"] = [_end(KEY_LOW, 0.1, achieved=True, look=4000,
                                      point=999.0)]
            good["digest"] = keep
            (pathlib.Path(tmp) / f"{units[0].task_id}.json").write_text(
                json.dumps(good))
            with self.assertRaises(ArtifactRefused):
                resume.completed(tmp, look=4000, science_sha="a" * 40)

    def test_recomputing_a_reused_unit_is_refused(self):
        """План считал юнит недостающим, хотя он был. Молчать нельзя."""
        from s5b_execution import resume
        a = {"t1": {"task_id": "t1"}}
        with self.assertRaises(resume.ResumeRefused) as caught:
            resume.merge_parts(a, {"t1": {"task_id": "t1"}})
        self.assertIn("посчитаны заново", str(caught.exception))
        self.assertEqual(set(resume.merge_parts(a, {"t2": {}})), {"t1", "t2"})


class FullRunEqualsPartialPlusResumeTests(unittest.TestCase):
    """Итог возобновления обязан совпасть с непрерывным прогоном."""

    def _parts(self, units, where):
        out = {}
        for i, u in enumerate(units):
            ends = [_end(KEY_LOW, 0.1, achieved=True, look=4000,
                         point=100.0 + i),
                    _end(KEY_LOW, 0.01, achieved=False, look=None)]
            out[u.task_id] = _unit(u.task_id, u.arm, 4000, ends, u.keys)
        return out

    def test_the_ledger_and_digest_are_identical(self):
        from s5b_execution import resume
        from s5b_execution.ledger import Ledger
        units = _two_arms()
        with tempfile.TemporaryDirectory() as tmp:
            parts = self._parts(units, tmp)
            whole = Ledger()
            whole.absorb(4000, list(parts.values()))

            # частичный прогон: посчитан первый юнит; возобновление — второй
            reused = {units[0].task_id: parts[units[0].task_id]}
            fresh = {units[1].task_id: parts[units[1].task_id]}
            joined = resume.merge_parts(reused, fresh)
            after = Ledger()
            after.absorb(4000, list(joined.values()))

            self.assertEqual(whole.digest(), after.digest())
            self.assertEqual(whole.settled_count(), after.settled_count())
            self.assertEqual(
                {k: v for k, v in whole.finalise(4000).items()},
                {k: v for k, v in after.finalise(4000).items()})

    def test_the_order_of_reuse_does_not_change_the_result(self):
        """Переупаковка оставшихся юнитов в другие шарды ничего не меняет."""
        from s5b_execution.ledger import Ledger
        units = _two_arms()
        with tempfile.TemporaryDirectory() as tmp:
            parts = self._parts(units, tmp)
            one, two = Ledger(), Ledger()
            one.absorb(4000, [parts[units[0].task_id],
                              parts[units[1].task_id]])
            two.absorb(4000, [parts[units[1].task_id],
                              parts[units[0].task_id]])
            self.assertEqual(one.digest(), two.digest())


class CheckpointCarriesTheEarlyTauTests(unittest.TestCase):
    """Блокер 64000: сырые части 16000 не содержат концов с tau = 4000."""

    def _ledger(self):
        from s5b_execution.ledger import Ledger
        early = _unit("u1", "armT", 4000, [
            _end(KEY_LOW, 0.1, achieved=True, look=4000, point=100.0),
            _end(KEY_LOW, 0.01, achieved=False, look=None)])
        late = _unit("u1", "armT", 16_000, [
            # тот же конец: другое значение И потеря точности
            _end(KEY_LOW, 0.1, achieved=False, look=None),
            _end(KEY_LOW, 0.01, achieved=True, look=16_000, point=50.0)])
        led = Ledger()
        led.absorb(4000, [early])
        led.absorb(16_000, [late])
        return led

    def test_a_roundtrip_keeps_the_payload_and_the_tau(self):
        from s5b_execution.ledger import Ledger
        led = self._ledger()
        cp = led.to_checkpoint(canonical_arms={"armT"}, provenance={})
        back = Ledger.from_checkpoint(cp)
        got = back.finalise(16_000)[EndpointId("armT", tuple(KEY_LOW), 0.1)]
        self.assertEqual(got["look"], 4000, "ранний tau потерян в чекпойнте")
        self.assertEqual(got["point"], 100.0)
        self.assertEqual(back.digest(), led.digest())

    def test_the_next_look_builds_on_the_checkpoint(self):
        """Чекпойнт 16000 + сырые 64000 -> ранний tau всё ещё 4000."""
        from s5b_execution.ledger import Ledger
        cp = self._ledger().to_checkpoint(canonical_arms={"armT"},
                                          provenance={})
        back = Ledger.from_checkpoint(cp)
        back.absorb(64_000, [_unit("u1", "armT", 64_000, [
            _end(KEY_LOW, 0.1, achieved=True, look=64_000, point=7.0),
            _end(KEY_LOW, 0.01, achieved=True, look=64_000, point=8.0)])])
        final = back.finalise(64_000)
        self.assertEqual(final[EndpointId("armT", tuple(KEY_LOW), 0.1)]["look"],
                         4000)
        self.assertEqual(final[EndpointId("armT", tuple(KEY_LOW), 0.1)]["point"],
                         100.0)
        self.assertEqual(final[EndpointId("armT", tuple(KEY_LOW), 0.01)]["look"],
                         16_000)

    def test_a_checkpoint_whose_digest_disagrees_is_refused(self):
        from s5b_execution.ledger import Ledger, LedgerRefused
        cp = self._ledger().to_checkpoint(canonical_arms={"armT"},
                                          provenance={})
        cp["settled"][0]["payload"]["point"] = 12345.0
        with self.assertRaises(LedgerRefused) as caught:
            Ledger.from_checkpoint(cp)
        self.assertIn("отпечаток", str(caught.exception))

    def test_an_unknown_checkpoint_version_is_refused(self):
        from s5b_execution.ledger import Ledger, LedgerRefused
        with self.assertRaises(LedgerRefused):
            Ledger.from_checkpoint({"version": 99})


# ---------------------------------------------------------------------------
# Адверсариальный аудит возобновления и чекпойнта.
#
# Сценарии подбирались НЕ для подтверждения, а для поломки: каждый описывает
# способ, которым прерванный прогон мог бы тихо испортить науку.
# ---------------------------------------------------------------------------

def _payload(unit, look=4000, point=100.0, achieved=True):
    ends = [_end(KEY_LOW, 0.1, achieved=achieved, look=look, point=point),
            _end(KEY_LOW, 0.01, achieved=False, look=None)]
    return _unit(unit.task_id, unit.arm, look, ends, unit.keys)


def _n_arms(n, look=4000):
    from simulation import s5b_shard as S
    keys = tuple(scheduler.KEYS)
    tags = sorted(a["tag"] for a in S.production_arms())[:n]
    return [S.Unit(arm=t, look=look, keys=keys, weight=0.0) for t in tags]


class ResumeAdversarialTests(unittest.TestCase):
    """Попытки сломать переиспользование."""

    def test_the_filesystem_cannot_hold_two_copies_of_one_task_id(self):
        """Дубликат с ОДИНАКОВЫМ содержимым невозможен по построению.

        Файл называется своим `task_id`, поэтому каталог физически не
        удержит две копии. При `merge-multiple` вторая перезаписывает
        первую. Записано тестом, чтобы проверка на дубликат в
        `resume.completed` не считалась защитой от того, чего не бывает.
        """
        from s5b_execution import resume
        units = _n_arms(1)
        with tempfile.TemporaryDirectory() as tmp:
            _run_manifest(tmp, units)
            path = pathlib.Path(tmp) / f"{units[0].task_id}.json"
            path.write_text(json.dumps(_payload(units[0], point=1.0)))
            path.write_text(json.dumps(_payload(units[0], point=2.0)))
            got = resume.completed(tmp, look=4000, science_sha="a" * 40)
            self.assertEqual(len(got), 1)
            self.assertEqual(got[units[0].task_id]["endpoints"][0]["point"],
                             2.0)

    def test_a_conflicting_duplicate_is_refused_where_it_can_occur(self):
        """Там, где дубликат ВОЗМОЖЕН — при слиянии частей — он отказ."""
        from s5b_execution import resume
        units = _n_arms(1)
        a = _payload(units[0], point=1.0)
        b = _payload(units[0], point=2.0)
        with self.assertRaises(resume.ResumeRefused):
            resume.merge_parts({units[0].task_id: a}, {units[0].task_id: b})

    def test_correct_parts_with_a_tampered_manifest_are_refused(self):
        """Манифест подменён, части настоящие. Координаты разойдутся."""
        from s5b_execution import resume
        units = _n_arms(2)
        with tempfile.TemporaryDirectory() as tmp:
            _run_manifest(tmp, units)
            m = json.loads((pathlib.Path(tmp) / "manifest.json").read_text())
            m["units"][0]["keys"] = [list(scheduler.KEYS[0])]   # обрезан
            (pathlib.Path(tmp) / "manifest.json").write_text(json.dumps(m))
            (pathlib.Path(tmp) / f"{units[0].task_id}.json").write_text(
                json.dumps(_payload(units[0])))
            with self.assertRaises(resume.ResumeRefused) as caught:
                resume.completed(tmp, look=4000, science_sha="a" * 40)
            self.assertIn("координаты", str(caught.exception))

    def test_a_reused_part_from_another_execution_sha_is_allowed(self):
        """EXECUTION_SHA науку не определяет — значит не запрещает.

        Допустимость держится на трёх вещах: тот же SCIENCE_SHA, те же
        научные координаты, сошедшийся отпечаток содержимого. Слой
        исполнения в этот список не входит намеренно: иначе любая правка
        планировщика обесценивала бы посчитанное.
        """
        from s5b_execution import resume
        units = _n_arms(1)
        with tempfile.TemporaryDirectory() as tmp:
            _run_manifest(tmp, units)          # execution_sha = "b"*40
            m = json.loads((pathlib.Path(tmp) / "manifest.json").read_text())
            m["provenance"]["execution_sha"] = "9" * 40      # другой слой
            (pathlib.Path(tmp) / "manifest.json").write_text(json.dumps(m))
            (pathlib.Path(tmp) / f"{units[0].task_id}.json").write_text(
                json.dumps(_payload(units[0])))
            got = resume.completed(tmp, look=4000, science_sha="a" * 40)
            self.assertEqual(set(got), {units[0].task_id})

    def test_the_origin_of_reused_parts_is_preserved(self):
        """Провенанс обязан помнить, откуда взята переиспользованная часть."""
        from s5b_execution import resume
        units = _n_arms(1)
        with tempfile.TemporaryDirectory() as tmp:
            _run_manifest(tmp, units)
            (pathlib.Path(tmp) / f"{units[0].task_id}.json").write_text(
                json.dumps(_payload(units[0])))
            got = resume.origin(tmp, look=4000, science_sha="a" * 40)
            self.assertEqual(got["reused"], 1)
            self.assertEqual(got["from_execution_sha"], "b" * 40)
            self.assertEqual(got["from_science_sha"], "a" * 40)
            self.assertTrue(got["parts_digest"])


class TwoInterruptionsGiveTheSameScienceTests(unittest.TestCase):
    """АРИФМЕТИКА слияния и реестра — и только она.

    Этот класс НЕ доказывает, что цепочка прогонов даёт ту же науку:
    он собирает реестр вручную из `merge_parts` и `Ledger`, минуя
    `plan`/`reduce`. Именно поэтому он оставался зелёным, пока
    настоящий конвейер на тех же данных ОТКАЗЫВАЛ: сведение сверяет
    приехавшее с манифестом своего прогона, а продолжение объявляет
    лишь остаток. Свойство цепочки доказывается в
    `ChainThroughTheCliTests`, через CLI и на всех 156 юнитах.
    """

    def _split(self, units, sizes):
        parts = {u.task_id: _payload(u, point=100.0 + i)
                 for i, u in enumerate(units)}
        ids = sorted(parts)
        out, at = [], 0
        for n in sizes:
            out.append({t: parts[t] for t in ids[at:at + n]})
            at += n
        self.assertEqual(at, len(ids))
        return parts, out

    def test_three_runs_equal_one(self):
        from s5b_execution import resume
        from s5b_execution.ledger import Ledger
        units = _n_arms(10)
        parts, chunks = self._split(units, [2, 3, 5])

        whole = Ledger()
        whole.absorb(4000, list(parts.values()))

        joined: dict = {}
        checkpoints = []
        for chunk in chunks:
            joined = resume.merge_parts(joined, chunk)
            step = Ledger()
            step.absorb(4000, list(joined.values()))
            checkpoints.append(step.to_checkpoint(
                canonical_arms={u.arm for u in units}, provenance={}))

        self.assertEqual(whole.digest(), checkpoints[-1]["ledger_digest"])
        after = Ledger.from_checkpoint(checkpoints[-1])
        self.assertEqual(whole.finalise(4000), after.finalise(4000))

    def test_every_intermediate_checkpoint_round_trips(self):
        from s5b_execution import resume
        from s5b_execution.ledger import Ledger
        units = _n_arms(10)
        parts, chunks = self._split(units, [2, 3, 5])
        joined: dict = {}
        for chunk in chunks:
            joined = resume.merge_parts(joined, chunk)
            step = Ledger()
            step.absorb(4000, list(joined.values()))
            cp = step.to_checkpoint(canonical_arms={u.arm for u in units},
                                    provenance={})
            self.assertEqual(Ledger.from_checkpoint(cp).digest(),
                             step.digest())

    def test_the_order_of_the_chunks_does_not_matter(self):
        from s5b_execution import resume
        from s5b_execution.ledger import Ledger
        units = _n_arms(10)
        parts, chunks = self._split(units, [2, 3, 5])
        a, b = {}, {}
        for c in chunks:
            a = resume.merge_parts(a, c)
        for c in reversed(chunks):
            b = resume.merge_parts(b, c)
        one, two = Ledger(), Ledger()
        one.absorb(4000, list(a.values()))
        two.absorb(4000, list(b.values()))
        self.assertEqual(one.digest(), two.digest())


class CheckpointTravelsTests(unittest.TestCase):
    """Чекпойнт переносится между каталогами и машинами."""

    def test_moving_the_file_does_not_change_the_science(self):
        from s5b_execution.ledger import Ledger
        units = _n_arms(3)
        led = Ledger()
        led.absorb(4000, [_payload(u, point=100.0 + i)
                          for i, u in enumerate(units)])
        cp = led.to_checkpoint(canonical_arms={u.arm for u in units},
                               provenance={"inputs": {"/where/it/ran": "d0"}})
        with tempfile.TemporaryDirectory() as one, \
                tempfile.TemporaryDirectory() as two:
            (pathlib.Path(one) / "checkpoint.json").write_text(
                json.dumps(cp, sort_keys=True))
            moved = json.loads(
                (pathlib.Path(one) / "checkpoint.json").read_text())
            (pathlib.Path(two) / "checkpoint.json").write_text(
                json.dumps(moved, sort_keys=True))
            back = Ledger.from_checkpoint(json.loads(
                (pathlib.Path(two) / "checkpoint.json").read_text()))
        self.assertEqual(back.digest(), led.digest())
        self.assertEqual(back.finalise(4000), led.finalise(4000))

    def test_a_settled_arm_absent_next_look_survives_the_round_trip(self):
        """Рука закрылась целиком, на следующей ступени её нет вовсе."""
        from s5b_execution.ledger import Ledger
        from simulation import s5b_shard as S
        keys = tuple(scheduler.KEYS)
        tags = sorted(a["tag"] for a in S.production_arms())[:2]
        gone = S.Unit(arm=tags[0], look=4000, keys=keys, weight=0.0)
        stays = S.Unit(arm=tags[1], look=4000, keys=keys, weight=0.0)
        led = Ledger()
        led.absorb(4000, [
            _unit(gone.task_id, gone.arm, 4000, [
                _end(KEY_LOW, 0.1, achieved=True, look=4000, point=7.0),
                _end(KEY_LOW, 0.01, achieved=True, look=4000, point=8.0)],
                gone.keys),
            _payload(stays, point=50.0)])
        cp = led.to_checkpoint(canonical_arms=set(tags), provenance={})
        back = Ledger.from_checkpoint(cp)
        # следующая ступень: закрывшейся руки НЕТ, приезжает только вторая
        nxt = S.Unit(arm=tags[1], look=16_000, keys=keys, weight=0.0)
        back.absorb(16_000, [_unit(nxt.task_id, nxt.arm, 16_000, [
            _end(KEY_LOW, 0.1, achieved=True, look=16_000, point=999.0),
            _end(KEY_LOW, 0.01, achieved=True, look=16_000, point=5.0)],
            nxt.keys)])
        final = back.finalise(16_000)
        self.assertEqual(final[EndpointId(tags[0], tuple(KEY_LOW), 0.1)]["point"],
                         7.0, "закрывшаяся рука потеряна вместе с ранним tau")
        self.assertEqual(final[EndpointId(tags[1], tuple(KEY_LOW), 0.1)]["look"],
                         4000, "ранний tau второй руки подменён поздним")
        self.assertEqual(final[EndpointId(tags[1], tuple(KEY_LOW), 0.01)]["look"],
                         16_000)


class TheOriginIsActuallyWiredIntoTheArtefactTests(unittest.TestCase):
    """Функция работает — этого мало. Она должна быть ПОДКЛЮЧЕНА.

    Предыдущая версия проверяла `resume.origin()` напрямую, и диверсия,
    удалившая строку `"reused": reuse_origin,` из провенанса, прошла
    незамеченной: функция осталась рабочей, артефакт — безголосым. Тот же
    класс, на котором сегодня уже горел `merge_arm`.
    """

    def test_a_resumed_reduce_records_where_the_parts_came_from(self):
        import os
        from s5b_execution import cli
        env = {"SCIENCE_SHA": "a" * 40, "EXECUTION_SHA": "e" * 40,
               "REQUEST_SHA": "c" * 40}
        keep = {k: os.environ.get(k) for k in env}
        try:
            os.environ.update(env)
            with tempfile.TemporaryDirectory() as old, \
                    tempfile.TemporaryDirectory() as new:
                rows = _canonical_parts(old, endpoints=[
                    _end(KEY_LOW, 0.1, achieved=True, look=4000)])
                # половина остаётся в старом прогоне, половина в новом
                ids = sorted(r["task_id"] for r in rows)
                half = len(ids) // 2
                shutil = __import__("shutil")
                shutil.copy(pathlib.Path(old) / "manifest.json",
                            pathlib.Path(new) / "manifest.json")
                for t in ids[half:]:
                    shutil.move(str(pathlib.Path(old) / f"{t}.json"),
                                str(pathlib.Path(new) / f"{t}.json"))
                cli.main(["reduce", "--look", "4000", "--resume", old,
                          "--out", new])
                got = json.loads((pathlib.Path(new) / "reduced.json")
                                 .read_text())["summary"]["provenance"]
        finally:
            for name, value in keep.items():
                os.environ.pop(name, None)
                if value is not None:
                    os.environ[name] = value
        self.assertIn("reused", got, "артефакт не помнит происхождения частей")
        self.assertEqual(got["reused"]["reused"], half)
        self.assertEqual(got["reused"]["from_science_sha"], "a" * 40)
        self.assertTrue(got["reused"]["parts_digest"])


# --- ЦЕПОЧКА ПРОГОНОВ ЧЕРЕЗ CLI ----------------------------------------
#
# Прежний «главный» тест сравнивал реестры, собранные вручную из
# `merge_parts` и `Ledger`. Он был ЗЕЛЁНЫМ И ЛОЖНЫМ: настоящий конвейер
# в той же ситуации отказывался, потому что сведение сверяет приехавшее
# с манифестом ЭТОГО прогона, а прогон-продолжение объявляет лишь
# остаток. Проверялась арифметика слияния, а не механизм. Тот же класс
# ошибки, на котором уже горели `merge_arm` и `resume.origin`.

@contextlib.contextmanager
def _chain_env():
    names = {"SCIENCE_SHA": "a" * 40, "EXECUTION_SHA": "b" * 40,
             "REQUEST_SHA": "c" * 40}
    keep = {k: os.environ.get(k) for k in names}
    os.environ.update(names)
    try:
        yield
    finally:
        for name, value in keep.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value


def _cli(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.main(argv)
    return buf.getvalue()


def _plan(out, resume_dir=""):
    argv = ["plan", "--look", "4000", "--out", str(out)]
    if resume_dir:
        argv += ["--resume", str(resume_dir)]
    return json.loads(_cli(argv).strip().splitlines()[-1])


def _reduce(out, resume_dir=""):
    argv = ["reduce", "--look", "4000", "--out", str(out)]
    if resume_dir:
        argv += ["--resume", str(resume_dir)]
    _cli(argv)
    return json.loads((pathlib.Path(out) / "reduced.json").read_text())


def _compute(manifest_path, out, only=None):
    """Подмена вычисления: наука здесь не проверяется, проверяется механика."""
    from s5b_execution.identity import recompute_digest
    rows = sorted(json.loads(pathlib.Path(manifest_path).read_text())["units"],
                  key=lambda r: r["task_id"])
    if only is not None:
        rows = rows[:only]
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for row in rows:
        base = 100.0 + (int(row["task_id"][:6], 16) % 97)
        ends = [{"key": list(key), "fraction": scheduler.FRACTIONS[0],
                 "point": base, "low": base - 1.0, "high": base + 1.0,
                 "radius": 1.0, "status": ACHIEVED, "look": row["look"]}
                for key in row["keys"]]
        payload = {"task_id": row["task_id"], "arm": row["arm"],
                   "look": row["look"], "keys": row["keys"], "endpoints": ends}
        payload["digest"] = recompute_digest(payload)
        (out / f"{row['task_id']}.json").write_text(
            json.dumps(payload, sort_keys=True))
    return [r["task_id"] for r in rows]


def _run_chain(root, shares, whole_chain=True):
    """Цепочка прогонов. `whole_chain` — видит ли следующий прогон ВСЮ
    цепочку (части всех прогонов плюс манифест первого) или только
    предыдущий прогон."""
    root = pathlib.Path(root)
    res = root / "resumed"
    dirs, done, total = [], 0, None

    def refill(upto):
        if res.exists():
            shutil.rmtree(res)
        res.mkdir(parents=True)
        srcs = dirs[:upto] if whole_chain else dirs[upto - 1:upto]
        for src in srcs:
            for f in src.glob("*.json"):
                if f.name != "manifest.json":
                    shutil.copy(f, res / f.name)
        shutil.copy((dirs[0] if whole_chain else dirs[upto - 1]) / "manifest.json",
                    res / "manifest.json")

    for i, share in enumerate(shares):
        d = root / f"run{i}"
        d.mkdir(parents=True, exist_ok=True)
        if i:
            refill(i)
        got = _plan(d, resume_dir=res if i else "")
        if total is None:
            total = got["units"]
        ids = _compute(d / "manifest.json", d,
                       None if i == len(shares) - 1 else int(total * share))
        done += len(ids)
        dirs.append(d)
    return dirs[-1], res, done, total


class ChainThroughTheCliTests(unittest.TestCase):
    """Один непрерывный прогон против цепочки прерванных — ЧЕРЕЗ CLI.

    Сверяется всё, чем ступень отчитывается: реестр, ранний `tau`
    каждого конца, ячейки и научный отпечаток выхода. Проход идёт по
    настоящему `plan`/`reduce` на всех 156 юнитах сетки.
    """

    #: эталон считается ОДИН раз на класс: он одинаков для всех разбиений,
    #: а 156 юнитов сетки — не та цена, чтобы платить её дважды
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        with _chain_env():
            whole = pathlib.Path(cls._tmp.name) / "whole"
            cls.total = _plan(whole)["units"]
            _compute(whole / "manifest.json", whole)
            cls.ref = _reduce(whole)
            cls.ref_dir = whole

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _same(self, ref, got, where):
        self.assertEqual(got["summary"]["ledger_digest"],
                         ref["summary"]["ledger_digest"], f"{where}: реестр")
        self.assertEqual(got["summary"]["provenance"]["output_digest"],
                         ref["summary"]["provenance"]["output_digest"],
                         f"{where}: научный отпечаток выхода")
        self.assertEqual(got["cells"], ref["cells"], f"{where}: ячейки")

    def _same_tau(self, ref_dir, got_dir, where):
        a = json.loads((pathlib.Path(ref_dir) / "checkpoint.json").read_text())
        b = json.loads((pathlib.Path(got_dir) / "checkpoint.json").read_text())
        self.assertEqual({json.dumps(r["id"], sort_keys=True): r["tau"]
                          for r in a["settled"]},
                         {json.dumps(r["id"], sort_keys=True): r["tau"]
                          for r in b["settled"]},
                         f"{where}: ранний tau разошёлся")

    def _chain(self, name, shares):
        with _chain_env(), tempfile.TemporaryDirectory() as tmp:
            last, res, done, total = _run_chain(tmp, shares)
            self.assertEqual(total, self.total)
            self.assertEqual(done, self.total,
                             f"{name}: цепочка пересчитала уже посчитанное "
                             f"либо потеряла часть работы")
            got = _reduce(last, resume_dir=res)
            self._same(self.ref, got, name)
            self._same_tau(self.ref_dir, last, name)

    def test_a_two_part_chain_gives_the_same_science(self):
        self._chain("две части", [0.5, 0.5])

    def test_a_three_part_chain_gives_the_same_science(self):
        """Реальная эксплуатация после 23 сентября: не одна остановка, а две."""
        self._chain("три части", [0.2, 0.35, 0.45])


class TheChainMustBeWholeTests(unittest.TestCase):
    """Указание на один прогон цепочки — отказ, и ДО вычисления.

    Прогон-продолжение объявляет остаток. Если указать возобновление на
    него, работа более раннего прогона не видна: трёхчастная цепочка
    планировала 102 юнита вместо 71 и молча считала заново то, что уже
    было посчитано. Молча — худшее из возможных поведений.
    """

    def test_pointing_at_a_continuation_is_refused_at_plan(self):
        with _chain_env(), tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as caught:
                _run_chain(pathlib.Path(tmp) / "cut", [0.2, 0.35, 0.45],
                           whole_chain=False)
            self.assertIn("это продолжение, а не начало", str(caught.exception))

    def test_reduce_refuses_a_truncated_chain_on_its_own(self):
        """Гейт плана — не единственный: сведение тоже обязано отказать.

        Объявленное ступенью = манифест этого прогона плюс манифест
        цепочки, и объединение держится гейтом «продолжение объявляет
        ПОДМНОЖЕСТВО». Если цепочка обрезана, подмножеством оно быть
        перестаёт, и сведение отказывает даже там, где план обошли.
        """
        with _chain_env(), tempfile.TemporaryDirectory() as tmp:
            first = pathlib.Path(tmp) / "first"
            _plan(first)
            _compute(first / "manifest.json", first, only=80)
            res = pathlib.Path(tmp) / "resumed"
            res.mkdir()
            for f in first.glob("*.json"):
                shutil.copy(f, res / f.name)
            second = pathlib.Path(tmp) / "second"
            second.mkdir()
            _plan(second, resume_dir=res)
            _compute(second / "manifest.json", second)
            # цепочку обрезали: её манифест стал объявлять лишь часть
            m = json.loads((res / "manifest.json").read_text())
            m["units"] = m["units"][:100]
            (res / "manifest.json").write_text(json.dumps(m))
            with self.assertRaises(SystemExit) as caught:
                _reduce(second, resume_dir=res)
            self.assertIn("которых нет в манифесте цепочки",
                          str(caught.exception))
