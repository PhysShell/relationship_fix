"""Валидация pilot-пакета до выдачи разметчикам (read-only).

Проверяет: структуру items, уникальность id, target внутри messages, покрытие
strata, консистентность manifest с онтологией (sha256, active/deferred labels,
allowed_units против utterance-only sampling frame).

    uv run python -m metrics.validate_items \
        --pilot-dir ../../data/pilot/v0 --ontology ../../data/ontology/behavior-v0.1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from metrics.agreement import load_jsonl


def validate(pilot_dir: Path, ontology_path: Path) -> list[str]:
    issues: list[str] = []
    manifest = json.loads((pilot_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
    items = load_jsonl(pilot_dir / manifest["items_file"])
    strata = json.loads((pilot_dir / manifest["strata_file"]).read_text(encoding="utf-8"))["strata"]
    ontology = json.loads(ontology_path.read_text(encoding="utf-8"))

    # --- items ---
    ids = [i["item_id"] for i in items]
    for item_id, count in Counter(ids).items():
        if count > 1:
            issues.append(f"items: duplicate item_id '{item_id}'")
    for item in items:
        if item.get("schema_version") != "rf.pilot-item.v1":
            issues.append(f"{item.get('item_id')}: bad schema_version")
        if item.get("language") not in ("ru", "en"):
            issues.append(f"{item['item_id']}: language must be ru|en")
        message_ids = [m["message_id"] for m in item.get("messages", [])]
        if len(set(message_ids)) != len(message_ids):
            issues.append(f"{item['item_id']}: duplicate message ids")
        if item.get("target_message_id") not in message_ids:
            issues.append(f"{item['item_id']}: target_message_id not among messages")
        for message in item.get("messages", []):
            if not message.get("text", "").strip():
                issues.append(f"{item['item_id']}/{message.get('message_id')}: empty text")
            if message.get("author") not in ("a", "b"):
                issues.append(f"{item['item_id']}/{message.get('message_id')}: author must be a|b")

    # --- strata ---
    if set(strata) != set(ids):
        missing = set(ids) - set(strata)
        extra = set(strata) - set(ids)
        if missing:
            issues.append(f"strata: items without stratum: {sorted(missing)}")
        if extra:
            issues.append(f"strata: unknown items: {sorted(extra)}")
    for item_id, stratum in strata.items():
        if stratum not in ("challenge", "natural"):
            issues.append(f"strata/{item_id}: unknown stratum '{stratum}'")

    # --- manifest vs ontology ---
    actual_sha = hashlib.sha256(ontology_path.read_bytes()).hexdigest()
    if manifest["ontology_sha256"] != actual_sha:
        issues.append(
            f"manifest: ontology_sha256 mismatch (manifest {manifest['ontology_sha256'][:12]}…, "
            f"file {actual_sha[:12]}…) — обновите manifest вместе с онтологией")
    if manifest["ontology_version"] != ontology["ontology_version"]:
        issues.append("manifest: ontology_version mismatch")

    labels = {l["id"]: l for l in ontology["labels"]}
    for label in manifest["active_labels"]:
        if label not in labels:
            issues.append(f"manifest: active label '{label}' not in ontology")
        elif "utterance" not in labels[label]["allowed_units"]:
            issues.append(f"manifest: active label '{label}' is not utterance-capable")
    for label, info in manifest.get("deferred_labels", {}).items():
        if label not in labels:
            issues.append(f"manifest: deferred label '{label}' not in ontology")
        elif "utterance" in labels[label]["allowed_units"]:
            issues.append(f"manifest: '{label}' is utterance-capable — deferral unjustified")
        if info.get("estimability_status") != "not_applicable":
            issues.append(f"manifest: deferred '{label}' must be not_applicable (не underpowered: 'не искали' != 'не нашли')")
    uncovered = set(labels) - set(manifest["active_labels"]) - set(manifest.get("deferred_labels", {}))
    if uncovered:
        issues.append(f"manifest: labels neither active nor deferred: {sorted(uncovered)}")

    counts = Counter(strata.values())
    print(f"items: {len(items)}; strata: {dict(counts)}; "
          f"languages: {dict(Counter(i['language'] for i in items))}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--ontology", type=Path, required=True)
    args = parser.parse_args()
    issues = validate(args.pilot_dir, args.ontology)
    if issues:
        print("PILOT PACKAGE INVALID:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("OK: pilot package valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
