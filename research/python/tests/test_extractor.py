"""Exact-diff fixtures for the local extractor.

Every test is a small stream plus a hand-computable expected answer, compared
exactly. This is the suite the first ten qualification participants will extend:
each new class of dirt they bring gets an explicit expected result and a
regression fixture here, and the extractor is frozen only when all of them pass
on one clean rerun.

Nothing here checks statistics. It checks byte truth.
"""

import dataclasses
import unittest

from extractor import extract as ex
from extractor.model import (
    EPISODE_GAP_SECONDS,
    HORIZONS_HOURS,
    ExtractionResult,
    Mode,
    RawMessage,
)

HOUR = 3600.0
WEEK = 7 * 24 * HOUR
P = "participant"
Q = "partner"


def msg(mid, actor, at_hours, chars=10, offset=0, device="d0", deleted=False, synced=None):
    """`at_hours` is UTC; the local clock is derived so normalisation has work."""
    utc = at_hours * HOUR
    return RawMessage(
        message_id=mid,
        actor=actor,
        local_time=utc + offset * 60.0,
        utc_offset_minutes=offset,
        char_count=chars,
        device_id=device,
        deleted=deleted,
        synced_at=synced,
    )


def run(messages, *, start=0.0, end=WEEK, mode=Mode.PRODUCTION, consent=False, participant=P):
    return ex.extract(messages, participant, "w1", start, end, mode=mode,
                      consent_to_share_trace=consent)


def horizon(result, hours):
    return result.aggregate.horizon(hours)


class BurstTests(unittest.TestCase):
    def test_a_run_of_partner_messages_is_one_opportunity(self):
        """The ball changed hands once, so it is one opportunity, not three."""
        result = run([
            msg("m1", Q, 0.0), msg("m2", Q, 0.02), msg("m3", Q, 0.04),
            msg("m4", P, 0.5),
        ], mode=Mode.QUALIFICATION, consent=True)
        trace = ex.qualification_trace(result)
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["opener_id"], "m1")
        self.assertEqual(trace[0]["latency_seconds"], 0.5 * HOUR)
        self.assertEqual(horizon(result, 6.0).opportunities_eligible, 1)

    def test_the_ball_going_back_and_forth_opens_a_new_opportunity_each_time(self):
        result = run([
            msg("a", Q, 0.0), msg("b", P, 1.0),
            msg("c", Q, 2.0), msg("d", Q, 2.1), msg("e", P, 3.0),
        ], mode=Mode.QUALIFICATION, consent=True)
        trace = ex.qualification_trace(result)
        self.assertEqual([t["opener_id"] for t in trace], ["a", "c"])
        self.assertEqual([t["latency_seconds"] for t in trace], [HOUR, HOUR])

    def test_a_partner_run_with_no_reply_at_all_stays_one_opportunity(self):
        result = run([msg("a", Q, 0.0), msg("b", Q, 5.0), msg("c", Q, 30.0)],
                     mode=Mode.QUALIFICATION, consent=True)
        self.assertEqual(len(ex.qualification_trace(result)), 1)


class DecompositionTests(unittest.TestCase):
    """start_to_reentry = run_span + reply_speed, exactly, on every completed
    transition. Verified on 2,942 MaiChat transitions; pinned here on the shapes
    that make the terms differ."""

    def test_a_single_message_run_makes_the_two_latencies_coincide(self):
        result = run([msg("a", Q, 0.0), msg("b", P, 1.0)],
                     mode=Mode.QUALIFICATION, consent=True)
        row, = ex.qualification_trace(result)
        self.assertEqual(row["run_span_seconds"], 0.0)
        self.assertEqual(row["reply_speed_seconds"], row["latency_seconds"])
        self.assertEqual(row["run_message_count"], 1)

    def test_a_long_run_separates_them(self):
        """Partner writes for twenty minutes, participant answers in one."""
        result = run([msg("a", Q, 0.0), msg("b", Q, 10 / 60), msg("c", Q, 20 / 60),
                      msg("d", P, 21 / 60)], mode=Mode.QUALIFICATION, consent=True)
        row, = ex.qualification_trace(result)
        self.assertAlmostEqual(row["run_span_seconds"], 20 * 60, places=6)
        self.assertAlmostEqual(row["reply_speed_seconds"], 60, places=6)
        self.assertAlmostEqual(row["latency_seconds"], 21 * 60, places=6)
        self.assertEqual(row["run_message_count"], 3)

    def test_the_identity_holds_on_every_completed_transition(self):
        result = run([msg("a", Q, 0.0), msg("b", Q, 0.5), msg("c", P, 1.0),
                      msg("d", Q, 2.0), msg("e", P, 4.0),
                      msg("f", Q, 5.0), msg("g", Q, 5.5), msg("h", Q, 6.0)],
                     mode=Mode.QUALIFICATION, consent=True)
        completed = [r for r in ex.qualification_trace(result)
                     if r["latency_seconds"] is not None]
        self.assertEqual(len(completed), 2)
        for row in completed:
            self.assertAlmostEqual(
                row["latency_seconds"],
                row["run_span_seconds"] + row["reply_speed_seconds"], places=6)

    def test_reply_speed_is_undefined_for_a_non_response(self):
        """Which is exactly why it cannot be the primary: a metric built on it
        silently drops the cases that matter most."""
        result = run([msg("a", Q, 0.0), msg("b", Q, 1.0)],
                     mode=Mode.QUALIFICATION, consent=True)
        row, = ex.qualification_trace(result)
        self.assertIsNone(row["reply_speed_seconds"])
        self.assertIsNone(row["latency_seconds"])
        self.assertEqual(row["run_span_seconds"], HOUR)
        self.assertEqual(horizon(result, 6.0).sum_reply_speed_seconds, 0.0)
        self.assertIsNone(horizon(result, 6.0).mean_reply_speed_seconds)

    def test_the_descriptive_sums_are_aggregate_only_and_hand_checkable(self):
        result = run([msg("a", Q, 0.0), msg("b", Q, 1.0), msg("c", P, 2.0),
                      msg("d", Q, 3.0), msg("e", P, 3.5)])
        agg = horizon(result, 6.0)
        self.assertEqual(agg.opportunities_eligible, 2)
        self.assertEqual(agg.sum_run_span_seconds, HOUR)          # 1h + 0
        self.assertEqual(agg.sum_run_messages, 3)                 # 2 + 1
        self.assertEqual(agg.sum_reply_speed_seconds, HOUR + 0.5 * HOUR)
        self.assertEqual(agg.mean_run_messages, 1.5)


class RightCensoringTests(unittest.TestCase):
    """Assigning H to a non-response is only sound when the whole window was
    observed. That rule already exists as calendar censoring; named here in
    survival terms so nobody re-derives it as a new concern."""

    def test_an_unobserved_window_is_excluded_rather_than_scored_as_H(self):
        """Opportunity at 20:00, H=12h, coverage ends at 01:00. We know only
        T > 5h — so the opportunity is not eligible, not a 12h non-response."""
        result = run([msg("a", Q, 20.0)], start=0.0, end=25.0 * HOUR)
        self.assertEqual(horizon(result, 12.0).opportunities_eligible, 0)
        self.assertEqual(horizon(result, 12.0).sum_min_latency_seconds, 0.0)
        self.assertEqual(horizon(result, 6.0).opportunities_eligible, 0)

    def test_a_fully_observed_window_does_score_the_horizon(self):
        result = run([msg("a", Q, 0.0)], start=0.0, end=25.0 * HOUR)
        self.assertEqual(horizon(result, 12.0).opportunities_eligible, 1)
        self.assertEqual(horizon(result, 12.0).sum_min_latency_seconds, 12 * HOUR)


class HorizonTests(unittest.TestCase):
    def test_a_reply_lands_on_each_side_of_the_grid(self):
        """Opened at 0, replied at 8h: late for 6h, in time for 12h and 24h."""
        result = run([msg("a", Q, 0.0), msg("b", P, 8.0)])
        self.assertEqual(
            [(h.horizon_hours, h.replied_within, h.sum_min_latency_seconds)
             for h in result.aggregate.horizons],
            [(6.0, 0, 6 * HOUR), (12.0, 1, 8 * HOUR), (24.0, 1, 8 * HOUR)],
        )

    def test_no_reply_contributes_the_horizon_not_nothing(self):
        result = run([msg("a", Q, 0.0)])
        for hours in HORIZONS_HOURS:
            aggregate = horizon(result, hours)
            self.assertEqual(aggregate.opportunities_eligible, 1)
            self.assertEqual(aggregate.replied_within, 0)
            self.assertEqual(aggregate.sum_min_latency_seconds, hours * HOUR)
            self.assertEqual(aggregate.rmtr_seconds, hours * HOUR)

    def test_replied_within_zero_leaves_the_conditional_mean_undefined(self):
        result = run([msg("a", Q, 0.0)])
        self.assertIsNone(horizon(result, 12.0).conditional_mean_latency_seconds)
        self.assertEqual(horizon(result, 12.0).reply_rate, 0.0)

    def test_the_conditional_mean_is_recovered_from_the_three_numbers(self):
        """One reply at 2h, one non-reply, H=12: mean over repliers must be 2h."""
        result = run([
            msg("a", Q, 0.0), msg("b", P, 2.0),
            msg("c", Q, 50.0),
        ])
        aggregate = horizon(result, 12.0)
        self.assertEqual(aggregate.opportunities_eligible, 2)
        self.assertEqual(aggregate.replied_within, 1)
        self.assertEqual(aggregate.sum_min_latency_seconds, 2 * HOUR + 12 * HOUR)
        self.assertEqual(aggregate.conditional_mean_latency_seconds, 2 * HOUR)


class CalendarCensoringTests(unittest.TestCase):
    def test_eligibility_differs_between_horizons_at_the_period_edge(self):
        """Opened at 2h in a period ending at 25h: 2+24 > 25, so 24h is out.

        This is exactly why opportunities_eligible is exported per horizon.
        """
        result = run([msg("a", Q, 2.0), msg("b", P, 3.0)], end=25 * HOUR)
        self.assertEqual(
            [(h.horizon_hours, h.opportunities_eligible, h.replied_within,
              h.sum_min_latency_seconds) for h in result.aggregate.horizons],
            [(6.0, 1, 1, HOUR), (12.0, 1, 1, HOUR), (24.0, 0, 0, 0.0)],
        )

    def test_an_opportunity_censored_by_the_calendar_is_not_a_non_reply(self):
        """Without the rule this would score as a 6h non-reply instead of absent."""
        result = run([msg("a", Q, 21.0)], end=24 * HOUR)
        self.assertEqual(horizon(result, 6.0).opportunities_eligible, 0)
        self.assertEqual(horizon(result, 6.0).sum_min_latency_seconds, 0.0)
        self.assertIsNone(horizon(result, 6.0).rmtr_seconds)


class NormalizationTests(unittest.TestCase):
    def test_the_same_instant_in_two_timezones_is_one_instant(self):
        shifted = run([
            msg("a", Q, 0.0, offset=180),      # UTC+3
            msg("b", P, 1.0, offset=-480),     # UTC-8
        ])
        plain = run([msg("a", Q, 0.0), msg("b", P, 1.0)])
        self.assertEqual(ex.production_export(shifted.aggregate),
                         ex.production_export(plain.aggregate))
        self.assertEqual(horizon(shifted, 6.0).sum_min_latency_seconds, HOUR)

    def test_input_order_cannot_matter(self):
        messages = [msg("a", Q, 0.0), msg("b", P, 1.0), msg("c", Q, 2.0), msg("d", P, 2.5)]
        forward = ex.production_export(run(messages).aggregate)
        backward = ex.production_export(run(list(reversed(messages))).aggregate)
        self.assertEqual(forward, backward)

    def test_identical_timestamps_resolve_deterministically(self):
        both = [msg("z", Q, 1.0), msg("a", P, 1.0)]
        first = ex.production_export(run(both).aggregate)
        second = ex.production_export(run(list(reversed(both))).aggregate)
        self.assertEqual(first, second)

    def test_two_devices_reporting_one_message_collapse_to_one(self):
        result = run([
            msg("a", Q, 0.0, device="phone"),
            msg("a", Q, 0.001, device="laptop"),   # same id, slightly later clock
            msg("b", P, 1.0),
        ])
        self.assertEqual(result.aggregate.duplicates_dropped, 1)
        self.assertEqual(horizon(result, 6.0).opportunities_eligible, 1)
        self.assertEqual(horizon(result, 6.0).sum_min_latency_seconds, HOUR)  # earliest wins

    def test_two_similar_messages_without_a_shared_id_are_not_merged(self):
        """A deliberate limitation: near-duplicates are left alone rather than
        guessed at. Qualification exists to find out how often this bites."""
        result = run([msg("a", Q, 0.0), msg("b", Q, 0.001), msg("c", P, 1.0)])
        self.assertEqual(result.aggregate.duplicates_dropped, 0)

    def test_late_sync_does_not_move_an_event(self):
        late = run([
            msg("a", Q, 0.0, synced=8 * HOUR),
            msg("b", P, 1.0),
        ])
        prompt = run([msg("a", Q, 0.0), msg("b", P, 1.0)])
        self.assertEqual(horizon(late, 6.0).sum_min_latency_seconds,
                         horizon(prompt, 6.0).sum_min_latency_seconds)
        self.assertEqual(late.aggregate.max_sync_lag_seconds, 8 * HOUR)

    def test_sync_time_is_not_an_event_time_for_period_membership(self):
        """Sent inside the period, learned about after it ended. It counts."""
        result = run([msg("a", Q, 100.0, synced=200 * HOUR), msg("b", P, 101.0)],
                     start=0.0, end=150 * HOUR)
        self.assertEqual(horizon(result, 6.0).opportunities_eligible, 1)
        self.assertEqual(horizon(result, 6.0).sum_min_latency_seconds, HOUR)

    def test_sync_time_is_not_an_event_time_for_ordering(self):
        """If the opener were placed at its sync time it would land AFTER the
        reply, and a real reply would be scored as a non-reply."""
        result = run([msg("a", Q, 0.0, synced=8 * HOUR), msg("b", P, 1.0)],
                     mode=Mode.QUALIFICATION, consent=True)
        trace = ex.qualification_trace(result)
        self.assertEqual(trace[0]["opened_at"], 0.0)
        self.assertEqual(trace[0]["reply_id"], "b")
        self.assertEqual(horizon(result, 6.0).replied_within, 1)

    def test_a_deleted_message_is_dropped_and_counted(self):
        result = run([msg("a", Q, 0.0), msg("x", P, 0.5, deleted=True), msg("b", P, 2.0)])
        self.assertEqual(result.aggregate.deleted_dropped, 1)
        self.assertEqual(horizon(result, 6.0).sum_min_latency_seconds, 2 * HOUR)

    def test_a_deleted_reply_looks_like_a_non_reply_and_that_is_why_we_count_them(self):
        result = run([msg("a", Q, 0.0), msg("x", P, 0.5, deleted=True)])
        self.assertEqual(horizon(result, 6.0).replied_within, 0)
        self.assertEqual(horizon(result, 6.0).sum_min_latency_seconds, 6 * HOUR)
        self.assertEqual(result.aggregate.deleted_dropped, 1)


class LeftBoundaryTests(unittest.TestCase):
    """Topology is built on the full stream; the period selects, it does not cut.

    Cutting first invents a hand-over at the left edge and loses a return across
    it. Both are pinned here because both are invisible in mid-stream fixtures.
    """

    def test_a_partner_run_crossing_the_left_edge_does_not_open_a_new_opportunity(self):
        """A at -1h hands the ball over; B at +1h merely continues that run.
        Cut the stream at 0 first and B becomes index 0 — a phantom hand-over."""
        result = run([
            msg("A", Q, -1.0), msg("B", Q, 1.0), msg("C", P, 2.0),
        ], start=0.0, end=100 * HOUR, mode=Mode.QUALIFICATION, consent=True)
        self.assertEqual(ex.qualification_trace(result), [])
        self.assertEqual(horizon(result, 6.0).opportunities_eligible, 0)

    def test_a_genuine_hand_over_inside_the_period_still_counts(self):
        result = run([
            msg("A", Q, -1.0), msg("B", P, 0.5), msg("C", Q, 1.0), msg("D", P, 2.0),
        ], start=0.0, end=100 * HOUR, mode=Mode.QUALIFICATION, consent=True)
        trace = ex.qualification_trace(result)
        self.assertEqual([t["opener_id"] for t in trace], ["C"])
        self.assertEqual(horizon(result, 6.0).sum_min_latency_seconds, HOUR)

    def test_an_opportunity_opened_before_the_period_belongs_to_no_period_here(self):
        result = run([msg("A", Q, -1.0), msg("B", P, 2.0)], start=0.0, end=100 * HOUR)
        self.assertEqual(horizon(result, 6.0).opportunities_eligible, 0)
        self.assertEqual(result.aggregate.own_messages.count, 1)

    def test_a_return_across_the_left_edge_survives(self):
        """Last message five hours before the period; the participant comes back
        inside it. Cut first and the predecessor is gone, so the return vanishes."""
        result = run([msg("A", Q, -5.0), msg("B", P, 1.0)], start=0.0, end=100 * HOUR)
        self.assertEqual(result.aggregate.own_episode_returns, 1)

    def test_a_participant_message_with_no_predecessor_at_all_is_not_a_return(self):
        result = run([msg("B", P, 1.0)], start=0.0, end=100 * HOUR)
        self.assertEqual(result.aggregate.own_episode_returns, 0)

    def test_a_return_outside_the_period_is_not_counted(self):
        """Judged against the full stream, counted only inside the period."""
        result = run([
            msg("A", Q, -5.0), msg("B", P, 1.0),      # return, inside  -> counts
            msg("C", P, 500.0),                        # return, outside -> does not
        ], start=0.0, end=100 * HOUR)
        self.assertEqual(result.aggregate.own_episode_returns, 1)


class DuplicateConflictTests(unittest.TestCase):
    """One message_id, two copies, disagreeing on something that cannot change."""

    def test_disagreeing_actors_fail_closed(self):
        with self.assertRaises(ex.DuplicateConflict):
            run([msg("a", Q, 1.0, chars=12, device="phone"),
                 msg("a", P, 0.9, chars=12, device="laptop")])

    def test_disagreeing_char_counts_fail_closed(self):
        with self.assertRaises(ex.DuplicateConflict):
            run([msg("a", Q, 1.0, chars=12, device="phone"),
                 msg("a", Q, 0.9, chars=80, device="laptop")])

    def test_the_refusal_does_not_depend_on_input_order(self):
        copies = [msg("a", Q, 1.0, chars=12, device="phone"),
                  msg("a", P, 0.9, chars=80, device="laptop")]
        for stream in (copies, list(reversed(copies))):
            with self.assertRaises(ex.DuplicateConflict):
                run(stream)

    def test_present_versus_deleted_fails_closed_in_either_order(self):
        """One phone says the message is there, the other says it was deleted.

        Dropping deleted copies before the conflict check made this the single
        disagreement resolved silently — always in favour of present — while a
        changed author already failed closed. Both permutations are asserted
        because the old code reached the same silent answer along two different
        paths.
        """
        copies = [msg("a", Q, 1.0, device="phone", deleted=False),
                  msg("a", Q, 1.0, device="laptop", deleted=True)]
        for stream in (copies, list(reversed(copies))):
            with self.assertRaises(ex.DeletionStateConflict):
                run(stream)
            with self.assertRaises(ex.DuplicateConflict):   # same failure family
                run(stream)

    def test_two_copies_that_agree_they_are_deleted_are_not_a_conflict(self):
        result = run([msg("a", Q, 1.0, device="phone", deleted=True),
                      msg("a", Q, 1.0, device="laptop", deleted=True),
                      msg("b", Q, 2.0), msg("c", P, 3.0)])
        self.assertEqual(result.aggregate.deleted_dropped, 1)    # distinct ids
        self.assertEqual(result.aggregate.duplicates_dropped, 1)  # repeat sightings
        self.assertEqual(horizon(result, 6.0).opportunities_eligible, 1)

    def test_a_clock_disagreement_alone_is_resolved_not_refused(self):
        """Two phones disagreeing about when is plausible; earliest wins."""
        result = run([msg("a", Q, 1.0, chars=12, device="phone"),
                      msg("a", Q, 0.5, chars=12, device="laptop"),
                      msg("b", P, 2.0)])
        self.assertEqual(result.aggregate.duplicates_dropped, 1)
        self.assertEqual(horizon(result, 6.0).sum_min_latency_seconds, 1.5 * HOUR)


class DeletionContractTests(unittest.TestCase):
    def test_the_extractor_reconstructs_current_state_not_frozen_history(self):
        """Named honestly: recomputing an old period after a reply is deleted
        turns `replied` into `non-replied`. Stability after a period closes is
        persistence's job, not this extractor's."""
        before = run([msg("a", Q, 0.0), msg("b", P, 1.0)])
        after = run([msg("a", Q, 0.0), msg("b", P, 1.0, deleted=True)])
        self.assertEqual(horizon(before, 6.0).replied_within, 1)
        self.assertEqual(horizon(after, 6.0).replied_within, 0)
        self.assertEqual(after.aggregate.deleted_dropped, 1)


class PeriodBoundaryTests(unittest.TestCase):
    def test_messages_outside_the_period_are_dropped(self):
        """`before` is the PARTICIPANT's, so `a` is a genuine hand-over inside
        the period. Making it the partner's would merely continue a run that
        opened earlier — see LeftBoundaryTests."""
        result = run([
            msg("before", P, -5.0), msg("a", Q, 1.0), msg("b", P, 2.0),
            msg("after", P, 200.0),
        ], start=0.0, end=100 * HOUR)
        self.assertEqual(result.aggregate.own_messages.count, 1)
        self.assertEqual(horizon(result, 6.0).opportunities_eligible, 1)
        self.assertEqual(horizon(result, 6.0).sum_min_latency_seconds, HOUR)

    def test_the_period_is_half_open(self):
        """[start, end). The opportunity path cannot see this — a message at
        exactly `end` is calendar-censored for every H anyway — so it is pinned
        on the participant's own message count, which can."""
        at_end = run([msg("edge", P, 10.0)], start=0.0, end=10 * HOUR)
        self.assertEqual(at_end.aggregate.own_messages.count, 0)
        at_start = run([msg("edge", P, 0.0)], start=0.0, end=10 * HOUR)
        self.assertEqual(at_start.aggregate.own_messages.count, 1)
        just_inside = run([msg("edge", P, 9.99)], start=0.0, end=10 * HOUR)
        self.assertEqual(just_inside.aggregate.own_messages.count, 1)


class OwnSideTests(unittest.TestCase):
    def test_own_length_summary_counts_only_the_participant(self):
        result = run([msg("a", Q, 0.0, chars=500), msg("b", P, 1.0, chars=7),
                      msg("c", Q, 2.0, chars=500), msg("d", P, 3.0, chars=13)])
        self.assertEqual(result.aggregate.own_messages.count, 2)
        self.assertEqual(result.aggregate.own_messages.total_chars, 20)
        self.assertEqual(result.aggregate.own_messages.mean_chars, 10.0)

    def test_episode_returns_need_a_real_gap(self):
        gap = EPISODE_GAP_SECONDS / HOUR
        result = run([msg("a", Q, 0.0), msg("b", P, 0.1),
                      msg("c", Q, 5.0), msg("d", P, 5.0 + gap)])
        self.assertEqual(result.aggregate.own_episode_returns, 1)


class ExportBoundaryTests(unittest.TestCase):
    """What leaves the device, and what provably cannot."""

    def test_the_production_export_carries_aggregates_and_nothing_else(self):
        result = run([msg("a", Q, 0.0), msg("b", P, 1.0), msg("c", Q, 2.0)])
        payload = ex.production_export(result.aggregate)
        self.assertEqual(set(payload), set(ex.EXPORT_KEYS))
        for entry in payload["horizons"]:
            self.assertEqual(set(entry), set(ex.EXPORT_HORIZON_KEYS))

    def test_the_partner_scoped_diagnostics_are_pinned_as_an_open_question(self):
        """deleted_dropped / duplicates_dropped / max_sync_lag cover the whole
        input stream, so in single-enrolled mode they partly describe the
        partner's device. Useful now, to be decided before the variance pilot;
        pinned so that decision is a field removal, not an act of memory."""
        result = run([msg("a", Q, 0.0), msg("b", P, 1.0)])
        payload = ex.production_export(result.aggregate)
        self.assertTrue(ex.PARTNER_SCOPED_DIAGNOSTIC_KEYS <= set(payload))
        self.assertEqual(ex.PARTNER_SCOPED_DIAGNOSTIC_KEYS,
                         {"deleted_dropped", "duplicates_dropped", "max_sync_lag_seconds"})

    def test_no_opportunity_identifier_or_open_time_reaches_the_export(self):
        result = run([msg("a", Q, 0.0), msg("b", P, 1.0)])
        payload = repr(ex.production_export(result.aggregate))
        for leak in ("opener", "opened_at", "reply_id", "reply_at", "message_id", "device"):
            self.assertNotIn(leak, payload)

    def test_production_never_builds_a_trace(self):
        result = run([msg("a", Q, 0.0), msg("b", P, 1.0)])
        self.assertIsNone(result._trace)
        with self.assertRaises(PermissionError):
            result.export_trace()

    def test_qualification_without_consent_refuses(self):
        result = run([msg("a", Q, 0.0)], mode=Mode.QUALIFICATION, consent=False)
        with self.assertRaises(PermissionError):
            ex.qualification_trace(result)

    def test_qualification_with_consent_yields_the_per_opportunity_rows(self):
        result = run([msg("a", Q, 0.0), msg("b", P, 1.0)],
                     mode=Mode.QUALIFICATION, consent=True)
        self.assertEqual(ex.qualification_trace(result), [{
            "opener_id": "a", "opened_at": 0.0,
            "reply_id": "b", "reply_at": HOUR, "latency_seconds": HOUR,
            "run_span_seconds": 0.0, "reply_speed_seconds": HOUR,
            "run_message_count": 1,
        }])

    def test_no_type_in_the_package_can_hold_message_text(self):
        from extractor import model

        forbidden = {"text", "body", "content", "message_text", "message", "snippet"}
        for name in dir(model):
            attribute = getattr(model, name)
            if not dataclasses.is_dataclass(attribute):
                continue
            fields = {f.name for f in dataclasses.fields(attribute)}
            self.assertEqual(fields & forbidden, set(), f"{name} can hold text")

    def test_group_chats_are_out_of_scope_rather_than_silently_wrong(self):
        with self.assertRaises(ValueError):
            run([msg("a", Q, 0.0), msg("b", "third", 1.0), msg("c", P, 2.0)])


class ResultShapeTests(unittest.TestCase):
    def test_mode_is_part_of_the_result_not_a_forgotten_flag(self):
        result = run([msg("a", Q, 0.0)])
        self.assertIsInstance(result, ExtractionResult)
        self.assertIs(result.mode, Mode.PRODUCTION)


if __name__ == "__main__":
    unittest.main()
