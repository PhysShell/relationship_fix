"""Гейты production-shaped пилота ступени 64000.

Юниты пилота обязаны совпадать с тем, что исполнит полная ступень при
смежной раскладке; порядок ключей на честном слове не принимается.
Вердикт проверяется на частях в формате `cli run`, собранных здесь с
ИЗВЕСТНЫМ содержимым — каждая ветка FAIL обязана сработать.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "execution") not in sys.path:
    sys.path.insert(0, str(ROOT / "execution"))

from simulation import s5b_shard as S                           # noqa: E402

from s5b_execution import cli, cost, layout as L, pilot as P     # noqa: E402
from s5b_execution.identity import (ACHIEVED, INSUFFICIENT,      # noqa: E402
                                    recompute_digest)
from s5b_execution.scheduler import FRACTIONS, KEYS, key_slices  # noqa: E402

SCIENCE = "7a62a3911f8bc000cf08ad97f76c0f962b07e615"
ENV = {"SCIENCE_SHA": SCIENCE, "EXECUTION_SHA": "a" * 40,
       "REQUEST_SHA": "b" * 40}
BUDGET = cost.SHARD_BUDGET_HOURS * 3600.0


class ThePilotUnitsAreTheProductionUnitsTests(unittest.TestCase):

    def test_g12_is_the_three_balanced_groups_of_the_heaviest_block(self):
        got = P.units(P.PILOT_ARM, 64000, 12, 60.0)
        want = [S.Unit(arm=P.PILOT_ARM, look=64000, keys=tuple(s), weight=0.0)
                for s in L.balanced_slices(12)[9:12]]
        self.assertEqual([u.task_id for u in got], [u.task_id for u in want])
        for u in got:
            self.assertEqual(len(u.keys), 6)
            self.assertEqual({k[0] for k in u.keys}, {60.0})
            self.assertEqual(L.counts(u.keys), {"days": [2, 2, 2],
                                                "horizon": [2, 2, 2],
                                                "maximise": [3, 3]})

    def test_the_contiguous_layout_is_refused_as_confounded(self):
        """Смежные группы блока — чистые уровни days: пилот их не примет."""
        with mock.patch.object(P, "balanced_slices", key_slices):
            with self.assertRaisesRegex(P.PilotRefused, "не сбалансирована"):
                P.units(P.PILOT_ARM, 64000, 12, 60.0)

    def test_the_fallback_g24_is_six_slices_of_three(self):
        got = P.units(P.PILOT_ARM, 64000, 24, 60.0)
        self.assertEqual([len(u.keys) for u in got], [3] * 6)
        flat = [k for u in got for k in u.keys]
        self.assertEqual(sorted(flat), sorted(k for k in KEYS if k[0] == 60.0))

    def test_only_the_two_declared_sizes_are_allowed(self):
        for groups in (1, 4, 36, 72):
            with self.assertRaises(P.PilotRefused, msg=groups):
                P.units(P.PILOT_ARM, 64000, groups, 60.0)

    def test_only_the_real_look_is_allowed(self):
        for look in (4000, 16000):
            with self.assertRaises(P.PilotRefused, msg=look):
                P.units(P.PILOT_ARM, look, 12, 60.0)

    def test_an_unknown_arm_or_block_is_refused(self):
        with self.assertRaises(P.PilotRefused):
            P.units("r0:c0:R9:m0", 64000, 12, 60.0)
        with self.assertRaises(P.PilotRefused):
            P.units(P.PILOT_ARM, 64000, 12, 7.0)

    def test_a_slicing_that_mixes_blocks_is_refused_not_trusted(self):
        """Порядок KEYS сдвинут на три ключа: группа блока тянет чужой δ."""
        def shifted(groups):
            order = KEYS[3:] + KEYS[:3]
            size = len(KEYS) // groups
            return tuple(tuple(order[i:i + size])
                         for i in range(0, len(order), size))
        with mock.patch.object(P, "balanced_slices", shifted):
            with self.assertRaisesRegex(P.PilotRefused, "содержит и δ"):
                P.units(P.PILOT_ARM, 64000, 12, 60.0)

    def test_overlapping_slices_are_refused(self):
        def overlapping(groups):
            s = list(L.balanced_slices(groups))
            s[10] = s[9]
            return tuple(s)
        with mock.patch.object(P, "balanced_slices", overlapping):
            with self.assertRaisesRegex(P.PilotRefused, "пересекаются"):
                P.units(P.PILOT_ARM, 64000, 12, 60.0)


class TheBalancedLayoutIsFrozenTests(unittest.TestCase):
    """Комбинаторика раскладок закреплена тестом, а не устным mod 3."""

    DAYS = sorted({k[1] for k in KEYS})
    HORIZONS = sorted({k[2] for k in KEYS})

    def _index(self, key):
        return (self.DAYS.index(key[1]), self.HORIZONS.index(key[2]),
                int(key[3]))

    def test_g12_is_d_plus_h_plus_x_mod_3_inside_each_block(self):
        slices = L.balanced_slices(12)
        for b, delta in enumerate(sorted({k[0] for k in KEYS})):
            for local in range(3):
                got = set(slices[3 * b + local])
                want = {k for k in KEYS if k[0] == delta
                        and sum(self._index(k)) % 3 == local}
                self.assertEqual(got, want, (delta, local))

    def test_g24_is_the_frozen_fallback_formula(self):
        slices = L.balanced_slices(24)
        for b, delta in enumerate(sorted({k[0] for k in KEYS})):
            for local in range(6):
                r, bit = divmod(local, 2)
                want = set()
                for k in KEYS:
                    if k[0] != delta:
                        continue
                    d, h, x = self._index(k)
                    if (h - d) % 3 == r and (x ^ (d % 2)) == bit:
                        want.add(k)
                self.assertEqual(set(slices[6 * b + local]), want, (delta, local))

    def test_every_group_is_balanced_and_inside_one_delta(self):
        for groups, size in ((12, 6), (24, 3)):
            slices = L.balanced_slices(groups)
            self.assertEqual(len(slices), groups)
            flat = [k for s in slices for k in s]
            self.assertEqual(sorted(flat), sorted(KEYS))
            for s in slices:
                self.assertEqual(len(s), size)
                self.assertEqual(len({k[0] for k in s}), 1)
                self.assertEqual(P._imbalance(s, groups), "", s)

    def test_the_fallback_splits_maximise_three_one_way_three_the_other(self):
        slices = L.balanced_slices(24)
        for b in range(4):
            got = sorted(tuple(L.counts(s)["maximise"]) for s in slices[6 * b:6 * b + 6])
            self.assertEqual(got, [(1, 2)] * 3 + [(2, 1)] * 3)

    def test_the_pair_count_is_that_of_the_contiguous_layout(self):
        """Лишнего to_bins нет: пар (группа, δ) столько же, сколько групп."""
        for groups in (12, 24):
            slices = L.balanced_slices(groups)
            self.assertEqual(sum(len({k[0] for k in s}) for s in slices), groups)

    def test_each_axis_of_the_balance_is_checked_on_its_own(self):
        block = [k for k in KEYS if k[0] == 60.0]
        idx = {k: self._index(k) for k in block}
        # days 2/2/2, но все шесть — один горизонт
        one_horizon = [k for k in block if idx[k][1] == 0]
        self.assertIn("horizon", P._imbalance(one_horizon, 12))
        # days и horizon 2/2/2, но maximise 6/0
        one_side = [k for k in block if idx[k][2] == 0
                    and (idx[k][0] + idx[k][1]) % 3 in (0, 1)]
        self.assertEqual(L.counts(one_side)["days"], [2, 2, 2])
        self.assertEqual(L.counts(one_side)["horizon"], [2, 2, 2])
        self.assertIn("maximise", P._imbalance(one_side, 12))

    def test_no_other_size_exists(self):
        for groups in (4, 6, 36):
            with self.assertRaises(ValueError):
                L.balanced_slices(groups)


# --- части в формате `cli run` --------------------------------------------

def _payload(unit, *, seconds=7000.0, status=ACHIEVED, drop=0, look=None):
    endpoints = []
    for k in unit.keys:
        for f in FRACTIONS:
            endpoints.append({"key": list(k), "fraction": f, "point": 1.0,
                              "low": 0.5, "high": 1.5, "radius": 0.1,
                              "status": status,
                              "look": (unit.look if status == ACHIEVED else None)
                              if look is None else look})
    if drop:
        endpoints = endpoints[:-drop]
    payload = {"task_id": unit.task_id, "arm": unit.arm, "look": unit.look,
               "keys": [list(k) for k in unit.keys], "endpoints": endpoints}
    payload["digest"] = recompute_digest(payload)
    if seconds is not None:
        payload["seconds"] = seconds
    payload["peak_rss_mb"] = 150.0
    return payload


def _pilot_dir(tmp, *, groups=12, science=SCIENCE, declare=None, **per_unit):
    """Каталог как у задания вердикта: манифест пилота и части."""
    tmp = pathlib.Path(tmp)
    units = P.units(P.PILOT_ARM, 64000, groups, 60.0)
    declared = units if declare is None else declare(units)
    manifest = P.manifest(declared, groups=groups, block=60.0)
    manifest["provenance"] = {"science_sha": science}
    (tmp / "manifest.json").write_text(json.dumps(manifest))
    for i, u in enumerate(units):
        spec = per_unit.get(f"u{i}", {})
        if spec is None:
            continue
        payload = _payload(u, **spec.get("payload", {}))
        if "tamper" in spec:
            payload["endpoints"][0]["point"] = 99.0
        (tmp / f"{u.task_id}.json").write_text(json.dumps(payload))
    return tmp


class TheVerdictTests(unittest.TestCase):

    def _judge(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            return P.judge(_pilot_dir(tmp, **kw), look=64000, science_sha=SCIENCE)

    def test_all_units_inside_the_budget_is_a_pass(self):
        got = self._judge()
        self.assertEqual(got["status"], "PASS", got["reasons"])
        self.assertEqual(len(got["units"]), 3)

    def test_the_budget_itself_is_inside(self):
        got = self._judge(u1={"payload": {"seconds": BUDGET}})
        self.assertEqual(got["status"], "PASS", got["reasons"])

    def test_one_slow_unit_is_a_fail(self):
        got = self._judge(u2={"payload": {"seconds": BUDGET + 60}})
        self.assertEqual(got["status"], "FAIL")
        self.assertAlmostEqual(got["worst_hours"], (BUDGET + 60) / 3600, places=3)

    def test_a_missing_unit_is_a_crash_or_timeout(self):
        got = self._judge(u1=None)
        self.assertEqual(got["status"], "FAIL")
        self.assertTrue(any("падение или таймаут" in r for r in got["reasons"]))

    def test_tampered_content_is_refused(self):
        got = self._judge(u0={"tamper": True})
        self.assertEqual(got["status"], "FAIL")

    def test_a_missing_endpoint_is_a_wrong_payload(self):
        got = self._judge(u0={"payload": {"drop": 1}})
        self.assertEqual(got["status"], "FAIL")
        self.assertTrue(any("концы не те" in r for r in got["reasons"]))

    def test_an_unknown_status_is_a_wrong_payload(self):
        got = self._judge(u0={"payload": {"status": "BOGUS"}})
        self.assertEqual(got["status"], "FAIL")

    def test_an_achieved_endpoint_without_its_look_is_a_wrong_payload(self):
        got = self._judge(u0={"payload": {"look": 16000}})
        self.assertEqual(got["status"], "FAIL")

    def test_insufficient_endpoints_are_a_valid_payload(self):
        got = self._judge(u0={"payload": {"status": INSUFFICIENT}})
        self.assertEqual(got["status"], "PASS", got["reasons"])

    def test_a_different_science_is_refused(self):
        got = self._judge(science="c" * 40)
        self.assertEqual(got["status"], "FAIL")

    def test_a_manifest_that_quietly_drops_a_unit_is_refused(self):
        got = self._judge(declare=lambda us: us[:2], u2=None)
        self.assertEqual(got["status"], "FAIL")
        self.assertTrue(any("не те юниты" in r for r in got["reasons"]))

    def test_an_unrecorded_time_is_a_fail(self):
        got = self._judge(u0={"payload": {"seconds": None}})
        self.assertEqual(got["status"], "FAIL")


class TheCliModesTests(unittest.TestCase):

    def _cli(self, argv):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, ENV), contextlib.redirect_stdout(buf):
            code = cli.main(argv)
        return code, buf.getvalue()

    def test_pilot_writes_a_manifest_with_one_unit_per_shard(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text = self._cli(["pilot", "--look", "64000", "--arm",
                                    P.PILOT_ARM, "--groups", "12",
                                    "--block", "60", "--out", tmp])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(text)["shards"], [0, 1, 2])
            m = json.loads((pathlib.Path(tmp) / "manifest.json").read_text())
            self.assertEqual([u["shard"] for u in m["units"]], [0, 1, 2])
            self.assertEqual(m["provenance"]["science_sha"], SCIENCE)
            self.assertEqual(m["pilot"]["groups"], 12)

    def test_pilot_refuses_a_forbidden_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                self._cli(["pilot", "--look", "64000", "--arm", P.PILOT_ARM,
                           "--groups", "6", "--block", "60", "--out", tmp])

    def test_judge_is_green_on_pass_and_red_on_fail(self):
        for spec, want in (({}, 0),
                           ({"u0": {"payload": {"seconds": BUDGET * 2}}}, 1)):
            with tempfile.TemporaryDirectory() as parts, \
                    tempfile.TemporaryDirectory() as out:
                _pilot_dir(parts, **spec)
                code, _ = self._cli(["judge", "--look", "64000",
                                     "--parts", parts, "--out", out])
                self.assertEqual(code, want, spec)
                verdict = json.loads(
                    (pathlib.Path(out) / "pilot-verdict.json").read_text())
                self.assertEqual(verdict["status"],
                                 "PASS" if want == 0 else "FAIL")


class ThePilotIsNotWiredIntoThePlannerTests(unittest.TestCase):

    def test_the_planner_does_not_import_the_pilot(self):
        code = ("import sys; sys.path[:0] = ['research/python', 'execution'];"
                "import s5b_execution.cli, s5b_execution.scheduler;"
                "print('s5b_execution.pilot' in sys.modules)")
        done = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "False")

    def test_nothing_about_the_share_changed(self):
        self.assertIsNone(cost.UNDIVIDED_SHARE)


if __name__ == "__main__":
    unittest.main()
