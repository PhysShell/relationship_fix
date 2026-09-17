"""What a source's numbers actually mean. Declared by the adapter, never guessed.

The MaiChat pass produced one declaration — that its timestamps are server
receive times, not send times. Characterising the Seufert WhatsApp corpus
produced four more, and one of them is not a caveat but a hard refusal.

WhatsApp's own export carries WHOLE-MINUTE timestamps. A minute-resolution
source therefore defines a PARTIAL order: within one minute it does not say who
spoke first. Our core turns `(timestamp, message_id)` into a TOTAL order, and
its tie-break is only sound when the id is a real identity from the source. If
an adapter synthesises ids for a source that has none and lets the core break
ties with them, it manufactures hand-overs that are not in the data — and on
that corpus a sixth of adjacent message pairs are both cross-actor and
simultaneous, so it would be manufacturing them constantly.

Hence `assert_topology_oracle_usable`: the refusal is mechanical, not a
paragraph someone has to remember.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TimestampSemantics(str, Enum):
    """What the number in a message's time field actually is.

    Never inferred. An adapter that does not know says UNKNOWN, and a consumer
    that needs send-time must refuse rather than assume.
    """

    SEND_LOCAL = "send_local"              # clock of the sending device
    SERVER_RECEIVE = "server_receive"      # e.g. MaiChat
    EXPORT_RENDERED = "export_rendered"    # a timestamp printed by an exporter
    UNKNOWN = "unknown"


class TimestampResolution(str, Enum):
    """The grain of the source clock. A coarse timestamp is a bucket, not a point."""

    MILLISECOND = "millisecond"
    SECOND = "second"
    MINUTE = "minute"
    MIXED = "mixed"          # observed varying within one corpus
    UNKNOWN = "unknown"

    @property
    def bucket_seconds(self) -> float:
        return {"millisecond": 0.001, "second": 1.0, "minute": 60.0}.get(self.value, float("nan"))


class OrderingSemantics(str, Enum):
    """Whether the source says who spoke first."""

    TOTAL = "total"                                   # every pair is ordered
    PARTIAL_WITHIN_EQUAL_TIMESTAMP = "partial_within_equal_timestamp"
    UNKNOWN = "unknown"


class OrderingEvidence(str, Enum):
    """WHAT establishes the order, which is a separate question from identity.

    A source can guarantee that file order is message order while giving no ids
    at all: topology is then known exactly and deduplication is impossible.
    Conversely, stable ids on their own order nothing. Conflating the two was a
    defect in the first version of this module.
    """

    TIMESTAMP = "timestamp"                # the clock is fine enough to order everything
    SOURCE_SEQUENCE = "source_sequence"    # the source guarantees its own emission order
    STABLE_ORDER_KEY = "stable_order_key"  # a monotone key independent of the clock
    NONE = "none"


class MessageIdentity(str, Enum):
    STABLE_ID = "stable_id"          # the source gives a real per-message identity
    CONTENT_HASH = "content_hash"    # repeats collapse; "ок" and "ок" are one value
    NONE = "none"


class Deduplication(str, Enum):
    BY_STABLE_ID = "by_stable_id"
    DISABLED = "disabled"            # no identity to deduplicate on; do not invent one


class LengthSemantics(str, Enum):
    """What a character count counts. Not decoration.

    A column called `char_count` that excludes emojis is a different quantity
    from one that includes them. Six months on, somebody compares two columns
    with the same name and triumphantly discovers a psychological effect of
    Unicode.
    """

    TEXT_CHARS = "text_chars"
    TEXT_CHARS_EXCLUDING_EMOJI = "text_chars_excluding_emoji"
    BUCKETED = "bucketed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SourceSemantics:
    """One adapter's declaration about its source. Every field is required."""

    timestamp_meaning: TimestampSemantics
    timestamp_resolution: TimestampResolution
    ordering: OrderingSemantics
    ordering_evidence: OrderingEvidence
    message_identity: MessageIdentity
    deduplication: Deduplication
    length: LengthSemantics
    notes: tuple[str, ...] = ()

    @property
    def usable_as_topology_oracle(self) -> bool:
        """Exact hand-over claims need a total order AND something that establishes it.

        Identity is deliberately NOT part of this test. Ids answer a different
        question — deduplication, cross-device reconciliation, stable references
        — and a source with guaranteed emission order and no ids at all knows
        its topology perfectly.
        """
        return (self.ordering is OrderingSemantics.TOTAL
                and self.ordering_evidence is not OrderingEvidence.NONE)

    @property
    def deduplication_possible(self) -> bool:
        """The other question, answered by identity rather than by order."""
        return self.message_identity is MessageIdentity.STABLE_ID

    @property
    def boundary_uncertainty_seconds(self) -> float:
        """A coarse timestamp near a period edge is ambiguous by a whole bucket."""
        return self.timestamp_resolution.bucket_seconds


class TopologyOracleRefused(ValueError):
    """The source cannot support an exact hand-over claim."""


def assert_topology_oracle_usable(semantics: SourceSemantics, source: str) -> None:
    """Refuse any topology-derived use of a source that does not order its messages.

    NOT merely exact per-message claims. An earlier version of this docstring
    said a one-minute ordering error was "negligible against a six-hour horizon",
    which is wrong, and wrong because of the very clause that followed it. If the
    ambiguity only shifted a known latency by up to a minute, it would indeed be
    nothing against H=6h. But an ambiguous cross-actor tie changes the actor
    SEQUENCE, and therefore how many hand-overs exist at all:

        12:01 A                 one reading:  A | B A   -> one hand-over
        12:01 B                 another:      A B | A   -> hand-over, answered
        12:01 A                 another:      A B A ... -> different pairing again

    A single flipped tie can turn one opportunity into two, and the extra one
    contributes a FULL H to `sum_min_latency` if it ends up unanswered. That
    moves `opportunities_eligible`, `replied_within`, `sum_min_latency_H` and the
    RMTR denominator. It is not sixty seconds against six hours.

    So a partially-ordered source supports parsing, spans, volume, sender-set
    checks, message-type and length accounting — and no topology-derived
    aggregate computed the ordinary way. What it CAN support is bounds over all
    admissible orderings, which is a different computation and a far more
    interesting one; see docs/research/reactivity-power-design.md §6.1.2.
    """
    if semantics.usable_as_topology_oracle:
        return
    raise TopologyOracleRefused(
        f"{source}: ordering={semantics.ordering.value}, "
        f"evidence={semantics.ordering_evidence.value} — topology-derived aggregates "
        f"are not supported as point values; compute bounds over admissible orderings "
        f"or restrict to unambiguous segments"
    )
