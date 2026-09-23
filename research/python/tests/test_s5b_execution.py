"""Гейты слоя ИСПОЛНЕНИЯ: свой `tau` у каждого конца.

Слой лежит отдельным деревом (`execution/`), потому что в производстве он
приезжает ДРУГИМ checkout'ом, нежели наука. Здесь это дерево кладётся на
путь явно: единственный шов, и он назван вслух, а не спрятан в конфиг.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "execution") not in sys.path:
    sys.path.insert(0, str(ROOT / "execution"))

from s5b_execution import cost, provenance, reduction, scheduler   # noqa: E402
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
    return {"task_id": task_id, "arm": arm, "look": look,
            "keys": [list(k) for k in keys], "endpoints": endpoints,
            "digest": f"d{task_id}"}


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

    def test_the_budget_sits_below_the_breached_one(self):
        """4.0 пробит фактом 4.188 на первой же производственной ступени."""
        self.assertLess(cost.SHARD_BUDGET_HOURS, 4.0)
        self.assertLess(cost.SHARD_BUDGET_HOURS, cost.PLATFORM_CAP_HOURS)
        self.assertGreaterEqual(cost.BUDGET_HEADROOM,
                                cost.OBSERVED_RUNNER_SPREAD)

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

        Вывести ожидаемое из полученного значило бы сравнить набор сам с
        собой: проверка полноты проходила бы всегда. Гейт поведенческий
        намеренно — его текстовая версия диверсию ПРОПУСТИЛА, потому что
        подмена оставила docstring на месте.
        """
        from s5b_execution import cli
        from simulation import s5b_shard as S
        keys = tuple(scheduler.KEYS)
        came = S.Unit(arm="armA", look=4000, keys=keys, weight=0.0)
        never = S.Unit(arm="armB", look=4000, keys=keys, weight=0.0)
        with tempfile.TemporaryDirectory() as tmp:
            where = pathlib.Path(tmp)
            (where / "manifest.json").write_text(json.dumps({
                "look": 4000, "shards": 1, "units": [
                    {"task_id": u.task_id, "arm": u.arm, "look": 4000,
                     "shard": 0, "keys": [list(k) for k in keys]}
                    for u in (came, never)]}))
            (where / f"{came.task_id}.json").write_text(json.dumps(
                {"task_id": came.task_id, "arm": "armA", "look": 4000,
                 "keys": [list(k) for k in keys], "endpoints": [],
                 "digest": "d0"}))
            payloads = load_unit_payloads(where)
            self.assertEqual(len(payloads), 1)
            with self.assertRaises(Exception) as caught:
                cli._verify_with_frozen_merge(where, 4000, payloads)
            self.assertIn("не хватает юнитов", str(caught.exception))
