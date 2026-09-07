"""Тесты blinded A/B: детерминизм, отсутствие утечки, покрытие map, сведение ответов."""

import json
import unittest

from metrics.naturalness_ab import (
    assert_no_leak,
    build_packet,
    check_candidates,
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
                {"candidate_id": f"pc-{k:02d}-c1", "checker": "ok",
                 "messages": [{"author": "a", "text": f"A{k}"}, {"author": "b", "text": f"B{k} one"}]},
                {"candidate_id": f"pc-{k:02d}-c2", "checker": "ok",
                 "messages": [{"author": "a", "text": f"A{k}"}, {"author": "b", "text": f"B{k} two"}]},
            ],
            "vetoed": [],
            "source_package": "annotation-pilot-v0",
        })
    return {"schema_version": "rf.naturalness-ab-candidates.v1", "ab_id": "test",
            "veto_checklist": [{"id": "V1", "check": "construct"}, {"id": "V3", "check": "no new action"}],
            "items": items}


def corpus_for(c):
    return {"annotation-pilot-v0": {
        i["item_id"]: {"messages": [(m["author"], m["text"]) for m in i["original"]["messages"]],
                       "target_index": i["original"]["target_index"]}
        for i in c["items"]}}


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


class AdmissibilityTests(unittest.TestCase):
    """Veto-review оставляет след: кандидат либо допущен, либо vetoed с причиной и пунктом
    чек-листа, либо rejected как negative control. Ничего не исчезает бесследно."""

    def test_clean_fixture_is_admissible(self):
        c = candidates()
        issues, notes = check_candidates(c, corpus_for(c))
        self.assertEqual(issues, [])
        self.assertEqual(notes, [])

    def test_vetoed_needs_reason_checklist_and_single_home(self):
        c = candidates(n_items=1)
        cand = c["items"][0]["candidates"][1]
        c["items"][0]["vetoed"] = [{"candidate_id": cand["candidate_id"], "messages": cand["messages"],
                                    "vetoed_by": "facilitator", "checklist": ["V9"], "reason": ""}]
        issues, _ = check_candidates(c, corpus_for(c))
        joined = "\n".join(issues)
        self.assertIn("vetoed without reason", joined)
        self.assertIn("existing veto_checklist ids", joined)
        self.assertIn("appears 2 times", joined)

    def test_proper_veto_is_recorded_and_excluded_from_pairs(self):
        c = candidates(n_items=1)
        cand = c["items"][0]["candidates"].pop(1)
        c["items"][0]["vetoed"] = [{**cand, "vetoed_by": "facilitator", "checklist": ["V3"], "reason": "adds an apology"}]
        issues, _ = check_candidates(c, corpus_for(c))
        self.assertEqual(issues, [])
        packet, mapping = build_packet(c, "rater-1", "seed-1")
        self.assertEqual(len(packet["pairs"]), 1)
        self.assertNotIn(cand["candidate_id"], [v["candidate_id"] for v in mapping["map"].values()])
        result = score(c, {}, {})
        self.assertTrue(result["compared_only_admissible"])
        self.assertEqual(result["n_vetoed"], 1)
        self.assertEqual(result["per_item"][0]["vetoed_before_issuance"][0]["reason"], "adds an apology")

    def test_candidate_shape_rules(self):
        c = candidates(n_items=1)
        item = c["items"][0]
        item["candidates"][0]["messages"] = list(item["original"]["messages"])            # identical
        item["candidates"][1]["messages"] = item["candidates"][1]["messages"] + [{"author": "a", "text": "extra"}]  # new message
        item["candidates"][1]["checker"] = ""
        issues, _ = check_candidates(c, corpus_for(c))
        joined = "\n".join(issues)
        for fragment in ("identical to the original", "message count/authors differ", "without checker note"):
            self.assertIn(fragment, joined)

    def test_original_is_verified_against_corpus(self):
        c = candidates(n_items=1)
        corpus = corpus_for(c)
        corpus["annotation-pilot-v0"]["pc-01"]["messages"][1] = ("b", "B1 something else")
        issues, _ = check_candidates(c, corpus)
        self.assertTrue(any("differs from the corpus" in i for i in issues))
        c["items"][0]["source_package"] = "annotation-ux-v6"
        issues, notes = check_candidates(c, corpus)
        self.assertEqual(issues, [])
        self.assertTrue(any("not verified" in n for n in notes))

    def test_missing_vetoed_list_or_checklist_is_an_issue(self):
        c = candidates(n_items=1)
        del c["items"][0]["vetoed"]
        c["veto_checklist"] = []
        issues, _ = check_candidates(c)
        joined = "\n".join(issues)
        self.assertIn("'vetoed' list is required", joined)
        self.assertIn("veto_checklist", joined)


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
