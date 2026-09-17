"""The scanner's own fixtures, including the two invalid-output classes that
tdesktop is known to produce.

Synthetic throughout: a test that needs someone's real conversation to pass is
a test that cannot run.
"""

import dataclasses
import json
import unittest

from tools.export_scan import Inversion, ScanResult, scan_bytes

CHAT = "Personal chat"


def export(messages, wrap="single", chat_type=None) -> bytes:
    chat = {"name": "n", "type": chat_type or CHAT, "id": 1, "messages": messages}
    document = chat if wrap == "single" else {"chats": {"list": [chat]}}
    return json.dumps(document).encode("utf-8")


def msg(mid, at, kind="message", sender=None):
    entry = {"id": mid, "type": kind, "date": "x", "date_unixtime": str(at)}
    if sender is not None:
        entry["from_id"] = sender
    return entry


class ShapeTests(unittest.TestCase):
    def test_both_export_shapes_are_found(self):
        for wrap in ("single", "full"):
            got = scan_bytes(export([msg(1, 100), msg(2, 200)], wrap), "s")
            self.assertEqual(got.entries, 2, wrap)

    def test_service_entries_are_counted_apart_from_messages(self):
        got = scan_bytes(export([msg(1, 100), msg(2, 200, "service"),
                                 msg(3, 300, "pinned?")]), "s")
        self.assertEqual((got.messages, got.service, got.other_types), (1, 1, 1))


class StrictParsingTests(unittest.TestCase):
    """Both known classes of invalid output, reproduced as bytes."""

    def test_the_backslash_x_escape_is_rejected(self):
        """tdesktop#27571 (4.15.1, closed as not planned): `\\x01` inside a
        string. jq: "parse error: Invalid escape". Python agrees."""
        raw = b'{"messages": [{"id": 1, "data": "1=412\\x012=97180"}]}'
        got = scan_bytes(raw, "s")
        self.assertFalse(got.strict_json_valid)
        self.assertEqual(got.entries, 0)
        self.assertIn("REFUSED", got.verdict)

    def test_an_unquoted_value_is_rejected(self):
        """tdesktop#24961 (4.1.1): custom emoji produced a bare, unquoted
        value where JSON requires a string."""
        raw = b'{"messages": [{"id": 1, "document_id": video_files/sticker (2).webm}]}'
        self.assertFalse(scan_bytes(raw, "s").strict_json_valid)

    def test_nan_and_infinity_are_refused_too(self):
        """The standard library accepts these by default; JSON does not."""
        self.assertFalse(scan_bytes(b'{"messages": [{"id": NaN}]}', "s").strict_json_valid)

    def test_the_parse_error_carries_no_file_content(self):
        """A parser message can quote the offending bytes; the scan keeps the
        position only. Evidence must not smuggle the data it is evidence about."""
        raw = b'{"messages": [{"text": "secret plans\\x01more secrets"}]}'
        got = scan_bytes(raw, "s")
        self.assertNotIn("secret", got.parse_error or "")


class ChronologyTests(unittest.TestCase):
    """The decisive question: does ascending id mean ascending time?"""

    def test_a_clean_export_reports_no_inversion_and_claims_nothing_more(self):
        got = scan_bytes(export([msg(217558, 1000), msg(217581, 2000),
                                 msg(217623, 3000)]), "s")
        self.assertEqual(got.chronology_counterexamples, 0)
        self.assertIn("no inversion observed", got.verdict)
        self.assertNotIn("QUALIFIED", got.verdict)

    def test_one_pair_with_id_up_and_time_down_refutes_it(self):
        """And it need not be inside a second — hours apart is stronger."""
        got = scan_bytes(export([msg(10, 90000), msg(11, 1000)]), "s")
        self.assertEqual(got.chronology_counterexamples, 1)
        self.assertEqual(got.samples[0], Inversion(1, 10, 90000, 11, 1000))
        self.assertIn("REFUTED", got.verdict)

    def test_equal_timestamps_are_counted_but_are_not_counterexamples(self):
        got = scan_bytes(export([msg(1, 500), msg(2, 500)]), "s")
        self.assertEqual(got.equal_timestamp_pairs, 1)
        self.assertEqual(got.chronology_counterexamples, 0)

    def test_id_going_backwards_is_an_id_inversion_not_a_chronology_one(self):
        got = scan_bytes(export([msg(5, 100), msg(4, 200)]), "s")
        self.assertEqual(got.adjacent_id_inversions, 1)
        self.assertEqual(got.chronology_counterexamples, 0)

    def test_samples_are_capped_while_the_count_is_not(self):
        pairs = []
        for i in range(60):
            pairs += [msg(2 * i + 1, 100000 + i), msg(2 * i + 2, 1)]
        got = scan_bytes(export(pairs), "s")
        self.assertGreater(got.chronology_counterexamples, 20)
        self.assertEqual(len(got.samples), 20)


class ChatTypeAndSenderTests(unittest.TestCase):
    """Type is a category, not a name — and it decides what a scan qualifies."""

    def test_the_chat_type_is_reported(self):
        got = scan_bytes(export([msg(1, 1)], chat_type="private_group"), "s")
        self.assertEqual(got.chat_types, ("private_group",))

    def test_a_same_actor_tie_is_not_a_cross_actor_tie(self):
        """Only a cross-actor tie can change how many times the ball changed
        hands; a same-actor one cannot move topology at all."""
        got = scan_bytes(export([msg(1, 500, sender="user1"),
                                 msg(2, 500, sender="user1")]), "s")
        self.assertEqual(got.equal_timestamp_pairs, 1)
        self.assertEqual(got.equal_timestamp_cross_actor_pairs, 0)

    def test_a_cross_actor_tie_is_counted_separately(self):
        got = scan_bytes(export([msg(1, 500, sender="user1"),
                                 msg(2, 500, sender="user2")]), "s")
        self.assertEqual(got.equal_timestamp_cross_actor_pairs, 1)
        self.assertEqual(got.distinct_senders, 2)

    def test_senders_are_counted_and_not_kept(self):
        messages = [msg(i, 100 * i, sender=f"user{i}") for i in range(1, 4)]
        got = scan_bytes(export(messages), "s")
        self.assertEqual(got.distinct_senders, 3)
        self.assertNotIn("user1", json.dumps(dataclasses.asdict(got)))


class IdAccountingTests(unittest.TestCase):
    def test_negative_ids_are_counted_as_migrated_history(self):
        got = scan_bytes(export([msg(-999999999, 100), msg(5, 200)]), "s")
        self.assertEqual(got.negative_ids, 1)

    def test_duplicate_ids_are_counted(self):
        got = scan_bytes(export([msg(7, 100), msg(7, 200)]), "s")
        self.assertEqual(got.duplicate_ids, 1)

    def test_a_missing_timestamp_is_counted_and_breaks_no_comparison(self):
        got = scan_bytes(export([msg(1, 100), {"id": 2, "type": "message"},
                                 msg(3, 50)]), "s")
        self.assertEqual(got.missing_date_unixtime, 1)
        self.assertEqual(got.chronology_counterexamples, 1)   # 1 vs 3, across the gap

    def test_an_unparsable_id_is_counted_rather_than_guessed(self):
        got = scan_bytes(export([{"id": "abc", "type": "message",
                                  "date_unixtime": "100"}]), "s")
        self.assertEqual(got.unparsable_ids, 1)


class PrivacyShapeTests(unittest.TestCase):
    """The result type must not be able to carry the thing it was reading."""

    FORBIDDEN = {"text", "text_entities", "from", "from_id", "actor", "name",
                 "photo", "file", "reactions", "reply_to_message_id", "chat_id"}

    def test_no_result_field_can_hold_message_content(self):
        fields = set(ScanResult.__dataclass_fields__)
        self.assertEqual(fields & self.FORBIDDEN, set())
        self.assertEqual(set(Inversion.__dataclass_fields__) & self.FORBIDDEN, set())

    def test_a_scan_of_a_chat_full_of_text_retains_none_of_it(self):
        messages = [dict(msg(i, 100 * i), text=f"very private thing {i}",
                         **{"from": "Alice", "from_id": "user1"}) for i in range(1, 6)]
        got = scan_bytes(export(messages), "s")
        rendered = json.dumps(dataclasses.asdict(got))
        self.assertNotIn("private", rendered)
        self.assertNotIn("Alice", rendered)
        self.assertNotIn("user1", rendered)
        self.assertEqual(got.entries, 5)


if __name__ == "__main__":
    unittest.main()
