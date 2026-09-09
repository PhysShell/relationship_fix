"""Blinded human A/B для naturalness-кандидатов (gate §4, шаги 4–6 порядка работ).

Вход (facilitator-only): <ab-dir>/ab-manifest.json + candidates.json — для каждого
flagged item оригинал и кандидаты minimal edit. Выход `build`: per-rater пакеты
packets/rater-N.json (opaque pair ids, случайная сторона оригинала, свой порядок),
packet-map/rater-N.json (facilitator-only обратная карта) и packets/checksums.json.
Оценщик отвечает на два независимых вопроса по каждой паре:

    more_natural:  left | right | no_difference   («какой вариант больше похож на реальную переписку пары?»)
    meaning_shift: same | slight | substantial    («отличаются ли варианты по смыслу или накалу?»)

`check` — admissibility bookkeeping до выдачи (veto-review фасилитатора): кандидат лежит
ровно в одном из списков candidates | vetoed (пункт veto_checklist + причина) | rejected
(negative control, история не переписывается); оригиналы сверяются с корпусом по
manifest.sources. `build` отказывает, если check нашёл проблемы: A/B сравнивает только
admissible candidates, и это должно быть видно из записи.

`score` читает responses/rater-N.jsonl, возвращает ответы в canonical пространство и
пишет ab-result.json/.md с рекомендацией на кандидата:

    reject_meaning_shift   хотя бы один оценщик: substantial
    eligible               иначе, если кандидата предпочли строго больше оценщиков, чем оригинал
    keep_original          иначе

Рекомендация не является решением: accept/reject делает фасилитатор вручную (шаг 6),
и принятая версия получает authoring.accepted_via = blinded_ab.

    uv run python -m metrics.naturalness_ab check --ab-dir ../../data/pilot/naturalness-ab/v0-flagged
    uv run python -m metrics.naturalness_ab build --ab-dir ../../data/pilot/naturalness-ab/v0-flagged
    uv run python -m metrics.naturalness_ab score --ab-dir ../../data/pilot/naturalness-ab/v0-flagged
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

MORE_NATURAL = ("left", "right", "no_difference")
MEANING_SHIFT = ("same", "slight", "substantial")
RESPONSE_SCHEMA = "rf.naturalness-ab-response.v1"


def pair_id(seed: str, item_id: str, candidate_id: str) -> str:
    digest = hashlib.sha256(f"{seed}:{item_id}:{candidate_id}".encode("utf-8")).hexdigest()
    return f"pair-{digest[:6]}"


def _display(messages: list[dict]) -> list[dict]:
    return [{"author": m["author"].upper(), "text": m["text"]} for m in messages]


def load_sources(ab_dir: Path, manifest: dict) -> tuple[dict[str, dict[str, dict]], list[str]]:
    """package_id → {item_id → {'messages': [(author, text)], 'target_index'}} из manifest.sources.
    sha256, если он записан, обязан совпадать: оригинал сверяется с тем корпусом, который пинили."""
    corpus: dict[str, dict[str, dict]] = {}
    issues: list[str] = []
    for source in manifest.get("sources", []):
        pid = source["package_id"]
        package = {}
        if "snapshot_file" in source:
            # hash-pinned projection of a YAML source (dogfood): stdlib-only tooling cannot read YAML
            snap_path = ab_dir / source["snapshot_file"]
            src_path = ab_dir / source["source_file"]
            if not snap_path.exists() or not src_path.exists():
                issues.append(f"sources/{pid}: snapshot or source file not found")
                continue
            snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
            actual = hashlib.sha256(src_path.read_bytes()).hexdigest()
            if actual != source.get("source_sha256") or actual != snapshot.get("source_sha256"):
                issues.append(f"sources/{pid}: {src_path.name} changed since the snapshot was pinned — regenerate the snapshot")
                continue
            for item in snapshot["items"]:
                package[item["item_id"]] = {"messages": [(m["author"], m["text"]) for m in item["messages"]],
                                            "target_index": item["target_index"]}
            corpus[pid] = package
            continue
        path = ab_dir / source["items_file"]
        if not path.exists():
            issues.append(f"sources/{pid}: {path} not found")
            continue
        if source.get("sha256"):
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != source["sha256"]:
                issues.append(f"sources/{pid}: sha256 mismatch — источник менялся после пина")
                continue
        for item in load_jsonl(path):
            ids = [m["message_id"] for m in item["messages"]]
            package[item["item_id"]] = {
                "messages": [(m["author"], m["text"]) for m in item["messages"]],
                "target_index": ids.index(item["target_message_id"]),
            }
        corpus[pid] = package
    return corpus, issues


def check_candidates(candidates: dict, corpus: dict[str, dict[str, dict]] | None = None) -> tuple[list[str], list[str]]:
    """Admissibility bookkeeping. Возвращает (issues, notes): issues блокируют build."""
    issues: list[str] = []
    notes: list[str] = []
    checklist = candidates.get("veto_checklist") or []
    checklist_ids = [c.get("id") for c in checklist]
    if not checklist or len(set(checklist_ids)) != len(checklist_ids) or not all(c.get("check") for c in checklist):
        issues.append("veto_checklist: обязателен непустой список {id, check} с уникальными id")
    seen_ids: Counter = Counter()

    for item in candidates.get("items", []):
        iid = item.get("item_id", "?")
        original = item.get("original", {})
        orig_msgs = [(m.get("author"), m.get("text")) for m in original.get("messages", [])]
        if not orig_msgs or not (0 <= original.get("target_index", -1) < len(orig_msgs)):
            issues.append(f"{iid}: original needs messages and a valid target_index")
        if corpus is not None:
            package = corpus.get(item.get("source_package"))
            if package is None:
                notes.append(f"{iid}: original not verified — source '{item.get('source_package')}' не резолвится в JSONL-пакет")
            elif iid not in package:
                issues.append(f"{iid}: not found in source package '{item.get('source_package')}'")
            elif package[iid]["messages"] != orig_msgs or package[iid]["target_index"] != original.get("target_index"):
                issues.append(f"{iid}: original differs from the corpus text — исходник должен быть дословным")

        admissible = item.get("candidates", [])
        vetoed = item.get("vetoed", [])
        if "vetoed" not in item:
            issues.append(f"{iid}: 'vetoed' list is required (пустой, если вето не было)")
        if not admissible:
            notes.append(f"{iid}: no admissible candidates — item остаётся оригиналом")

        for cand in admissible:
            cid = cand.get("candidate_id", "?")
            seen_ids[cid] += 1
            msgs = [(m.get("author"), m.get("text")) for m in cand.get("messages", [])]
            if not cand.get("checker"):
                issues.append(f"{iid}/{cid}: candidate without checker note")
            if not msgs or any(not t or not str(t).strip() for _, t in msgs):
                issues.append(f"{iid}/{cid}: empty message text")
            if msgs == orig_msgs:
                issues.append(f"{iid}/{cid}: candidate identical to the original")
            if [a for a, _ in msgs] != [a for a, _ in orig_msgs]:
                issues.append(f"{iid}/{cid}: message count/authors differ from the original — это новый item, не edit (V7)")
        for veto in vetoed:
            cid = veto.get("candidate_id", "?")
            seen_ids[cid] += 1
            if not veto.get("messages"):
                issues.append(f"{iid}/{cid}: vetoed entry must keep the candidate text")
            if not (veto.get("reason") or "").strip():
                issues.append(f"{iid}/{cid}: vetoed without reason")
            if not veto.get("vetoed_by"):
                issues.append(f"{iid}/{cid}: vetoed_by is required")
            refs = veto.get("checklist") or []
            if not refs or any(r not in checklist_ids for r in refs):
                issues.append(f"{iid}/{cid}: vetoed must reference existing veto_checklist ids, got {refs}")
        for rej in item.get("rejected", []):
            if not rej.get("messages") or not (rej.get("why") or "").strip():
                issues.append(f"{iid}: rejected entry needs messages and why")
    for cid, count in seen_ids.items():
        if count > 1:
            issues.append(f"candidate id '{cid}' appears {count} times across candidates/vetoed — ровно один список")
    return issues, notes


def build_packet(candidates: dict, rater_id: str, seed: str) -> tuple[dict, dict]:
    """Возвращает (packet, map). Сторона оригинала и порядок пар — детерминированны от seed."""
    rng = random.Random(seed)
    pairs = []
    mapping: dict[str, dict] = {}
    for item in candidates["items"]:
        for candidate in item["candidates"]:
            pid = pair_id(seed, item["item_id"], candidate["candidate_id"])
            if pid in mapping:
                raise ValueError(f"pair id collision for seed '{seed}': {pid}")
            original_left = rng.random() < 0.5
            left, right = ((item["original"]["messages"], candidate["messages"]) if original_left
                           else (candidate["messages"], item["original"]["messages"]))
            pairs.append({
                "pair_id": pid,
                "language": item["language"],
                "left": _display(left),
                "right": _display(right),
            })
            mapping[pid] = {
                "item_id": item["item_id"],
                "candidate_id": candidate["candidate_id"],
                "original_side": "left" if original_left else "right",
            }
    rng.shuffle(pairs)
    packet = {"schema_version": "rf.naturalness-ab-packet.v1", "rater_id": rater_id, "pairs": pairs}
    return packet, {"schema_version": "rf.naturalness-ab-packet-map.v1", "rater_id": rater_id, "map": mapping}


FORBIDDEN_PACKET_KEYS = frozenset({
    "item_id", "candidate_id", "original", "original_side", "candidates", "candidate", "rejected",
    "flags", "severity", "stratum", "checker", "edit_constraint", "scope", "origin", "source_package", "why",
})


def _keys(node, found: set) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            _keys(value, found)
    elif isinstance(node, list):
        for value in node:
            _keys(value, found)


def assert_no_leak(packet: dict, candidates: dict) -> None:
    """В пакете нет facilitator-полей (какая сторона оригинал, флаги, constraints) и нет
    item/candidate ids. Проверяются ключи структуры и ids, а не слова внутри реплик:
    текст сообщения имеет право содержать любое слово."""
    keys: set = set()
    _keys(packet, keys)
    leaked_keys = sorted(keys & FORBIDDEN_PACKET_KEYS)
    if leaked_keys:
        raise ValueError(f"facilitator keys {leaked_keys} leaked into packet for {packet['rater_id']}")
    serialized = json.dumps(packet, ensure_ascii=False)
    ids = [i["item_id"] for i in candidates["items"]]
    ids += [c["candidate_id"] for i in candidates["items"] for c in i["candidates"]]
    for token in ids:
        if token in serialized:
            raise ValueError(f"id '{token}' leaked into packet for {packet['rater_id']}")


def validate_responses(responses: list[dict], mapping: dict, rater_id: str) -> list[str]:
    issues = []
    seen: Counter = Counter(r.get("pair_id") for r in responses)
    for pid, count in seen.items():
        if count > 1:
            issues.append(f"{rater_id}: pair '{pid}' answered {count} times")
        if pid not in mapping:
            issues.append(f"{rater_id}: unknown pair '{pid}'")
    for missing in sorted(set(mapping) - set(seen)):
        issues.append(f"{rater_id}: pair '{missing}' not answered")
    for r in responses:
        if r.get("schema_version") != RESPONSE_SCHEMA:
            issues.append(f"{rater_id}/{r.get('pair_id')}: bad schema_version")
        if r.get("rater_id") != rater_id:
            issues.append(f"{rater_id}/{r.get('pair_id')}: rater_id mismatch")
        if r.get("more_natural") not in MORE_NATURAL:
            issues.append(f"{rater_id}/{r.get('pair_id')}: more_natural must be one of {MORE_NATURAL}")
        if r.get("meaning_shift") not in MEANING_SHIFT:
            issues.append(f"{rater_id}/{r.get('pair_id')}: meaning_shift must be one of {MEANING_SHIFT}")
    return issues


def recommend(tally: dict) -> str:
    if tally["meaning_shift"]["substantial"] > 0:
        return "reject_meaning_shift"
    if tally["prefers_candidate"] > tally["prefers_original"]:
        return "eligible"
    return "keep_original"


def score(candidates: dict, layers: dict[str, list[dict]], maps: dict[str, dict]) -> dict:
    """layers: rater_id → responses (в opaque pair ids); maps: rater_id → packet map."""
    tallies: dict[str, dict] = {}
    for item in candidates["items"]:
        for candidate in item["candidates"]:
            tallies[candidate["candidate_id"]] = {
                "item_id": item["item_id"],
                "candidate_id": candidate["candidate_id"],
                "n_raters": 0,
                "prefers_candidate": 0,
                "prefers_original": 0,
                "no_difference": 0,
                "meaning_shift": {"same": 0, "slight": 0, "substantial": 0},
                "notes": [],
            }
    for rater_id, responses in layers.items():
        mapping = maps[rater_id]
        for r in responses:
            entry = mapping[r["pair_id"]]
            tally = tallies[entry["candidate_id"]]
            tally["n_raters"] += 1
            choice = r["more_natural"]
            if choice == "no_difference":
                tally["no_difference"] += 1
            elif choice == entry["original_side"]:
                tally["prefers_original"] += 1
            else:
                tally["prefers_candidate"] += 1
            tally["meaning_shift"][r["meaning_shift"]] += 1
            if r.get("note"):
                tally["notes"].append({"rater_id": rater_id, "note": r["note"]})
    for tally in tallies.values():
        tally["recommendation"] = recommend(tally)

    per_item = []
    for item in candidates["items"]:
        own = [tallies[c["candidate_id"]] for c in item["candidates"]]
        eligible = [t for t in own if t["recommendation"] == "eligible"]
        best = max(eligible, key=lambda t: (t["prefers_candidate"] - t["prefers_original"], t["prefers_candidate"]),
                   default=None)
        per_item.append({
            "item_id": item["item_id"],
            "candidates": [t["candidate_id"] for t in own],
            "vetoed_before_issuance": [{"candidate_id": v["candidate_id"], "checklist": v.get("checklist"), "reason": v.get("reason")}
                                       for v in item.get("vetoed", [])],
            "best_eligible": best["candidate_id"] if best else None,
            "suggested_outcome": "accept_best_eligible" if best else "keep_original",
        })
    return {
        "schema_version": "rf.naturalness-ab-result.v1",
        "ab_id": candidates["ab_id"],
        "compared_only_admissible": True,
        "n_vetoed": sum(len(i.get("vetoed", [])) for i in candidates["items"]),
        "n_raters": len(layers),
        "per_candidate": list(tallies.values()),
        "per_item": per_item,
        "rule": "reject_meaning_shift if any 'substantial'; eligible if candidate votes > original votes; "
                "final accept/reject is manual (gate §4 step 6)",
    }


def render_markdown(result: dict) -> str:
    lines = [f"# Naturalness A/B — {result['ab_id']}", "",
             f"Raters: {result['n_raters']}. Rule: {result['rule']}", "",
             "| item | candidate | n | cand | orig | none | same/slight/subst | recommendation |",
             "|---|---|---|---|---|---|---|---|"]
    for t in result["per_candidate"]:
        ms = t["meaning_shift"]
        lines.append(f"| {t['item_id']} | {t['candidate_id']} | {t['n_raters']} | {t['prefers_candidate']} "
                     f"| {t['prefers_original']} | {t['no_difference']} | {ms['same']}/{ms['slight']}/{ms['substantial']} "
                     f"| {t['recommendation']} |")
    lines += ["", "| item | best eligible | suggested outcome | vetoed before issuance |", "|---|---|---|---|"]
    for p in result["per_item"]:
        vetoed = ", ".join(v["candidate_id"] for v in p.get("vetoed_before_issuance", [])) or "—"
        lines.append(f"| {p['item_id']} | {p['best_eligible'] or '—'} | {p['suggested_outcome']} | {vetoed} |")
    lines += ["", f"A/B compared admissible candidates only; {result.get('n_vetoed', 0)} vetoed before issuance (see candidates.json)."]
    return "\n".join(lines) + "\n"


def run_check(ab_dir: Path, manifest: dict, candidates: dict) -> list[str]:
    corpus, issues = load_sources(ab_dir, manifest)
    cand_issues, notes = check_candidates(candidates, corpus)
    issues += cand_issues
    for note in notes:
        print(f"note: {note}")
    n_adm = sum(len(i.get("candidates", [])) for i in candidates["items"])
    n_veto = sum(len(i.get("vetoed", [])) for i in candidates["items"])
    n_rej = sum(len(i.get("rejected", [])) for i in candidates["items"])
    print(f"admissibility: {len(candidates['items'])} items, {n_adm} admissible, {n_veto} vetoed, {n_rej} rejected (negative controls)")
    return issues


def cmd_check(ab_dir: Path) -> int:
    manifest = json.loads((ab_dir / "ab-manifest.json").read_text(encoding="utf-8"))
    candidates = json.loads((ab_dir / manifest["candidates_file"]).read_text(encoding="utf-8"))
    issues = run_check(ab_dir, manifest, candidates)
    if issues:
        print("CANDIDATES NOT ADMISSIBLE FOR ISSUANCE:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("OK: candidates admissible")
    return 0


def cmd_build(ab_dir: Path, force: bool) -> int:
    manifest = json.loads((ab_dir / "ab-manifest.json").read_text(encoding="utf-8"))
    candidates = json.loads((ab_dir / manifest["candidates_file"]).read_text(encoding="utf-8"))
    issues = run_check(ab_dir, manifest, candidates)
    if issues:
        print("REFUSED: candidates failed admissibility check — run `check` and fix candidates.json first:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    packets_dir = ab_dir / manifest["packets_dir"]
    map_dir = ab_dir / manifest["packet_map_dir"]
    packets_dir.mkdir(exist_ok=True)
    map_dir.mkdir(exist_ok=True)
    checksums: dict[str, str] = {}
    for rater_id, cfg in manifest["raters"].items():
        target = packets_dir / f"{rater_id}.json"
        if target.exists() and not force:
            print(f"REFUSED: {target} already exists — после выдачи пакета reshuffle запрещён "
                  "(--force только до выдачи)", file=sys.stderr)
            return 1
        packet, mapping = build_packet(candidates, rater_id, cfg["seed"])
        assert_no_leak(packet, candidates)
        content = json.dumps(packet, ensure_ascii=False, indent=2) + "\n"
        target.write_text(content, encoding="utf-8")
        (map_dir / f"{rater_id}.json").write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        key = f"{manifest['packets_dir']}{rater_id}.json"
        checksums[key] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        print(f"{rater_id}: {len(packet['pairs'])} pairs, sha256 {checksums[key][:12]}…")
    (packets_dir / "checksums.json").write_text(
        json.dumps({"schema_version": "rf.naturalness-ab-checksums.v1", "sha256": checksums},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK: A/B packets generated")
    return 0


def cmd_score(ab_dir: Path) -> int:
    manifest = json.loads((ab_dir / "ab-manifest.json").read_text(encoding="utf-8"))
    candidates = json.loads((ab_dir / manifest["candidates_file"]).read_text(encoding="utf-8"))
    layers: dict[str, list[dict]] = {}
    maps: dict[str, dict] = {}
    issues: list[str] = []
    for rater_id in manifest["raters"]:
        responses_path = ab_dir / manifest["responses_dir"] / f"{rater_id}.jsonl"
        map_path = ab_dir / manifest["packet_map_dir"] / f"{rater_id}.json"
        if not responses_path.exists():
            print(f"skip: {rater_id} has no responses yet", file=sys.stderr)
            continue
        mapping = json.loads(map_path.read_text(encoding="utf-8"))["map"]
        responses = load_jsonl(responses_path)
        issues += validate_responses(responses, mapping, rater_id)
        layers[rater_id] = responses
        maps[rater_id] = mapping
    if not layers:
        print("NO RESPONSES: nothing to score", file=sys.stderr)
        return 2
    if issues:
        print("RESPONSE VALIDATION FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    result = score(candidates, layers, maps)
    (ab_dir / "ab-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ab_dir / "ab-result.md").write_text(render_markdown(result), encoding="utf-8")
    print(f"OK: scored {len(layers)} raters → {ab_dir / 'ab-result.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="admissibility bookkeeping кандидатов (veto-review) без генерации")
    check.add_argument("--ab-dir", type=Path, required=True)
    build = sub.add_parser("build", help="сгенерировать blinded per-rater пакеты")
    build.add_argument("--ab-dir", type=Path, required=True)
    build.add_argument("--force", action="store_true", help="перезаписать пакеты (ТОЛЬКО до выдачи)")
    sc = sub.add_parser("score", help="свести ответы оценщиков")
    sc.add_argument("--ab-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "check":
        return cmd_check(args.ab_dir)
    if args.command == "build":
        return cmd_build(args.ab_dir, args.force)
    return cmd_score(args.ab_dir)


if __name__ == "__main__":
    sys.exit(main())
