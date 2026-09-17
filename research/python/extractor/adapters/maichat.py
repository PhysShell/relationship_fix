"""MaiChat → RawMessage. The adapter owns source semantics; the core does not.

MaiChat: A Text-based Dialogue Corpus Rich In Conversational Features.
Dao, Lai & Bell, LREC 2026, https://aclanthology.org/2026.lrec-1.123/
Dataset v1.0, https://doi.org/10.7488/ds/8083 — CC BY-SA 4.0.
Not vendored: share-alike would follow a copy into this repository, and the
harness takes a path instead.

Verified at the primary source before anything was built on it (README §4, §7):
50 conversations, 100 participants, 4,975 messages, 2 of them `deliveryStatus:
failed`, millisecond UTC timestamps, ethics approval by the School of
Informatics panel and informed consent for release.

THE POINT OF THIS FILE. `RawMessage` is documented as carrying a SENDING-DEVICE
clock. MaiChat's `time` is the SERVER RECEIVE time — README §7, verbatim: «the
gap between the last log timestamp and "time" therefore reflects both send delay
and network latency». Those are different quantities, so the adapter declares
which one it is handing over rather than quietly assigning it. Every result
computed from this corpus is a result about observed server-receive time, and
`AdapterProvenance` travels with the messages so that sentence cannot be lost.

The same applies to failed delivery. Whether an undelivered message took part in
the conversation is a question about the source, not about topology, so the
adapter decides it and says so. The core extractor never learns that MaiChat
exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from ..model import RawMessage

SOURCE = "MaiChat v1.0 (Dao, Lai & Bell, LREC 2026; doi:10.7488/ds/8083)"
LICENCE = "CC BY-SA 4.0 — attribution and share-alike; derivative datasets carry the same licence"


class TimestampSemantics(str, Enum):
    """What the number in a message's time field actually is.

    Never inferred. An adapter that does not know says UNKNOWN, and a consumer
    that needs send-time must refuse rather than assume.
    """

    SEND_LOCAL = "send_local"            # clock of the sending device — what RawMessage assumes
    SERVER_RECEIVE = "server_receive"    # what MaiChat provides
    UNKNOWN = "unknown"


class FailedDeliveryPolicy(str, Enum):
    EXCLUDED = "excluded_from_topology"
    INCLUDED = "included_in_topology"


@dataclass(frozen=True, slots=True)
class AdapterProvenance:
    """What a downstream sentence about these numbers is allowed to say."""

    source: str
    timestamp_semantics: TimestampSemantics
    failed_delivery_policy: FailedDeliveryPolicy
    licence: str
    conversation_id: str
    participants: tuple[str, str]
    messages_in_file: int
    failed_excluded: int

    def claim_prefix(self) -> str:
        """Prepended to any reported result, so the caveat cannot detach."""
        return (f"on {self.source}, using source-provided "
                f"{self.timestamp_semantics.value} timestamps")


def _epoch(node: dict) -> float:
    """MongoDB Extended JSON {"$date": "...Z"} → epoch seconds, UTC."""
    raw = node["$date"]
    if isinstance(raw, (int, float)):          # some exports use millis
        return raw / 1000.0
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(
        tzinfo=timezone.utc).timestamp()


def _oid(node: dict) -> str:
    return node["$oid"]


def load_conversation(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def adapt(
    conversation: dict,
    failed_delivery: FailedDeliveryPolicy = FailedDeliveryPolicy.EXCLUDED,
) -> tuple[list[RawMessage], AdapterProvenance]:
    """One MaiChat conversation → messages the core extractor can read.

    `content` is measured and dropped in the same expression: `char_count` is
    the only thing that survives, and `RawMessage` has nowhere to put text even
    if someone tried.

    `utc_offset_minutes` is 0 because MaiChat's timestamps are already UTC —
    which is NOT the same as saying the field means what RawMessage's docstring
    says it means. That is what the provenance is for.
    """
    conversation_id = _oid(conversation["_id"])
    participants = (_oid(conversation["firstId"]), _oid(conversation["secondId"]))

    messages: list[RawMessage] = []
    failed_excluded = 0
    for message in conversation["messages"]:
        failed = message.get("deliveryStatus") == "failed"
        if failed and failed_delivery is FailedDeliveryPolicy.EXCLUDED:
            failed_excluded += 1
            continue
        messages.append(RawMessage(
            message_id=_oid(message["_id"]),
            actor=_oid(message["ofUser"]),
            local_time=_epoch(message["time"]),
            utc_offset_minutes=0,
            char_count=len(message["content"]),
            device_id=message.get("deviceType", "unknown"),
        ))

    provenance = AdapterProvenance(
        source=SOURCE,
        timestamp_semantics=TimestampSemantics.SERVER_RECEIVE,
        failed_delivery_policy=failed_delivery,
        licence=LICENCE,
        conversation_id=conversation_id,
        participants=participants,
        messages_in_file=len(conversation["messages"]),
        failed_excluded=failed_excluded,
    )
    return messages, provenance


def adapt_file(path: str | Path, **kwargs) -> tuple[list[RawMessage], AdapterProvenance]:
    return adapt(load_conversation(path), **kwargs)
