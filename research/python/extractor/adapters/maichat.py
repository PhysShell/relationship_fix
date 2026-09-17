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
computed from this corpus is a result about observed server-receive time.

`AdapterProvenance` is returned ALONGSIDE the messages, not welded to them. The
core `ExtractionResult` is deliberately blind to where its input came from, and
no type stops a caller from dropping the provenance on the floor — so the
guarantee is a contract on this layer, stated plainly rather than overstated:
**the MaiChat harness publishes no number without its `AdapterProvenance`**. The
core staying source-agnostic is the better division of labour anyway.

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
from .guards import verify_dyad_membership
from .semantics import (
    Deduplication,
    LengthSemantics,
    MessageIdentity,
    OrderingEvidence,
    OrderingSemantics,
    SourceSemantics,
    TimestampResolution,
    TimestampSemantics,
)

#: MaiChat's declaration. Compare with the WhatsApp-export corpora, where
#: resolution is MINUTE, ordering is partial and identity is absent.
SEMANTICS = SourceSemantics(
    timestamp_meaning=TimestampSemantics.SERVER_RECEIVE,
    timestamp_resolution=TimestampResolution.MILLISECOND,
    ordering=OrderingSemantics.TOTAL,
    ordering_evidence=OrderingEvidence.TIMESTAMP,   # ms clock orders everything
    message_identity=MessageIdentity.SOURCE_STABLE_ID,   # MongoDB ObjectID per message
    deduplication=Deduplication.BY_STABLE_ID,
    length=LengthSemantics.TEXT_CHARS,              # len(content), emojis included
    notes=("server receive time, not send time — README §7",),
)

SOURCE = "MaiChat v1.0 (Dao, Lai & Bell, LREC 2026; doi:10.7488/ds/8083)"
LICENCE = "CC BY-SA 4.0 — attribution and share-alike; derivative datasets carry the same licence"


class FailedDeliveryPolicy(str, Enum):
    EXCLUDED = "excluded_from_topology"
    INCLUDED = "included_in_topology"


@dataclass(frozen=True, slots=True)
class AdapterProvenance:
    """What a downstream sentence about these numbers is allowed to say."""

    source: str
    failed_delivery_policy: FailedDeliveryPolicy
    licence: str
    semantics: SourceSemantics
    conversation_id: str
    participants: tuple[str, str]
    messages_in_file: int
    failed_excluded: int

    def claim_prefix(self) -> str:
        """Prepended to any reported result, so the caveat cannot detach."""
        return (f"on {self.source}, using source-provided "
                f"{self.semantics.timestamp_meaning.value} timestamps at "
                f"{self.semantics.timestamp_resolution.value} resolution")


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

    Dyad membership is checked here rather than downstream: the core only asks
    that a stream have at most two actors, which a mis-joined file can satisfy
    while being about the wrong two people. MaiChat passes this trivially; the
    rule lives here so the messier adapters inherit something already tested.
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

    verify_dyad_membership((m.actor for m in messages), participants,
                           f"{SOURCE} conv {conversation_id}")

    provenance = AdapterProvenance(
        source=SOURCE,
        failed_delivery_policy=failed_delivery,
        licence=LICENCE,
        semantics=SEMANTICS,
        conversation_id=conversation_id,
        participants=participants,
        messages_in_file=len(conversation["messages"]),
        failed_excluded=failed_excluded,
    )
    return messages, provenance


def adapt_file(path: str | Path, **kwargs) -> tuple[list[RawMessage], AdapterProvenance]:
    return adapt(load_conversation(path), **kwargs)
