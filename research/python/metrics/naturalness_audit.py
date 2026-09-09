"""Слепой аудит naturalness/adjacency всех stimulus-items (gate §11, шаг «independent blind audit»).

Pass A (стерильный): аудитор получает packets/auditor-N.json — только реплики A/B под opaque
ids в своём порядке; ни strata, ни labels, ни target-маркера, ни флагов critic-1. Три вопроса
на item:

    natural:            yes | partly | no
    invisible_context:  yes | no | not_applicable   (not_applicable ⇔ в item одно сообщение)
    other_problem:      свободный текст, "" если нет

Pass B (диагностический) открывается только после заморозки ответов Pass A: `report`
записывает sha256 файлов ответов в audit-result.json, возвращает ответы в canonical
пространство и строит сравнение с critic-1-triage (facilitator-only) по stratum —
counts, не статистика. Это проверка вывода «дефект рождается из boundary construction
pressure», который пока стоит на одном проходе одного критика.

    uv run python -m metrics.naturalness_audit build  --ab-dir ../../data/pilot/naturalness-audit/v0-all
    uv run python -m metrics.naturalness_audit report --ab-dir ../../data/pilot/naturalness-audit/v0-all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

from metrics.agreement import load_jsonl

NATURAL = ("yes", "partly", "no")
INVISIBLE_CONTEXT = ("yes", "no", "not_applicable")
RESPONSE_SCHEMA = "rf.naturalness-audit-response.v1"
ALLOWED_PACKET_KEYS = frozenset({"schema_version", "auditor_id", "items", "audit_item_id", "language", "messages", "author", "text"})
ADJACENCY_FLAGS = frozenset({"NON_ADJACENT_REPLY", "EXPOSITION_FOR_READER"})


def load_stimuli(audit_dir: Path, manifest: dict) -> tuple[list[dict], list[str]]:
    """Все items из manifest.sources: JSONL-пакеты и hash-pinned snapshot'ы YAML-источников.
    Любой дрейф источника относительно пина — отказ, не предупреждение."""
    stimuli: list[dict] = []
    issues: list[str] = []
    for source in manifest["sources"]:
        pid = source["package_id"]
        if "items_file" in source:
            path = audit_dir / source["items_file"]
            if not path.exists():
                issues.append(f"sources/{pid}: {path} not found")
                continue
            if source.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                issues.append(f"sources/{pid}: sha256 mismatch — источник менялся после пина")
                continue
            for item in load_jsonl(path):
                stimuli.append({"package_id": pid, "item_id": item["item_id"], "language": item["language"],
                                "messages": [{"author": m["author"], "text": m["text"]} for m in item["messages"]]})
        elif "snapshot_file" in source:
            snap_path = audit_dir / source["snapshot_file"]
            src_path = audit_dir / source["source_file"]
            if not snap_path.exists() or not src_path.exists():
                issues.append(f"sources/{pid}: snapshot or source file not found")
                continue
            snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
            actual = hashlib.sha256(src_path.read_bytes()).hexdigest()
            if actual != source["source_sha256"] or actual != snapshot.get("source_sha256"):
                issues.append(f"sources/{pid}: {src_path.name} changed since the snapshot was pinned — regenerate the snapshot")
                continue
            for item in snapshot["items"]:
                stimuli.append({"package_id": pid, "item_id": item["item_id"], "language": item["language"],
                                "messages": [{"author": m["author"], "text": m["text"]} for m in item["messages"]]})
        else:
            issues.append(f"sources/{pid}: needs items_file or snapshot_file")
    return stimuli, issues


def opaque_audit_id(seed: str, package_id: str, item_id: str) -> str:
    digest = hashlib.sha256(f"{seed}:{package_id}/{item_id}".encode("utf-8")).hexdigest()
    return f"audit-{digest[:6]}"


def build_packet(stimuli: list[dict], auditor_id: str, seed: str) -> tuple[dict, dict]:
    mapping: dict[str, dict] = {}
    entries = []
    for s in stimuli:
        oid = opaque_audit_id(seed, s["package_id"], s["item_id"])
        if oid in mapping:
            raise ValueError(f"opaque id collision for seed '{seed}': {oid}")
        mapping[oid] = {"package_id": s["package_id"], "item_id": s["item_id"], "n_messages": len(s["messages"])}
        entries.append({"audit_item_id": oid, "language": s["language"],
                        "messages": [{"author": m["author"].upper(), "text": m["text"]} for m in s["messages"]]})
    random.Random(seed).shuffle(entries)
    packet = {"schema_version": "rf.naturalness-audit-packet.v1", "auditor_id": auditor_id, "items": entries}
    return packet, {"schema_version": "rf.naturalness-audit-packet-map.v1", "auditor_id": auditor_id, "map": mapping}


def _keys(node, found: set) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            found.add(k)
            _keys(v, found)
    elif isinstance(node, list):
        for v in node:
            _keys(v, found)


def assert_sterile(packet: dict, stimuli: list[dict]) -> None:
    """Pass A видит только реплики: никаких лишних ключей и никаких canonical ids."""
    keys: set = set()
    _keys(packet, keys)
    extra = sorted(keys - ALLOWED_PACKET_KEYS)
    if extra:
        raise ValueError(f"non-sterile keys {extra} in packet for {packet['auditor_id']}")
    serialized = json.dumps(packet, ensure_ascii=False)
    for s in stimuli:
        if s["item_id"] in serialized:
            raise ValueError(f"canonical id '{s['item_id']}' leaked into packet for {packet['auditor_id']}")


def validate_responses(responses: list[dict], mapping: dict, auditor_id: str) -> list[str]:
    issues = []
    seen: Counter = Counter(r.get("audit_item_id") for r in responses)
    for oid, count in seen.items():
        if count > 1:
            issues.append(f"{auditor_id}: item '{oid}' answered {count} times")
        if oid not in mapping:
            issues.append(f"{auditor_id}: unknown item '{oid}'")
    for missing in sorted(set(mapping) - set(seen)):
        issues.append(f"{auditor_id}: item '{missing}' not answered")
    for r in responses:
        oid = r.get("audit_item_id")
        if r.get("schema_version") != RESPONSE_SCHEMA:
            issues.append(f"{auditor_id}/{oid}: bad schema_version")
        if r.get("auditor_id") != auditor_id:
            issues.append(f"{auditor_id}/{oid}: auditor_id mismatch")
        if r.get("natural") not in NATURAL:
            issues.append(f"{auditor_id}/{oid}: natural must be one of {NATURAL}")
        ic = r.get("invisible_context")
        if ic not in INVISIBLE_CONTEXT:
            issues.append(f"{auditor_id}/{oid}: invisible_context must be one of {INVISIBLE_CONTEXT}")
        elif oid in mapping:
            single = mapping[oid]["n_messages"] == 1
            if single and ic != "not_applicable":
                issues.append(f"{auditor_id}/{oid}: single-message item ⇒ invisible_context must be not_applicable")
            if not single and ic == "not_applicable":
                issues.append(f"{auditor_id}/{oid}: multi-message item ⇒ invisible_context must be yes|no")
        if not isinstance(r.get("other_problem", ""), str):
            issues.append(f"{auditor_id}/{oid}: other_problem must be a string ('' if none)")
    return issues


def severity_rank(triage: dict) -> dict[str, int]:
    return {name: i for i, name in enumerate(triage["severity_order"])}


def report(layers: dict[str, list[dict]], maps: dict[str, dict], triage: dict, strata: dict[str, str]) -> dict:
    """Pass B: аудиторы × critic-1, по stratum. Только counts: ячейки размером с ладонь."""
    rank = severity_rank(triage)
    threshold = rank[triage["flagged_threshold"]]
    critic = {t["item_id"]: t for t in triage["items"]}

    per_item: dict[str, dict] = {}
    for auditor_id, responses in layers.items():
        mapping = maps[auditor_id]
        for r in responses:
            entry = mapping[r["audit_item_id"]]
            iid = entry["item_id"]
            row = per_item.setdefault(iid, {
                "item_id": iid, "package_id": entry["package_id"],
                "stratum": "dogfood" if entry["package_id"] != "annotation-pilot-v0" else strata.get(iid, "?"),
                "auditors": {},
                "critic1_severity": critic.get(iid, {}).get("severity", "none"),
                "critic1_flags": critic.get(iid, {}).get("flags", []),
            })
            row["auditors"][auditor_id] = {"natural": r["natural"], "invisible_context": r["invisible_context"],
                                           "other_problem": r.get("other_problem", "")}
    for row in per_item.values():
        answers = row["auditors"].values()
        row["auditor_not_natural_any"] = any(a["natural"] in ("no", "partly") for a in answers)
        row["auditor_not_natural_all"] = all(a["natural"] in ("no", "partly") for a in answers)
        row["auditor_invisible_context_any"] = any(a["invisible_context"] == "yes" for a in answers)
        row["auditor_other_problem_any"] = any(a["other_problem"].strip() for a in answers)
        row["critic1_flagged"] = rank.get(row["critic1_severity"], 0) >= threshold
        bare = {f.split(":", 1)[-1] for f in row["critic1_flags"]}
        row["critic1_adjacency"] = bool(bare & ADJACENCY_FLAGS)

    rows = sorted(per_item.values(), key=lambda r: r["item_id"])

    def two_by_two(a_key, b_key, subset):
        table = {"both": 0, "auditor_only": 0, "critic_only": 0, "neither": 0}
        for r in subset:
            a, b = r[a_key], r[b_key]
            table["both" if a and b else "auditor_only" if a else "critic_only" if b else "neither"] += 1
        return table

    by_stratum = {}
    for stratum in sorted({r["stratum"] for r in rows}):
        subset = [r for r in rows if r["stratum"] == stratum]
        by_stratum[stratum] = {
            "n_items": len(subset),
            "auditor_not_natural_any": sum(r["auditor_not_natural_any"] for r in subset),
            "auditor_invisible_context_any": sum(r["auditor_invisible_context_any"] for r in subset),
            "critic1_flagged": sum(r["critic1_flagged"] for r in subset),
            "natural_x_critic1": two_by_two("auditor_not_natural_any", "critic1_flagged", subset),
        }

    auditor_ids = sorted(layers)
    inter_auditor = None
    if len(auditor_ids) >= 2:
        a, b = auditor_ids[:2]
        pairs = [(r["auditors"][a]["natural"], r["auditors"][b]["natural"]) for r in rows
                 if a in r["auditors"] and b in r["auditors"]]
        inter_auditor = {
            "auditors": [a, b], "n_items": len(pairs),
            "natural_exact_agreement": sum(x == y for x, y in pairs),
            "natural_binary_agreement": sum((x == "yes") == (y == "yes") for x, y in pairs),
        }

    return {
        "schema_version": "rf.naturalness-audit-result.v1",
        "n_auditors": len(layers),
        "n_items": len(rows),
        "interpretation": "diagnostic association on small counts; not a causal claim and not a significance test",
        "natural_x_critic1_all": two_by_two("auditor_not_natural_any", "critic1_flagged", rows),
        "invisible_context_x_critic1_adjacency_all": two_by_two("auditor_invisible_context_any", "critic1_adjacency", rows),
        "by_stratum": by_stratum,
        "inter_auditor": inter_auditor,
        "per_item": rows,
    }


def render_markdown(result: dict) -> str:
    lines = [f"# Naturalness audit — Pass B report", "",
             f"Auditors: {result['n_auditors']}, items: {result['n_items']}. {result['interpretation']}.", "",
             "| stratum | n | auditor not-natural (any) | auditor invisible-context (any) | critic-1 flagged | both | auditor only | critic only | neither |",
             "|---|---|---|---|---|---|---|---|---|"]
    for stratum, s in result["by_stratum"].items():
        t = s["natural_x_critic1"]
        lines.append(f"| {stratum} | {s['n_items']} | {s['auditor_not_natural_any']} | {s['auditor_invisible_context_any']} "
                     f"| {s['critic1_flagged']} | {t['both']} | {t['auditor_only']} | {t['critic_only']} | {t['neither']} |")
    lines += ["", "```json", json.dumps({k: result[k] for k in ("natural_x_critic1_all", "invisible_context_x_critic1_adjacency_all", "inter_auditor")},
                                        ensure_ascii=False, indent=2), "```", "",
              "| item | stratum | critic-1 | " + " | ".join(f"{a} natural/ctx" for a in sorted({a for r in result['per_item'] for a in r['auditors']})) + " |",
              "|---|---|---|" + "---|" * len({a for r in result['per_item'] for a in r['auditors']})]
    auditors = sorted({a for r in result["per_item"] for a in r["auditors"]})
    for r in result["per_item"]:
        cells = " | ".join(f"{r['auditors'][a]['natural']}/{r['auditors'][a]['invisible_context']}" if a in r["auditors"] else "—"
                           for a in auditors)
        lines.append(f"| {r['item_id']} | {r['stratum']} | {r['critic1_severity']} | {cells} |")
    return "\n".join(lines) + "\n"


def cmd_build(audit_dir: Path, force: bool) -> int:
    manifest = json.loads((audit_dir / "audit-manifest.json").read_text(encoding="utf-8"))
    stimuli, issues = load_stimuli(audit_dir, manifest)
    if issues:
        print("REFUSED: sources not usable:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    packets_dir = audit_dir / manifest["packets_dir"]
    map_dir = audit_dir / manifest["packet_map_dir"]
    packets_dir.mkdir(exist_ok=True)
    map_dir.mkdir(exist_ok=True)
    checksums: dict[str, str] = {}
    for auditor_id, cfg in manifest["auditors"].items():
        target = packets_dir / f"{auditor_id}.json"
        if target.exists() and not force:
            print(f"REFUSED: {target} already exists — после выдачи пакета reshuffle запрещён "
                  "(--force только до выдачи)", file=sys.stderr)
            return 1
        packet, mapping = build_packet(stimuli, auditor_id, cfg["seed"])
        assert_sterile(packet, stimuli)
        content = json.dumps(packet, ensure_ascii=False, indent=2) + "\n"
        target.write_text(content, encoding="utf-8")
        (map_dir / f"{auditor_id}.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        key = f"{manifest['packets_dir']}{auditor_id}.json"
        checksums[key] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        print(f"{auditor_id}: {len(packet['items'])} items, sha256 {checksums[key][:12]}…")
    (packets_dir / "checksums.json").write_text(
        json.dumps({"schema_version": "rf.naturalness-audit-checksums.v1", "sha256": checksums}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print("OK: sterile Pass A packets generated")
    return 0


def cmd_report(audit_dir: Path) -> int:
    manifest = json.loads((audit_dir / "audit-manifest.json").read_text(encoding="utf-8"))
    triage = json.loads((audit_dir / manifest["critic_1_triage_file"]).read_text(encoding="utf-8"))
    strata = json.loads((audit_dir / manifest["strata_file"]).read_text(encoding="utf-8"))["strata"]
    layers: dict[str, list[dict]] = {}
    maps: dict[str, dict] = {}
    frozen: dict[str, str] = {}
    issues: list[str] = []
    for auditor_id in manifest["auditors"]:
        responses_path = audit_dir / manifest["responses_dir"] / f"{auditor_id}.jsonl"
        if not responses_path.exists():
            print(f"skip: {auditor_id} has no responses yet", file=sys.stderr)
            continue
        mapping = json.loads((audit_dir / manifest["packet_map_dir"] / f"{auditor_id}.json").read_text(encoding="utf-8"))["map"]
        responses = load_jsonl(responses_path)
        issues += validate_responses(responses, mapping, auditor_id)
        layers[auditor_id] = responses
        maps[auditor_id] = mapping
        frozen[f"{manifest['responses_dir']}{auditor_id}.jsonl"] = hashlib.sha256(responses_path.read_bytes()).hexdigest()
    if not layers:
        print("NO RESPONSES: Pass A not submitted, Pass B does not open", file=sys.stderr)
        return 2
    if issues:
        print("RESPONSE VALIDATION FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    result = report(layers, maps, triage, strata)
    result["pass_a_frozen_sha256"] = frozen
    (audit_dir / "audit-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (audit_dir / "audit-result.md").write_text(render_markdown(result), encoding="utf-8")
    print(f"OK: Pass A frozen ({len(frozen)} layers, sha256 recorded); Pass B report → {audit_dir / 'audit-result.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="сгенерировать стерильные per-auditor пакеты Pass A")
    build.add_argument("--ab-dir", "--audit-dir", dest="audit_dir", type=Path, required=True)
    build.add_argument("--force", action="store_true", help="перезаписать пакеты (ТОЛЬКО до выдачи)")
    rep = sub.add_parser("report", help="заморозить ответы Pass A и построить Pass B report")
    rep.add_argument("--ab-dir", "--audit-dir", dest="audit_dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        return cmd_build(args.audit_dir, args.force)
    return cmd_report(args.audit_dir)


if __name__ == "__main__":
    sys.exit(main())
