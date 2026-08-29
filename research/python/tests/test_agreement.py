"""Тесты agreement-математики. Гейтящие числа обязаны быть воспроизводимы и проверяемы."""

import unittest

from metrics.agreement import (
    confusion_analysis,
    krippendorff_alpha_binary,
    label_stats,
)


class KrippendorffAlphaTests(unittest.TestCase):
    def test_hand_computed_example(self):
        # units: (0,0), (1,1), (0,1) → coincidence: o00=2, o11=2, o01=o10=1;
        # Do = 2/6; De = 2*3*3/(6*5) = 0.6; alpha = 1 - (1/3)/0.6 = 0.4444…
        alpha = krippendorff_alpha_binary([(0, 0), (1, 1), (0, 1)])
        self.assertAlmostEqual(alpha, 0.4444, places=4)

    def test_perfect_agreement_with_variance(self):
        alpha = krippendorff_alpha_binary([(0, 0), (1, 1), (0, 0), (1, 1)])
        self.assertAlmostEqual(alpha, 1.0, places=6)

    def test_all_identical_values_is_undefined(self):
        # Все ответы «0» — chance disagreement нулевой, alpha не определён.
        self.assertIsNone(krippendorff_alpha_binary([(0, 0), (0, 0), (0, 0)]))

    def test_systematic_disagreement_is_negative(self):
        alpha = krippendorff_alpha_binary([(0, 1), (1, 0), (0, 1), (1, 0)])
        self.assertLess(alpha, 0)


class LabelStatsTests(unittest.TestCase):
    @staticmethod
    def row(da, db, la=(), lb=()):
        return {"decision_a": da, "decision_b": db, "labels_a": set(la), "labels_b": set(lb)}

    def test_abstained_units_are_excluded_not_counted_as_negative(self):
        rows = [
            self.row("assigned", "assigned", {"B.X"}, {"B.X"}),
            self.row("abstained", "assigned", (), {"B.X"}),
        ]
        stats = label_stats("B.X", rows)
        self.assertEqual(stats["n_units"], 1)  # abstained-пара не вошла

    def test_underpowered_when_positive_union_too_small(self):
        rows = [self.row("assigned", "assigned", {"B.X"}, {"B.X"})] + [
            self.row("none_observed", "none_observed") for _ in range(19)
        ]
        stats = label_stats("B.X", rows)
        self.assertEqual(stats["estimability_status"], "underpowered_not_estimable")
        self.assertEqual(stats["positive_union"], 1)

    def test_passed_with_enough_positives_and_agreement(self):
        rows = [self.row("assigned", "assigned", {"B.X"}, {"B.X"}) for _ in range(6)] + [
            self.row("none_observed", "none_observed") for _ in range(6)
        ]
        stats = label_stats("B.X", rows)
        self.assertEqual(stats["estimability_status"], "passed")
        self.assertEqual(stats["alpha"], 1.0)
        self.assertEqual(stats["positive_agreement_dice"], 1.0)
        self.assertTrue(stats["meets_target"])

    def test_positive_agreement_catches_negative_only_consensus(self):
        # Согласны на 10 negatives, но ни разу — на positive: Dice = 0 при внятном n.
        rows = [self.row("none_observed", "none_observed") for _ in range(10)] + [
            self.row("assigned", "none_observed", {"B.X"}, ()),
            self.row("none_observed", "assigned", (), {"B.X"}),
            self.row("assigned", "none_observed", {"B.X"}, ()),
            self.row("none_observed", "assigned", (), {"B.X"}),
            self.row("assigned", "none_observed", {"B.X"}, ()),
        ]
        stats = label_stats("B.X", rows)
        self.assertEqual(stats["positive_agreement_dice"], 0.0)
        self.assertLess(stats["alpha"], 0.0)


class ConfusionTests(unittest.TestCase):
    @staticmethod
    def row(da, db, la=(), lb=()):
        return {"decision_a": da, "decision_b": db, "labels_a": set(la), "labels_b": set(lb)}

    def test_label_vs_label_pairing(self):
        rows = [self.row("assigned", "assigned", {"B.VALIDATION"}, {"B.REPAIR_ATTEMPT"})]
        result = confusion_analysis(rows)
        self.assertEqual(
            result["label_vs_label_disagreements"],
            {"B.REPAIR_ATTEMPT <-> B.VALIDATION": 1})

    def test_label_vs_none(self):
        rows = [self.row("assigned", "none_observed", {"B.AVOIDANCE_TOPIC_SHIFT"}, ())]
        result = confusion_analysis(rows)
        self.assertEqual(
            result["label_vs_none_disagreements"],
            {"B.AVOIDANCE_TOPIC_SHIFT <-> NONE_OBSERVED": 1})

    def test_decision_matrix_counts_abstained(self):
        rows = [self.row("abstained", "assigned", (), {"B.X"})]
        result = confusion_analysis(rows)
        self.assertEqual(result["decision_matrix"], {"abstained|assigned": 1})

    def test_shared_labels_do_not_count_as_disagreement(self):
        rows = [self.row("assigned", "assigned",
                         {"B.VALIDATION", "B.REPAIR_ATTEMPT"}, {"B.VALIDATION"})]
        result = confusion_analysis(rows)
        self.assertEqual(result["label_vs_label_disagreements"], {})


if __name__ == "__main__":
    unittest.main()
