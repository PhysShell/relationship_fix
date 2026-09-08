"""Тесты metrics.materialize: exact accepted→built equality gate, package-level replaces,
fresh ids, carried_over из frozen source, отказы (sha pin, overwrite, missing mapping),
dogfood yaml парсер/рендер с sidecar."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from metrics.items import SCHEMA_V1, canonical_content_sha256, item_content_sha256
from metrics.materialize import (SPEC_SCHEMA, build_package, dogfood_package, parse_dogfood_yaml,
                                 render_dogfood_yaml, seal_package, verify_package)
from metrics.validate_items import validate


def v1(item_id, texts, target=2, language="ru"):
    return {
        "schema_version": SCHEMA_V1, "item_id": item_id, "language": language,
        "messages": [{"message_id": f"{item_id}-m{i}", "author": "ab"[(i - 1) % 2], "text": t}
                     for i, t in enumerate(texts, start=1)],
        "target_message_id": f"{item_id}-m{target}",
    }


def candidate(cid, kind, messages, outcome="accepted", at_build=None, caveat=None):
    review = {"date": "2026-09-08", "outcome": outcome, "by": "facilitator", "reason": "ok", "at_build": at_build or {}}
    if caveat:
        review["caveat"] = caveat
    return {"candidate_id": cid, "origin": "llm_assisted", "kind": kind, "messages": messages,
            "checker": "x", "facilitator_review": review,
            "provenance": {"method": "external_dialogue_seeded", "source_corpus": "Aniemore/resd_annotated",
                           "source_license": "MIT", "source_text_copied": False, "extra": "dropped"}}


DOGFOOD_YAML = """schema_version: rf.dogfood-items.v1
dogfood_id: annotation-ux-v6
status: debug_only_not_scientific_evidence
language: ru
included_in_scientific_pilot: false
purpose: >-
  Fresh cases.

items:
  - item_id: dg-04
    probe: p
    messages:
      - author: a
        text: "Я проснулась от холода."
      - author: b
        text: "Ты вчера оставила окно открытым, \\"да\\"."
        target: true
    design_note: >-
      note one

  - item_id: dg-05
    probe: q
    messages:
      - author: a
        text: "Мне было страшно."
      - author: b
        text: "Понимаю."
        target: true
    design_note: >-
      note two

methodological_rule: >-
  Do not add expected labels.
"""


class Fixture:
    """v0 (3 items) + candidates (pc-02 → replacement, pc-03 → revision) + spec для v0.1."""

    def __init__(self, root: Path):
        self.root = root
        self.ontology = root / "ontology.json"
        self.ontology.write_text(json.dumps({"ontology_version": "t", "labels": [{"id": "B.X", "allowed_units": ["utterance"]}]}), encoding="utf-8")
        self.source = [v1("pc-01", ("Раз.", "Два.")), v1("pc-02", ("Три.", "Четыре.")), v1("pc-03", ("Пять.", "Шесть."), target=1)]
        v0 = root / "v0"
        v0.mkdir()
        (v0 / "items.jsonl").write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in self.source) + "\n", encoding="utf-8")
        (v0 / "strata.json").write_text(json.dumps({"strata": {"pc-01": "natural", "pc-02": "challenge", "pc-03": "challenge"}}), encoding="utf-8")
        (v0 / "eligibility.json").write_text(json.dumps({"annotators": {}}), encoding="utf-8")
        (v0 / "pilot-manifest.json").write_text(json.dumps({
            "schema_version": "rf.pilot-manifest.v1", "pilot_id": "annotation-pilot-v0", "ontology_version": "t",
            "ontology_sha256": hashlib.sha256(self.ontology.read_bytes()).hexdigest(),
            "items_file": "items.jsonl", "strata_file": "strata.json", "active_labels": ["B.X"], "annotators": [],
            "eligibility_criteria": ["fluent_ru", "has_not_seen_items"], "blind_rules": ["r"],
        }), encoding="utf-8")
        self.candidates_path = root / "candidates.json"
        self.write_candidates()
        self.pkg = root / "v0.1"
        self.pkg.mkdir()
        self.spec_path = self.pkg / "build-spec.json"
        self.write_spec()

    def write_candidates(self, revision_text="шесть, ну"):
        parent = {"package_id": "annotation-pilot-v0", "item_id": "pc-03", "content_sha256": item_content_sha256(self.source[2])}
        data = {"items": [
            {"item_id": "pc-02", "source_package": "annotation-pilot-v0", "edit_constraint": "demand",
             "original": {"messages": [{"author": "a", "text": "Три."}, {"author": "b", "text": "Четыре."}], "target_index": 1},
             "candidates": [candidate("pc-02-d2", "replacement", [{"author": "a", "text": "Ключи?"}, {"author": "b", "text": "Унёс."}],
                                      at_build={"accepted_via": "facilitator", "design_intent": "demand"})],
             "vetoed": [candidate("pc-02-d1", "replacement", [{"author": "a", "text": "x"}, {"author": "b", "text": "y"}], outcome="vetoed")]},
            {"item_id": "pc-03", "source_package": "annotation-pilot-v0",
             "original": {"messages": [{"author": "a", "text": "Пять."}, {"author": "b", "text": "Шесть."}], "target_index": 0},
             "candidates": [candidate("pc-03-d1", "revision", [{"author": "a", "text": "Пять."}, {"author": "b", "text": revision_text}],
                                      at_build={"accepted_via": "facilitator", "revision_reason": "naturalness", "parent_item_version": parent},
                                      caveat="V7 soft")],
             "vetoed": []},
            {"item_id": "dg-04", "source_package": "annotation-ux-v6",
             "original": {"messages": [{"author": "a", "text": "Я проснулась от холода."}, {"author": "b", "text": "Ты вчера оставила окно открытым, \"да\"."}], "target_index": 1},
             "candidates": [candidate("dg-04-d1", "replacement", [{"author": "a", "text": "Замёрзла."}, {"author": "b", "text": "Вентилятор \"работал\"."}],
                                      at_build={"accepted_via": "facilitator", "design_intent": "blame vs fact"})],
             "vetoed": []},
        ]}
        self.candidates_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.candidates_sha = hashlib.sha256(self.candidates_path.read_bytes()).hexdigest()

    def write_spec(self, **overrides):
        spec = {
            "schema_version": SPEC_SCHEMA, "package_id": "annotation-pilot-v0.1", "build_date": "2026-09-08",
            "contract": "docs/contract.md", "source_package_dir": "../v0", "candidates_file": "../candidates.json",
            "candidates_sha256": self.candidates_sha, "replacements": {"pc-02": "pc-21"},
            "carried_over_origin": "unrecorded", "revision_reason": "naturalness", "ontology": "../ontology.json",
            "instructions": "docs/i.md",
            "presentation": {"annotator-1": {"seed": "s1"}, "annotator-2": {"seed": "s2"}},
        }
        spec.update(overrides)
        self.spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")

    def items(self):
        return [json.loads(l) for l in (self.pkg / "items.jsonl").read_text(encoding="utf-8").splitlines()]


class BuildTests(unittest.TestCase):
    def test_build_materializes_three_kinds_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            self.assertEqual(build_package(fx.spec_path), [])
            items = {i["item_id"]: i for i in fx.items()}
            self.assertEqual(set(items), {"pc-01", "pc-21", "pc-03"})  # pc-02 retired, pc-21 fresh
            carried = items["pc-01"]["authoring"]
            self.assertEqual((carried["origin"], carried["accepted_via"], carried["revision_reason"]), ("unrecorded", "carried_over", None))
            self.assertEqual(carried["parent_item_version"]["content_sha256"], item_content_sha256(fx.source[0]))
            rev = items["pc-03"]
            self.assertEqual([m["text"] for m in rev["messages"]], ["Пять.", "шесть, ну"])
            self.assertEqual(rev["target_message_id"], "pc-03-m1")
            self.assertEqual(rev["authoring"]["accepted_via"], "facilitator")
            self.assertEqual(rev["authoring"]["revision_reason"], "naturalness")
            self.assertEqual(rev["authoring"]["caveat"], "V7 soft")
            self.assertNotIn("extra", rev["authoring"]["provenance"])
            rep = items["pc-21"]
            self.assertEqual([m["message_id"] for m in rep["messages"]], ["pc-21-m1", "pc-21-m2"])
            self.assertEqual(rep["target_message_id"], "pc-21-m2")
            self.assertIsNone(rep["authoring"]["parent_item_version"])
            self.assertEqual(rep["authoring"]["accepted_via"], "facilitator")
            self.assertEqual(rep["authoring"]["design_intent"], "demand")
            self.assertNotIn("replaces", rep["authoring"])  # retirement — package-level, не поле item'а
            manifest = json.loads((fx.pkg / "pilot-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["replaces"]["pc-02"]["new_item_id"], "pc-21")
            self.assertEqual(manifest["replaces"]["pc-02"]["retired"]["content_sha256"], item_content_sha256(fx.source[1]))
            self.assertEqual(manifest["pilot_id"], "annotation-pilot-v0.1")
            self.assertEqual(manifest["build"]["candidates_sha256"], fx.candidates_sha)
            strata = json.loads((fx.pkg / "strata.json").read_text(encoding="utf-8"))["strata"]
            self.assertEqual(strata, {"pc-01": "natural", "pc-21": "challenge", "pc-03": "challenge"})
            # собранный пакет проходит validate_items с lineage в соседний v0 (новый инвариант: parent=null + facilitator)
            self.assertEqual(validate(fx.pkg, fx.ontology), [])
            self.assertEqual(verify_package(fx.pkg), [])

    def test_tampered_text_fails_exact_equality_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            self.assertEqual(build_package(fx.spec_path), [])
            rows = fx.items()
            rows[2]["messages"][1]["text"] = "шесть, ну."  # одна запятая/точка «по дороге»
            (fx.pkg / "items.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            self.assertTrue(any("exact equality gate" in i for i in verify_package(fx.pkg)))
            rows[1]["item_id"] = "pc-02"  # retired id возвращён
            (fx.pkg / "items.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            joined = "\n".join(verify_package(fx.pkg))
            self.assertIn("pc-02", joined)

    def test_candidates_pin_and_overwrite_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_spec(candidates_sha256="0" * 64)
            self.assertTrue(any("sha256" in i for i in build_package(fx.spec_path)))
            fx.write_spec()
            self.assertEqual(build_package(fx.spec_path), [])
            self.assertTrue(any("REFUSED" in i for i in build_package(fx.spec_path)))
            fx.write_candidates(revision_text="шесть же")  # acceptance изменился после сборки
            self.assertTrue(any("sha256" in i for i in verify_package(fx.pkg)))

    def test_missing_replacement_id_and_id_reuse_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_spec(replacements={})
            self.assertTrue(any("без нового id" in i for i in build_package(fx.spec_path)))
            fx.write_spec(replacements={"pc-02": "pc-01"})
            self.assertTrue(any("переиспользует" in i for i in build_package(fx.spec_path)))

    def test_seal_then_any_change_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            self.assertEqual(build_package(fx.spec_path), [])
            self.assertEqual(seal_package(fx.pkg), [])
            self.assertTrue(any("REFUSED" in i for i in build_package(fx.spec_path, force=True)))
            (fx.pkg / "strata.json").write_text((fx.pkg / "strata.json").read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertTrue(any("после seal" in i for i in verify_package(fx.pkg)))


class DogfoodTests(unittest.TestCase):
    def test_parser_reads_items_and_escapes(self):
        header, items = parse_dogfood_yaml(DOGFOOD_YAML)
        self.assertEqual(header["dogfood_id"], "annotation-ux-v6")
        self.assertEqual([i["item_id"] for i in items], ["dg-04", "dg-05"])
        self.assertEqual(items[0]["messages"][1]["text"], 'Ты вчера оставила окно открытым, "да".')
        self.assertEqual(items[0]["target_index"], 1)

    def test_render_changes_only_targeted_lines(self):
        changes = {"dg-04": {"new_item_id": "dg-10", "messages": [{"author": "a", "text": "Замёрзла."}, {"author": "b", "text": 'Вентилятор "работал".'}]}}
        out = render_dogfood_yaml(DOGFOOD_YAML, "annotation-ux-v7", ["lineage:", "  derived_from: annotation-ux-v6"], changes)
        header, items = parse_dogfood_yaml(out)
        self.assertEqual(header["dogfood_id"], "annotation-ux-v7")
        self.assertEqual([i["item_id"] for i in items], ["dg-10", "dg-05"])
        self.assertEqual(items[0]["messages"][1]["text"], 'Вентилятор "работал".')
        self.assertIn("    probe: p", out)          # остальное побайтно
        self.assertIn("methodological_rule:", out)
        self.assertIn("  derived_from: annotation-ux-v6", out)

    def test_dogfood_package_writes_v7_and_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            src = fx.root / "v0" / "form"
            src.mkdir()
            (src / "dogfood-v6-items.yaml").write_text(DOGFOOD_YAML, encoding="utf-8")
            sha = hashlib.sha256(DOGFOOD_YAML.encode("utf-8")).hexdigest()
            _, parsed = parse_dogfood_yaml(DOGFOOD_YAML)
            (fx.root / "snap.json").write_text(json.dumps({"source_sha256": sha, "items": parsed}, ensure_ascii=False), encoding="utf-8")
            fx.write_spec(dogfood={"source_yaml": "../v0/form/dogfood-v6-items.yaml", "source_sha256": sha,
                                   "source_snapshot": "../snap.json", "source_dogfood_id": "annotation-ux-v6",
                                   "target_yaml": "form/dogfood-v7-items.yaml", "target_dogfood_id": "annotation-ux-v7",
                                   "provenance_file": "form/dogfood-v7-provenance.json", "replacements": {"dg-04": "dg-10"}})
            self.assertEqual(dogfood_package(fx.spec_path), [])
            _, items = parse_dogfood_yaml((fx.pkg / "form" / "dogfood-v7-items.yaml").read_text(encoding="utf-8"))
            self.assertEqual([i["item_id"] for i in items], ["dg-10", "dg-05"])
            self.assertEqual(items[0]["messages"][1]["text"], 'Вентилятор "работал".')
            prov = json.loads((fx.pkg / "form" / "dogfood-v7-provenance.json").read_text(encoding="utf-8"))
            recs = {r["old"]["item_id"]: r for r in prov["items"]}
            self.assertEqual(recs["dg-04"]["kind"], "replacement")
            self.assertEqual(recs["dg-04"]["result"]["item_id"], "dg-10")
            self.assertEqual(recs["dg-04"]["old"]["content_sha256"],
                             canonical_content_sha256("ru", parsed[0]["messages"], 1))
            self.assertEqual(recs["dg-05"]["kind"], "carried_over")
            self.assertEqual(recs["dg-05"]["old"]["content_sha256"], recs["dg-05"]["result"]["content_sha256"])
            self.assertTrue(any("REFUSED" in i for i in dogfood_package(fx.spec_path)))
            # stale pin → отказ
            fx.write_spec(dogfood={**json.loads(fx.spec_path.read_text(encoding="utf-8"))["dogfood"], "source_sha256": "0" * 64})
            self.assertTrue(any("sha256" in i for i in dogfood_package(fx.spec_path, force=True)))


if __name__ == "__main__":
    unittest.main()
