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
    "observation_window_seconds",
    "deleted_dropped", "duplicates_dropped", "max_sync_lag_seconds",
})
EXPORT_HORIZON_KEYS = frozenset({
    "horizon_hours", "opportunities_eligible", "sum_min_latency_seconds", "replied_within",
    "sum_reply_speed_seconds", "sum_run_span_seconds", "sum_run_messages",
})

#: Exported fields whose scope is the WHOLE input stream and therefore partly
#: describes the non-enrolled partner's device and deletions. Useful for
#: qualification, open question before the variance pilot: does the server need
#: these as numbers, or is a local data-quality flag enough? Pinned as a set so
#: the decision is a field removal rather than an act of memory.
PARTNER_SCOPED_DIAGNOSTIC_KEYS = frozenset({
    "deleted_dropped", "duplicates_dropped", "max_sync_lag_seconds",
})


class DuplicateConflict(ValueError):
    """Two copies of one message_id disagree on a field that cannot change.

    The reference extractor fails closed rather than picking a winner: a
    synthesised record that never existed would diff cleanly against nothing,
    and which copy won would depend on input order. A shipping client may prefer
    to count these and carry on; the oracle refuses, so a human looks.
    """


class DeletionStateConflict(DuplicateConflict):
    """One device says the message is there, another says it was deleted.

    A subclass, so `except DuplicateConflict` still catches it: it is the same
    failure — copies of one id disagreeing about something that cannot be true
    both ways. Dropping deleted copies BEFORE the conflict check used to make
    this the one disagreement the extractor resolved silently, always in favour
    of present. The most consequential field was the only unguarded one, while
    a changed author already failed closed.

    No "deletion always wins" rule is invented here. Which copy is current
    depends on the exporter's semantics, and the oracle does not guess.
    """


def normalize(raw: list[RawMessage]) -> tuple[list[NormalizedMessage], int, int, float]:
    """Timezone → UTC, drop deletions, collapse device duplicates, total-order.

    Returns the stream plus three extraction diagnostics: how many messages were
    dropped as deleted, how many duplicate copies were collapsed, and the worst
    sync lag seen. Rules, all exact:

      * event time is `local_time - utc_offset`, never `synced_at`. A message
        that syncs eight hours late still happened when it was sent, and late
        sync is therefore invisible to latency. This is a stated limitation:
        we cannot observe delivery, only sending.
      * `deleted_dropped` counts distinct ids dropped as deleted;
        `duplicates_dropped` counts repeat sightings of an id, deleted copies
        included. Both are hand-checkable from the input by counting.
      * a deleted message is dropped entirely. Name the contract correctly:
        this is CURRENT-STATE RECONSTRUCTION, not historically stable
        aggregation. Recomputing an old period after a reply is deleted WILL
        turn `replied` into `non-replied`. Stability after a period closes is
        the job of persistence — snapshot or event log — and not of this
        reference extractor. A deleted reply looks like a non-reply, which is
        why the count is exported.
      * duplicates are collapsed by `message_id` only, keeping the EARLIEST
        timestamp: clock disagreement between two phones is plausible. Fields
        that CANNOT legitimately differ for one id — `actor`, `char_count` —
        must match, and a disagreement raises `DuplicateConflict` instead of
        being silently resolved. Two genuinely similar messages do not share an
        id and are deliberately NOT merged.
      * order is (timestamp, message_id), so identical timestamps resolve
        deterministically and input order cannot matter.
    """
    max_sync_lag = 0.0
    duplicates_dropped = 0
    #: id -> (actor, char_count, deleted). Deleted copies are recorded here too,
    #: so the present/deleted disagreement is reachable by the check below.
    seen: dict[str, tuple[str, int, bool]] = {}
    by_id: dict[str, NormalizedMessage] = {}

    for message in raw:
        max_sync_lag = max(max_sync_lag, message.sync_lag_seconds)
        prior = seen.get(message.message_id)
        if prior is not None:
            duplicates_dropped += 1
            prior_actor, prior_chars, prior_deleted = prior
            if prior_actor != message.actor or prior_chars != message.char_count:
                raise DuplicateConflict(
                    f"copies of {message.message_id!r} disagree: "
                    f"actor {prior_actor!r}/{message.actor!r}, "
                    f"char_count {prior_chars}/{message.char_count}"
                )
            if prior_deleted != message.deleted:
                raise DeletionStateConflict(
                    f"copies of {message.message_id!r} disagree about deletion: "
                    f"{'deleted' if prior_deleted else 'present'}/"
                    f"{'deleted' if message.deleted else 'present'}"
                )
        seen[message.message_id] = (message.actor, message.char_count, message.deleted)
        if message.deleted:
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

    deleted_dropped = sum(1 for _, _, deleted in seen.values() if deleted)
    stream = sorted(by_id.values(), key=lambda m: m.sort_key)
    return stream, deleted_dropped, duplicates_dropped, max_sync_lag


def find_opportunities(stream: list[NormalizedMessage], participant: str) -> list[Opportunity]:
    """One opportunity per hand-over of the ball to `participant`.

    Opens at the first partner message whose predecessor is not the partner (or
    which starts the stream). A run of partner messages with no reply in between
    is ONE opportunity however long it runs: the ball changed hands once.

    MUST be given the FULL normalized stream, not a stream already cut to the
    period. Cutting first invents opportunities at the left edge: a partner
    message that merely continues a run already open before `period_start`
    becomes index 0 of the slice and looks like a fresh hand-over. Selection by
    period happens afterwards, on `opened_at`.
    """
    opportunities = []
    for index, message in enumerate(stream):
        if message.actor == participant:
            continue
        if index > 0 and stream[index - 1].actor != participant:
            continue                      # still inside the partner's run
        end = index
        while end + 1 < len(stream) and stream[end + 1].actor != participant:
            end += 1
        reply = next((m for m in stream[end + 1:] if m.actor == participant), None)
        opportunities.append(Opportunity(
            opener_id=message.message_id,
            opened_at=message.timestamp,
            reply_id=reply.message_id if reply else None,
            reply_at=reply.timestamp if reply else None,
            run_end_at=stream[end].timestamp,
            run_message_count=end - index + 1,
        ))
    return opportunities


def _episode_returns(
    stream: list[NormalizedMessage],
    participant: str,
    period_start: float,
    period_end: float,
) -> int:
    """Counted inside the period, but judged against the FULL stream.

    Same left-edge trap as opportunities: the first participant message inside
    the period cannot see the message immediately before `period_start` if the
    stream was cut first, so a genuine return after a long pause disappears
    exactly at the boundary. A message with no predecessor at all is not counted
    — we cannot know whether it followed a pause.
    """
    returns = 0
    for index, message in enumerate(stream):
        if message.actor != participant or index == 0:
            continue
        if not (period_start <= message.timestamp < period_end):
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
    """The whole extractor.

    Messages outside the period are NOT dropped first — that was the left-edge
    bug. Topology is built on the full normalized stream and the period then
    SELECTS: opportunities by `opened_at`, own messages and episode returns by
    timestamp, the latter still judged against the full stream. A well-meaning
    refactor that reintroduces an early slice reintroduces a phantom hand-over
    at `period_start`; `LeftBoundaryTests` exists to stop it.

    `mode` is a required part of the contract rather than a flag with a helpful
    default behaviour: PRODUCTION never builds the per-opportunity trace at all.
    """
    actors = {m.actor for m in raw}
    if len(actors) > 2:
        raise ValueError(f"the extractor handles dyads only, got actors: {sorted(actors)}")

    stream, deleted_dropped, duplicates_dropped, max_sync_lag = normalize(raw)
    # topology on the full stream, selection by period afterwards — see
    # find_opportunities' docstring for what cutting first would invent.
    opportunities = [
        o for o in find_opportunities(stream, participant)
        if period_start <= o.opened_at < period_end
    ]

    horizons = []
    for hours in horizons_hours:
        seconds = hours * 3600.0
        eligible = [o for o in opportunities if o.eligible_for(seconds, period_end)]
        replied = [o for o in eligible if o.replied_within(seconds)]
        horizons.append(HorizonAggregate(
            horizon_hours=hours,
            opportunities_eligible=len(eligible),
            sum_min_latency_seconds=sum(o.restricted_latency(seconds) for o in eligible),
            replied_within=len(replied),
            sum_reply_speed_seconds=sum(o.reply_speed_seconds for o in replied),
            sum_run_span_seconds=sum(o.run_span_seconds for o in eligible),
            sum_run_messages=sum(o.run_message_count for o in eligible),
        ))

    own = [m for m in stream
           if m.actor == participant and period_start <= m.timestamp < period_end]
    aggregate = PeriodAggregate(
        participant_id=participant,
        period_id=period_id,
        horizons=tuple(horizons),
        own_messages=LengthSummary(count=len(own), total_chars=sum(m.char_count for m in own)),
        own_episode_returns=_episode_returns(stream, participant, period_start, period_end),
        observation_window_seconds=period_end - period_start,
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
                "sum_reply_speed_seconds": h.sum_reply_speed_seconds,
                "sum_run_span_seconds": h.sum_run_span_seconds,
                "sum_run_messages": h.sum_run_messages,
            }
            for h in aggregate.horizons
        ],
        "own_message_count": aggregate.own_messages.count,
        "own_total_chars": aggregate.own_messages.total_chars,
        "own_episode_returns": aggregate.own_episode_returns,
        "observation_window_seconds": aggregate.observation_window_seconds,
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
            "run_span_seconds": o.run_span_seconds,
            "reply_speed_seconds": o.reply_speed_seconds,
            "run_message_count": o.run_message_count,
        }
        for o in result.export_trace()
    ]
