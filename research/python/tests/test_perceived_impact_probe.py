"""TRACK 4 probe: recipient-perceived impact vs observer estimate.

These tests do not re-run the empirical finding -- that lives in
docs/research/perceived-impact-audit.md and is reproduced by running the module
against the two reference CSVs, which are not vendored here. What is tested is
the machinery that produced it: the id join, the fixed-width block reader, the
tie-corrected statistic, and the three places where this probe could quietly
turn an absence or a calibration offset into a finding.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from external.perceived_impact_probe import (
    PERMUTATION_ITERATIONS,
    SHARED_DIMENSIONS,
    ObserverRating,
    SelfReport,
    associate,
    association_difference,
    disagreements,
    kendall_tau_b,
    label_blindness_control,
    label_effect,
    load_observer_ratings,
    load_self_reports,
    pair,
    permutation_contrast,
    scale_use,
)


def rating(value, **overrides):
    out = {d: float(value) for d in SHARED_DIMENSIONS}
    out.update({k: float(v) for k, v in overrides.items()})
    return out


def self_report(cid, value, label="human label", source="human response", **overrides):
    return SelfReport(cid, rating(value, **overrides), actual_source=source, stated_label=label)


def observer(cid, value, group="experts", **overrides):
    return ObserverRating(cid, group, rating(value, **overrides))


class KendallTests(unittest.TestCase):
    def test_perfect_concordance(self):
        self.assertAlmostEqual(kendall_tau_b([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)

    def test_perfect_discordance(self):
        self.assertAlmostEqual(kendall_tau_b([1, 2, 3, 4], [40, 30, 20, 10]), -1.0)

    def test_ties_are_corrected_not_counted_as_agreement(self):
        """Without the tie correction a rater who says '6' to everything would
        look like it agrees with everyone. That is the empathy-inflation trap."""
        with self.assertRaises(ValueError):
            kendall_tau_b([1, 2, 3, 4], [6, 6, 6, 6])

    def test_partial_ties_shrink_the_denominator(self):
        value = kendall_tau_b([1, 2, 3, 4], [10, 20, 20, 30])
        self.assertGreater(value, 0.8)
        self.assertLess(value, 1.0)

    def test_length_mismatch_is_an_error(self):
        with self.assertRaises(ValueError):
            kendall_tau_b([1, 2], [1, 2, 3])


class IntervalTests(unittest.TestCase):
    def test_interval_brackets_the_point_estimate(self):
        xs = [1, 2, 3, 4, 5, 6, 7, 8, 5, 3]
        ys = [2, 1, 4, 3, 7, 5, 8, 6, 4, 5]
        result = associate("x->y", xs, ys, iterations=200)
        self.assertLessEqual(result.ci_low, result.tau_b)
        self.assertLessEqual(result.tau_b, result.ci_high)
        self.assertEqual(result.n, 10)

    def test_difference_is_resampled_jointly_not_compared_by_eye(self):
        xs = [1, 2, 3, 4, 5, 6, 7, 8]
        tracks = [1, 2, 3, 4, 5, 6, 7, 8]
        ignores = [8, 1, 7, 2, 6, 3, 5, 4]
        result = association_difference("tracks minus ignores", xs, tracks, ignores, iterations=200)
        self.assertGreater(result.tau_b, 0.5)
        self.assertGreater(result.ci_low, 0.0)


class PermutationTests(unittest.TestCase):
    def test_separated_arms_are_flagged(self):
        result = permutation_contrast("sep", [6.0] * 20, [2.0] * 20, iterations=500)
        self.assertLess(result.p_value, 0.05)
        self.assertAlmostEqual(result.difference, 4.0)

    def test_p_value_is_bounded_below_by_one_over_iterations(self):
        result = permutation_contrast("sep", [6.0] * 20, [2.0] * 20, iterations=500)
        self.assertGreaterEqual(result.p_value, 1 / 501)


class PairingTests(unittest.TestCase):
    def test_an_observer_row_with_no_recipient_row_is_reported_not_dropped(self):
        selves = {"a": self_report("a", 5)}
        observers = {"a": observer("a", 3), "ghost": observer("ghost", 3)}
        ids, report = pair(selves, observers)
        self.assertEqual(ids, ["a"])
        self.assertEqual(report.observer_only, ["ghost"])
        self.assertFalse(report.complete)

    def test_unpaired_recipients_are_recorded_and_do_not_block_completeness(self):
        selves = {"a": self_report("a", 5), "b": self_report("b", 4)}
        ids, report = pair(selves, {"a": observer("a", 3)})
        self.assertEqual(report.self_only, ["b"])
        self.assertTrue(report.complete)


class LoaderTests(unittest.TestCase):
    def test_self_report_rows_missing_a_dimension_are_skipped_not_imputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "self.csv"
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["id", *SHARED_DIMENSIONS, "responseR", "labelR"])
                writer.writerow(["ok", *["5"] * 6, "human response", "ai label"])
                writer.writerow(["partial", "5", "5", "5", "5", "5", "", "human response", "ai label"])
            loaded = load_self_reports(path)
        self.assertEqual(sorted(loaded), ["ok"])
        self.assertEqual(loaded["ok"].stated_label, "ai label")

    def test_observer_block_is_read_by_position_despite_duplicate_headers(self):
        """The reference file concatenates four differently-keyed blocks with
        repeated column names; a dict reader would silently return the last one."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "combined.csv"
            head = ["other_id", "m_understood", "annotation_method"]
            block = ["perceived_conversation_id", *[f"m_{d}" for d in SHARED_DIMENSIONS],
                     "m_emotional", "m_practical", "annotation_method"]
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(head + block)
                writer.writerow(["x", "9", "decoy", "c1", *["3"] * 6, "3", "3", "experts"])
                writer.writerow(["y", "9", "decoy", "c1", *["5"] * 6, "5", "5", "crowd"])
            loaded = load_observer_ratings(path)
        self.assertEqual(sorted(loaded), ["crowd", "experts"])
        self.assertEqual(loaded["experts"]["c1"].composite, 3.0)
        self.assertEqual(loaded["crowd"]["c1"].composite, 5.0)


class CompositeTests(unittest.TestCase):
    def test_composite_is_the_mean_of_the_six_shared_dimensions(self):
        report = self_report("a", 5, understood=7, caredfor=1)
        self.assertAlmostEqual(report.composite, (7 + 5 + 5 + 5 + 5 + 1) / 6)

    def test_scale_use_reports_where_a_group_lives_not_just_its_mean(self):
        summary = scale_use([6.0, 6.0, 6.0, 1.0])
        self.assertAlmostEqual(summary["mean"], 4.75)
        self.assertAlmostEqual(summary["share_at_or_above"], 0.75)
        self.assertEqual(summary["min"], 1.0)


class DisagreementTests(unittest.TestCase):
    """The offset trap: two sides 3 points apart produce a full list of
    'disagreements' that says nothing except that they used different parts of
    the scale."""

    def setUp(self):
        self.ids = ["a", "b", "c", "d"]
        self.selves = {c: self_report(c, v) for c, v in zip(self.ids, [7.0, 6.0, 5.0, 4.0])}
        self.observers = {c: observer(c, v) for c, v in zip(self.ids, [4.0, 3.0, 2.0, 1.0])}

    def test_raw_gaps_are_all_one_direction_when_the_sides_are_offset(self):
        cases = disagreements(self.ids, self.selves, self.observers, threshold=3.0)
        self.assertEqual(len(cases), 4)
        self.assertTrue(all(case.direction == "observer_low_recipient_high" for case in cases))

    def test_centering_removes_a_pure_offset_and_leaves_nothing(self):
        """Perfectly rank-identical sides 3 points apart must yield no centered
        disagreement at all."""
        cases = disagreements(self.ids, self.selves, self.observers, threshold=0.5, centered=True)
        self.assertEqual(cases, [])

    def test_centering_surfaces_a_genuine_ordering_flip(self):
        self.observers["d"] = observer("d", 4.0)   # observer's favourite, recipient's least
        self.observers["a"] = observer("a", 1.0)
        cases = disagreements(self.ids, self.selves, self.observers, threshold=2.0, centered=True)
        self.assertEqual({case.conversation_id for case in cases}, {"a", "d"})
        self.assertEqual({case.direction for case in cases},
                         {"observer_low_recipient_high", "observer_high_recipient_low"})


class LabelTests(unittest.TestCase):
    def test_label_effect_needs_both_randomised_arms(self):
        selves = {c: self_report(c, 5, label="human label") for c in ("a", "b")}
        with self.assertRaises(ValueError):
            label_effect(selves)

    def test_label_effect_is_computed_within_one_actual_authorship_condition(self):
        """Mixing actual sources would confound the label manipulation with the
        thing the label is about."""
        selves = {}
        for i in range(10):
            selves[f"h{i}"] = self_report(f"h{i}", 6, label="human label", source="human response")
            selves[f"a{i}"] = self_report(f"a{i}", 4, label="ai label", source="human response")
            selves[f"x{i}"] = self_report(f"x{i}", 1, label="ai label", source="ai response")
        effect = label_effect(selves, "human response")
        self.assertEqual((effect.n_a, effect.n_b), (10, 10))
        self.assertAlmostEqual(effect.difference, 2.0)

    def test_control_splits_observer_ratings_by_an_arm_observers_never_saw(self):
        ids = [f"c{i}" for i in range(8)]
        selves = {c: self_report(c, 5, label="human label" if i % 2 else "ai label")
                  for i, c in enumerate(ids)}
        observers = {c: observer(c, 3) for c in ids}
        control = label_blindness_control(ids, selves, observers)
        self.assertEqual(control.difference, 0.0)
        self.assertEqual((control.n_a, control.n_b), (4, 4))


class ConstantTests(unittest.TestCase):
    def test_permutation_iterations_are_fixed_so_the_p_floor_is_stable(self):
        self.assertEqual(PERMUTATION_ITERATIONS, 20000)


if __name__ == "__main__":
    unittest.main()
