"""Тесты rf.pilot-item.v2: content hash, stimulus-проекция, инварианты authoring и
сквозная валидация пакета с lineage в соседний пакет."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from metrics.items import SCHEMA_V1, SCHEMA_V2, authoring_issues, item_content_sha256, stimulus_only
from metrics.validate_items import structural_issues, validate


def v1(item_id="pc-01", texts=("Раз.", "Два."), target=2, language="ru"):
    return {
        "schema_version": SCHEMA_V1, "item_id": item_id, "language": language,
        "messages": [{"message_id": f"{item_id}-m{i}", "author": "ab"[(i - 1) % 2], "text": t}
                     for i, t in enumerate(texts, start=1)],
        "target_message_id": f"{item_id}-m{target}",
    }


def v2(authoring, **kwargs):
    item = v1(**kwargs)
    item["schema_version"] = SCHEMA_V2
    item["authoring"] = authoring
    return item


def parent_ref(parent, package_id="annotation-pilot-v0"):
    return {"package_id": package_id, "item_id": parent["item_id"], "content_sha256": item_content_sha256(parent)}


class ContentHashTests(unittest.TestCase):
    def test_hash_ignores_ids_and_authoring(self):
        a = v1(item_id="pc-01")
        b = v2({"origin": "unrecorded"}, item_id="x-99")
        self.assertEqual(item_content_sha256(a), item_content_sha256(b))

    def test_hash_sees_text_and_target(self):
        base = v1()
        self.assertNotEqual(item_content_sha256(base), item_content_sha256(v1(texts=("Раз.", "Три."))))
        self.assertNotEqual(item_content_sha256(base), item_content_sha256(v1(target=1)))

    def test_stimulus_only_drops_authoring(self):
        projected = stimulus_only(v2({"origin": "human", "note": "secret"}))
        self.assertEqual(projected["schema_version"], SCHEMA_V1)
        self.assertNotIn("authoring", projected)
        self.assertNotIn("note", json.dumps(projected))


class AuthoringRuleTests(unittest.TestCase):
    parent = v1()

    def lookup(self, package_id, item_id):
        return self.parent if (package_id, item_id) == ("annotation-pilot-v0", "pc-01") else None

    def test_original_is_clean(self):
        item = v2({"origin": "human", "revision_reason": None, "accepted_via": "original", "parent_item_version": None})
        self.assertEqual(authoring_issues(item, self.lookup), [])

    def test_original_cannot_claim_ab_acceptance(self):
        item = v2({"origin": "human", "revision_reason": None, "accepted_via": "blinded_ab", "parent_item_version": None})
        self.assertTrue(any("must be 'original'" in i for i in authoring_issues(item, self.lookup)))

    def test_carried_over_requires_identical_text(self):
        same = v2({"origin": "unrecorded", "revision_reason": None, "accepted_via": "carried_over",
                   "parent_item_version": parent_ref(self.parent)})
        self.assertEqual(authoring_issues(same, self.lookup), [])
        changed = v2({"origin": "unrecorded", "revision_reason": None, "accepted_via": "carried_over",
                      "parent_item_version": parent_ref(self.parent)}, texts=("Раз.", "Другое."))
        self.assertTrue(any("content differs" in i for i in authoring_issues(changed, self.lookup)))

    def test_revision_requires_changed_text_and_named_acceptance(self):
        ok = v2({"origin": "llm_assisted", "revision_reason": "naturalness", "accepted_via": "blinded_ab",
                 "parent_item_version": parent_ref(self.parent)}, texts=("Раз.", "да блин."))
        self.assertEqual(authoring_issues(ok, self.lookup), [])
        identical = v2({"origin": "llm_assisted", "revision_reason": "naturalness", "accepted_via": "blinded_ab",
                        "parent_item_version": parent_ref(self.parent)})
        self.assertTrue(any("identical" in i for i in authoring_issues(identical, self.lookup)))
        unnamed = v2({"origin": "human", "revision_reason": "grammar", "accepted_via": "original",
                      "parent_item_version": parent_ref(self.parent)}, texts=("Раз.", "Два!"))
        self.assertTrue(any("blinded_ab|facilitator" in i for i in authoring_issues(unnamed, self.lookup)))

    def test_revision_cannot_be_unrecorded(self):
        item = v2({"origin": "unrecorded", "revision_reason": "naturalness", "accepted_via": "facilitator",
                   "parent_item_version": parent_ref(self.parent)}, texts=("Раз.", "Два!"))
        self.assertTrue(any("someone wrote it" in i for i in authoring_issues(item, self.lookup)))

    def test_parent_hash_and_existence_are_verified(self):
        wrong = parent_ref(self.parent)
        wrong["content_sha256"] = hashlib.sha256(b"nope").hexdigest()
        item = v2({"origin": "human", "revision_reason": "adjacency", "accepted_via": "facilitator",
                   "parent_item_version": wrong}, texts=("Раз.", "Два!"))
        self.assertTrue(any("content_sha256 mismatch" in i for i in authoring_issues(item, self.lookup)))
        missing = v2({"origin": "human", "revision_reason": "adjacency", "accepted_via": "facilitator",
                      "parent_item_version": parent_ref(self.parent, package_id="ghost")}, texts=("Раз.", "Два!"))
        self.assertTrue(any("not found" in i for i in authoring_issues(missing, self.lookup)))

    def test_bad_enums_are_reported(self):
        item = v2({"origin": "model", "revision_reason": "vibes", "accepted_via": "taste", "parent_item_version": None})
        joined = "\n".join(authoring_issues(item, self.lookup))
        for field in ("authoring.origin must be", "authoring.revision_reason must be", "authoring.accepted_via must be"):
            self.assertIn(field, joined)

    def test_structural_rules_for_schema_versions(self):
        self.assertTrue(any("requires 'authoring'" in i for i in structural_issues([v1() | {"schema_version": SCHEMA_V2}])))
        self.assertTrue(any("does not carry" in i for i in structural_issues([v1() | {"authoring": {}}])))
        self.assertTrue(any("mixed schema" in i for i in structural_issues([v1(), v2({}, item_id="pc-02")])))


class PackageLineageTests(unittest.TestCase):
    """v0 (v1 items) и v0.1 (v2 items c parent → v0) лежат рядом; validate() v0.1
    обязан найти родителя по pilot_id соседнего manifest'а и проверить hash."""

    def write_package(self, root, name, pilot_id, items, ontology_path):
        pkg = root / name
        pkg.mkdir()
        (pkg / "items.jsonl").write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")
        (pkg / "strata.json").write_text(json.dumps({"strata": {i["item_id"]: "challenge" for i in items}}), encoding="utf-8")
        (pkg / "eligibility.json").write_text(json.dumps({"annotators": {}}), encoding="utf-8")
        (pkg / "pilot-manifest.json").write_text(json.dumps({
            "pilot_id": pilot_id, "ontology_version": "t", "items_file": "items.jsonl", "strata_file": "strata.json",
            "ontology_sha256": hashlib.sha256(ontology_path.read_bytes()).hexdigest(),
            "active_labels": ["B.X"], "annotators": [],
        }), encoding="utf-8")
        return pkg

    def test_child_package_validates_against_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ontology = root / "ontology.json"
            ontology.write_text(json.dumps({"ontology_version": "t", "labels": [{"id": "B.X", "allowed_units": ["utterance"]}]}), encoding="utf-8")
            parent = v1()
            self.write_package(root, "v0", "annotation-pilot-v0", [parent], ontology)
            child_ok = v2({"origin": "llm_assisted", "revision_reason": "naturalness", "accepted_via": "blinded_ab",
                           "parent_item_version": parent_ref(parent)}, texts=("Раз.", "ну два"))
            pkg = self.write_package(root, "v0.1", "annotation-pilot-v0.1", [child_ok], ontology)
            self.assertEqual(validate(pkg, ontology), [])

            child_bad = v2({"origin": "llm_assisted", "revision_reason": "naturalness", "accepted_via": "blinded_ab",
                            "parent_item_version": parent_ref(parent)})  # текст не изменился
            (pkg / "items.jsonl").write_text(json.dumps(child_bad, ensure_ascii=False) + "\n", encoding="utf-8")
            self.assertTrue(any("identical" in i for i in validate(pkg, ontology)))

    def test_presentation_must_not_leak_authoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ontology = root / "ontology.json"
            ontology.write_text(json.dumps({"ontology_version": "t", "labels": [{"id": "B.X", "allowed_units": ["utterance"]}]}), encoding="utf-8")
            item = v2({"origin": "human", "revision_reason": None, "accepted_via": "original", "parent_item_version": None})
            pkg = self.write_package(root, "v0.1", "annotation-pilot-v0.1", [item], ontology)
            manifest = json.loads((pkg / "pilot-manifest.json").read_text())
            manifest["presentation"] = {"annotator-1": {"seed": "s"}}
            (pkg / "pilot-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (pkg / "presentation").mkdir()
            (pkg / "presentation-map").mkdir()
            leaked = {**item, "item_id": "item-abc123", "target_message_id": "item-abc123-m2",
                      "messages": [{"message_id": "item-abc123-m1", "author": "a", "text": "Раз."},
                                   {"message_id": "item-abc123-m2", "author": "b", "text": "Два."}]}
            (pkg / "presentation" / "annotator-1.jsonl").write_text(json.dumps(leaked, ensure_ascii=False) + "\n", encoding="utf-8")
            (pkg / "presentation-map" / "annotator-1.json").write_text(json.dumps({"map": {"item-abc123": "pc-01"}}), encoding="utf-8")
            self.assertTrue(any("без authoring" in i for i in validate(pkg, ontology)))


if __name__ == "__main__":
    unittest.main()
