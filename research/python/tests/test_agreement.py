"""Тесты agreement-математики. Гейтящие числа обязаны быть воспроизводимы и проверяемы."""

import json
import tempfile
import unittest
from pathlib import Path

from metrics.agreement import (
    boundary_collapse_diagnostic,
    build_unit_rows,
    check_eligibility,
    confusion_analysis,
    directional_bias,
    feedback_crosstab,
    krippendorff_alpha_binary,
    label_stats,
    validate_responses,
)

REQUIRED = ["did_not_author_ontology", "fluent_ru", "fluent_en", "has_not_seen_items"]


def write_record(dir_path, annotator, package_id="annotation-pilot-v0.1", criteria=REQUIRED, schema="rf.issuance-record.v1"):
    record = {
        "schema_version": schema,
        "package_id": package_id,
        "annotator_id": annotator,
        "eligibility": {"criteria": criteria},
    }
    (dir_path / f"{annotator}.json").write_text(json.dumps(record), encoding="utf-8")


class EligibilityCheckTests(unittest.TestCase):
    """agreement больше не читает sealed eligibility.json (issuance repair, d95bdbe:
    тот файл — null template, запечатанный с пакетом, и остаётся null навсегда).
    Единственный источник — issuance record, который metrics.issuance new уже
    проверил сам перед выдачей."""

    def test_valid_issuance_records_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_record(d, "annotator-1")
            write_record(d, "annotator-2")
            self.assertIsNone(check_eligibility(d, "annotation-pilot-v0.1", ["annotator-1", "annotator-2"], REQUIRED))

    def test_missing_record_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_record(d, "annotator-1")
            problem = check_eligibility(d, "annotation-pilot-v0.1", ["annotator-1", "annotator-2"], REQUIRED)
            self.assertIn("annotator-2.json", problem)

    def test_wrong_package_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_record(d, "annotator-1", package_id="annotation-pilot-v0")
            problem = check_eligibility(d, "annotation-pilot-v0.1", ["annotator-1"], REQUIRED)
            self.assertIn("package_id", problem)

    def test_missing_criterion_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_record(d, "annotator-1", criteria=["did_not_author_ontology", "fluent_ru", "fluent_en"])
            problem = check_eligibility(d, "annotation-pilot-v0.1", ["annotator-1"], REQUIRED)
            self.assertIn("has_not_seen_items", problem)

    def test_bad_schema_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_record(d, "annotator-1", schema="rf.annotator-eligibility.v1")
            problem = check_eligibility(d, "annotation-pilot-v0.1", ["annotator-1"], REQUIRED)
            self.assertIn("schema_version", problem)


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


def row(item_id, labels_a, labels_b, decision_a="assigned", decision_b="assigned"):
    """Синтетическая пара решений. Пустой набор labels => решение none_observed."""
    return {
        "item_id": item_id,
        "decision_a": decision_a if labels_a else ("none_observed" if decision_a == "assigned" else decision_a),
        "decision_b": decision_b if labels_b else ("none_observed" if decision_b == "assigned" else decision_b),
        "labels_a": set(labels_a),
        "labels_b": set(labels_b),
        "reason_a": None, "reason_b": None,
        "feedback_collected_a": False, "feedback_collected_b": False,
        "feedback_a": set(), "feedback_b": set(),
    }


A = "B.BLAME_CRITICISM"
B = "B.PRESSURE_FOR_CHANGE"


class BoundaryCollapseDiagnosticTests(unittest.TestCase):
    """prereg §1.8. Диагностика границы, НЕ тест размерности."""

    def test_perfect_superordinate_agreement_with_zero_boundary_agreement(self):
        """Оба всегда видят «что-то из пары», но никогда не сходятся какой именно.
        union alpha должна быть высокой, part alpha — нулевой/отрицательной."""
        rows = [row(f"i{i}", [A], [B]) if i % 2 else row(f"i{i}", [B], [A]) for i in range(12)]
        rows += [row(f"n{i}", [], []) for i in range(12)]  # negatives, иначе alpha не определена
        d = boundary_collapse_diagnostic((A, B), rows)

        self.assertEqual(d["estimability_status"], "passed")
        self.assertEqual(d["n_units"], 24)
        self.assertEqual(d["both_union_positive"], 12)
        self.assertEqual(d["split_on_which_label"], 12, "все 12 — расхождение внутри границы")
        self.assertAlmostEqual(d["union_alpha"], 1.0, places=4)
        for part_alpha in d["part_alphas"].values():
            self.assertLess(part_alpha, 0.1, "внутри границы согласия нет")
        self.assertGreater(d["delta_union_minus_max_part"], 0.8)

    def test_distinct_constructs_show_no_union_advantage(self):
        """Оба надёжно различают A и B => union не даёт преимущества."""
        rows = [row(f"a{i}", [A], [A]) for i in range(6)]
        rows += [row(f"b{i}", [B], [B]) for i in range(6)]
        rows += [row(f"n{i}", [], []) for i in range(12)]
        d = boundary_collapse_diagnostic((A, B), rows)

        self.assertEqual(d["split_on_which_label"], 0)
        self.assertAlmostEqual(d["union_alpha"], 1.0, places=4)
        self.assertAlmostEqual(d["delta_union_minus_max_part"], 0.0, places=4)

    def test_underpowered_when_too_few_positives(self):
        rows = [row(f"n{i}", [], []) for i in range(20)] + [row("p1", [A], [A])]
        d = boundary_collapse_diagnostic((A, B), rows)
        self.assertEqual(d["estimability_status"], "underpowered_not_estimable")

    def test_abstained_units_are_excluded_not_punished(self):
        """Тот же критерий pairable, что в label_stats — числа обязаны быть сопоставимы."""
        rows = [row(f"n{i}", [], []) for i in range(12)] + [row(f"p{i}", [A], [A]) for i in range(6)]
        rows.append(row("abs", [], [A], decision_a="abstained"))
        d = boundary_collapse_diagnostic((A, B), rows)
        self.assertEqual(d["n_units"], 18, "abstained unit не входит в pairable")
        self.assertEqual(d["n_units"], label_stats(A, rows)["n_units"])

    def test_diagnostic_carries_its_own_interpretation_guard(self):
        """Правило интерпретации живёт в артефакте, а не только в прозе документа."""
        rows = [row(f"n{i}", [], []) for i in range(12)] + [row(f"p{i}", [A], [B]) for i in range(6)]
        d = boundary_collapse_diagnostic((A, B), rows)
        self.assertIn("NOT a dimensionality test", d["interpretation_note"])


class DirectionalBiasTests(unittest.TestCase):
    """prereg §1.9. Описательно; вывода «кто прав» нет и быть не может."""

    def test_fully_one_sided_disagreement(self):
        """A ставит label там, где B не ставит — и никогда наоборот."""
        rows = [row(f"x{i}", [A], []) for i in range(8)] + [row(f"n{i}", [], []) for i in range(8)]
        d = directional_bias(A, rows)
        self.assertEqual(d["n_positive_a"], 8)
        self.assertEqual(d["n_positive_b"], 0)
        self.assertEqual(d["signed_difference_a_minus_b"], 8)
        self.assertEqual(d["one_sidedness"], 1.0)

    def test_scattered_disagreement_is_not_one_sided(self):
        rows = [row(f"x{i}", [A], []) for i in range(4)] + [row(f"y{i}", [], [A]) for i in range(4)]
        d = directional_bias(A, rows)
        self.assertEqual(d["signed_difference_a_minus_b"], 0)
        self.assertEqual(d["one_sidedness"], 0.0, "поровну в обе стороны => рассеянное")

    def test_no_disagreement_yields_none_not_zero(self):
        """Отсутствие расхождений — не «нулевая односторонность», а неопределённость."""
        rows = [row(f"p{i}", [A], [A]) for i in range(5)] + [row(f"n{i}", [], []) for i in range(5)]
        d = directional_bias(A, rows)
        self.assertEqual(d["disagreements"], 0)
        self.assertIsNone(d["one_sidedness"])

    def test_bias_never_claims_a_correct_layer(self):
        rows = [row(f"x{i}", [A], []) for i in range(8)] + [row(f"n{i}", [], []) for i in range(8)]
        self.assertIn("no gold standard", directional_bias(A, rows)["interpretation_note"])
