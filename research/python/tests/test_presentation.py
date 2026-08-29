"""Тесты blind presentation layer: детерминизм, отсутствие утечки canonical id, remap."""

import unittest

from metrics.presentation import assert_no_canonical_leak, build_presentation, opaque_id

ITEMS = [
    {"schema_version": "rf.pilot-item.v1", "item_id": "pc-01", "language": "ru",
     "messages": [{"message_id": "pc-01-m1", "author": "a", "text": "Раз."},
                  {"message_id": "pc-01-m2", "author": "b", "text": "Два."}],
     "target_message_id": "pc-01-m2"},
    {"schema_version": "rf.pilot-item.v1", "item_id": "pc-02", "language": "ru",
     "messages": [{"message_id": "pc-02-m1", "author": "a", "text": "Три."}],
     "target_message_id": "pc-02-m1"},
    {"schema_version": "rf.pilot-item.v1", "item_id": "pn-01", "language": "en",
     "messages": [{"message_id": "pn-01-m1", "author": "b", "text": "Four."}],
     "target_message_id": "pn-01-m1"},
]


class PresentationTests(unittest.TestCase):
    def test_deterministic_for_same_seed(self):
        first = build_presentation(ITEMS, "seed-x")
        second = build_presentation(ITEMS, "seed-x")
        self.assertEqual(first, second)

    def test_different_seeds_give_different_ids(self):
        _, map_a = build_presentation(ITEMS, "seed-a")
        _, map_b = build_presentation(ITEMS, "seed-b")
        self.assertEqual(set(map_a.values()), set(map_b.values()))  # те же canonical
        self.assertNotEqual(set(map_a.keys()), set(map_b.keys()))   # разные opaque

    def test_no_canonical_leak_in_presented_ids(self):
        presented, _ = build_presentation(ITEMS, "seed-x")
        assert_no_canonical_leak(presented, {i["item_id"] for i in ITEMS})
        for item in presented:
            self.assertTrue(item["item_id"].startswith("item-"))
            self.assertNotIn("pc-", item["item_id"])
            self.assertNotIn("pn-", item["item_id"])

    def test_target_message_remapped_consistently(self):
        presented, mapping = build_presentation(ITEMS, "seed-x")
        for item in presented:
            self.assertIn(item["target_message_id"],
                          [m["message_id"] for m in item["messages"]])
            canonical = mapping[item["item_id"]]
            original = next(i for i in ITEMS if i["item_id"] == canonical)
            # target остался тем же сообщением по позиции/тексту
            original_target = next(m for m in original["messages"]
                                   if m["message_id"] == original["target_message_id"])
            presented_target = next(m for m in item["messages"]
                                    if m["message_id"] == item["target_message_id"])
            self.assertEqual(presented_target["text"], original_target["text"])

    def test_remap_roundtrip(self):
        presented, mapping = build_presentation(ITEMS, "seed-x")
        responses = [{"item_id": p["item_id"], "decision": "none_observed"} for p in presented]
        canonical = {mapping[r["item_id"]] for r in responses}
        self.assertEqual(canonical, {i["item_id"] for i in ITEMS})

    def test_opaque_id_is_stable(self):
        self.assertEqual(opaque_id("s", "pc-01"), opaque_id("s", "pc-01"))
        self.assertNotEqual(opaque_id("s", "pc-01"), opaque_id("s", "pc-02"))


if __name__ == "__main__":
    unittest.main()
