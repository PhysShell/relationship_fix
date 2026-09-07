"""Тесты blinded A/B: детерминизм, отсутствие утечки, покрытие map, сведение ответов."""

import json
import unittest

from metrics.naturalness_ab import (
    assert_no_leak,
    build_packet,
    recommend,
    score,
    validate_responses,
)


def candidates(n_items=4):
    items = []
    for k in range(1, n_items + 1):
        items.append({
            "item_id": f"pc-{k:02d}", "language": "ru", "flags": ["THERAPIST_VOICE"], "severity": "high",
            "original": {"messages": [{"author": "a", "text": f"A{k}"}, {"author": "b", "text": f"B{k} original"}],
                         "target_index": 1},
            "candidates": [
                {"candidate_id": f"pc-{k:02d}-c1", "messages": [{"author": "a", "text": f"A{k}"}, {"author": "b", "text": f"B{k} one"}]},
                {"candidate_id": f"pc-{k:02d}-c2", "messages": [{"author": "a", "text": f"A{k}"}, {"author": "b", "text": f"B{k} two"}]},
            ],
        })
    return {"schema_version": "rf.naturalness-ab-candidates.v1", "ab_id": "test", "items": items}


class BuildTests(unittest.TestCase):
    def test_deterministic_and_complete(self):
        c = candidates()
        p1, m1 = build_packet(c, "rater-1", "seed-1")
        p2, m2 = build_packet(c, "rater-1", "seed-1")
        self.assertEqual(p1, p2)
        self.assertEqual(set(m1["map"]), {p["pair_id"] for p in p1["pairs"]})
        self.assertEqual(len(m1["map"]), 8)
        self.assertEqual({(v["item_id"], v["candidate_id"]) for v in m1["map"].values()},
                         {(i["item_id"], cc["candidate_id"]) for i in c["items"] for cc in i["candidates"]})

    def test_raters_get_their_own_order_and_sides(self):
        c = candidates()
        p1, m1 = build_packet(c, "rater-1", "seed-1")
        p2, m2 = build_packet(c, "rater-2", "seed-2")
        self.assertNotEqual([p["pair_id"] for p in p1["pairs"]], [p["pair_id"] for p in p2["pairs"]])
        for mapping in (m1, m2):
            self.assertEqual({v["original_side"] for v in mapping["map"].values()}, {"left", "right"})

    def test_original_side_matches_content(self):
        c = candidates()
        packet, mapping = build_packet(c, "rater-1", "seed-1")
        for pair in packet["pairs"]:
            entry = mapping["map"][pair["pair_id"]]
            shown = pair[entry["original_side"]][1]["text"]
            self.assertIn("original", shown)

    def test_no_leak(self):
        c = candidates()
        packet, _ = build_packet(c, "rater-1", "seed-1")
        assert_no_leak(packet, c)
        serialized = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn("pc-", serialized)
        self.assertNotIn("THERAPIST", serialized)
        self.assertEqual(set(packet["pairs"][0]), {"pair_id", "language", "left", "right"})
        with self.assertRaises(ValueError):  # facilitator key
            assert_no_leak({**packet, "pairs": [{**packet["pairs"][0], "original_side": "left"}]}, c)
        with self.assertRaises(ValueError):  # id in a value
            assert_no_leak({**packet, "pairs": [{**packet["pairs"][0], "pair_id": "pc-01-c1"}]}, c)


class ScoreTests(unittest.TestCase):
    def responses(self, mapping, rater_id, choose):
        out = []
        for pid, entry in mapping["map"].items():
            more_natural, shift = choose(entry)
            out.append({"schema_version": "rf.naturalness-ab-response.v1", "pair_id": pid,
                        "rater_id": rater_id, "more_natural": more_natural, "meaning_shift": shift})
        return out

    def test_votes_are_remapped_through_original_side(self):
        c = candidates(n_items=1)
        packet, mapping = build_packet(c, "rater-1", "seed-1")

        def choose(entry):
            other = "right" if entry["original_side"] == "left" else "left"
            if entry["candidate_id"].endswith("c1"):
                return other, "same"          # кандидат 1 естественнее, смысл тот же
            return entry["original_side"], "substantial"  # кандидат 2 хуже и меняет смысл

        layer = self.responses(mapping, "rater-1", choose)
        self.assertEqual(validate_responses(layer, mapping["map"], "rater-1"), [])
        result = score(c, {"rater-1": layer}, {"rater-1": mapping["map"]})
        by_id = {t["candidate_id"]: t for t in result["per_candidate"]}
        self.assertEqual(by_id["pc-01-c1"]["prefers_candidate"], 1)
        self.assertEqual(by_id["pc-01-c1"]["recommendation"], "eligible")
        self.assertEqual(by_id["pc-01-c2"]["prefers_original"], 1)
        self.assertEqual(by_id["pc-01-c2"]["recommendation"], "reject_meaning_shift")
        self.assertEqual(result["per_item"][0]["best_eligible"], "pc-01-c1")
        self.assertEqual(result["per_item"][0]["suggested_outcome"], "accept_best_eligible")

    def test_tie_keeps_original(self):
        tally = {"prefers_candidate": 2, "prefers_original": 2, "meaning_shift": {"same": 4, "slight": 0, "substantial": 0}}
        self.assertEqual(recommend(tally), "keep_original")

    def test_response_validation(self):
        c = candidates(n_items=1)
        _, mapping = build_packet(c, "rater-1", "seed-1")
        pids = list(mapping["map"])
        bad = [
            {"schema_version": "rf.naturalness-ab-response.v1", "pair_id": pids[0], "rater_id": "rater-1",
             "more_natural": "up", "meaning_shift": "same"},
            {"schema_version": "rf.naturalness-ab-response.v1", "pair_id": pids[0], "rater_id": "rater-1",
             "more_natural": "left", "meaning_shift": "same"},
            {"schema_version": "rf.naturalness-ab-response.v1", "pair_id": "pair-ghost", "rater_id": "rater-2",
             "more_natural": "left", "meaning_shift": "same"},
        ]
        issues = validate_responses(bad, mapping["map"], "rater-1")
        joined = "\n".join(issues)
        for fragment in ("answered 2 times", "unknown pair", "not answered", "more_natural must be", "rater_id mismatch"):
            self.assertIn(fragment, joined)


if __name__ == "__main__":
    unittest.main()
