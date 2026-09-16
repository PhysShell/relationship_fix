"""Tests for interaction-primitives-v0 (Pilot B).

Gating numbers must be reproducible and checkable. The alpha implementation is
new — Pilot A's is binary and two-coder — so it is pinned against known values
AND cross-checked against the existing one on the case both cover.
"""

import json
import tempfile
import unittest
from pathlib import Path

from metrics.agreement import krippendorff_alpha_binary
from metrics.primitives import (
    ANNOTATORS,
    BOUNDARY_TOLERANCE,
    bootstrap_ci,
    boundary_stats,
    krippendorff_alpha_nominal,
    materialize,
    opaque_id,
    pairwise_confusion,
    primitive_stats,
    raw_agreement,
    report,
    validate_boundary_responses,
    validate_corpus,
    validate_responses,
)

CORPUS = Path(__file__).resolve().parents[3] / "data/research/interaction-primitives-v0"


class NominalAlphaTests(unittest.TestCase):
    def test_perfect_agreement(self):
        self.assertAlmostEqual(krippendorff_alpha_nominal([["A", "A"], ["B", "B"]]), 1.0)

    def test_systematic_disagreement_is_worse_than_chance(self):
        self.assertAlmostEqual(krippendorff_alpha_nominal([["A", "B"], ["A", "B"]]), -0.5)

    def test_matches_pilot_a_binary_implementation(self):
        """Two different implementations must not quietly disagree on the case
        they both cover."""
        for pairs in ([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0), (1, 1)],
                      [(0, 0), (0, 1), (1, 1), (1, 1), (0, 0), (0, 1)],
                      [(1, 1), (1, 0), (0, 0), (0, 0), (1, 1), (1, 0)]):
            with self.subTest(pairs=pairs):
                nominal = krippendorff_alpha_nominal([[str(a), str(b)] for a, b in pairs])
                self.assertAlmostEqual(nominal, krippendorff_alpha_binary(pairs), places=9)

    def test_three_coders(self):
        self.assertAlmostEqual(krippendorff_alpha_nominal([["A"] * 3, ["B"] * 3]), 1.0)
        mixed = krippendorff_alpha_nominal([["A", "A", "B"], ["B", "B", "A"], ["A", "A", "A"]])
        self.assertIsNotNone(mixed)
        self.assertLess(mixed, 1.0)

    def test_uneven_coder_counts_are_handled(self):
        """A unit two people coded and another three must both contribute."""
        self.assertAlmostEqual(
            krippendorff_alpha_nominal([["A", "A", None], ["B", "B", "B"]]), 1.0)

    def test_single_rating_units_carry_no_agreement(self):
        self.assertIsNone(krippendorff_alpha_nominal([["A", None], ["B", None]]))

    def test_one_category_is_undefined_not_perfect(self):
        self.assertIsNone(krippendorff_alpha_nominal([["A", "A"], ["A", "A"]]))

    def test_four_categories(self):
        units = [["SAME", "SAME"], ["DIFFERENT", "DIFFERENT"],
                 ["MIXED", "MIXED"], ["INSUFFICIENT", "INSUFFICIENT"]]
        self.assertAlmostEqual(krippendorff_alpha_nominal(units), 1.0)


class DiagnosticsTests(unittest.TestCase):
    def test_raw_agreement_is_pairwise(self):
        self.assertEqual(raw_agreement([["A", "A", "B"]]), round(1 / 3, 4))

    def test_confusion_localises_the_split(self):
        c = pairwise_confusion([["SAME", "MIXED"], ["SAME", "MIXED"], ["DIFFERENT", "MIXED"]])
        self.assertEqual(c["MIXED <-> SAME"], 2)
        self.assertEqual(c["DIFFERENT <-> MIXED"], 1)

    def test_abstention_is_reported_not_silently_dropped(self):
        stats = primitive_stats([["YES", "INSUFFICIENT"]] * 12, ("YES", "NO", "INSUFFICIENT"))
        self.assertEqual(stats["distribution"]["INSUFFICIENT"], 12)
        self.assertEqual(stats["abstention_rate"], 0.5)

    def test_underpowered_when_everyone_abstains(self):
        stats = primitive_stats([["INSUFFICIENT", "INSUFFICIENT"]] * 20, ("YES", "NO", "INSUFFICIENT"))
        self.assertEqual(stats["estimability_status"], "underpowered_not_estimable")

    def test_underpowered_below_minimum_units(self):
        stats = primitive_stats([["YES", "NO"]] * 5, ("YES", "NO", "INSUFFICIENT"))
        self.assertEqual(stats["estimability_status"], "underpowered_not_estimable")

    def test_bootstrap_ci_is_deterministic(self):
        units = [["YES", "YES"]] * 10 + [["NO", "NO"]] * 10 + [["YES", "NO"]] * 4
        self.assertEqual(bootstrap_ci(units), bootstrap_ci(units))


class BoundaryMetricTests(unittest.TestCase):
    def _chain(self, a, b):
        return {"c1": {f"m{i}|m{i+1}": [a[i], b[i]] for i in range(len(a))}}

    def test_off_by_one_fails_strict_and_passes_tolerant(self):
        """The whole reason both are preregistered: one coder moving a boundary by
        a single message scores zero exact and one tolerant."""
        a = ["BOUNDARY", "NO_BOUNDARY", "NO_BOUNDARY", "NO_BOUNDARY"]
        b = ["NO_BOUNDARY", "BOUNDARY", "NO_BOUNDARY", "NO_BOUNDARY"]
        stats = boundary_stats(self._chain(a, b))
        self.assertEqual(stats["exact_match_f1_mean"], 0.0)
        self.assertEqual(stats["tolerant_f1_mean"], 1.0)
        self.assertEqual(stats["tolerance_messages"], BOUNDARY_TOLERANCE)

    def test_two_off_is_outside_tolerance(self):
        a = ["BOUNDARY", "NO_BOUNDARY", "NO_BOUNDARY", "NO_BOUNDARY"]
        b = ["NO_BOUNDARY", "NO_BOUNDARY", "BOUNDARY", "NO_BOUNDARY"]
        self.assertEqual(boundary_stats(self._chain(a, b))["tolerant_f1_mean"], 0.0)

    def test_nobody_marked_a_boundary_is_undefined_not_perfect(self):
        flat = ["NO_BOUNDARY"] * 4
        self.assertIsNone(boundary_stats(self._chain(flat, flat))["tolerant_f1_mean"])

    def test_strict_and_tolerant_are_reported_separately(self):
        a = ["BOUNDARY", "NO_BOUNDARY", "NO_BOUNDARY", "NO_BOUNDARY"]
        b = ["NO_BOUNDARY", "BOUNDARY", "NO_BOUNDARY", "NO_BOUNDARY"]
        stats = boundary_stats(self._chain(a, b))
        for key in ("strict_position_alpha", "exact_match_f1_mean", "tolerant_f1_mean"):
            self.assertIn(key, stats)
        self.assertIn("NOT independent", stats["note"])


class CorpusTests(unittest.TestCase):
    def test_shipped_corpus_is_valid(self):
        self.assertEqual(validate_corpus(CORPUS), [])

    def test_corpus_shape(self):
        rel = [json.loads(l) for l in (CORPUS / "relation-items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        seg = [json.loads(l) for l in (CORPUS / "segmentation-items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(rel), 60)
        self.assertEqual(len({it["stratum"] for it in rel}), 12)
        self.assertGreaterEqual(sum("P3" in it["applicable_primitives"] for it in rel), 20)
        self.assertGreaterEqual(sum("P4" in it["applicable_primitives"] for it in rel), 20)
        self.assertGreaterEqual(sum(len(c["candidate_boundaries"]) for c in seg), 40)

    def test_p3_p4_applicability_follows_anchor_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "relation-items.jsonl").write_text(json.dumps({
                "schema_version": "rf.primitives-item.v1", "item_id": "bad", "language": "ru",
                "stratum": "easy_positive", "anchor_kind": "neutral",
                "messages": [{"message_id": "bad-m1", "author": "a", "text": "x", "timestamp": 1},
                             {"message_id": "bad-m2", "author": "b", "text": "y", "timestamp": 2}],
                "anchor_message_id": "bad-m1", "target_message_id": "bad-m2",
                "applicable_primitives": ["P1", "P2", "P3"]}, ensure_ascii=False) + "\n",
                encoding="utf-8")
            (d / "segmentation-items.jsonl").write_text("", encoding="utf-8")
            self.assertTrue(any("P3 applicability" in i for i in validate_corpus(d)))


class PresentationTests(unittest.TestCase):
    def test_layers_are_deterministic_and_distinct(self):
        first = (CORPUS / "presentation" / "annotator-1-relation.jsonl").read_text(encoding="utf-8")
        materialize(CORPUS)
        self.assertEqual(first, (CORPUS / "presentation" / "annotator-1-relation.jsonl").read_text(encoding="utf-8"))
        others = (CORPUS / "presentation" / "annotator-2-relation.jsonl").read_text(encoding="utf-8")
        self.assertNotEqual(first, others, "each annotator gets their own order and ids")

    def test_presentation_hides_facilitator_only_fields(self):
        for annotator in ANNOTATORS:
            rows = [json.loads(l) for l in
                    (CORPUS / "presentation" / f"{annotator}-relation.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
            for row in rows:
                self.assertNotIn("stratum", row, "knowing what an item tests anchors the answer")
                self.assertNotIn("anchor_kind", row)
                self.assertTrue(row["item_id"].startswith("x"))

    def test_opaque_ids_do_not_collide_across_annotators(self):
        ids = {a: {opaque_id(f"rf-primitives-v0/{a}", f"rp-{i:02d}") for i in range(1, 61)}
               for a in ANNOTATORS}
        self.assertEqual(len(set().union(*ids.values())), 60 * len(ANNOTATORS))


class ResponseValidationTests(unittest.TestCase):
    ITEM = {"item_id": "rp-01", "anchor_kind": "negative",
            "applicable_primitives": ["P1", "P2", "P3"]}

    def _resp(self, **kw):
        base = {"schema_version": "rf.primitives-response.v1", "item_id": "rp-01",
                "p1": "YES", "p2": "SAME", "p3": "NO", "p4": None}
        base.update(kw)
        return base

    def test_valid_response_passes(self):
        self.assertEqual(validate_responses([self.ITEM], [self._resp()], "a1"), [])

    def test_answering_an_inapplicable_primitive_is_rejected(self):
        issues = validate_responses([self.ITEM], [self._resp(p4="YES")], "a1")
        self.assertTrue(any("not applicable" in i for i in issues))

    def test_missing_applicable_primitive_is_rejected(self):
        issues = validate_responses([self.ITEM], [self._resp(p3=None)], "a1")
        self.assertTrue(any("P3 must be one of" in i for i in issues))

    def test_unknown_category_is_rejected(self):
        issues = validate_responses([self.ITEM], [self._resp(p2="KIND_OF")], "a1")
        self.assertTrue(any("P2 must be one of" in i for i in issues))

    def test_unanswered_item_is_reported(self):
        self.assertTrue(any("not answered" in i for i in validate_responses([self.ITEM], [], "a1")))

    def test_boundary_values_are_constrained(self):
        chain = {"item_id": "sg-01", "candidate_boundaries": ["sg-01-m1|sg-01-m2"]}
        bad = {"schema_version": "rf.primitives-boundary-response.v1", "item_id": "sg-01",
               "boundaries": {"sg-01-m1|sg-01-m2": "MAYBE"}}
        self.assertTrue(any("must be one of" in i
                            for i in validate_boundary_responses([chain], [bad], "a1")))


class ReportGuardTests(unittest.TestCase):
    def test_report_refuses_without_two_layers(self):
        """No responses exist yet; the report must refuse rather than invent one."""
        self.assertEqual(report(CORPUS), 2)
