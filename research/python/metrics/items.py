"""Pilot items: схемы rf.pilot-item.v1 / v2, content hash, stimulus-проекция.

v1 — только stimulus: item_id, language, messages[{message_id, author, text}],
target_message_id.

v2 — v1 + блок `authoring`: история происхождения текста этой версии item.
Facilitator-only: разметчику никогда не показывается (presentation-слой всегда
проецирует item в v1-форму, validate_items ловит утечку).

    "authoring": {
      "origin":              "human" | "llm_assisted" | "unrecorded",
      "revision_reason":     null | "naturalness" | "adjacency" | "grammar" | "other",
      "accepted_via":        "original" | "carried_over" | "blinded_ab" | "facilitator",
      "parent_item_version": null | {"package_id": ..., "item_id": ..., "content_sha256": ...},
      "note":                "..."   (необязательно)
    }

Инварианты (проверяет authoring_issues):
- parent_item_version = null  ⇒  revision_reason = null и accepted_via ∈ {original, facilitator}
  (original — текст без записанной приёмки; facilitator — новый original, принятый фасилитатором,
  например replacement flagged item'а: чем он что заменяет — package-level `replaces` в manifest,
  не поле item'а; изменение 2026-09-08, cutover contract);
- accepted_via = facilitator без parent  ⇒  origin ≠ unrecorded (кто-то этот текст написал);
- parent есть и revision_reason = null  ⇔  accepted_via = carried_over и content-hash
  ребёнка == content-hash родителя (текст перенесён без изменений);
- parent есть и revision_reason задан  ⇒  accepted_via ∈ {blinded_ab, facilitator} и
  content-hash ребёнка != родителя (правка обязана менять текст);
- parent.content_sha256 обязан совпадать с фактическим hash родителя в его пакете;
- origin описывает текст ИМЕННО ЭТОЙ версии: принятый LLM-кандидат — llm_assisted, даже
  если принял его человек; unrecorded — только для текста, созданного до введения
  provenance (пакет v0), то есть только у original / carried_over.

Content-hash считается от того, что видит разметчик (language, авторы и тексты
сообщений, позиция target), и не зависит от item_id / message_id / authoring.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

SCHEMA_V1 = "rf.pilot-item.v1"
SCHEMA_V2 = "rf.pilot-item.v2"
ITEM_SCHEMAS = (SCHEMA_V1, SCHEMA_V2)

ORIGINS = ("human", "llm_assisted", "unrecorded")
REVISION_REASONS = ("naturalness", "adjacency", "grammar", "other")
ACCEPTED_VIA = ("original", "carried_over", "blinded_ab", "facilitator")
# Без parent допустимы только эти способы приёмки (replacement = новый original, принятый фасилитатором).
ORIGINLESS_ACCEPTED_VIA = ("original", "facilitator")

STIMULUS_KEYS = ("schema_version", "item_id", "language", "messages", "target_message_id")


def canonical_content_sha256(language: str | None, messages: list[dict], target_index: int | None) -> str:
    """Hash канонической формы stimulus'а (язык, авторы+тексты по порядку, индекс target) —
    одна и та же для item'ов пакета и для источников без message_id (dogfood yaml snapshot)."""
    canonical = {
        "language": language,
        "messages": [{"author": m.get("author"), "text": m.get("text")} for m in messages],
        "target_index": target_index,
    }
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def item_content_sha256(item: dict) -> str:
    """Hash содержимого stimulus'а: язык, авторы+тексты по порядку, индекс target."""
    messages = item["messages"]
    target_index = next(
        (i for i, m in enumerate(messages) if m.get("message_id") == item.get("target_message_id")), None)
    return canonical_content_sha256(item.get("language"), messages, target_index)


def stimulus_only(item: dict) -> dict:
    """v1-проекция item'а: всё, что не stimulus (authoring, design notes), отбрасывается."""
    projected = {k: item[k] for k in STIMULUS_KEYS if k in item}
    projected["schema_version"] = SCHEMA_V1
    projected["messages"] = [
        {"message_id": m["message_id"], "author": m["author"], "text": m["text"]}
        for m in item["messages"]
    ]
    return projected


ParentLookup = Callable[[str, str], "dict | None"]


def authoring_issues(item: dict, parent_lookup: ParentLookup) -> list[str]:
    """Проверка блока authoring одного v2-item. parent_lookup(package_id, item_id)
    возвращает родительский item (любой схемы) или None, если пакет/item не найден."""
    item_id = item.get("item_id", "?")
    authoring = item.get("authoring")
    if not isinstance(authoring, dict):
        return [f"{item_id}: v2 item without 'authoring' block"]
    issues: list[str] = []

    origin = authoring.get("origin")
    if origin not in ORIGINS:
        issues.append(f"{item_id}: authoring.origin must be one of {ORIGINS}, got {origin!r}")
    reason = authoring.get("revision_reason")
    if reason is not None and reason not in REVISION_REASONS:
        issues.append(f"{item_id}: authoring.revision_reason must be null or one of {REVISION_REASONS}, got {reason!r}")
    accepted = authoring.get("accepted_via")
    if accepted not in ACCEPTED_VIA:
        issues.append(f"{item_id}: authoring.accepted_via must be one of {ACCEPTED_VIA}, got {accepted!r}")
    parent = authoring.get("parent_item_version")
    if "parent_item_version" not in authoring:
        issues.append(f"{item_id}: authoring.parent_item_version is required (null for originals)")
    note = authoring.get("note")
    if note is not None and not isinstance(note, str):
        issues.append(f"{item_id}: authoring.note must be a string")

    if parent is None:
        if accepted not in ORIGINLESS_ACCEPTED_VIA:
            issues.append(f"{item_id}: no parent ⇒ accepted_via must be one of {ORIGINLESS_ACCEPTED_VIA}, got {accepted!r}")
        if reason is not None:
            issues.append(f"{item_id}: no parent ⇒ revision_reason must be null, got {reason!r}")
        if accepted == "facilitator" and origin == "unrecorded":
            issues.append(f"{item_id}: facilitator-accepted original cannot have origin 'unrecorded' — someone wrote it")
        return issues

    if not isinstance(parent, dict) or not all(k in parent for k in ("package_id", "item_id", "content_sha256")):
        issues.append(f"{item_id}: parent_item_version needs package_id, item_id, content_sha256")
        return issues

    parent_item = parent_lookup(parent["package_id"], parent["item_id"])
    if parent_item is None:
        issues.append(f"{item_id}: parent {parent['package_id']}/{parent['item_id']} not found — lineage unverifiable")
    else:
        actual = item_content_sha256(parent_item)
        if actual != parent["content_sha256"]:
            issues.append(f"{item_id}: parent content_sha256 mismatch (declared {parent['content_sha256'][:12]}…, "
                          f"actual {actual[:12]}…)")
        same_text = item_content_sha256(item) == actual
        if reason is None:
            if accepted != "carried_over":
                issues.append(f"{item_id}: parent without revision_reason ⇒ accepted_via must be 'carried_over', got {accepted!r}")
            if not same_text:
                issues.append(f"{item_id}: carried_over but content differs from parent — declare a revision_reason")
        else:
            if accepted not in ("blinded_ab", "facilitator"):
                issues.append(f"{item_id}: revision ⇒ accepted_via must be blinded_ab|facilitator, got {accepted!r}")
            if same_text:
                issues.append(f"{item_id}: revision_reason={reason!r} but content is identical to parent")
            if origin == "unrecorded":
                issues.append(f"{item_id}: a revision cannot have origin 'unrecorded' — someone wrote it")
    return issues
