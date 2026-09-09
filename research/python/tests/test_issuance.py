"""Tests metrics.issuance: a record is written only against a proven, sealed,
issuable package AND an external eligibility record that is established for
this person; the sealed eligibility.json (null template) is never read as
operational state and never edited; the token is printed once as the personal
link and never stored; verify re-derives every hash, the eligibility one included."""

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from metrics.issuance import build_record, cmd_new, personal_link, prove_eligibility, verify_record

CRITERIA = ["did_not_author_ontology", "fluent_ru", "fluent_en", "has_not_seen_items"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Root:
    """A sealed package whose eligibility.json is the null template, plus an
    external eligibility record for annotator-1 outside the package."""

    def __init__(self, root: Path, criteria=None):
        self.root = root
        pkg = root / "data/pilot/v0.1"
        (pkg / "presentation").mkdir(parents=True)
        (root / "data/ontology").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "private").mkdir()
        ontology = b'{"ontology_version":"behavior-v0.1","labels":[]}'
        (root / "data/ontology/behavior-v0.1.json").write_bytes(ontology)
        (root / "docs/instructions.md").write_bytes("# инструкция\n".encode("utf-8"))
        items = b'{"item_id":"pc-01"}\n'
        pres = b'{"schema_version":"rf.pilot-item.v1","item_id":"item-aaaaaa","language":"ru","messages":[{"message_id":"item-aaaaaa-m1","author":"a","text":"x"}],"target_message_id":"item-aaaaaa-m1"}\n'
        manifest = json.dumps({"pilot_id": "annotation-pilot-v0.1", "ontology_version": "behavior-v0.1",
                               "ontology_sha256": sha(ontology), "active_labels": ["B.X"],
                               "eligibility_criteria": CRITERIA}).encode()
        # sealed as the build left it: every criterion null, and it stays that way
        sealed_eligibility = json.dumps({"annotators": {"annotator-1": {c: None for c in CRITERIA}}}).encode()
        (pkg / "items.jsonl").write_bytes(items)
        (pkg / "presentation/annotator-1.jsonl").write_bytes(pres)
        (pkg / "pilot-manifest.json").write_bytes(manifest)
        (pkg / "eligibility.json").write_bytes(sealed_eligibility)
        checksums = "".join(f"{sha(b)}  {n}\n" for n, b in [("items.jsonl", items), ("pilot-manifest.json", manifest),
                                                             ("eligibility.json", sealed_eligibility), ("presentation/annotator-1.jsonl", pres)])
        (pkg / "CHECKSUMS.sha256").write_text(checksums, encoding="utf-8")
        self.registry = root / "data/pilot/package-registry.json"
        self.registry.write_text(json.dumps({"schema_version": "rf.package-registry.v1", "packages": {
            "annotation-pilot-v0.1": {"dir": "data/pilot/v0.1", "status": "issuable", "checksums_sha256": sha(checksums.encode())},
            "annotation-pilot-v0": {"dir": "data/pilot/v0", "status": "frozen_non_issuable"}}}), encoding="utf-8")
        self.checksums = checksums
        self.sealed_eligibility = sealed_eligibility
        self.eligibility = root / "private/annotator-1.json"
        self.write_eligibility(criteria if criteria is not None else {c: True for c in CRITERIA})

    def write_eligibility(self, criteria, package="annotation-pilot-v0.1", annotator="annotator-1",
                          schema="rf.annotator-eligibility.v1", established_by="facilitator"):
        self.eligibility.write_text(json.dumps({
            "schema_version": schema, "package_id": package, "annotator_id": annotator,
            "criteria": criteria, "established_at": "2026-09-09T10:00:00Z", "established_by": established_by,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def build(self, package="annotation-pilot-v0.1", annotator="annotator-1", eligibility=None):
        return build_record(self.root, self.registry, package, annotator, eligibility or self.eligibility,
                            "docs/instructions.md", "ru", "facilitator", "2026-09-09T10:05:00Z", "tok")


class IssuanceTests(unittest.TestCase):
    def test_record_proves_package_and_external_eligibility_and_hides_the_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            record, issues = r.build()
            self.assertEqual(issues, [])
            self.assertEqual(record["token_sha256"], sha(b"tok"))
            self.assertNotIn('"tok"', json.dumps(record))
            self.assertEqual(record["package"]["checksums_sha256"], sha(r.checksums.encode()))
            self.assertEqual(record["presentation"]["file"], "presentation/annotator-1.jsonl")
            self.assertEqual(record["ontology"]["version"], "behavior-v0.1")
            self.assertEqual(record["eligibility"]["sha256"], sha(r.eligibility.read_bytes()))
            self.assertEqual(record["eligibility"]["criteria"], sorted(CRITERIA))
            self.assertEqual(record["eligibility"]["established_by"], "facilitator")
            self.assertNotIn("private", json.dumps(record["eligibility"]))  # by hash, not by path
            # the sealed template stayed null and sealed
            self.assertEqual((r.root / "data/pilot/v0.1/eligibility.json").read_bytes(), r.sealed_eligibility)
            self.assertEqual(verify_record(r.root, r.registry, record), [])
            self.assertEqual(verify_record(r.root, r.registry, record, r.eligibility), [])

    def test_eligibility_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp), criteria={c: True for c in CRITERIA} | {"has_not_seen_items": False})
            _, issues = r.build()
            self.assertTrue(any("not established" in i and "has_not_seen_items" in i for i in issues))
            r.write_eligibility({c: True for c in CRITERIA} | {"fluent_en": None})
            _, issues = r.build()
            self.assertTrue(any("fluent_en" in i for i in issues))
            r.write_eligibility({c: True for c in CRITERIA if c != "fluent_ru"})
            _, issues = r.build()
            self.assertTrue(any("manifest requires" in i and "fluent_ru" in i for i in issues))
            r.write_eligibility({c: True for c in CRITERIA}, annotator="annotator-2")
            _, issues = r.build()
            self.assertTrue(any("annotator_id" in i for i in issues))
            r.write_eligibility({c: True for c in CRITERIA}, package="annotation-pilot-v0")
            _, issues = r.build()
            self.assertTrue(any("package_id" in i for i in issues))
            r.write_eligibility({c: True for c in CRITERIA}, schema="rf.something-else.v1")
            _, issues = r.build()
            self.assertTrue(any("schema_version" in i for i in issues))
            r.write_eligibility({c: True for c in CRITERIA}, established_by="")
            _, issues = r.build()
            self.assertTrue(any("established_by" in i for i in issues))
            _, issues = r.build(eligibility=r.root / "private/nobody.json")
            self.assertTrue(any("not found" in i for i in issues))

    def test_sealed_eligibility_template_is_not_operational_state(self):
        """With the template sealed at null, issuance must still work from the
        external record (the old behaviour refused here), and an edit to the
        sealed file must be refused as a broken seal, not accepted as eligibility."""
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            self.assertIn(b"null", r.sealed_eligibility)
            record, issues = r.build()
            self.assertEqual(issues, [])
            self.assertEqual(record["annotator_id"], "annotator-1")
            (r.root / "data/pilot/v0.1/eligibility.json").write_text(
                json.dumps({"annotators": {"annotator-1": {c: True for c in CRITERIA}}}), encoding="utf-8")
            _, issues = r.build()
            self.assertTrue(any("sealed file changed: eligibility.json" in i for i in issues))

    def test_package_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            _, issues = r.build(package="annotation-pilot-v0")
            self.assertTrue(any("not issuable" in i for i in issues))
            _, issues = r.build(package="annotation-pilot-ghost")
            self.assertTrue(any("unknown" in i for i in issues))
            _, issues = r.build(annotator="annotator-9")
            self.assertTrue(any("seal has no entry for presentation/annotator-9.jsonl" in i for i in issues))
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

    def test_verify_detects_changed_instruction_and_changed_eligibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            record, _ = r.build()
            r.write_eligibility({c: True for c in CRITERIA}, established_by="someone else")
            self.assertTrue(any("bytes differ" in i for i in verify_record(r.root, r.registry, record, r.eligibility)))
            self.assertEqual(verify_record(r.root, r.registry, record), [])  # without the file: hashes of the package still prove
            (r.root / "docs/instructions.md").write_bytes(b"different\n")
            self.assertTrue(any("instruction document" in i for i in verify_record(r.root, r.registry, record)))

    def test_cmd_new_prints_the_link_exactly_once_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Root(Path(tmp))
            out = r.root / "private/issuance/annotator-1.json"

            class Args:
                root = str(r.root); registry = str(r.registry); package = "annotation-pilot-v0.1"; annotator = "annotator-1"
                eligibility = str(r.eligibility); instructions = "docs/instructions.md"; ui_language = "ru"
                issued_by = "facilitator"; issued_at = None; base_url = "https://relationship-fix.example/"
            Args.out = str(out)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(cmd_new(Args), 0)
            printed = buf.getvalue()
            lines = printed.splitlines()
            link = lines[lines.index("personal link — shown once, not stored:") + 1]
            self.assertTrue(link.startswith("https://relationship-fix.example/t/"))
            token = link.rsplit("/t/", 1)[1]
            self.assertEqual(printed.count(token), 1)  # one line, one appearance of the secret
            record = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(record["token_sha256"], sha(token.encode()))
            self.assertNotIn(token, out.read_text(encoding="utf-8"))
            self.assertEqual(cmd_new(Args), 1)

    def test_personal_link_without_base_url_is_the_path(self):
        self.assertEqual(personal_link(None, "abc"), "/t/abc")
        self.assertEqual(personal_link("https://h/", "abc"), "https://h/t/abc")

    def test_prove_eligibility_is_strict_about_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "e.json"
            p.write_text(json.dumps({"schema_version": "rf.annotator-eligibility.v1", "package_id": "p", "annotator_id": "a",
                                     "criteria": {"x": 1}, "established_at": "t", "established_by": "f"}), encoding="utf-8")
            _, issues = prove_eligibility(p, "p", "a", ["x"])
            self.assertTrue(any("exactly true" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
