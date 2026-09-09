"""Issuance records (J): what exactly one pseudonymous annotator is issued.

    uv run python -m metrics.issuance new --root ../.. --package annotation-pilot-v0.1 \
        --annotator annotator-1 --eligibility /secure/eligibility/annotator-1.json \
        --instructions docs/pilot-v0.1-instructions.md \
        --base-url https://relationship-fix.example \
        --out /secure/issuance/annotator-1.json
    uv run python -m metrics.issuance verify --root ../.. --record /secure/issuance/annotator-1.json \
        [--eligibility /secure/eligibility/annotator-1.json]

Two kinds of state, kept apart on purpose:

- the sealed package (data/pilot/v0.1) is immutable history. Its eligibility.json
  is the template that was sealed with it (all null) and is never edited: editing
  it would break the seal, and a seal that has to be broken to issue is no seal;
- a person's actual eligibility is an external record, `rf.annotator-eligibility.v1`,
  kept outside the package (a private path or /var/lib/relationship-fix/eligibility
  on the host), established by the facilitator before issuance.

`new` proves the sealed package (registry status issuable, CHECKSUMS.sha256 equals
the registry pin, every sealed file unchanged, the annotator's presentation file
sealed, the manifest sealed and pinning the ontology file, the instruction
document present), then proves the external eligibility record separately
(schema, package and annotator match, every criterion the manifest names is
present and exactly true, established_at/established_by present), records that
record's sha256 in the issuance record, generates a token, stores only the
token's sha256, and prints the personal link exactly once. The raw token is not
written anywhere by this tool.

`verify` re-derives every hash in an issuance record; with --eligibility it also
re-checks that the eligibility record is the one issued against.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

RECORD_SCHEMA = "rf.issuance-record.v1"
REGISTRY_SCHEMA = "rf.package-registry.v1"
ELIGIBILITY_SCHEMA = "rf.annotator-eligibility.v1"


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


def prove_eligibility(path: Path, package_id: str, annotator: str, required_criteria: list[str]) -> tuple[dict, list[str]]:
    """The external eligibility record, proven on its own: it is not part of the
    sealed package and must not be, because it is established per person after
    the seal. Returns (record, issues)."""
    if not path.exists():
        return {}, [f"eligibility record {path} not found"]
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {}, [f"eligibility record {path}: not JSON ({exc})"]
    issues: list[str] = []
    if record.get("schema_version") != ELIGIBILITY_SCHEMA:
        issues.append(f"eligibility record: schema_version must be {ELIGIBILITY_SCHEMA}")
    if record.get("package_id") != package_id:
        issues.append(f"eligibility record: package_id {record.get('package_id')!r} is not {package_id}")
    if record.get("annotator_id") != annotator:
        issues.append(f"eligibility record: annotator_id {record.get('annotator_id')!r} is not {annotator}")
    criteria = record.get("criteria")
    if not isinstance(criteria, dict):
        issues.append("eligibility record: criteria must be an object of criterion → true")
    else:
        missing = [c for c in required_criteria if c not in criteria]
        if missing:
            issues.append(f"eligibility record: criteria the manifest requires are not established: {missing}")
        not_true = [c for c, v in criteria.items() if v is not True]
        if not_true:
            issues.append(f"eligibility record: not established (must be exactly true): {not_true} — issuance refused")
    if not str(record.get("established_at") or "").strip():
        issues.append("eligibility record: established_at is required")
    if not str(record.get("established_by") or "").strip():
        issues.append("eligibility record: established_by is required")
    return record, issues


def build_record(root: Path, registry_path: Path, package_id: str, annotator: str, eligibility_path: Path,
                 instructions: str, ui_language: str, issued_by: str, issued_at: str, token: str) -> tuple[dict, list[str]]:
    entry, package_dir, checksums, issues = prove_package(root, registry_path, package_id)
    if issues:
        return {}, issues
    presentation_name = f"presentation/{annotator}.jsonl"
    for required in ("items.jsonl", "pilot-manifest.json", presentation_name):
        if required not in checksums:
            issues.append(f"{package_id}: seal has no entry for {required}")
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
    eligibility, eligibility_issues = prove_eligibility(eligibility_path, package_id, annotator, manifest.get("eligibility_criteria", []))
    issues += eligibility_issues
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
        # The external eligibility record, by hash and by content that matters;
        # not by path, because the path is a private location.
        "eligibility": {
            "schema_version": ELIGIBILITY_SCHEMA,
            "sha256": sha256_file(eligibility_path),
            "criteria": sorted(eligibility["criteria"]),
            "established_at": eligibility["established_at"],
            "established_by": eligibility["established_by"],
            "note": "sealed eligibility.json in the package is the null template sealed with it and is never edited; the operational record lives outside the package",
        },
        "ui_language": ui_language,
        "issued_at": issued_at,
        "issued_by": issued_by,
        "note": "token is never stored: only its sha256; the personal link was printed once by metrics.issuance new and handed to the person out of band",
    }
    return record, []


def verify_record(root: Path, registry_path: Path, record: dict, eligibility_path: Path | None = None) -> list[str]:
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
    elig = record.get("eligibility")
    if not isinstance(elig, dict) or len(elig.get("sha256", "")) != 64:
        issues.append("record: no eligibility provenance (sha256 of the external eligibility record)")
    elif eligibility_path is not None:
        if not eligibility_path.exists():
            issues.append(f"eligibility record {eligibility_path} not found")
        elif sha256_file(eligibility_path) != elig["sha256"]:
            issues.append("eligibility record: bytes differ from the one this issuance was made against")
        else:
            manifest = json.loads((package_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
            _, elig_issues = prove_eligibility(eligibility_path, record["package_id"], record["annotator_id"],
                                               manifest.get("eligibility_criteria", []))
            issues += elig_issues
    return issues


def personal_link(base_url: str | None, token: str) -> str:
    path = f"/t/{token}"
    return (base_url.rstrip("/") + path) if base_url else path


def cmd_new(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.exists():
        print(f"REFUSED: {out} exists — a record is issued once; a new issuance is a new record", file=sys.stderr)
        return 1
    token = secrets.token_urlsafe(32)
    issued_at = args.issued_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record, issues = build_record(Path(args.root), Path(args.registry), args.package, args.annotator,
                                  Path(args.eligibility), args.instructions, args.ui_language, args.issued_by,
                                  issued_at, token)
    if issues:
        print("ISSUANCE REFUSED:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"record: {out} (sha256 {sha256_file(out)[:12]}…) for {args.annotator} — copy it to RF_ISSUANCE_DIR on the host and restart the service")
    # The secret appears exactly once, as the link the person receives.
    print("personal link — shown once, not stored:")
    print(personal_link(args.base_url, token))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    issues = verify_record(Path(args.root), Path(args.registry), record,
                           Path(args.eligibility) if args.eligibility else None)
    if issues:
        print("RECORD INVALID:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print(f"OK: {args.record} proves against the sealed package, the registry"
          + (" and the eligibility record" if args.eligibility else ""))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--root", required=True, help="repository root; registry, instruction and ontology paths are relative to it")
    n.add_argument("--registry", default=None, help="default <root>/data/pilot/package-registry.json")
    n.add_argument("--package", required=True)
    n.add_argument("--annotator", required=True)
    n.add_argument("--eligibility", required=True, help="external rf.annotator-eligibility.v1 record for this person (private path)")
    n.add_argument("--instructions", required=True, help="repo-relative path of the instruction document")
    n.add_argument("--base-url", default=os.environ.get("RF_PUBLIC_BASE_URL"),
                   help="public origin of annotation-web for the printed link (default: $RF_PUBLIC_BASE_URL; without it only the /t/ path is printed)")
    n.add_argument("--ui-language", default="ru")
    n.add_argument("--issued-by", default="facilitator")
    n.add_argument("--issued-at", default=None)
    n.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--root", required=True)
    v.add_argument("--registry", default=None)
    v.add_argument("--record", required=True)
    v.add_argument("--eligibility", default=None, help="re-check the external eligibility record against the issuance")
    args = parser.parse_args()
    if args.registry is None:
        args.registry = str(Path(args.root) / "data/pilot/package-registry.json")
    return cmd_new(args) if args.cmd == "new" else cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
