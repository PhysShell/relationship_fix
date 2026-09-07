"""Тесты слепого аудита: стерильность Pass A, детерминизм, правило not_applicable, Pass B counts."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from metrics.naturalness_audit import (
    assert_sterile,
    build_packet,
    load_stimuli,
    report,
    validate_responses,
)


def stimuli():
    return [
        {"package_id": "annotation-pilot-v0", "item_id": "pc-01", "language": "ru",
         "messages": [{"author": "a", "text": "Раз."}, {"author": "b", "text": "Два."}]},
        {"package_id": "annotation-pilot-v0", "item_id": "pn-01", "language": "ru",
         "messages": [{"author": "a", "text": "Одно сообщение."}]},
        {"package_id": "annotation-ux-v6", "item_id": "dg-04", "language": "ru",
         "messages": [{"author": "a", "text": "Три."}, {"author": "b", "text": "Четыре."}]},
    ]


TRIAGE = {"severity_order": ["none", "low", "medium", "medium-high", "high"], "flagged_threshold": "medium",
          "items": [{"item_id": "pc-01", "flags": ["THERAPIST_VOICE"], "severity": "high"},
                    {"item_id": "pn-01", "flags": [], "severity": "none"},
                    {"item_id": "dg-04", "flags": ["EXPOSITION_FOR_READER"], "severity": "medium-high"}]}
STRATA = {"pc-01": "challenge", "pn-01": "natural"}


class PassATests(unittest.TestCase):
    def test_sterile_and_deterministic(self):
        s = stimuli()
        p1, m1 = build_packet(s, "auditor-1", "seed-1")
        p2, _ = build_packet(s, "auditor-1", "seed-1")
        self.assertEqual(p1, p2)
        assert_sterile(p1, s)
        serialized = json.dumps(p1, ensure_ascii=False)
        for token in ("pc-", "pn-", "dg-", "target", "stratum", "flags", "severity"):
            self.assertNotIn(token, serialized)
        self.assertEqual(set(m1["map"]), {e["audit_item_id"] for e in p1["items"]})
        self.assertEqual({v["item_id"] for v in m1["map"].values()}, {"pc-01", "pn-01", "dg-04"})

    def test_non_sterile_packet_is_rejected(self):
        s = stimuli()
        packet, _ = build_packet(s, "auditor-1", "seed-1")
        with self.assertRaises(ValueError):
            assert_sterile({**packet, "items": [{**packet["items"][0], "stratum": "challenge"}]}, s)
        with self.assertRaises(ValueError):
            assert_sterile({**packet, "items": [{**packet["items"][0], "audit_item_id": "pc-01"}]}, s)

    def test_auditors_get_different_orders(self):
        s = stimuli() * 3  # 9 entries, distinct ids needed → make ids unique
        for i, st in enumerate(s):
            st = dict(st); st["item_id"] = f"{st['item_id']}-{i}"; s[i] = st
        p1, _ = build_packet(s, "auditor-1", "seed-1")
        p2, _ = build_packet(s, "auditor-2", "seed-2")
        self.assertNotEqual([e["messages"] for e in p1["items"]], [e["messages"] for e in p2["items"]])


class ResponseTests(unittest.TestCase):
    def responses(self, mapping, auditor_id, natural="yes"):
        out = []
        for oid, entry in mapping["map"].items():
            out.append({"schema_version": "rf.naturalness-audit-response.v1", "audit_item_id": oid, "auditor_id": auditor_id,
                        "natural": natural, "invisible_context": "not_applicable" if entry["n_messages"] == 1 else "no",
                        "other_problem": ""})
        return out

    def test_valid_layer(self):
        _, mapping = build_packet(stimuli(), "auditor-1", "seed-1")
        self.assertEqual(validate_responses(self.responses(mapping, "auditor-1"), mapping["map"], "auditor-1"), [])

    def test_not_applicable_rule_both_directions(self):
        _, mapping = build_packet(stimuli(), "auditor-1", "seed-1")
        layer = self.responses(mapping, "auditor-1")
        for r in layer:
            r["invisible_context"] = "no" if mapping["map"][r["audit_item_id"]]["n_messages"] == 1 else "not_applicable"
        issues = validate_responses(layer, mapping["map"], "auditor-1")
        joined = "\n".join(issues)
        self.assertIn("single-message item", joined)
        self.assertIn("multi-message item", joined)

    def test_missing_and_unknown(self):
        _, mapping = build_packet(stimuli(), "auditor-1", "seed-1")
        layer = self.responses(mapping, "auditor-1")[:-1]
        layer.append({**layer[0], "audit_item_id": "audit-ghost"})
        joined = "\n".join(validate_responses(layer, mapping["map"], "auditor-1"))
        self.assertIn("not answered", joined)
        self.assertIn("unknown item", joined)


class PassBTests(unittest.TestCase):
    def test_counts_against_critic1_by_stratum(self):
        s = stimuli()
        _, m1 = build_packet(s, "auditor-1", "seed-1")
        _, m2 = build_packet(s, "auditor-2", "seed-2")

        def layer(mapping, auditor_id, verdicts):
            out = []
            for oid, entry in mapping["map"].items():
                out.append({"schema_version": "rf.naturalness-audit-response.v1", "audit_item_id": oid, "auditor_id": auditor_id,
                            "natural": verdicts[entry["item_id"]],
                            "invisible_context": "not_applicable" if entry["n_messages"] == 1 else ("yes" if entry["item_id"] == "dg-04" else "no"),
                            "other_problem": ""})
            return out

        layers = {"auditor-1": layer(m1, "auditor-1", {"pc-01": "no", "pn-01": "yes", "dg-04": "yes"}),
                  "auditor-2": layer(m2, "auditor-2", {"pc-01": "partly", "pn-01": "yes", "dg-04": "partly"})}
        result = report(layers, {"auditor-1": m1["map"], "auditor-2": m2["map"]}, TRIAGE, STRATA)
        self.assertEqual(result["n_items"], 3)
        # pc-01: auditors not natural + critic flagged → both; dg-04: auditor-2 partly + critic flagged → both; pn-01: neither
        self.assertEqual(result["natural_x_critic1_all"], {"both": 2, "auditor_only": 0, "critic_only": 0, "neither": 1})
        self.assertEqual(result["by_stratum"]["dogfood"]["natural_x_critic1"]["both"], 1)
        self.assertEqual(result["by_stratum"]["natural"]["critic1_flagged"], 0)
        self.assertEqual(result["invisible_context_x_critic1_adjacency_all"], {"both": 1, "auditor_only": 0, "critic_only": 0, "neither": 2})
        # binary (yes vs not-yes): pc-01 no/partly agree, pn-01 yes/yes agree, dg-04 yes/partly disagree
        self.assertEqual(result["inter_auditor"]["natural_binary_agreement"], 2)
        self.assertEqual(result["inter_auditor"]["natural_exact_agreement"], 1)    # only pn-01 identical


class SourceLoadingTests(unittest.TestCase):
    def test_snapshot_must_match_pinned_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "dogfood.yaml"
            src.write_text("items: []\n", encoding="utf-8")
            sha = hashlib.sha256(src.read_bytes()).hexdigest()
            snap = root / "snapshot.json"
            snap.write_text(json.dumps({"source_sha256": sha, "items": [
                {"item_id": "dg-04", "language": "ru", "messages": [{"author": "a", "text": "x"}], "target_index": 0}]}), encoding="utf-8")
            manifest = {"sources": [{"package_id": "annotation-ux-v6", "snapshot_file": "snapshot.json",
                                     "source_file": "dogfood.yaml", "source_sha256": sha}]}
            stimuli_out, issues = load_stimuli(root, manifest)
            self.assertEqual(issues, [])
            self.assertEqual(stimuli_out[0]["item_id"], "dg-04")
            src.write_text("items: [changed]\n", encoding="utf-8")
            _, issues = load_stimuli(root, manifest)
            self.assertTrue(any("regenerate the snapshot" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
