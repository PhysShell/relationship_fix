"""Issuance records (J prep): what exactly one pseudonymous annotator is issued.

    uv run python -m metrics.issuance new --root ../.. --package annotation-pilot-v0.1 \
        --annotator annotator-1 --instructions docs/pilot-v0.1-instructions.md \
        --out ../../data/pilot/v0.1/issuance/annotator-1.json
    uv run python -m metrics.issuance verify --root ../.. --record ../../data/pilot/v0.1/issuance/annotator-1.json

`new` proves the package before writing anything: registry status issuable, seal
(CHECKSUMS.sha256) hashes to the registry pin, the annotator's presentation file
hashes to its sealed entry, the manifest is sealed and pins the ontology file,
the instruction document exists, and eligibility.json says every criterion is
true for this annotator. Then it generates a token, writes the record with the
token's sha256 only, and prints the raw token ONCE to stdout. The token is not
stored anywhere by this tool; the facilitator hands it to the person.

The record is what annotation-web loads (Registry.hs proves the same hashes
again at start) and what the export ties the response layer back to. The
sealed manifest describes the research artifact; the record describes what a
person saw. `verify` re-derives every hash in a record.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import secrets
import sys
from pathlib import Path

RECORD_SCHEMA = "rf.issuance-record.v1"
REGISTRY_SCHEMA = "rf.package-registry.v1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_checksums(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        if len(digest) != 64 or not name:
            raise ValueError(f"unreadable CHECKSUMS line: {line}")
        entries[name.strip()] = digest.lower()
    return entries


def prove_package(root: Path, registry_path: Path, package_id: str) -> tuple[dict, Path, dict[str, str], list[str]]:
    """Returns (registry entry, package dir, checksums, issues). Issues are fail-closed."""
    issues: list[str] = []
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != REGISTRY_SCHEMA:
        return {}, root, {}, [f"registry: schema_version must be {REGISTRY_SCHEMA}"]
    entry = registry.get("packages", {}).get(package_id)
    if entry is None:
        return {}, root, {}, [f"registry: package {package_id} unknown — not served"]
    if entry.get("status") != "issuable":
        return entry, root, {}, [f"registry: package {package_id} has status {entry.get('status')!r} — not issuable"]
    package_dir = root / entry["dir"]
    seal = package_dir / "CHECKSUMS.sha256"
    if not seal.exists():
        return entry, package_dir, {}, [f"{package_id}: not sealed (no CHECKSUMS.sha256)"]
    actual = sha256_file(seal)
    pin = (entry.get("checksums_sha256") or "").lower()
    if not pin:
        issues.append(f"registry: issuable package {package_id} has no checksums_sha256 pin")
    elif actual != pin:
        issues.append(f"{package_id}: CHECKSUMS.sha256 hashes to {actual[:12]}…, registry pin is {pin[:12]}…")
    try:
        checksums = parse_checksums(seal.read_text(encoding="utf-8"))
    except ValueError as exc:
        return entry, package_dir, {}, issues + [str(exc)]
    for name, digest in checksums.items():
        target = package_dir / name
        if not target.exists():
            issues.append(f"{package_id}: sealed file missing: {name}")
        elif sha256_file(target) != digest:
            issues.append(f"{package_id}: sealed file changed: {name}")
    return entry, package_dir, checksums, issues


def build_record(root: Path, registry_path: Path, package_id: str, annotator: str, instructions: str,
                 ui_language: str, issued_by: str, issued_at: str, token: str) -> tuple[dict, list[str]]:
    entry, package_dir, checksums, issues = prove_package(root, registry_path, package_id)
    if issues:
        return {}, issues
    presentation_name = f"presentation/{annotator}.jsonl"
    if presentation_name not in checksums:
        issues.append(f"{package_id}: no sealed presentation file for {annotator}")
    if "items.jsonl" not in checksums:
        issues.append(f"{package_id}: seal has no items.jsonl entry")
    if "pilot-manifest.json" not in checksums:
        issues.append(f"{package_id}: seal has no pilot-manifest.json entry")
    if issues:
        return {}, issues
    manifest = json.loads((package_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("pilot_id") != package_id:
        issues.append(f"{package_id}: manifest pilot_id is {manifest.get('pilot_id')!r}")
    ontology_version = manifest.get("ontology_version", "")
    ontology_file = Path("data/ontology") / f"{ontology_version}.json"
    ontology_path = root / ontology_file
    if not ontology_path.exists():
        issues.append(f"ontology file {ontology_file} not found")
    else:
        actual = sha256_file(ontology_path)
        if actual != manifest.get("ontology_sha256"):
            issues.append(f"ontology {ontology_file} hashes to {actual[:12]}…, manifest pins {str(manifest.get('ontology_sha256'))[:12]}…")
    instructions_path = root / instructions
    if not instructions_path.exists():
        issues.append(f"instruction document {instructions} not found")
    eligibility_path = package_dir / "eligibility.json"
    if not eligibility_path.exists():
        issues.append(f"{package_id}: eligibility.json missing")
    else:
        eligibility = json.loads(eligibility_path.read_text(encoding="utf-8")).get("annotators", {})
        record = eligibility.get(annotator)
        if record is None:
            issues.append(f"{package_id}: eligibility.json has no entry for {annotator}")
        else:
            pending = [c for c, v in record.items() if v is not True]
            if pending:
                issues.append(f"{package_id}/{annotator}: eligibility not established for {pending} — issuance refused")
    if ui_language not in ("ru", "en"):
        issues.append(f"ui_language must be ru|en, got {ui_language!r}")
    if issues:
        return {}, issues
    record = {
        "schema_version": RECORD_SCHEMA,
        "package_id": package_id,
        "annotator_id": annotator,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "package": {"dir": entry["dir"], "items_sha256": checksums["items.jsonl"], "checksums_sha256": sha256_file(package_dir / "CHECKSUMS.sha256")},
        "presentation": {"file": presentation_name, "sha256": checksums[presentation_name]},
        "instructions": {"file": instructions, "sha256": sha256_file(instructions_path)},
        "ontology": {"file": str(ontology_file), "version": ontology_version, "sha256": manifest["ontology_sha256"],
                     "active_labels": manifest.get("active_labels", [])},
        "ui_language": ui_language,
        "issued_at": issued_at,
        "issued_by": issued_by,
        "note": "token is never stored: only its sha256; the raw token was printed once by metrics.issuance new and handed to the person out of band",
    }
    return record, []


def verify_record(root: Path, registry_path: Path, record: dict) -> list[str]:
    issues: list[str] = []
    if record.get("schema_version") != RECORD_SCHEMA:
        return [f"record: schema_version must be {RECORD_SCHEMA}"]
    entry, package_dir, checksums, issues = prove_package(root, registry_path, record["package_id"])
    if issues:
        return issues
    if entry["dir"] != record["package"]["dir"]:
        issues.append("record: package dir differs from registry")
    if record["package"]["checksums_sha256"] != sha256_file(package_dir / "CHECKSUMS.sha256"):
        issues.append("record: checksums_sha256 differs from the seal")
    if checksums.get("items.jsonl") != record["package"]["items_sha256"]:
        issues.append("record: items_sha256 differs from the sealed entry")
    pres = record["presentation"]
    if checksums.get(pres["file"]) != pres["sha256"]:
        issues.append("record: presentation sha256 differs from the sealed entry")
    if sha256_file(package_dir / pres["file"]) != pres["sha256"]:
        issues.append("record: presentation file bytes differ from the record")
    ins = record["instructions"]
    if not (root / ins["file"]).exists() or sha256_file(root / ins["file"]) != ins["sha256"]:
        issues.append("record: instruction document differs from the record (or is missing)")
    ont = record["ontology"]
    if not (root / ont["file"]).exists() or sha256_file(root / ont["file"]) != ont["sha256"]:
        issues.append("record: ontology file differs from the record (or is missing)")
    if len(record.get("token_sha256", "")) != 64:
        issues.append("record: token_sha256 is not a sha256")
    return issues


def cmd_new(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.exists():
        print(f"REFUSED: {out} exists — a record is issued once; a new issuance is a new record", file=sys.stderr)
        return 1
    token = secrets.token_urlsafe(32)
    issued_at = args.issued_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record, issues = build_record(Path(args.root), Path(args.registry), args.package, args.annotator,
                                  args.instructions, args.ui_language, args.issued_by, issued_at, token)
    if issues:
        print("ISSUANCE REFUSED:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"record: {out} (sha256 {sha256_file(out)[:12]}…)")
    print(f"token for {args.annotator} — shown once, not stored:")
    print(token)
    print(f"link path: /t/{token}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    issues = verify_record(Path(args.root), Path(args.registry), record)
    if issues:
        print("RECORD INVALID:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print(f"OK: {args.record} proves against the sealed package and the registry")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--root", required=True, help="repository root; registry and record paths are relative to it")
    n.add_argument("--registry", default=None, help="default <root>/data/pilot/package-registry.json")
    n.add_argument("--package", required=True)
    n.add_argument("--annotator", required=True)
    n.add_argument("--instructions", required=True, help="repo-relative path of the instruction document")
    n.add_argument("--ui-language", default="ru")
    n.add_argument("--issued-by", default="facilitator")
    n.add_argument("--issued-at", default=None)
    n.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--root", required=True)
    v.add_argument("--registry", default=None)
    v.add_argument("--record", required=True)
    args = parser.parse_args()
    if args.registry is None:
        args.registry = str(Path(args.root) / "data/pilot/package-registry.json")
    return cmd_new(args) if args.cmd == "new" else cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
