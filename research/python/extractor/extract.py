"""raw message stream → local derived aggregates. Nothing else.

Reference implementation for qualification exact-diff. Every rule below is
stated so a human can compute the expected answer by hand and compare byte for
byte; where a rule loses information the loss is counted and surfaced rather
than silently absorbed.
"""

from __future__ import annotations

from .model import (
    EPISODE_GAP_SECONDS,
    HORIZONS_HOURS,
    ExtractionResult,
    HorizonAggregate,
    LengthSummary,
    Mode,
    NormalizedMessage,
    Opportunity,
    PeriodAggregate,
    RawMessage,
)

#: Keys a production export may contain. Anything else is a bug, and the test
#: suite compares against this set rather than eyeballing the payload.
EXPORT_KEYS = frozenset({
    "participant_id", "period_id", "horizons",
    "own_message_count", "own_total_chars", "own_episode_returns",
    "deleted_dropped", "duplicates_dropped", "max_sync_lag_seconds",
})
EXPORT_HORIZON_KEYS = frozenset({
    "horizon_hours", "opportunities_eligible", "sum_min_latency_seconds", "replied_within",
})


def normalize(raw: list[RawMessage]) -> tuple[list[NormalizedMessage], int, int, float]:
    """Timezone → UTC, drop deletions, collapse device duplicates, total-order.

    Returns the stream plus three extraction diagnostics: how many messages were
    dropped as deleted, how many duplicate copies were collapsed, and the worst
    sync lag seen. Rules, all exact:

      * event time is `local_time - utc_offset`, never `synced_at`. A message
        that syncs eight hours late still happened when it was sent, and late
        sync is therefore invisible to latency. This is a stated limitation:
        we cannot observe delivery, only sending.
      * a deleted message is dropped entirely, because a later deletion must not
        be able to change an aggregate about the past. Consequence worth naming:
        a deleted reply looks like a non-reply, which is why the count is
        exported.
      * duplicates are collapsed by `message_id` only, keeping the EARLIEST
        timestamp. Two copies of one message from two phones share an id; two
        genuinely similar messages do not, and are deliberately NOT merged.
      * order is (timestamp, message_id), so identical timestamps resolve
        deterministically and input order cannot matter.
    """
    deleted_dropped = 0
    max_sync_lag = 0.0
    by_id: dict[str, NormalizedMessage] = {}

    for message in raw:
        max_sync_lag = max(max_sync_lag, message.sync_lag_seconds)
        if message.deleted:
            deleted_dropped += 1
            continue
        existing = by_id.get(message.message_id)
        if existing is None:
            by_id[message.message_id] = NormalizedMessage(
                message_id=message.message_id,
                actor=message.actor,
                timestamp=message.timestamp,
                char_count=message.char_count,
                devices=(message.device_id,),
                sync_lag_seconds=message.sync_lag_seconds,
            )
            continue
        by_id[message.message_id] = NormalizedMessage(
            message_id=existing.message_id,
            actor=existing.actor,
            timestamp=min(existing.timestamp, message.timestamp),
            char_count=existing.char_count,
            devices=tuple(sorted(set(existing.devices) | {message.device_id})),
            sync_lag_seconds=max(existing.sync_lag_seconds, message.sync_lag_seconds),
        )

    duplicates_dropped = sum(1 for m in raw if not m.deleted) - len(by_id)
    stream = sorted(by_id.values(), key=lambda m: m.sort_key)
    return stream, deleted_dropped, duplicates_dropped, max_sync_lag


def find_opportunities(stream: list[NormalizedMessage], participant: str) -> list[Opportunity]:
    """One opportunity per hand-over of the ball to `participant`.

    Opens at the first partner message whose predecessor is not the partner (or
    which starts the stream). A run of partner messages with no reply in between
    is ONE opportunity however long it runs: the ball changed hands once.
    """
    opportunities = []
    for index, message in enumerate(stream):
        if message.actor == participant:
            continue
        if index > 0 and stream[index - 1].actor != participant:
            continue                      # still inside the partner's run
        reply = next((m for m in stream[index + 1:] if m.actor == participant), None)
        opportunities.append(Opportunity(
            opener_id=message.message_id,
            opened_at=message.timestamp,
            reply_id=reply.message_id if reply else None,
            reply_at=reply.timestamp if reply else None,
        ))
    return opportunities


def _episode_returns(stream: list[NormalizedMessage], participant: str) -> int:
    returns = 0
    for index, message in enumerate(stream):
        if message.actor != participant or index == 0:
            continue
        if message.timestamp - stream[index - 1].timestamp >= EPISODE_GAP_SECONDS:
            returns += 1
    return returns


def extract(
    raw: list[RawMessage],
    participant: str,
    period_id: str,
    period_start: float,
    period_end: float,
    mode: Mode = Mode.PRODUCTION,
    consent_to_share_trace: bool = False,
    horizons_hours: tuple[float, ...] = HORIZONS_HOURS,
) -> ExtractionResult:
    """The whole extractor. Messages outside the period are dropped first.

    `mode` is a required part of the contract rather than a flag with a helpful
    default behaviour: PRODUCTION never builds the per-opportunity trace at all.
    """
    actors = {m.actor for m in raw}
    if len(actors) > 2:
        raise ValueError(f"the extractor handles dyads only, got actors: {sorted(actors)}")

    stream, deleted_dropped, duplicates_dropped, max_sync_lag = normalize(raw)
    stream = [m for m in stream if period_start <= m.timestamp < period_end]
    opportunities = find_opportunities(stream, participant)

    horizons = []
    for hours in horizons_hours:
        seconds = hours * 3600.0
        eligible = [o for o in opportunities if o.eligible_for(seconds, period_end)]
        horizons.append(HorizonAggregate(
            horizon_hours=hours,
            opportunities_eligible=len(eligible),
            sum_min_latency_seconds=sum(o.restricted_latency(seconds) for o in eligible),
            replied_within=sum(1 for o in eligible if o.replied_within(seconds)),
        ))

    own = [m for m in stream if m.actor == participant]
    aggregate = PeriodAggregate(
        participant_id=participant,
        period_id=period_id,
        horizons=tuple(horizons),
        own_messages=LengthSummary(count=len(own), total_chars=sum(m.char_count for m in own)),
        own_episode_returns=_episode_returns(stream, participant),
        deleted_dropped=deleted_dropped,
        duplicates_dropped=duplicates_dropped,
        max_sync_lag_seconds=max_sync_lag,
    )
    return ExtractionResult(
        aggregate=aggregate,
        mode=mode,
        consent_to_share_trace=consent_to_share_trace,
        _trace=tuple(opportunities) if mode is Mode.QUALIFICATION else None,
    )


def production_export(aggregate: PeriodAggregate) -> dict:
    """The only thing that leaves the device. Per person, per period, nothing else."""
    return {
        "participant_id": aggregate.participant_id,
        "period_id": aggregate.period_id,
        "horizons": [
            {
                "horizon_hours": h.horizon_hours,
                "opportunities_eligible": h.opportunities_eligible,
                "sum_min_latency_seconds": h.sum_min_latency_seconds,
                "replied_within": h.replied_within,
            }
            for h in aggregate.horizons
        ],
        "own_message_count": aggregate.own_messages.count,
        "own_total_chars": aggregate.own_messages.total_chars,
        "own_episode_returns": aggregate.own_episode_returns,
        "deleted_dropped": aggregate.deleted_dropped,
        "duplicates_dropped": aggregate.duplicates_dropped,
        "max_sync_lag_seconds": aggregate.max_sync_lag_seconds,
    }


def qualification_trace(result: ExtractionResult) -> list[dict]:
    """Per-opportunity rows for one human to check by hand against their own
    expectation. Refuses outside qualification and without consent."""
    return [
        {
            "opener_id": o.opener_id,
            "opened_at": o.opened_at,
            "reply_id": o.reply_id,
            "reply_at": o.reply_at,
            "latency_seconds": o.latency_seconds,
        }
        for o in result.export_trace()
    ]
