"""Гейты PoC модели стоимости группы ключей.

Модель НЕ подключена к планировщику. Гейты держат три вещи: что проверка
идёт на данных, НЕ вошедших в подгонку; что неподключённость — факт, а
не обещание; и что «сбалансированная» раскладка сбалансирована и по
тому, чего модель не видит.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "execution") not in sys.path:
    sys.path.insert(0, str(ROOT / "execution"))

from s5b_execution import cost, keycost as K                  # noqa: E402

RECORD = json.loads(
    (ROOT / "docs/research/s5b-calibration-4000.json").read_text())


class TheCheckIsOnDataNotUsedForFittingTests(unittest.TestCase):
    """Подгонка точная: 5 неизвестных на 5 наблюдений. Проверка — только g=2."""

    def test_fitting_uses_exactly_variants_1_and_4(self):
        self.assertEqual(K.fit(RECORD)["fitted_on"], [1, 4])

    def test_a_fitted_variant_is_refused_as_a_check(self):
        m = K.fit(RECORD)
        for fitted in (1, 4):
            with self.assertRaises(K.ModelRefused):
                K.check_heldout(m, RECORD, fitted)

    def test_the_heldout_variant_is_reproduced_within_the_declared_tolerance(self):
        got = K.check_heldout(K.fit(RECORD), RECORD, 2)
        self.assertTrue(got["passed"], f"модель не воспроизвела g=2: {got}")
        self.assertLessEqual(got["worst_relative_error"], K.HELDOUT_TOLERANCE)

    def test_the_tolerance_is_declared_and_not_loose(self):
        """Допуск на порядок меньше запаса решения, а не подобран под невязку."""
        self.assertLessEqual(K.HELDOUT_TOLERANCE, 0.05)

    def test_a_model_that_ignores_the_profile_fails_the_same_check(self):
        """Равные ключи — ровно то, что сейчас делает планировщик.

        Та же проверка обязана его ОТВЕРГНУТЬ: иначе она не различает
        модели и ничего не доказывает про нашу.
        """
        m = K.fit(RECORD)
        mean = sum(m["per_key"].values()) / len(m["per_key"])
        flat = {"undivided": m["undivided"],
                "per_key": {t: mean for t in m["per_key"]},
                "fitted_on": m["fitted_on"]}
        self.assertFalse(K.check_heldout(flat, RECORD, 2)["passed"],
                         "проверка пропускает и модель равных ключей")


class ThePocIsNotWiredTests(unittest.TestCase):
    """Неподключённость проверяется импортом, а не обещанием в константе."""

    def test_the_planner_does_not_import_the_model(self):
        code = ("import sys; sys.path[:0] = ['research/python', 'execution'];"
                "import s5b_execution.cli, s5b_execution.scheduler;"
                "print('s5b_execution.keycost' in sys.modules)")
        done = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "False",
                         "планировщик тянет PoC модели стоимости")

    def test_the_share_is_still_unset(self):
        """Измерение есть, а подстановки нет: это отдельное решение."""
        self.assertIsNone(cost.UNDIVIDED_SHARE)


class BalanceOnWhatTheModelCannotSeeTests(unittest.TestCase):
    """Сбалансированность по модели ≠ сбалансированность по ключам."""

    def test_lpt_is_flagged_as_aligned_with_unmeasured_axes(self):
        m = K.scaled(K.fit(RECORD), 16.0)
        bal = K.coordinate_balance(K.balanced_partition(m, 6))
        horizon_rows = bal[2]
        self.assertTrue(any(len(set(r)) > 1 for r in horizon_rows),
                        "LPT вдруг перемешал горизонты — пометка устарела")
        self.assertTrue(K.LPT_ALIGNS_WITH_UNMEASURED_AXES)

    def test_factorial_partition_is_balanced_on_every_coordinate(self):
        bins = K.factorial_partition(6)
        self.assertEqual(sorted(k for b in bins for k in b),
                         sorted(K.KEYS), "не разбиение ключей")
        for axis, rows in K.coordinate_balance(bins).items():
            for row in rows:
                self.assertEqual(len(set(row)), 1,
                                 f"координата {axis}: {row} неравномерно")
            self.assertTrue(all(r == rows[0] for r in rows),
                            f"координата {axis}: группы различаются")

    def test_factorial_costs_the_same_as_lpt_under_the_model(self):
        m = K.scaled(K.fit(RECORD), 16.0)
        lpt = max(K.group_seconds(m, b) for b in K.balanced_partition(m, 6))
        fac = max(K.group_seconds(m, b) for b in K.factorial_partition(6))
        self.assertAlmostEqual(lpt, fac, places=6)

    def test_factorial_is_refused_where_it_is_not_derived(self):
        for g in (4, 5, 7):
            with self.assertRaises(K.ModelRefused):
                K.factorial_partition(g)


class WhatTheModelSaysAbout64000Tests(unittest.TestCase):
    """Условно: линейность по просмотру — допущение, а не замер."""

    def _model(self, factor):
        return K.scaled(K.fit(RECORD), factor)

    def test_contiguous_needs_more_groups_than_balanced(self):
        budget = cost.SHARD_BUDGET_HOURS * 3600
        for factor in (16.0, cost.seconds_for(120.0, 64000)
                       / RECORD["variants"][0]["C_g_sum_wall"]):
            m = self._model(factor)
            contiguous = K.minimum_groups(m, budget, K.worst_contiguous)
            balanced = K.minimum_groups(m, budget, K.worst_balanced)
            self.assertIsNotNone(contiguous)
            self.assertGreater(contiguous, balanced,
                               f"при x{factor:.2f} смежная раскладка не хуже")

    def test_the_planner_weight_underestimates_the_tail_group(self):
        """Вес `T_full * len/72` занижает хвостовую группу смежной раскладки."""
        from s5b_execution.scheduler import key_slices
        m = self._model(16.0)
        full = K.group_seconds(m, K.KEYS)
        tail = key_slices(5)[-1]
        planner = full * len(tail) / len(K.KEYS)
        self.assertGreater(K.group_seconds(m, tail), 1.5 * planner,
                           "хвост оказался не тяжелее оценки планировщика")


def _second_run(scale=1.3, per_tier=None, cell_bump=None, drop_cells=False,
                identical=True, incomplete=None):
    """Синтетический второй прогон из первого: нормированный профиль задан."""
    import copy
    from s5b_execution import calibrate
    m = K.fit(RECORD)
    und = m["undivided"]
    per = dict(m["per_key"]) if per_tier is None else per_tier
    rec = {"arm": RECORD["arm"], "look": 4000, "variants": [],
           "comparisons": [{"identical": identical}, {"identical": identical}],
           "incomplete": incomplete}

    def group(keys):
        return (und + sum(per[k[0]] for k in keys)) * scale

    for label, slices in (("1", (K.KEYS,)),
                          ("4", __import__("s5b_execution.scheduler",
                                           fromlist=["x"]).key_slices(4)),
                          ("cells6", calibrate.cells_partition())):
        if drop_cells and label == "cells6":
            continue
        rows = [{"keys": [list(k) for k in sl], "key_count": len(sl),
                 "wall_seconds": group(sl)} for sl in slices]
        if label == "cells6" and cell_bump:
            rows[0]["wall_seconds"] *= cell_bump
        rec["variants"].append({
            "label": label, "groups": len(slices), "groups_detail": rows,
            "C_g_sum_wall": sum(r["wall_seconds"] for r in rows),
            "W_g_max_wall": max(r["wall_seconds"] for r in rows)})
    by = {v["label"]: v for v in rec["variants"]}
    c1 = by["1"]["C_g_sum_wall"]
    rec["shares"] = {"s_4": (by["4"]["C_g_sum_wall"] / c1 - 1) / 3}
    if "cells6" in by:
        rec["shares"]["s_6"] = (by["cells6"]["C_g_sum_wall"] / c1 - 1) / 5
    return rec


class GateAVerdictTests(unittest.TestCase):
    """Пороги Gate A объявлены до прогона; вердикт по нормированным величинам."""

    def test_the_same_profile_on_a_slower_runner_passes(self):
        got = K.gate_a(RECORD, _second_run(scale=1.3))
        self.assertTrue(got["verdict"].startswith("PASS"), got)

    def test_absolute_seconds_are_not_what_is_compared(self):
        """Вдвое медленный раннер при том же профиле — всё ещё PASS."""
        got = K.gate_a(RECORD, _second_run(scale=1.96))
        self.assertTrue(got["verdict"].startswith("PASS"), got)

    def test_a_swapped_block_order_is_a_kill(self):
        m = K.fit(RECORD)
        per = dict(m["per_key"])
        per[15.0], per[60.0] = per[60.0], per[15.0]
        got = K.gate_a(RECORD, _second_run(per_tier=per))
        self.assertTrue(got["verdict"].startswith("KILL"))
        self.assertFalse(got["checks"]["order_preserved"])

    def test_a_drifted_profile_is_a_kill(self):
        m = K.fit(RECORD)
        per = dict(m["per_key"])
        per[60.0] *= 1.0 + 2 * K.GATE_A_RATIO_TOLERANCE
        got = K.gate_a(RECORD, _second_run(per_tier=per))
        self.assertFalse(got["checks"]["profile_transported"])
        self.assertTrue(got["verdict"].startswith("KILL"))

    def test_equal_cells_say_days_is_not_measured(self):
        got = K.gate_a(RECORD, _second_run())
        self.assertEqual(got["checks"]["uniformity_status"],
                         "NOT_DETECTED_DAYS_UNMEASURED",
                         "равные клетки выданы за PASS равномерности")

    def test_an_uneven_cell_kills_uniformity(self):
        got = K.gate_a(RECORD, _second_run(
            cell_bump=K.CELLS_EFFECT_SPREAD + 0.05))
        self.assertEqual(got["checks"]["uniformity_status"], "KILL")

    def test_the_band_between_thresholds_is_not_decided(self):
        mid = (K.CELLS_NO_EFFECT_SPREAD + K.CELLS_EFFECT_SPREAD) / 2
        got = K.gate_a(RECORD, _second_run(cell_bump=mid))
        self.assertEqual(got["checks"]["uniformity_status"], "UNDECIDED")

    def test_a_missing_probe_is_incomplete_not_a_pass(self):
        got = K.gate_a(RECORD, _second_run(drop_cells=True))
        self.assertTrue(got["verdict"].startswith("INCOMPLETE"))

    def test_changed_science_is_a_kill_before_anything_else(self):
        got = K.gate_a(RECORD, _second_run(identical=False))
        self.assertTrue(got["verdict"].startswith("KILL: наука"))

    def test_thresholds_are_declared_and_ordered(self):
        self.assertLess(K.CELLS_NO_EFFECT_SPREAD, K.CELLS_EFFECT_SPREAD)
        self.assertLessEqual(K.GATE_A_RATIO_TOLERANCE, 0.15)
        self.assertLessEqual(K.GATE_A_SHARE_AGREEMENT, 0.02)


if __name__ == "__main__":
    unittest.main()
