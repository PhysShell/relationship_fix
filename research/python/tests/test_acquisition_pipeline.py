"""Instrumentation qualification: the path around the frozen extractor.

Not "does the engine compute correctly" — 109 mutants answered that. These ask
whether the right data reaches it and whether only allowed data leaves.
"""

import dataclasses
import io
import json
import logging
import traceback
import unittest

from acquisition.model import Layer, ProducerProvenance, ProtocolWindow, Verdict
from acquisition.pipeline import run

HOUR = 3600.0
A, B = "user111", "user222"
WINDOW = ProtocolWindow(participant_id=A, period_id="w1", start=0.0, end=7 * 24 * HOUR)
PRODUCER = ProducerProvenance(application="Telegram Desktop", version="6.7.8",
                              platform="linux", consent_recorded=True)

#: Markers, so a privacy claim is checked rather than trusted.
SECRET_TEXT = "SUPER_SECRET_TEXT_918273"
SECRET_NAME = "PRIVATE_PERSON_NAME_918273"
SECRET_MEDIA = "/media/embarrassing-photo.jpg"


def message(mid, at_hours, sender, kind="message", text=SECRET_TEXT, **extra):
    entry = {
        "id": mid, "type": kind,
        "date": "2026-03-19T07:28:54",          # wall clock; must never be parsed
        "date_unixtime": str(int(at_hours * HOUR)),
        "from": SECRET_NAME, "from_id": sender,
        "text": text, "file": SECRET_MEDIA,
    }
    entry.update(extra)
    return entry


def export(messages, chat_type="personal_chat") -> bytes:
    return json.dumps({"name": SECRET_NAME, "type": chat_type, "id": 4941999364,
                       "messages": messages}).encode("utf-8")


#: One partner run at 1h answered at 2h; a second at 5h answered at 6h.
HAPPY = export([
    message(101, 1.0, B), message(102, 1.05, B),
    message(103, 2.0, A),
    message(104, 5.0, B),
    message(105, 6.0, A),
])


class HappyPathTests(unittest.TestCase):
    """The numbers AND the envelope. A pipeline that gets the burden right and
    loses the provenance has not qualified."""

    def setUp(self):
        self.result = run(HAPPY, WINDOW, PRODUCER)

    def test_the_verdict_is_accepted_and_carries_measurements(self):
        self.assertIs(self.result.verdict, Verdict.ACCEPTED)
        self.assertTrue(self.result.verdict.carries_measurements)
        self.assertIsNotNone(self.result.aggregate)

    def test_the_expected_sufficient_statistics_arrive_intact(self):
        cell = next(h for h in self.result.aggregate["horizons"] if h["horizon_hours"] == 6.0)
        self.assertEqual(cell["opportunities_eligible"], 2)
        self.assertEqual(cell["replied_within"], 2)
        self.assertEqual(cell["sum_min_latency_seconds"], 2 * HOUR)   # 1h + 1h
        self.assertEqual(cell["sum_run_messages"], 3)                 # 2 + 1

    def test_the_protocol_window_travels_unchanged(self):
        """Not re-derived from the file: the earliest message is at 1 h and the
        window starts at 0."""
        self.assertEqual(self.result.aggregate["observation_window_seconds"], 7 * 24 * HOUR)
        self.assertEqual(self.result.window, WINDOW)

    def test_provenance_survives_the_whole_path(self):
        self.assertEqual(self.result.producer.version, "6.7.8")
        self.assertEqual(self.result.source_type, "personal_chat")

    def test_the_source_cannot_report_deletions_and_says_so(self):
        """`deleted_dropped = 0` must travel with the reason, or the zero reads
        as "no deletions happened"."""
        self.assertEqual(self.result.aggregate["deleted_dropped"], 0)
        self.assertIn("deletions_unobservable", self.result.codes())

    def test_tie_counters_reach_the_outside(self):
        self.assertIn("cross_actor_tie_groups", self.result.aggregate)
        self.assertIn("ambiguous_opportunities", self.result.aggregate)
        self.assertEqual(self.result.aggregate["cross_actor_tie_groups"], 0)

    def test_a_cross_actor_tie_is_visible_end_to_end(self):
        tied = export([message(201, 1.0, B), message(202, 1.0, A),
                       message(203, 5.0, B), message(204, 6.0, A)])
        result = run(tied, WINDOW, PRODUCER)
        self.assertEqual(result.aggregate["cross_actor_tie_groups"], 1)
        self.assertEqual(result.aggregate["ambiguous_opportunities"], 1)

    def test_service_entries_are_excluded_and_counted(self):
        with_service = export([message(101, 1.0, B, kind="service", actor=B),
                               message(102, 2.0, B), message(103, 3.0, A)])
        result = run(with_service, WINDOW, PRODUCER)
        self.assertIn("service_entries_excluded", result.codes())
        cell = next(h for h in result.aggregate["horizons"] if h["horizon_hours"] == 6.0)
        self.assertEqual(cell["opportunities_eligible"], 1)


class FailureInjectionTests(unittest.TestCase):
    """Each one must be caught by the right layer, and none may come out as a
    measurement of zero."""

    def assert_refused(self, raw, code, layer, window=WINDOW, producer=PRODUCER):
        result = run(raw, window, producer)
        self.assertIs(result.verdict, Verdict.REFUSED, code)
        self.assertIsNone(result.aggregate, "a refusal must not carry numbers")
        self.assertIn(code, result.codes())
        self.assertEqual(result.findings[-1].layer, layer)
        return result

    def test_invalid_json(self):
        self.assert_refused(b'{"type": "personal_chat", "messages": [{"t": "a\\x01b"}]}',
                            "invalid_json", Layer.IMPORT)

    def test_truncated_file(self):
        self.assert_refused(HAPPY[: len(HAPPY) // 2], "invalid_json", Layer.IMPORT)

    def test_missing_date_unixtime_everywhere_leaves_nothing_usable(self):
        stripped = json.loads(HAPPY)
        for entry in stripped["messages"]:
            entry.pop("date_unixtime")
        self.assert_refused(json.dumps(stripped).encode(), "no_usable_messages", Layer.ADAPTER)

    def test_missing_producer_provenance(self):
        result = run(HAPPY, WINDOW, None)
        self.assertIs(result.verdict, Verdict.REFUSED)
        self.assertIn("missing_producer_provenance", result.codes())
        self.assertIsNone(result.aggregate)

    def test_consent_not_recorded(self):
        without = dataclasses.replace(PRODUCER, consent_recorded=False)
        self.assertIs(run(HAPPY, WINDOW, without).verdict, Verdict.REFUSED)

    def test_window_outside_the_export(self):
        elsewhere = ProtocolWindow(participant_id=A, period_id="w9",
                                   start=365 * 24 * HOUR, end=372 * 24 * HOUR)
        self.assert_refused(HAPPY, "window_outside_export", Layer.QUALIFICATION,
                            window=elsewhere)

    def test_the_participant_is_not_in_the_export(self):
        """Otherwise extraction succeeds and reports a person who did nothing —
        a wrong answer in the clothes of a right one."""
        stranger = ProtocolWindow(participant_id="user999", period_id="w1",
                                  start=0.0, end=7 * 24 * HOUR)
        self.assert_refused(HAPPY, "participant_absent_from_export", Layer.QUALIFICATION,
                            window=stranger)

    def test_an_unexpected_schema_shape_is_refused_not_guessed(self):
        self.assert_refused(b'{"type": "personal_chat", "messages": [42]}',
                            "malformed_entry", Layer.ADAPTER)

    def test_a_missing_actor_is_refused(self):
        entry = message(101, 1.0, B)
        entry.pop("from_id")
        self.assert_refused(export([entry]), "no_actor", Layer.ADAPTER)

    def test_the_wrong_chat_type_is_out_of_scope_not_refused(self):
        """The file is fine; it is simply not a dyad. Three public exports in a
        row were private_group, bot_chat and saved_messages."""
        for kind in ("private_group", "bot_chat", "saved_messages"):
            result = run(export(json.loads(HAPPY)["messages"], chat_type=kind),
                         WINDOW, PRODUCER)
            self.assertIs(result.verdict, Verdict.OUT_OF_SCOPE, kind)
            self.assertIsNone(result.aggregate)
            self.assertIn("not_the_target_chat_type", result.codes())

    def test_three_senders_are_out_of_scope_before_the_extractor_is_called(self):
        crowd = export([message(101, 1.0, B), message(102, 2.0, A),
                        message(103, 3.0, "user333")])
        result = run(crowd, WINDOW, PRODUCER)
        self.assertIs(result.verdict, Verdict.OUT_OF_SCOPE)
        self.assertIn("not_a_dyad", result.codes())

    def test_a_suspicious_round_count_downgrades_to_incomplete_not_accepted(self):
        """Silent truncation at exactly 10000 is documented. Measurements are
        still produced — and marked."""
        many = [message(1000 + i, 1.0 + i * 0.01, B if i % 2 else A) for i in range(10000)]
        result = run(export(many), WINDOW, PRODUCER)
        self.assertIs(result.verdict, Verdict.INCOMPLETE)
        self.assertIsNotNone(result.aggregate)
        self.assertIn("suspicious_round_count", result.codes())

    def test_no_failure_path_ever_produces_an_empty_measurement(self):
        """The property the whole module exists for: REFUSED stays REFUSED."""
        broken = [b"{", b'{"type": "personal_chat"}', b"[]", b'{"messages": []}',
                  HAPPY[:40], b'{"type": "personal_chat", "messages": []}']
        for raw in broken:
            result = run(raw, WINDOW, PRODUCER)
            self.assertFalse(result.verdict.carries_measurements, raw[:20])
            self.assertIsNone(result.aggregate, raw[:20])


class PrivacyBoundaryTests(unittest.TestCase):
    """Upstream holds the whole conversation. Downstream must hold none of it."""

    MARKERS = (SECRET_TEXT, SECRET_NAME, SECRET_MEDIA, "4941999364")

    def haystack(self, result) -> str:
        return json.dumps(dataclasses.asdict(result), default=str)

    def test_no_marker_survives_an_accepted_run(self):
        result = run(HAPPY, WINDOW, PRODUCER)
        text = self.haystack(result)
        for marker in self.MARKERS:
            self.assertNotIn(marker, text, marker)

    def test_no_marker_survives_a_refusal_either(self):
        """Refusal paths are where content usually escapes: an exception
        message quotes the offending bytes and someone logs it."""
        poisoned = b'{"type": "personal_chat", "messages": [{"text": "' \
                   + SECRET_TEXT.encode() + b'\\x01"}]}'
        result = run(poisoned, WINDOW, PRODUCER)
        self.assertIs(result.verdict, Verdict.REFUSED)
        self.assertNotIn(SECRET_TEXT, self.haystack(result))

    def test_nothing_leaks_through_logs_or_tracebacks(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        try:
            run(HAPPY, WINDOW, PRODUCER)
            run(b'{"type": "personal_chat", "messages": [{"x": "' + SECRET_TEXT.encode()
                + b'\\x01"}]}', WINDOW, PRODUCER)
            captured = stream.getvalue() + "".join(traceback.format_stack())
        finally:
            logging.getLogger().removeHandler(handler)
        for marker in self.MARKERS:
            self.assertNotIn(marker, captured, marker)

    def test_the_outward_payload_is_exactly_the_allowlist(self):
        from extractor.extract import EXPORT_KEYS
        result = run(HAPPY, WINDOW, PRODUCER)
        self.assertEqual(set(result.aggregate), set(EXPORT_KEYS))

    def test_the_date_string_is_never_parsed(self):
        """Every fixture message carries a wall-clock `date` five hours from its
        `date_unixtime`. If anything parsed it, the latencies would move."""
        shifted = json.loads(HAPPY)
        for entry in shifted["messages"]:
            entry["date"] = "1999-01-01T00:00:00"
        result = run(json.dumps(shifted).encode(), WINDOW, PRODUCER)
        self.assertEqual(result.aggregate, run(HAPPY, WINDOW, PRODUCER).aggregate)


class DeterminismTests(unittest.TestCase):
    def test_three_runs_of_one_artifact_agree_byte_for_byte(self):
        payloads = {json.dumps(run(HAPPY, WINDOW, PRODUCER).aggregate, sort_keys=True)
                    for _ in range(3)}
        self.assertEqual(len(payloads), 1)

    def test_the_scientific_payload_carries_no_clock_or_run_id(self):
        """Instrumentation metadata is deliberately absent from the result type,
        so determinism is structural rather than a habit."""
        fields = set(run(HAPPY, WINDOW, PRODUCER).aggregate)
        for forbidden in ("run_id", "generated_at", "timestamp", "hostname"):
            self.assertNotIn(forbidden, fields)


class SeamContractTests(unittest.TestCase):
    """Written to kill surviving mutants on the path, not to look thorough.
    Each corresponds to a flipped operator the suite failed to notice."""

    def test_a_message_exactly_at_the_window_start_counts_as_overlap(self):
        """The only in-window message sits exactly on the start. With `<`
        instead of `<=` the period would be declared uncovered — and a later
        message elsewhere in the file would hide the bug, which is why the
        fixture leaves nothing else inside."""
        window = ProtocolWindow(participant_id=A, period_id="w2",
                                start=24 * HOUR, end=48 * HOUR)
        edge_only = export([message(101, 24.0, B), message(102, 50.0, A)])
        self.assertIsNot(run(edge_only, window, PRODUCER).verdict, Verdict.REFUSED)

    def test_the_window_length_is_end_minus_start(self):
        """Every other fixture starts at 0, where subtraction and addition
        agree. Periods do not start at 0 — the same trap as in the extractor."""
        window = ProtocolWindow(participant_id=A, period_id="w3",
                                start=24 * HOUR, end=48 * HOUR)
        self.assertEqual(window.seconds, 24 * HOUR)

    def test_a_message_exactly_at_the_window_end_does_not_count_as_overlap(self):
        """`t < end`, not `<=`. Otherwise a period is "covered" by a message
        that belongs to the next one."""
        past_edge = export([message(101, 7 * 24.0, B), message(102, 7 * 24.0 + 1, A)])
        result = run(past_edge, WINDOW, PRODUCER)
        self.assertIs(result.verdict, Verdict.REFUSED)
        self.assertIn("window_outside_export", result.codes())

    def test_the_earliest_message_at_the_window_edge_raises_suspicion(self):
        """`coverage.completeness` is UNAVAILABLE: an export whose first
        message coincides with the window start may have been truncated there
        rather than started there. Measured, flagged, not resolved."""
        flush = export([message(101, 0.0, B), message(102, 1.0, A)])
        self.assertIn("starts_at_window_edge", run(flush, WINDOW, PRODUCER).codes())
        later = export([message(101, 1.0, B), message(102, 2.0, A)])
        self.assertNotIn("starts_at_window_edge", run(later, WINDOW, PRODUCER).codes())

    def test_suspicion_looks_at_the_earliest_message_not_the_latest(self):
        """`min`, not `max`: a late message says nothing about the left edge."""
        late_only = export([message(101, 100.0, B), message(102, 101.0, A)])
        self.assertNotIn("starts_at_window_edge", run(late_only, WINDOW, PRODUCER).codes())

    def test_an_id_below_the_supported_range_is_refused_not_wrapped(self):
        from acquisition.telegram import ID_OFFSET, encode_message_id
        encode_message_id(-ID_OFFSET)                       # the exact floor is fine
        with self.assertRaises(ValueError):
            encode_message_id(-ID_OFFSET - 1)

    def test_entity_text_contributes_its_length(self):
        """`events.media_only` is PARTIAL: `text` may be a list of entity
        objects, and a declared policy beats a silent zero."""
        entities = export([
            message(101, 1.0, B),
            message(102, 2.0, A, text=["plain ", {"type": "bold", "text": "bold"}, 8]),
        ])
        result = run(entities, WINDOW, PRODUCER)
        self.assertEqual(result.aggregate["own_total_chars"], len("plain ") + len("bold"))

    def test_media_without_a_caption_is_zero_characters_not_a_crash(self):
        media = export([message(101, 1.0, B), message(102, 2.0, A, text=None)])
        self.assertEqual(run(media, WINDOW, PRODUCER).aggregate["own_total_chars"], 0)


class OutwardShapeTests(unittest.TestCase):
    """The path's own types carry the privacy contract, so they are frozen and
    slotted for the same reason the extractor's are: nothing can be stapled on
    later, and nothing can be edited after the verdict."""

    def test_path_types_are_frozen_and_slotted(self):
        result = run(HAPPY, WINDOW, PRODUCER)
        for obj in (result, result.window, result.producer, result.findings[0]):
            self.assertFalse(hasattr(obj, "__dict__"), type(obj).__name__)
            field = next(iter(obj.__dataclass_fields__))
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(obj, field, getattr(obj, field))
        with self.assertRaises((AttributeError, TypeError)):
            setattr(result, "message_text", SECRET_TEXT)

    def test_a_refusal_carrying_numbers_cannot_be_constructed(self):
        """The invariant stated as a type, not as a convention."""
        from acquisition.model import OutwardResult
        with self.assertRaises(ValueError):
            OutwardResult(verdict=Verdict.REFUSED, window=WINDOW, producer=PRODUCER,
                          source_type=None, aggregate={"anything": 1})
        with self.assertRaises(ValueError):
            OutwardResult(verdict=Verdict.ACCEPTED, window=WINDOW, producer=PRODUCER,
                          source_type=None, aggregate=None)

    def test_a_window_must_have_positive_length(self):
        from acquisition.model import ProtocolWindow as W
        with self.assertRaises(ValueError):
            W(participant_id=A, period_id="w", start=10.0, end=10.0)

    def test_producer_provenance_refuses_blank_fields(self):
        from acquisition.model import ProducerProvenance as P
        for blank in ("application", "version", "platform"):
            with self.assertRaises(ValueError):
                P(**{**{"application": "a", "version": "v", "platform": "p",
                        "consent_recorded": True}, blank: ""})


if __name__ == "__main__":
    unittest.main()
