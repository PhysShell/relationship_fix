"""Tests metrics.issuance: a record is written only against a proven, sealed,
issuable package with eligibility established; the token is printed once and
never stored; verify re-derives every hash."""

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from metrics.issuance import build_record, cmd_new, verify_record


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Root:
    def __init__(self, root: Path, eligible=True):
        self.root = root
        pkg = root / "data/pilot/v0.1"
        (pkg / "presentation").mkdir(parents=True)
        (root / "data/ontology").mkdir(parents=True)
        (root / "docs").mkdir()
        ontology = b'{"ontology_version":"behavior-v0.1","labels":[]}'
        (root / "data/ontology/behavior-v0.1.json").write_bytes(ontology)
        (root / "docs/instructions.md").write_bytes("# инструкция\n".encode("utf-8"))
        items = b'{"item_id":"pc-01"}\n'
        pres = b'{"schema_version":"rf.pilot-item.v1","item_id":"item-aaaaaa","language":"ru","messages":[{"message_id":"item-aaaaaa-m1","author":"a","text":"x"}],"target_message_id":"item-aaaaaa-m1"}\n'
        manifest = json.dumps({"pilot_id": "annotation-pilot-v0.1", "ontology_version": "behavior-v0.1",
                               "ontology_sha256": sha(ontology), "active_labels": ["B.X"]}).encode()
        eligibility = json.dumps({"annotators": {"annotator-1": {"fluent_ru": eligible, "has_not_seen_items": eligible}}}).encode()
        (pkg / "items.jsonl").write_bytes(items)
        (pkg / "presentation/annotator-1.jsonl").write_bytes(pres)
        (pkg / "pilot-manifest.json").write_bytes(manifest)
        (pkg / "eligibility.json").write_bytes(eligibility)
        checksums = "".join(f"{sha(b)}  {n}\n" for n, b in [("items.jsonl", items), ("pilot-manifest.json", manifest),
                                                             ("eligibility.json", eligibility), ("presentation/annotator-1.jsonl", pres)])
        (pkg / "CHECKSUMS.sha256").write_text(checksums, encoding="utf-8")
        self.registry = root / "data/pilot/package-registry.json"
        self.registry.write_text(json.dumps({"schema_version": "rf.package-registry.v1", "packages": {
            "annotation-pilot-v0.1": {"dir": "data/pilot/v0.1", "status": "issuable", "checksums_sha256": sha(checksums.encode())},
            "annotation-pilot-v0": {"dir": "data/pilot/v0", "status": "frozen_non_issuable"}}}), encoding="utf-8")
        self.checksums = checksums

    def build(self, package="annotation-pilot-v0.1", annotator="annotator-1"):
        return build_record(self.root, self.registry, package, annotator, "docs/instructions.md", "ru", "facilitator", "2026-09-08T00:00:00Z", "tok")


class IssuanceTests(unittest.TestCase):
    def test_record_proves_the_package_and_hides_the_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            record, issues = r.build()
            self.assertEqual(issues, [])
            self.assertEqual(record["token_sha256"], sha(b"tok"))
            self.assertNotIn("tok\"", json.dumps(record))
            self.assertEqual(record["package"]["checksums_sha256"], sha(r.checksums.encode()))
            self.assertEqual(record["presentation"]["file"], "presentation/annotator-1.jsonl")
            self.assertEqual(record["ontology"]["version"], "behavior-v0.1")
            self.assertEqual(record["ontology"]["active_labels"], ["B.X"])
            self.assertEqual(verify_record(r.root, r.registry, record), [])

    def test_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            _, issues = r.build(package="annotation-pilot-v0")
            self.assertTrue(any("not issuable" in i for i in issues))
            _, issues = r.build(package="annotation-pilot-ghost")
            self.assertTrue(any("unknown" in i for i in issues))
            _, issues = r.build(annotator="annotator-9")
            self.assertTrue(any("no sealed presentation" in i for i in issues))
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp), eligible=None)
            _, issues = r.build()
            self.assertTrue(any("eligibility not established" in i for i in issues))
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            (r.root / "data/pilot/v0.1/presentation/annotator-1.jsonl").write_bytes(b"changed\n")
            _, issues = r.build()
            self.assertTrue(any("sealed file changed" in i for i in issues))
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            (r.root / "data/pilot/v0.1/CHECKSUMS.sha256").write_text(r.checksums + "\n", encoding="utf-8")
            _, issues = r.build()
            self.assertTrue(any("registry pin" in i for i in issues))

    def test_verify_detects_a_changed_instruction_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            record, _ = r.build()
            (r.root / "docs/instructions.md").write_bytes(b"different\n")
            self.assertTrue(any("instruction document" in i for i in verify_record(r.root, r.registry, record)))

    def test_cmd_new_prints_the_token_once_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            out = r.root / "data/pilot/v0.1/issuance/annotator-1.json"

            class Args:
                root = str(r.root); registry = str(r.registry); package = "annotation-pilot-v0.1"; annotator = "annotator-1"
                instructions = "docs/instructions.md"; ui_language = "ru"; issued_by = "facilitator"; issued_at = None
            Args.out = str(out)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(cmd_new(Args), 0)
            printed = buf.getvalue().splitlines()
            token = printed[printed.index(next(l for l in printed if l.startswith("token for"))) + 1]
            record = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(record["token_sha256"], sha(token.encode()))
            self.assertNotIn(token, out.read_text(encoding="utf-8"))
            self.assertEqual(cmd_new(Args), 1)


if __name__ == "__main__":
    unittest.main()
