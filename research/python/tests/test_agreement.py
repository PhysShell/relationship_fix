"""Тесты agreement-математики. Гейтящие числа обязаны быть воспроизводимы и проверяемы."""

import unittest

from metrics.agreement import (
    build_unit_rows,
    confusion_analysis,
    feedback_crosstab,
    krippendorff_alpha_binary,
    label_stats,
    validate_responses,
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


class FeedbackCrosstabTests(unittest.TestCase):
    """unnatural_example × disagreement / abstention / stratum: плохой stimulus и плохое
    definition — разные диагнозы, отчёт обязан их разводить."""

    ITEMS = [
        {"item_id": f"i{k}", "messages": [{"message_id": f"i{k}-m1", "author": "a", "text": "т"}],
         "target_message_id": f"i{k}-m1"} for k in range(1, 5)
    ]
    STRATA = {"i1": "challenge", "i2": "challenge", "i3": "natural", "i4": "natural"}

    @staticmethod
    def response(item_id, decision, labels=(), flags=None, reason=None):
        r = {"schema_version": "rf.pilot-response.v1", "item_id": item_id, "annotator_id": "x", "decision": decision}
        if labels:
            r["labels"] = list(labels)
            r["quotes"] = [{"label": l, "quote": "т"} for l in labels]
        if reason:
            r["abstention_reason"] = reason
        if flags is not None:
            r["feedback"] = {"flags": list(flags)}
        return r

    def test_not_collected_when_no_response_carries_feedback(self):
        a = [self.response(i["item_id"], "none_observed") for i in self.ITEMS]
        rows = build_unit_rows(self.ITEMS, a, a)
        self.assertFalse(feedback_crosstab(rows, self.STRATA)["collected"])

    def test_crosstabs(self):
        a = [self.response("i1", "assigned", ["B.X"], flags=["unnatural_example"]),
             self.response("i2", "assigned", ["B.X"], flags=[]),
             self.response("i3", "abstained", flags=["unnatural_example", "other"], reason="insufficient_context"),
             self.response("i4", "none_observed", flags=[])]
        b = [self.response("i1", "none_observed", flags=["unnatural_example"]),
             self.response("i2", "assigned", ["B.Y"], flags=[]),
             self.response("i3", "none_observed", flags=[]),
             self.response("i4", "none_observed", flags=[])]
        table = feedback_crosstab(build_unit_rows(self.ITEMS, a, b), self.STRATA)
        self.assertTrue(table["collected"])
        per = {p["item_id"]: p for p in table["per_item"]}
        self.assertEqual(per["i1"]["unnatural_flags"], 2)
        self.assertTrue(per["i1"]["decision_disagreement"])
        self.assertTrue(per["i2"]["label_disagreement"])
        self.assertFalse(per["i2"]["decision_disagreement"])
        self.assertEqual(per["i3"]["abstentions"], 1)
        self.assertEqual(per["i3"]["other_flags"], ["other"])
        # i1, i3 flagged (both disagree); i2 disagrees without flag; i4 clean & agrees
        self.assertEqual(table["unnatural_x_disagreement"], {"flagged_any": {"yes": 2, "no": 0},
                                                             "not_flagged": {"yes": 1, "no": 1}})
        self.assertEqual(table["unnatural_x_abstention"]["flagged_any"], {"yes": 1, "no": 1})
        self.assertEqual(table["unnatural_by_stratum"],
                         {"challenge": {"n_items": 2, "flagged_any": 1, "flagged_both": 1},
                          "natural": {"n_items": 2, "flagged_any": 1, "flagged_both": 0}})
        self.assertEqual(table["flag_totals"]["unnatural_example"], {"a": 2, "b": 1, "items_any": 2, "items_both": 1})

    def test_unknown_feedback_flag_is_rejected(self):
        bad = [self.response(i["item_id"], "none_observed", flags=["looks_fake"]) for i in self.ITEMS]
        issues = validate_responses(self.ITEMS, bad, "x", {"B.X"})
        self.assertTrue(all("unknown feedback flag" in i for i in issues))
        self.assertEqual(len(issues), 4)


if __name__ == "__main__":
    unittest.main()
