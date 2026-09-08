"""Materialization пакета из accepted candidates — cutover contract A–I
(docs/pilot-v0.1-cutover-contract.md). Accepted candidate — source of truth для текста;
exact accepted→built equality — gate, а не «человек внимательно проверил».

    uv run python -m metrics.materialize build   --spec ../../data/pilot/v0.1/build-spec.json
    uv run python -m metrics.materialize verify  --pilot-dir ../../data/pilot/v0.1
    uv run python -m metrics.materialize dogfood --spec ../../data/pilot/v0.1/build-spec.json
    uv run python -m metrics.materialize seal    --pilot-dir ../../data/pilot/v0.1

build    — из frozen source package + candidates.json (sha-pinned) собирает items.jsonl (v2),
           strata.json, pilot-manifest.json (с package-level `replaces` и блоком `build`),
           eligibility.json; сразу прогоняет verify. Отказывается перезаписывать существующий
           пакет (--force только до issuance).
verify   — exact equality: carried_over == frozen source (hash), revision/replacement ==
           accepted candidate (авторы, тексты, target по порядку); каждый accepted candidate
           использован ровно один раз; retired ids отсутствуют, новые ids не переиспользуют
           старые; `replaces` в manifest согласован; CHECKSUMS.sha256 (если запечатан) совпадает.
dogfood  — dogfood yaml другой storage contract (не rf.pilot-item.v2): из frozen v6 yaml
           (sha-pinned, парсер сверяется с pinned snapshot) и accepted dg-* candidates рендерит
           v7 yaml и provenance sidecar `old hash → candidate → result hash`; равенство с
           candidates проверяется парсингом результата.
seal     — CHECKSUMS.sha256 по всем файлам пакета (после validate_items и presentation);
           после seal любое изменение = новая версия.

Что materialize НЕ делает: не правит текст «по дороге» (ни запятой), не трогает Catalog.hs
и annotation-web (web cutover — отдельная приёмка), не выдаёт пакет (issuance — J).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from metrics.agreement import load_jsonl
from metrics.items import SCHEMA_V2, canonical_content_sha256, item_content_sha256

SPEC_SCHEMA = "rf.pilot-build-spec.v1"
BUILD_SCHEMA = "rf.pilot-build.v1"
DOGFOOD_PROVENANCE_SCHEMA = "rf.dogfood-provenance.v1"
PROVENANCE_KEYS = ("method", "source_kind", "source_corpus", "source_revision", "source_ref",
                   "source_license", "source_text_copied", "transformation", "source_language", "source_modality")
CHECKSUMS_FILE = "CHECKSUMS.sha256"


# ---------------------------------------------------------------- helpers

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_spec(spec_path: Path) -> tuple[dict, Path]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != SPEC_SCHEMA:
        raise ValueError(f"build spec: schema_version must be {SPEC_SCHEMA}")
    return spec, spec_path.parent


def load_candidates(path: Path, pinned_sha: str) -> dict:
    actual = sha256_file(path)
    if actual != pinned_sha:
        raise ValueError(f"candidates.json sha256 {actual[:12]}… != pinned {pinned_sha[:12]}… — "
                         "spec указывает не на тот файл acceptance, сборка отказана")
    return json.loads(path.read_text(encoding="utf-8"))


def accepted_for_package(candidates: dict, package_id: str) -> dict[str, dict]:
    """item_id → {'candidate', 'kind', 'at_build', 'item'} для accepted-кандидатов пакета.
    Ровно один accepted на item; иначе ValueError."""
    accepted: dict[str, dict] = {}
    for item in candidates.get("items", []):
        if item.get("source_package") != package_id:
            continue
        chosen = [c for c in item.get("candidates", [])
                  if (c.get("facilitator_review") or {}).get("outcome") == "accepted"]
        if len(chosen) > 1:
            raise ValueError(f"{item['item_id']}: {len(chosen)} accepted candidates — ровно один")
        if chosen:
            cand = chosen[0]
            review = cand["facilitator_review"]
            at_build = review.get("at_build") or {}
            if review.get("by") != "facilitator":
                raise ValueError(f"{cand['candidate_id']}: accepted, but not by facilitator")
            accepted[item["item_id"]] = {"candidate": cand, "kind": cand.get("kind"),
                                         "at_build": at_build, "item": item, "review": review}
    return accepted


def message_pairs(messages: list[dict]) -> list[tuple[str, str]]:
    return [(m.get("author"), m.get("text")) for m in messages]


def target_index_of(item: dict) -> int | None:
    return next((i for i, m in enumerate(item["messages"]) if m.get("message_id") == item.get("target_message_id")), None)


def provenance_subset(cand: dict) -> dict:
    prov = cand.get("provenance") or {}
    return {k: prov[k] for k in PROVENANCE_KEYS if k in prov}


# ---------------------------------------------------------------- build

def materialize_items(source_items: list[dict], source_pilot_id: str, accepted: dict[str, dict],
                      replacements: dict[str, str], carried_over_origin: str, revision_reason: str,
                      build_date: str) -> tuple[list[dict], dict[str, dict], list[str]]:
    """Возвращает (items v2 в порядке источника, replaces-блок manifest'а, issues)."""
    issues: list[str] = []
    built: list[dict] = []
    replaces: dict[str, dict] = {}
    source_ids = {i["item_id"] for i in source_items}
    for old, new in replacements.items():
        if old not in source_ids:
            issues.append(f"replacements: '{old}' не в source package")
        if new in source_ids:
            issues.append(f"replacements: новый id '{new}' переиспользует id source package — запрещено")
        if old not in accepted or accepted[old]["kind"] != "replacement":
            issues.append(f"replacements: для '{old}' нет accepted candidate kind=replacement")
    for iid, rec in accepted.items():
        if rec["kind"] == "replacement" and iid not in replacements:
            issues.append(f"{iid}: accepted replacement без нового id в spec.replacements")
        if rec["kind"] not in ("revision", "replacement"):
            issues.append(f"{iid}: unknown candidate kind {rec['kind']!r}")
    if issues:
        return [], {}, issues

    for src in source_items:
        iid = src["item_id"]
        src_hash = item_content_sha256(src)
        src_target = target_index_of(src)
        rec = accepted.get(iid)
        if rec is None:
            item = {
                "schema_version": SCHEMA_V2, "item_id": iid, "language": src["language"],
                "messages": [{"message_id": m["message_id"], "author": m["author"], "text": m["text"]} for m in src["messages"]],
                "target_message_id": src["target_message_id"],
                "authoring": {
                    "origin": carried_over_origin, "revision_reason": None, "accepted_via": "carried_over",
                    "parent_item_version": {"package_id": source_pilot_id, "item_id": iid, "content_sha256": src_hash},
                },
            }
            built.append(item)
            continue

        cand, at_build, review = rec["candidate"], rec["at_build"], rec["review"]
        cmsgs = cand["messages"]
        if [a for a, _ in message_pairs(cmsgs)] != [m["author"] for m in src["messages"]]:
            issues.append(f"{iid}/{cand['candidate_id']}: авторы кандидата не совпадают с источником (V7)")
            continue
        cand_target = rec["item"]["original"].get("target_index")
        if cand_target != src_target:
            issues.append(f"{iid}/{cand['candidate_id']}: target_index кандидата {cand_target} != источника {src_target}")
            continue
        note = (f"accepted {review.get('date')} by facilitator from {cand['candidate_id']} "
                f"(naturalness-ab {rec['item'].get('source_package')}→donor generation); reason: {review.get('reason', '')}")
        if rec["kind"] == "revision":
            expected_parent = {"package_id": source_pilot_id, "item_id": iid, "content_sha256": src_hash}
            declared = at_build.get("parent_item_version")
            if declared is not None and declared != expected_parent:
                issues.append(f"{iid}/{cand['candidate_id']}: at_build.parent_item_version не совпадает с frozen source "
                              f"(declared {str(declared.get('content_sha256'))[:12]}…, actual {src_hash[:12]}…)")
                continue
            if at_build.get("accepted_via", "facilitator") != "facilitator":
                issues.append(f"{iid}/{cand['candidate_id']}: at_build.accepted_via {at_build.get('accepted_via')!r} — эта сборка пишет только facilitator")
                continue
            reason = at_build.get("revision_reason", revision_reason)
            item = {
                "schema_version": SCHEMA_V2, "item_id": iid, "language": src["language"],
                "messages": [{"message_id": s["message_id"], "author": c["author"], "text": c["text"]}
                             for s, c in zip(src["messages"], cmsgs)],
                "target_message_id": src["target_message_id"],
                "authoring": {
                    "origin": cand.get("origin", "llm_assisted"), "revision_reason": reason,
                    "accepted_via": "facilitator", "parent_item_version": expected_parent,
                    "provenance": provenance_subset(cand), "note": note,
                },
            }
            if review.get("caveat"):
                item["authoring"]["caveat"] = review["caveat"]
            built.append(item)
        else:  # replacement → new original item, retired id never reused
            new_id = replacements[iid]
            item = {
                "schema_version": SCHEMA_V2, "item_id": new_id, "language": src["language"],
                "messages": [{"message_id": f"{new_id}-m{i}", "author": c["author"], "text": c["text"]}
                             for i, c in enumerate(cmsgs, start=1)],
                "target_message_id": f"{new_id}-m{cand_target + 1}",
                "authoring": {
                    "origin": cand.get("origin", "llm_assisted"), "revision_reason": None,
                    "accepted_via": "facilitator", "parent_item_version": None,
                    "provenance": provenance_subset(cand),
                    "design_intent": at_build.get("design_intent") or rec["item"].get("edit_constraint"),
                    "note": note + f"; new original replacing {source_pilot_id}/{iid} — see manifest.replaces",
                },
            }
            if review.get("caveat"):
                item["authoring"]["caveat"] = review["caveat"]
            built.append(item)
            replaces[iid] = {"new_item_id": new_id, "retired": {"package_id": source_pilot_id, "item_id": iid, "content_sha256": src_hash},
                             "accepted_candidate": cand["candidate_id"], "inherits_design_intent": True, "accepted": build_date}
    return built, replaces, issues


def build_manifest(source_manifest: dict, spec: dict, replaces: dict, spec_path: Path, candidates_sha: str,
                   source_items_sha: str, ontology_path: Path) -> dict:
    manifest = {
        "schema_version": source_manifest.get("schema_version", "rf.pilot-manifest.v1"),
        "pilot_id": spec["package_id"],
        "ontology_version": source_manifest["ontology_version"],
        "ontology_sha256": sha256_file(ontology_path),
        "unit_of_analysis": source_manifest.get("unit_of_analysis"),
        "active_labels": source_manifest["active_labels"],
        "deferred_labels": source_manifest.get("deferred_labels", {}),
        "items_file": "items.jsonl",
        "strata_file": "strata.json",
        "responses_dir": "responses/",
        "annotators": list(spec["presentation"]),
        "instructions": spec.get("instructions", source_manifest.get("instructions")),
        "blind_rules": source_manifest.get("blind_rules", []),
        "presentation": spec["presentation"],
        "eligibility_criteria": source_manifest.get("eligibility_criteria", []),
        "replaces": replaces,
        "build": {
            "schema_version": BUILD_SCHEMA,
            "tool": "metrics.materialize",
            "contract": spec.get("contract"),
            "build_date": spec["build_date"],
            "spec_file": spec_path.name,
            "spec_sha256": sha256_file(spec_path),
            "source_package": {"pilot_id": source_manifest["pilot_id"], "dir": spec["source_package_dir"], "items_sha256": source_items_sha},
            "candidates_file": spec["candidates_file"],
            "candidates_sha256": candidates_sha,
        },
    }
    return manifest


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_package(spec_path: Path, force: bool = False) -> list[str]:
    spec, base = load_spec(spec_path)
    out_dir = base
    if (out_dir / "items.jsonl").exists() and not force:
        return [f"REFUSED: {out_dir / 'items.jsonl'} уже существует — пакет immutable; --force только до issuance"]
    if (out_dir / CHECKSUMS_FILE).exists():
        return [f"REFUSED: пакет запечатан ({CHECKSUMS_FILE}); изменение = новая версия пакета"]
    source_dir = (base / spec["source_package_dir"]).resolve()
    source_manifest = json.loads((source_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
    source_items_path = source_dir / source_manifest["items_file"]
    source_items = load_jsonl(source_items_path)
    source_strata = json.loads((source_dir / source_manifest["strata_file"]).read_text(encoding="utf-8"))
    candidates_path = (base / spec["candidates_file"]).resolve()
    try:
        candidates = load_candidates(candidates_path, spec["candidates_sha256"])
        accepted = accepted_for_package(candidates, source_manifest["pilot_id"])
    except ValueError as exc:
        return [str(exc)]
    replacements = spec.get("replacements", {})
    built, replaces, issues = materialize_items(
        source_items, source_manifest["pilot_id"], accepted, replacements,
        spec.get("carried_over_origin", "unrecorded"), spec.get("revision_reason", "naturalness"), spec["build_date"])
    if issues:
        return issues
    strata = {replacements.get(k, k): v for k, v in source_strata["strata"].items()}
    ontology_path = (base / spec["ontology"]).resolve()
    manifest = build_manifest(source_manifest, spec, replaces, spec_path, sha256_file(candidates_path),
                              sha256_file(source_items_path), ontology_path)
    eligibility = {
        "schema_version": "rf.pilot-eligibility.v1",
        "note": "Заполняется фасилитатором ДО выдачи пакета. Только эти булевы поля — никакой демографии и персональных данных.",
        "annotators": {a: {c: None for c in manifest["eligibility_criteria"]} for a in manifest["annotators"]},
    }
    write_jsonl(out_dir / "items.jsonl", built)
    write_json(out_dir / "strata.json", {"schema_version": source_strata.get("schema_version", "rf.pilot-strata.v1"),
                                         "note": source_strata.get("note", ""), "strata": strata})
    write_json(out_dir / "pilot-manifest.json", manifest)
    write_json(out_dir / "eligibility.json", eligibility)
    (out_dir / "responses").mkdir(exist_ok=True)
    replaced = ", ".join(f"{old}→{rep['new_item_id']}" for old, rep in replaces.items()) or "—"
    print(f"built {len(built)} items → {out_dir / 'items.jsonl'} (sha256 {sha256_file(out_dir / 'items.jsonl')[:12]}…); "
          f"replaces: {replaced}")
    return verify_package(out_dir)


# ---------------------------------------------------------------- verify (gate F, A, B)

def verify_package(pilot_dir: Path) -> list[str]:
    issues: list[str] = []
    manifest = json.loads((pilot_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
    build = manifest.get("build")
    if not build or build.get("schema_version") != BUILD_SCHEMA:
        return ["manifest.build отсутствует — пакет не materialized этим инструментом, verify неприменим"]
    spec_path = pilot_dir / build["spec_file"]
    if not spec_path.exists():
        return [f"build spec {spec_path} отсутствует"]
    if sha256_file(spec_path) != build["spec_sha256"]:
        issues.append("build-spec.json изменён после сборки")
    spec, base = load_spec(spec_path)
    source_dir = (base / spec["source_package_dir"]).resolve()
    source_manifest = json.loads((source_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
    source_items_path = source_dir / source_manifest["items_file"]
    if sha256_file(source_items_path) != build["source_package"]["items_sha256"]:
        issues.append("source package items.jsonl изменился после сборки — frozen source нарушен")
    source = {i["item_id"]: i for i in load_jsonl(source_items_path)}
    source_strata = json.loads((source_dir / source_manifest["strata_file"]).read_text(encoding="utf-8"))["strata"]
    candidates_path = (base / spec["candidates_file"]).resolve()
    try:
        candidates = load_candidates(candidates_path, build["candidates_sha256"])
        accepted = accepted_for_package(candidates, source_manifest["pilot_id"])
    except ValueError as exc:
        return issues + [str(exc)]
    replacements = spec.get("replacements", {})
    built = load_jsonl(pilot_dir / manifest["items_file"])
    built_ids = [i["item_id"] for i in built]
    strata = json.loads((pilot_dir / manifest["strata_file"]).read_text(encoding="utf-8"))["strata"]
    used: dict[str, str] = {}

    for item in built:
        iid = item["item_id"]
        auth = item.get("authoring") or {}
        parent = auth.get("parent_item_version")
        pairs = message_pairs(item["messages"])
        tidx = target_index_of(item)
        if parent is not None and auth.get("revision_reason") is None:  # carried_over
            src = source.get(iid)
            if src is None:
                issues.append(f"{iid}: carried_over, но в source package нет такого item")
                continue
            if item_content_sha256(item) != item_content_sha256(src):
                issues.append(f"{iid}: carried_over, но содержимое отличается от frozen source")
            if [m["message_id"] for m in item["messages"]] != [m["message_id"] for m in src["messages"]]:
                issues.append(f"{iid}: carried_over, но message_id отличаются от source")
            if iid in accepted:
                issues.append(f"{iid}: есть accepted candidate, а item перенесён как carried_over")
        elif parent is not None:  # revision
            rec = accepted.get(iid)
            if rec is None or rec["kind"] != "revision":
                issues.append(f"{iid}: revision без accepted candidate kind=revision")
                continue
            cand = rec["candidate"]
            if pairs != message_pairs(cand["messages"]):
                issues.append(f"{iid}: текст item'а != accepted candidate {cand['candidate_id']} (exact equality gate)")
            if tidx != rec["item"]["original"].get("target_index"):
                issues.append(f"{iid}: target index != accepted candidate")
            src = source.get(iid)
            if src is None or parent.get("content_sha256") != item_content_sha256(src):
                issues.append(f"{iid}: parent hash != frozen source")
            used[iid] = cand["candidate_id"]
        elif auth.get("accepted_via") == "facilitator":  # replacement = new original
            olds = [old for old, rep in manifest.get("replaces", {}).items() if rep.get("new_item_id") == iid]
            if len(olds) != 1:
                issues.append(f"{iid}: новый original без ровно одной записи manifest.replaces")
                continue
            old = olds[0]
            rec = accepted.get(old)
            if rec is None or rec["kind"] != "replacement":
                issues.append(f"{iid}: replaces {old}, но accepted candidate kind=replacement для {old} нет")
                continue
            cand = rec["candidate"]
            if pairs != message_pairs(cand["messages"]):
                issues.append(f"{iid}: текст item'а != accepted candidate {cand['candidate_id']} (exact equality gate)")
            if tidx != rec["item"]["original"].get("target_index"):
                issues.append(f"{iid}: target index != accepted candidate")
            if iid in source:
                issues.append(f"{iid}: новый id переиспользует id source package")
            if old in built_ids:
                issues.append(f"{old}: retired id присутствует в пакете")
            if replacements.get(old) != iid:
                issues.append(f"{iid}: manifest.replaces не согласован со spec.replacements")
            if manifest["replaces"][old].get("retired", {}).get("content_sha256") != item_content_sha256(source[old]):
                issues.append(f"{old}: retired content hash в manifest.replaces != frozen source")
            used[old] = cand["candidate_id"]
        else:
            issues.append(f"{iid}: accepted_via {auth.get('accepted_via')!r} без parent — эта сборка таких не производит")

    for iid, rec in accepted.items():
        if iid not in used:
            issues.append(f"{iid}: accepted candidate {rec['candidate']['candidate_id']} не использован")
    if len(built) != len(source):
        issues.append(f"items: {len(built)} в пакете vs {len(source)} в source — размер должен совпадать (replacement 1:1)")
    expected_strata = {replacements.get(k, k): v for k, v in source_strata.items()}
    if strata != expected_strata:
        issues.append("strata.json не равен source strata под id-mapping replacements")
    checksums = pilot_dir / CHECKSUMS_FILE
    if checksums.exists():
        for line in checksums.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, name = line.split(maxsplit=1)
            target = pilot_dir / name.strip()
            if not target.exists() or sha256_file(target) != digest:
                issues.append(f"{CHECKSUMS_FILE}: {name.strip()} изменён после seal")
    if not issues:
        print(f"verify OK: {len(built)} items; accepted candidates used: {len(used)}; "
              f"replaces: {len(manifest.get('replaces', {}))}; package sha256 {sha256_file(pilot_dir / manifest['items_file'])[:12]}…")
    return issues


# ---------------------------------------------------------------- seal (I)

def seal_package(pilot_dir: Path) -> list[str]:
    issues = verify_package(pilot_dir)
    if issues:
        return issues
    files = ["build-spec.json", "items.jsonl", "strata.json", "pilot-manifest.json", "eligibility.json"]
    for sub in ("presentation", "presentation-map", "form"):
        d = pilot_dir / sub
        if d.exists():
            files += sorted(str(p.relative_to(pilot_dir)) for p in d.iterdir() if p.is_file())
    lines = [f"{sha256_file(pilot_dir / f)}  {f}" for f in files if (pilot_dir / f).exists()]
    (pilot_dir / CHECKSUMS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"sealed {len(lines)} files → {pilot_dir / CHECKSUMS_FILE}")
    return []


# ---------------------------------------------------------------- dogfood (D)

ITEM_RE = re.compile(r"^  - item_id: (\S+)\s*$")
AUTHOR_RE = re.compile(r"^      - author: (\S+)\s*$")
TEXT_RE = re.compile(r'^        text: "(.*)"\s*$')
TARGET_RE = re.compile(r"^        target: true\s*$")


def _unquote(raw: str) -> str:
    return raw.replace('\\"', '"').replace("\\\\", "\\")


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_dogfood_yaml(text: str) -> tuple[dict, list[dict]]:
    """Минимальный парсер подмножества dogfood yaml (stdlib-only): header-скаляры первого уровня
    и items[{item_id, messages[{author,text}], target_index}]. Всё остальное (probe, design_note)
    не интерпретируется. Парсер сверяется с pinned snapshot перед использованием."""
    header: dict[str, str] = {}
    items: list[dict] = []
    current: dict | None = None
    in_items = False
    for line in text.splitlines():
        if not in_items:
            if line.startswith("items:"):
                in_items = True
            elif re.match(r"^[a-z_]+: \S", line):
                key, _, value = line.partition(": ")
                header[key] = value.strip()
            continue
        if re.match(r"^[a-z_]+:", line):  # верхнеуровневый ключ после items — конец списка
            in_items = False
            continue
        m = ITEM_RE.match(line)
        if m:
            current = {"item_id": m.group(1), "messages": [], "target_index": None}
            items.append(current)
            continue
        if current is None:
            continue
        m = AUTHOR_RE.match(line)
        if m:
            current["messages"].append({"author": m.group(1), "text": None})
            continue
        m = TEXT_RE.match(line)
        if m and current["messages"]:
            current["messages"][-1]["text"] = _unquote(m.group(1))
            continue
        if TARGET_RE.match(line) and current["messages"]:
            current["target_index"] = len(current["messages"]) - 1
    return header, items


def render_dogfood_yaml(source_text: str, dogfood_id: str, lineage_lines: list[str],
                        changes: dict[str, dict]) -> str:
    """changes: old item_id → {'new_item_id': str|None, 'messages': [{author,text}]}.
    Меняются только строки item_id и text внутри блока item'а; остальное побайтно как в источнике."""
    out: list[str] = []
    current: str | None = None
    msg_index = -1
    lines = source_text.splitlines()
    for line in lines:
        if line.startswith("dogfood_id:"):
            out.append(f"dogfood_id: {dogfood_id}")
            continue
        if line.startswith("included_in_scientific_pilot:"):
            out.append(line)
            out.extend(lineage_lines)
            continue
        m = ITEM_RE.match(line)
        if m:
            current = m.group(1)
            msg_index = -1
            change = changes.get(current)
            if change and change.get("new_item_id"):
                out.append(f"  - item_id: {change['new_item_id']}")
                continue
            out.append(line)
            continue
        if current and AUTHOR_RE.match(line):
            msg_index += 1
        if current in changes and TEXT_RE.match(line):
            new_text = changes[current]["messages"][msg_index]["text"]
            out.append(f"        text: {_quote(new_text)}")
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def dogfood_package(spec_path: Path, force: bool = False) -> list[str]:
    spec, base = load_spec(spec_path)
    cfg = spec.get("dogfood")
    if not cfg:
        return ["spec.dogfood отсутствует"]
    issues: list[str] = []
    source_path = (base / cfg["source_yaml"]).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    source_sha = sha256_file(source_path)
    if source_sha != cfg["source_sha256"]:
        return [f"dogfood source yaml sha256 {source_sha[:12]}… != pinned {cfg['source_sha256'][:12]}… — frozen v6 изменён?"]
    snapshot = json.loads((base / cfg["source_snapshot"]).read_text(encoding="utf-8"))
    if snapshot.get("source_sha256") != source_sha:
        return ["pinned snapshot не соответствует source yaml"]
    header, parsed = parse_dogfood_yaml(source_text)
    snap_items = {i["item_id"]: i for i in snapshot["items"]}
    if {i["item_id"]: {"messages": i["messages"], "target_index": i["target_index"]} for i in parsed} != \
            {k: {"messages": v["messages"], "target_index": v["target_index"]} for k, v in snap_items.items()}:
        return ["парсер dogfood yaml не воспроизводит pinned snapshot — отказ (парсер не заслуживает доверия)"]
    if header.get("dogfood_id") != cfg["source_dogfood_id"]:
        return [f"source dogfood_id {header.get('dogfood_id')!r} != {cfg['source_dogfood_id']!r}"]
    language = header.get("language", "ru")

    candidates_path = (base / spec["candidates_file"]).resolve()
    try:
        candidates = load_candidates(candidates_path, spec["candidates_sha256"])
        accepted = accepted_for_package(candidates, cfg["source_dogfood_id"])
    except ValueError as exc:
        return [str(exc)]
    replacements = cfg.get("replacements", {})
    for old in replacements:
        if old not in accepted or accepted[old]["kind"] != "replacement":
            issues.append(f"dogfood replacements: для '{old}' нет accepted candidate kind=replacement")
    for iid, rec in accepted.items():
        if rec["kind"] == "replacement" and iid not in replacements:
            issues.append(f"dogfood {iid}: accepted replacement без нового id")
        if iid not in snap_items:
            issues.append(f"dogfood {iid}: accepted candidate для item'а, которого нет в v6")
        elif [m["author"] for m in rec["candidate"]["messages"]] != [m["author"] for m in snap_items[iid]["messages"]]:
            issues.append(f"dogfood {iid}: авторы кандидата != v6 (V7)")
    if issues:
        return issues

    target_path = base / cfg["target_yaml"]
    prov_path = base / cfg["provenance_file"]
    if (target_path.exists() or prov_path.exists()) and not force:
        return [f"REFUSED: {target_path.name} / {prov_path.name} уже существуют (--force только до issuance)"]

    changes = {iid: {"new_item_id": replacements.get(iid), "messages": rec["candidate"]["messages"]}
               for iid, rec in accepted.items()}
    lineage_lines = [
        "lineage:",
        f"  derived_from: {cfg['source_dogfood_id']}",
        f"  source_yaml: {cfg['source_yaml']}",
        f"  source_sha256: {source_sha}",
        f"  provenance_sidecar: {Path(cfg['provenance_file']).name}",
        "  rule: v6 frozen and hash-pinned; changes materialize as this new version; retired ids never reused",
    ]
    if replacements:
        lineage_lines.append("  replaces:")
        lineage_lines += [f"    {old}: {new}" for old, new in replacements.items()]
    rendered = render_dogfood_yaml(source_text, cfg["target_dogfood_id"], lineage_lines, changes)
    _, result_items = parse_dogfood_yaml(rendered)
    result = {i["item_id"]: i for i in result_items}

    records = []
    for old_id, snap in snap_items.items():
        old_hash = canonical_content_sha256(language, snap["messages"], snap["target_index"])
        rec = accepted.get(old_id)
        new_id = replacements.get(old_id, old_id)
        res = result.get(new_id)
        if res is None:
            issues.append(f"dogfood: {new_id} отсутствует в результате")
            continue
        res_hash = canonical_content_sha256(language, res["messages"], res["target_index"])
        if rec is None:
            if res_hash != old_hash:
                issues.append(f"dogfood {old_id}: carried over, но содержимое изменилось")
            records.append({"old": {"item_id": old_id, "content_sha256": old_hash}, "kind": "carried_over",
                            "accepted_candidate": None, "result": {"item_id": new_id, "content_sha256": res_hash},
                            "authoring": {"origin": "unrecorded", "revision_reason": None, "accepted_via": "carried_over"}})
            continue
        cand = rec["candidate"]
        if message_pairs(res["messages"]) != message_pairs(cand["messages"]) or res["target_index"] != snap["target_index"]:
            issues.append(f"dogfood {old_id}→{new_id}: результат != accepted candidate {cand['candidate_id']} (exact equality gate)")
        if rec["kind"] == "replacement" and old_id in result:
            issues.append(f"dogfood {old_id}: retired id присутствует в результате")
        records.append({
            "old": {"item_id": old_id, "content_sha256": old_hash}, "kind": rec["kind"],
            "accepted_candidate": cand["candidate_id"], "accepted": rec["review"].get("date"),
            "reason": rec["review"].get("reason"), "caveat": rec["review"].get("caveat"),
            "result": {"item_id": new_id, "content_sha256": res_hash},
            "authoring": ({"origin": cand.get("origin"), "revision_reason": spec.get("revision_reason", "naturalness"),
                           "accepted_via": "facilitator", "parent": {"dogfood_id": cfg["source_dogfood_id"], "item_id": old_id, "content_sha256": old_hash}}
                          if rec["kind"] == "revision" else
                          {"origin": cand.get("origin"), "revision_reason": None, "accepted_via": "facilitator", "parent": None,
                           "inherits_design_intent_from": old_id, "design_intent": rec["at_build"].get("design_intent")}),
            "provenance": provenance_subset(cand),
        })
    if len(result) != len(snap_items):
        issues.append(f"dogfood: {len(result)} items в результате vs {len(snap_items)} в v6")
    if issues:
        return issues
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(rendered, encoding="utf-8")
    provenance = {
        "schema_version": DOGFOOD_PROVENANCE_SCHEMA,
        "dogfood_id": cfg["target_dogfood_id"],
        "derived_from": {"dogfood_id": cfg["source_dogfood_id"], "yaml": cfg["source_yaml"], "sha256": source_sha},
        "result_yaml": {"file": Path(cfg["target_yaml"]).name, "sha256": sha256_file(target_path)},
        "candidates": {"file": spec["candidates_file"], "sha256": spec["candidates_sha256"]},
        "build_date": spec["build_date"],
        "contract": spec.get("contract"),
        "storage_contract": "dogfood yaml — не rf.pilot-item.v2; lineage только в этом sidecar (cutover contract D)",
        "web_surface": "src/annotation-web Catalog.hs НЕ переключён этой сборкой — web cutover, отдельная приёмка",
        "items": records,
    }
    write_json(prov_path, provenance)
    changed_ids = ", ".join(f"{k}→{replacements.get(k, k)}" for k in accepted)
    print(f"dogfood: {len(result)} items → {target_path} (sha256 {provenance['result_yaml']['sha256'][:12]}…); "
          f"sidecar {prov_path.name}; changed: {changed_ids}")
    return []


# ---------------------------------------------------------------- CLI

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--spec", type=Path, required=True); b.add_argument("--force", action="store_true")
    v = sub.add_parser("verify"); v.add_argument("--pilot-dir", type=Path, required=True)
    d = sub.add_parser("dogfood"); d.add_argument("--spec", type=Path, required=True); d.add_argument("--force", action="store_true")
    s = sub.add_parser("seal"); s.add_argument("--pilot-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == "build":
        issues = build_package(args.spec, force=args.force)
    elif args.cmd == "verify":
        issues = verify_package(args.pilot_dir)
    elif args.cmd == "dogfood":
        issues = dogfood_package(args.spec, force=args.force)
    else:
        issues = seal_package(args.pilot_dir)
    if issues:
        print(f"{args.cmd.upper()} FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print(f"OK: {args.cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
