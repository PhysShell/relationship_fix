"""Telegram Desktop import → qualification → adapter.

Every rule here is a line from the acquisition ledger, and each one names the
property it implements. The ledger closed with zero open extractor assumptions,
which is what finally permits an adapter to exist at all.

The adapter reads message text — it must, to count characters — and keeps none.
No type in this module has a field capable of holding text, a name, a media
path or a chat id, which is the same guarantee the extractor's types carry.
"""

from __future__ import annotations

import json

from extractor.model import RawMessage

from .model import Finding, Layer, ProtocolWindow, Verdict

#: `identity.message_id` — ids are integers, including negative ones for
#: migrated history (shifted by -1e9). `sort_key` in the frozen extractor
#: compares message_id as a STRING, where "10" < "9", so a bare decimal would
#: turn tie resolution into lexicographic noise. Offset-and-pad keeps numeric
#: order inside a string, injectively.
ID_OFFSET = 10 ** 12
ID_WIDTH = 15

#: `events.type` — only real messages take part in topology.
MESSAGE_TYPE = "message"

#: The pilot's target. Anything else is readable and not ours.
TARGET_CHAT_TYPE = "personal_chat"


class StrictJson(json.JSONDecoder):
    def __init__(self):
        super().__init__(parse_constant=self._refuse)

    @staticmethod
    def _refuse(name):
        raise ValueError(f"non-standard JSON constant {name!r}")


def encode_message_id(value: int) -> str:
    """Order-preserving string id. See ID_OFFSET."""
    shifted = value + ID_OFFSET
    if shifted < 0:
        raise ValueError("message id below the supported range")
    return f"{shifted:0{ID_WIDTH}d}"


class Refusal(Exception):
    """Raised with the layer that caught it, so attribution cannot drift."""

    def __init__(self, layer: Layer, code: str, detail: str = ""):
        self.finding = Finding(layer=layer, code=code, detail=detail)
        super().__init__(code)


def load(raw: bytes) -> dict:
    """`format.strict_json` is UNAVAILABLE — two classes of invalid output are
    documented — so parsing is strict and failure is a refusal, never a repair."""
    try:
        document = json.loads(raw.decode("utf-8"), cls=StrictJson)
    except (UnicodeDecodeError, ValueError) as failure:
        # the parser message may quote the offending bytes; keep the class only
        raise Refusal(Layer.IMPORT, "invalid_json", type(failure).__name__) from None
    if not isinstance(document, dict):
        raise Refusal(Layer.IMPORT, "not_an_export", "top level is not an object")
    return document


def qualify(document: dict) -> str:
    """Is this the target at all? Wrong type is OUT_OF_SCOPE, not a refusal:
    the file is fine, it is simply not a dyad. Three public exports in a row
    were private_group, bot_chat and saved_messages."""
    chat_type = document.get("type")
    if not isinstance(chat_type, str):
        raise Refusal(Layer.QUALIFICATION, "no_chat_type")
    if not isinstance(document.get("messages"), list):
        raise Refusal(Layer.QUALIFICATION, "no_messages_array")
    return chat_type


def adapt(document: dict, window: ProtocolWindow) -> tuple[list[RawMessage], tuple[Finding, ...]]:
    """Document → RawMessage, with every ledger contract applied.

    - `time.instant`: event time is `date_unixtime` only.
    - `time.local_string` is UNAVAILABLE: `date` is never parsed. It is the
      exporting machine's wall clock, measured at -5 h on a public export, with
      no offset recorded.
    - `events.type`: service entries are excluded and counted.
    - `events.deleted` is UNAVAILABLE: everything is `deleted=False`, and a
      finding says the source cannot report deletions, so a zero is never read
      as "none happened".
    - `identity.actor`: the actor is `from_id`, never the display name.
    """
    findings: list[Finding] = []
    messages: list[RawMessage] = []
    service = 0
    missing_time = 0

    for entry in document["messages"]:
        if not isinstance(entry, dict):
            raise Refusal(Layer.ADAPTER, "malformed_entry")
        if entry.get("type") != MESSAGE_TYPE:
            service += 1
            continue
        stamp = entry.get("date_unixtime")
        if stamp is None:
            missing_time += 1
            continue
        try:
            at = float(int(stamp))
            identifier = encode_message_id(int(entry["id"]))
        except (KeyError, TypeError, ValueError):
            raise Refusal(Layer.ADAPTER, "unusable_identity_or_time") from None
        actor = entry.get("from_id")
        if not isinstance(actor, (str, int)):
            raise Refusal(Layer.ADAPTER, "no_actor")
        text = entry.get("text")
        messages.append(RawMessage(
            message_id=identifier,
            actor=str(actor),
            local_time=at,               # already an instant
            utc_offset_minutes=0,        # `date` is not parsed, so none is applied
            char_count=_length(text),
            device_id="export",
            deleted=False,
            synced_at=None,
        ))

    findings.append(Finding(Layer.ADAPTER, "deletions_unobservable",
                            "the format has no concept of a deleted message"))
    if service:
        findings.append(Finding(Layer.ADAPTER, "service_entries_excluded", str(service)))
    if missing_time:
        findings.append(Finding(Layer.ADAPTER, "entries_without_timestamp", str(missing_time)))
    if not messages:
        raise Refusal(Layer.ADAPTER, "no_usable_messages")
    return messages, tuple(findings)


def _length(text) -> int:
    """`events.media_only` is PARTIAL: `text` may be a string, a list of
    entities, or absent. The policy is declared rather than inferred — media
    without a caption is zero characters."""
    if isinstance(text, str):
        return len(text)
    if isinstance(text, list):
        total = 0
        for part in text:
            if isinstance(part, str):
                total += len(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                total += len(part["text"])
        return total
    return 0


def coverage_findings(document: dict, messages: list[RawMessage],
                      window: ProtocolWindow) -> tuple[Finding, ...]:
    """`coverage.completeness` is UNAVAILABLE — silent truncation is documented
    at exactly 10000 messages. Suspicion is raised, never resolved."""
    findings = []
    if len(document["messages"]) == 10000:
        findings.append(Finding(Layer.QUALIFICATION, "suspicious_round_count", "10000"))
    stamps = [m.timestamp for m in messages]
    if not stamps or min(stamps) >= window.start:
        # NOTHING is observed before the window opens, so we cannot tell whether
        # the export begins there because the conversation did, or because the
        # file was cut at that point. `coverage.completeness` is UNAVAILABLE and
        # silent truncation is documented, so the left edge stays unproven.
        #
        # A message BEFORE the window start is the opposite of suspicious: it
        # demonstrates the export reaches back past the period, which is exactly
        # the coverage we want. The first version of this check flagged that
        # case — it fired on the evidence rather than on its absence, and the
        # golden positive path found it within a minute of existing.
        findings.append(Finding(Layer.QUALIFICATION, "left_edge_unproven",
                                "no message observed before the window opens"))
    return tuple(findings)
