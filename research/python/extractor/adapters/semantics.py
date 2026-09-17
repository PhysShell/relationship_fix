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

    timestamp_meaning: str            # e.g. 'server_receive', 'send_local'
    timestamp_resolution: TimestampResolution
    ordering: OrderingSemantics
    message_identity: MessageIdentity
    deduplication: Deduplication
    length: LengthSemantics
    notes: tuple[str, ...] = ()

    @property
    def usable_as_topology_oracle(self) -> bool:
        """Exact hand-over claims need a total order backed by real identity."""
        return (self.ordering is OrderingSemantics.TOTAL
                and self.message_identity is MessageIdentity.STABLE_ID)

    @property
    def boundary_uncertainty_seconds(self) -> float:
        """A coarse timestamp near a period edge is ambiguous by a whole bucket."""
        return self.timestamp_resolution.bucket_seconds


class TopologyOracleRefused(ValueError):
    """The source cannot support an exact hand-over claim."""


def assert_topology_oracle_usable(semantics: SourceSemantics, source: str) -> None:
    """Refuse exact-topology use of a source that does not order its messages.

    Aggregate use at hour scale is a different question and is NOT blocked here:
    a one-minute ordering error is negligible against a six-hour horizon, even
    though it can flip whether a particular hand-over exists at all.
    """
    if semantics.usable_as_topology_oracle:
        return
    raise TopologyOracleRefused(
        f"{source}: ordering={semantics.ordering.value}, "
        f"identity={semantics.message_identity.value} — exact hand-over claims are "
        f"not supported; synthesising ids to break ties would manufacture hand-overs"
    )
