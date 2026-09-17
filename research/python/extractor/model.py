"""Types for the local derived-aggregate extractor. No text, by construction.

ADR-0001 §Python role 1. This is the REFERENCE implementation and the
exact-diff oracle for qualification — the thing a device client must match —
not the shipping client itself.

The privacy boundary from reactivity-experiment-prereg §3.2 is enforced by the
type system rather than by discipline: there is no field anywhere in this
package that can hold message text. The extractor is handed a character count
and never a body, so "no message text leaves the device" is true because there
is nowhere to put it.

Nothing here knows about behaviour ontologies, calibration, impact or any other
psychology. It converts a message stream into counts and durations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

#: The pre-specified horizon grid (hours). Fixed before data
#: (reactivity-power-design §6.2); eligibility is computed separately for each.
HORIZONS_HOURS = (6.0, 12.0, 24.0)

#: A message following a gap at least this long counts as returning to the
#: conversation. Same value as the frozen segmentation spike's default, stated
#: here rather than imported: this package depends on nothing.
EPISODE_GAP_SECONDS = 3600.0


class Mode(str, Enum):
    """Production keeps nothing per-opportunity. Qualification may, with consent."""

    PRODUCTION = "production"
    QUALIFICATION = "qualification"


@dataclass(frozen=True, slots=True)
class RawMessage:
    """One message as a device sees it. Deliberately has no body.

    `local_time` is naive wall-clock seconds on the sending device and
    `utc_offset_minutes` its offset, so normalisation has something real to do.
    `synced_at` is when this device learned of the message, which is NOT the
    event time and never used as one.
    """

    message_id: str
    actor: str
    local_time: float
    utc_offset_minutes: int
    char_count: int
    device_id: str = "d0"
    deleted: bool = False
    synced_at: float | None = None      # epoch UTC, may lag far behind

    @property
    def timestamp(self) -> float:
        """Event time, epoch UTC."""
        return self.local_time - self.utc_offset_minutes * 60.0

    @property
    def sync_lag_seconds(self) -> float:
        if self.synced_at is None:
            return 0.0
        return max(0.0, self.synced_at - self.timestamp)


@dataclass(frozen=True, slots=True)
class NormalizedMessage:
    """After timezone normalisation, de-duplication and deletion removal."""

    message_id: str
    actor: str
    timestamp: float
    char_count: int
    devices: tuple[str, ...]
    sync_lag_seconds: float = 0.0

    @property
    def sort_key(self) -> tuple[float, str]:
        """Total order. Ties broken by id so identical timestamps are deterministic."""
        return (self.timestamp, self.message_id)


@dataclass(frozen=True, slots=True)
class Opportunity:
    """One moment where the ball passed to the participant.

    Opens on the FIRST message of the partner's consecutive run: a burst of
    three partner messages is one opportunity, not three, because the ball
    changed hands once.
    """

    opener_id: str
    opened_at: float
    reply_id: str | None
    reply_at: float | None

    @property
    def latency_seconds(self) -> float | None:
        if self.reply_at is None:
            return None
        return self.reply_at - self.opened_at

    def eligible_for(self, horizon_seconds: float, period_end: float) -> bool:
        """Calendar censoring: the whole window must fit inside the period.

        Without this an opportunity opening an hour before the period ends would
        be scored as a non-reply by the calendar rather than by behaviour — and
        the eligible SET therefore differs between horizons, which is why the
        counts below are per-horizon.
        """
        return self.opened_at + horizon_seconds <= period_end

    def restricted_latency(self, horizon_seconds: float) -> float:
        """min(latency, H); a non-reply contributes H, never nothing."""
        latency = self.latency_seconds
        if latency is None:
            return horizon_seconds
        return min(latency, horizon_seconds)

    def replied_within(self, horizon_seconds: float) -> bool:
        latency = self.latency_seconds
        return latency is not None and latency <= horizon_seconds


@dataclass(frozen=True, slots=True)
class HorizonAggregate:
    """The three sufficient statistics, per horizon. Nothing per-opportunity."""

    horizon_hours: float
    opportunities_eligible: int
    sum_min_latency_seconds: float
    replied_within: int

    @property
    def rmtr_seconds(self) -> float | None:
        if self.opportunities_eligible == 0:
            return None
        return self.sum_min_latency_seconds / self.opportunities_eligible

    @property
    def reply_rate(self) -> float | None:
        if self.opportunities_eligible == 0:
            return None
        return self.replied_within / self.opportunities_eligible

    @property
    def conditional_mean_latency_seconds(self) -> float | None:
        """Recoverable from the three numbers; the median is not, deliberately."""
        if self.replied_within == 0:
            return None
        horizon = self.horizon_hours * 3600.0
        unanswered = self.opportunities_eligible - self.replied_within
        return (self.sum_min_latency_seconds - unanswered * horizon) / self.replied_within


@dataclass(frozen=True, slots=True)
class LengthSummary:
    count: int
    total_chars: int

    @property
    def mean_chars(self) -> float | None:
        return self.total_chars / self.count if self.count else None


@dataclass(frozen=True, slots=True)
class PeriodAggregate:
    """Everything that may leave the device for one person and one period."""

    participant_id: str
    period_id: str
    horizons: tuple[HorizonAggregate, ...]
    own_messages: LengthSummary
    own_episode_returns: int
    # diagnostics about the extraction itself, not about anybody's behaviour
    deleted_dropped: int = 0
    duplicates_dropped: int = 0
    max_sync_lag_seconds: float = 0.0

    def horizon(self, horizon_hours: float) -> HorizonAggregate:
        for aggregate in self.horizons:
            if aggregate.horizon_hours == horizon_hours:
                return aggregate
        raise KeyError(f"no aggregate for H={horizon_hours}")


@dataclass
class ExtractionResult:
    """Aggregates always; the per-opportunity trace only under qualification.

    In PRODUCTION the trace is not merely withheld — it is never built and the
    accessor refuses. That is the difference between a policy and a guarantee.
    """

    aggregate: PeriodAggregate
    mode: Mode
    consent_to_share_trace: bool = False
    _trace: tuple[Opportunity, ...] | None = field(default=None, repr=False)

    def export_trace(self) -> tuple[Opportunity, ...]:
        if self.mode is not Mode.QUALIFICATION:
            raise PermissionError("a per-opportunity trace does not exist outside qualification")
        if not self.consent_to_share_trace:
            raise PermissionError("the participant has not consented to share the trace")
        if self._trace is None:
            raise PermissionError("no trace was retained")
        return self._trace
