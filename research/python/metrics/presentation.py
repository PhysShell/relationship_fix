"""Blind presentation layer для annotation-pilot-v0.

Canonical items.jsonl/strata.json иммутабельны, но их ID (pc-*/pn-*) и блочный
порядок протекают стратой. Разметчику выдаётся presentation-файл: opaque ids
(item-XXXXXX, детерминированно из per-annotator seed) и независимый
перемешанный порядок. Facilitator-only mapping возвращает ответы в canonical
пространство при скоринге.

    uv run python -m metrics.presentation --pilot-dir ../../data/pilot/v0

Повторный запуск отказывается перезаписывать существующие presentation-файлы
(--force только до старта pilot: после выдачи никаких reshuffle).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

from metrics.agreement import load_jsonl


def opaque_id(seed: str, canonical_id: str) -> str:
    digest = hashlib.sha256(f"{seed}:{canonical_id}".encode("utf-8")).hexdigest()
    return f"item-{digest[:6]}"


def build_presentation(items: list[dict], seed: str) -> tuple[list[dict], dict[str, str]]:
    """Возвращает (presentation items в перемешанном порядке, mapping opaque→canonical)."""
    mapping: dict[str, str] = {}
    for item in items:
        oid = opaque_id(seed, item["item_id"])
        if oid in mapping:
            raise ValueError(f"opaque id collision for seed '{seed}': {oid}")
        mapping[oid] = item["item_id"]

    inverse = {v: k for k, v in mapping.items()}
    shuffled = list(items)
    random.Random(seed).shuffle(shuffled)

    presented = []
    for item in shuffled:
        oid = inverse[item["item_id"]]
        messages = []
        msg_map = {}
        for index, message in enumerate(item["messages"], start=1):
            new_id = f"{oid}-m{index}"
            msg_map[message["message_id"]] = new_id
            messages.append({"message_id": new_id, "author": message["author"], "text": message["text"]})
        presented.append({
            "schema_version": "rf.pilot-item.v1",
            "item_id": oid,
            "language": item["language"],
            "messages": messages,
            "target_message_id": msg_map[item["target_message_id"]],
        })
    return presented, mapping


def assert_no_canonical_leak(presented: list[dict], canonical_ids: set[str]) -> None:
    for item in presented:
        ids = [item["item_id"], item["target_message_id"]] + [m["message_id"] for m in item["messages"]]
        for value in ids:
            for canonical in canonical_ids:
                if canonical in value:
                    raise ValueError(f"canonical id '{canonical}' leaked into presentation id '{value}'")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true",
                        help="перезаписать существующие presentation-файлы (ТОЛЬКО до старта pilot)")
    args = parser.parse_args()
    pilot_dir: Path = args.pilot_dir

    manifest = json.loads((pilot_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
    items = load_jsonl(pilot_dir / manifest["items_file"])
    canonical_ids = {i["item_id"] for i in items}
    presentation_cfg = manifest.get("presentation")
    if not presentation_cfg:
        print("manifest has no 'presentation' section (per-annotator seeds)", file=sys.stderr)
        return 1

    out_dir = pilot_dir / "presentation"
    map_dir = pilot_dir / "presentation-map"
    out_dir.mkdir(exist_ok=True)
    map_dir.mkdir(exist_ok=True)

    checksums: dict[str, str] = {}
    orders: dict[str, list[str]] = {}
    for annotator, cfg in presentation_cfg.items():
        target = out_dir / f"{annotator}.jsonl"
        if target.exists() and not args.force:
            print(f"REFUSED: {target} already exists — после выдачи пакета reshuffle запрещён "
                  "(--force только до старта pilot)", file=sys.stderr)
            return 1

        presented, mapping = build_presentation(items, cfg["seed"])
        assert_no_canonical_leak(presented, canonical_ids)
        content = "\n".join(json.dumps(p, ensure_ascii=False) for p in presented) + "\n"
        target.write_text(content, encoding="utf-8")
        (map_dir / f"{annotator}.json").write_text(
            json.dumps({"schema_version": "rf.pilot-presentation-map.v1",
                        "annotator": annotator, "map": mapping},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        checksums[f"presentation/{annotator}.jsonl"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        orders[annotator] = [mapping[p["item_id"]] for p in presented]
        print(f"{annotator}: {len(presented)} items, sha256 {checksums[f'presentation/{annotator}.jsonl'][:12]}…")

    annotators = list(orders)
    if len(annotators) >= 2 and orders[annotators[0]] == orders[annotators[1]]:
        print("WARNING: annotator orders are identical — seeds должны давать разные порядки", file=sys.stderr)
        return 1

    (out_dir / "checksums.json").write_text(
        json.dumps({"schema_version": "rf.pilot-presentation-checksums.v1", "sha256": checksums},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print("OK: presentation layer generated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
