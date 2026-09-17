"""MaiChat adapter: source semantics are declared, never inferred.

Fixtures are inline and tiny. The corpus itself is CC BY-SA 4.0 and is not
vendored — share-alike would follow a copy into this repository — so the harness
takes a path and these tests take dictionaries shaped like the real files.
"""

import unittest

from extractor.adapters.guards import DyadMembershipError
from extractor.adapters.maichat import (
    SEMANTICS,
    AdapterProvenance,
    FailedDeliveryPolicy,
    adapt,
)
from extractor.adapters.semantics import TimestampSemantics
from extractor.model import RawMessage

A = "656d3dd6104bbd083868580d"
B = "656d3dea104bbd0838685810"


def message(mid, actor, when, content="hi", device="Desktop", failed=False):
    node = {
        "_id": {"$oid": mid},
        "ofUser": {"$oid": actor},
        "content": content,
        "deviceType": device,
        "time": {"$date": when},
        "logs": [],
    }
    if failed:
        node["deliveryStatus"] = "failed"
    return node


def conversation(*messages):
    return {
        "_id": {"$oid": "c0"},
        "firstId": {"$oid": A},
        "secondId": {"$oid": B},
        "firstUserName": "conv001_1",
        "secondUserName": "conv001_2",
        "messages": list(messages),
    }


class SemanticsTests(unittest.TestCase):
    """The reason this adapter exists at all."""

    def test_the_timestamp_semantics_are_declared_as_server_receive(self):
        """RawMessage documents a sending-device clock; MaiChat's `time` is the
        server receive time (README §7). The adapter says so rather than
        assigning one to the other."""
        _, provenance = adapt(conversation(message("m1", A, "2023-12-07T20:13:50.843Z")))
        self.assertIs(provenance.semantics.timestamp_meaning, TimestampSemantics.SERVER_RECEIVE)
        self.assertIsNot(provenance.semantics.timestamp_meaning, TimestampSemantics.SEND_LOCAL)

    def test_there_is_one_typed_truth_about_the_timestamp_not_two(self):
        """A provenance field and a semantics field could drift apart; only the
        declaration survives, so agreement is structural rather than virtuous."""
        fields = {f.name for f in AdapterProvenance.__dataclass_fields__.values()}
        self.assertNotIn("timestamp_semantics", fields)
        self.assertIn("semantics", fields)

    def test_every_reported_claim_carries_the_semantics_with_it(self):
        _, provenance = adapt(conversation(message("m1", A, "2023-12-07T20:13:50.843Z")))
        self.assertIn("server_receive", provenance.claim_prefix())
        self.assertIn("MaiChat", provenance.claim_prefix())

    def test_the_licence_travels_with_the_data(self):
        _, provenance = adapt(conversation(message("m1", A, "2023-12-07T20:13:50.843Z")))
        self.assertIn("CC BY-SA 4.0", provenance.licence)


class ParsingTests(unittest.TestCase):
    def test_extended_json_wrappers_are_unwrapped(self):
        messages, _ = adapt(conversation(
            message("m1", A, "2023-12-07T20:13:50.843Z"),
            message("m2", B, "2023-12-07T20:13:52.000Z"),
        ))
        self.assertEqual([m.message_id for m in messages], ["m1", "m2"])
        self.assertEqual([m.actor for m in messages], [A, B])
        self.assertAlmostEqual(messages[1].timestamp - messages[0].timestamp, 1.157, places=3)

    def test_millisecond_dates_are_accepted_too(self):
        messages, _ = adapt(conversation({
            "_id": {"$oid": "m1"}, "ofUser": {"$oid": A}, "content": "x",
            "deviceType": "Mobile", "time": {"$date": 1701980030843}, "logs": [],
        }))
        self.assertAlmostEqual(messages[0].timestamp, 1701980030.843, places=3)

    def test_timestamps_are_utc_so_the_offset_is_zero(self):
        messages, _ = adapt(conversation(message("m1", A, "2023-12-07T20:13:50.843Z")))
        self.assertEqual(messages[0].utc_offset_minutes, 0)
        self.assertEqual(messages[0].local_time, messages[0].timestamp)

    def test_content_becomes_a_length_and_nothing_else(self):
        messages, _ = adapt(conversation(
            message("m1", A, "2023-12-07T20:13:50.843Z", content="something private")))
        self.assertEqual(messages[0].char_count, len("something private"))
        self.assertNotIn("private", repr(messages[0]))
        self.assertEqual({f for f in RawMessage.__dataclass_fields__} & {"content", "text"}, set())

    def test_device_type_carries_over_and_missing_is_named(self):
        node = message("m1", A, "2023-12-07T20:13:50.843Z", device="Tablet")
        self.assertEqual(adapt(conversation(node))[0][0].device_id, "Tablet")
        node.pop("deviceType")
        self.assertEqual(adapt(conversation(node))[0][0].device_id, "unknown")


class FailedDeliveryTests(unittest.TestCase):
    """Whether an undelivered message took part is a question about the source."""

    def test_failed_messages_are_excluded_by_default_and_counted(self):
        messages, provenance = adapt(conversation(
            message("m1", A, "2023-12-07T20:13:50.843Z"),
            message("m2", A, "2023-12-07T20:13:51.000Z", failed=True),
            message("m3", B, "2023-12-07T20:13:52.000Z"),
        ))
        self.assertEqual([m.message_id for m in messages], ["m1", "m3"])
        self.assertEqual(provenance.failed_excluded, 1)
        self.assertEqual(provenance.messages_in_file, 3)
        self.assertIs(provenance.failed_delivery_policy, FailedDeliveryPolicy.EXCLUDED)

    def test_the_other_policy_is_expressible_and_recorded(self):
        messages, provenance = adapt(
            conversation(message("m1", A, "2023-12-07T20:13:50.843Z", failed=True)),
            failed_delivery=FailedDeliveryPolicy.INCLUDED,
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(provenance.failed_excluded, 0)
        self.assertIs(provenance.failed_delivery_policy, FailedDeliveryPolicy.INCLUDED)

    def test_absence_of_the_field_means_delivered(self):
        _, provenance = adapt(conversation(message("m1", A, "2023-12-07T20:13:50.843Z")))
        self.assertEqual(provenance.failed_excluded, 0)


class DyadMembershipTests(unittest.TestCase):
    """The check the core cannot do: dyadic is not the same as the right dyad."""

    def test_a_third_speaker_is_refused_at_the_import_boundary(self):
        with self.assertRaises(DyadMembershipError):
            adapt(conversation(
                message("m1", A, "2023-12-07T20:13:50.843Z"),
                message("m2", "stranger", "2023-12-07T20:13:52.000Z"),
                message("m3", B, "2023-12-07T20:13:54.000Z"),
            ))

    def test_two_actors_who_are_the_wrong_two_pass_the_core_and_fail_here(self):
        """Exactly the gap: `len(actors) <= 2` holds, and the conversation is
        still about somebody the source never named."""
        node = conversation(
            message("m1", A, "2023-12-07T20:13:50.843Z"),
            message("m2", "stranger", "2023-12-07T20:13:52.000Z"),
        )
        actors = {m["ofUser"]["$oid"] for m in node["messages"]}
        self.assertEqual(len(actors), 2)          # the core would be satisfied
        with self.assertRaises(DyadMembershipError):
            adapt(node)

    def test_a_degenerate_declared_pair_is_refused(self):
        node = conversation(message("m1", A, "2023-12-07T20:13:50.843Z"))
        node["secondId"] = {"$oid": A}
        with self.assertRaises(DyadMembershipError):
            adapt(node)

    def test_one_side_silent_is_not_a_membership_problem(self):
        """B never speaks. That is a quiet conversation, not a wrong dyad."""
        messages, provenance = adapt(conversation(
            message("m1", A, "2023-12-07T20:13:50.843Z"),
            message("m2", A, "2023-12-07T20:13:52.000Z"),
        ))
        self.assertEqual(len(messages), 2)
        self.assertEqual(provenance.participants, (A, B))

    def test_the_guard_is_shared_so_the_next_adapter_inherits_it(self):
        from extractor.adapters import guards

        self.assertTrue(callable(guards.verify_dyad_membership))
        guards.verify_dyad_membership(["x", "y"], ("x", "y"), "t")
        with self.assertRaises(guards.DyadMembershipError):
            guards.verify_dyad_membership(["x", "z"], ("x", "y"), "t")


class ProvenanceShapeTests(unittest.TestCase):
    def test_provenance_names_both_participants(self):
        _, provenance = adapt(conversation(message("m1", A, "2023-12-07T20:13:50.843Z")))
        self.assertEqual(provenance.participants, (A, B))
        self.assertEqual(provenance.conversation_id, "c0")

    def test_provenance_is_immutable(self):
        _, provenance = adapt(conversation(message("m1", A, "2023-12-07T20:13:50.843Z")))
        with self.assertRaises((AttributeError, TypeError)):
            provenance.semantics = SEMANTICS
        self.assertIsInstance(provenance, AdapterProvenance)


if __name__ == "__main__":
    unittest.main()


class SourceSemanticsTests(unittest.TestCase):
    """The declaration the WhatsApp corpora forced into existence."""

    def test_maichat_declares_a_total_order_backed_by_real_ids(self):
        from extractor.adapters.maichat import SEMANTICS
        from extractor.adapters.semantics import (
            MessageIdentity,
            OrderingSemantics,
            TimestampResolution,
        )

        self.assertIs(SEMANTICS.timestamp_resolution, TimestampResolution.MILLISECOND)
        self.assertIs(SEMANTICS.ordering, OrderingSemantics.TOTAL)
        self.assertIs(SEMANTICS.message_identity, MessageIdentity.SOURCE_STABLE_ID)
        self.assertEqual(SEMANTICS.topology_claim_scope, "physical_chronology")
        self.assertTrue(SEMANTICS.usable_as_topology_oracle)

    def test_the_declaration_rides_along_with_every_claim(self):
        _, provenance = adapt(conversation(message("m1", A, "2023-12-07T20:13:50.843Z")))
        self.assertIn("millisecond", provenance.claim_prefix())

    def test_a_minute_resolution_source_is_refused_as_a_topology_oracle(self):
        """The WhatsApp-export shape: minute buckets, partial order, no ids.
        Synthesising ids to break cross-actor ties would manufacture hand-overs."""
        from extractor.adapters.semantics import (
            Deduplication,
            LengthSemantics,
            MessageIdentity,
            OrderingEvidence,
            OrderingSemantics,
            SourceSemantics,
            TimestampResolution,
            TopologyOracleRefused,
            assert_topology_oracle_usable,
        )

        whatsapp_like = SourceSemantics(
            timestamp_meaning=TimestampSemantics.EXPORT_RENDERED,
            timestamp_resolution=TimestampResolution.MINUTE,
            ordering=OrderingSemantics.PARTIAL_WITHIN_EQUAL_TIMESTAMP,
            ordering_evidence=OrderingEvidence.NONE,
            message_identity=MessageIdentity.NONE,
            deduplication=Deduplication.DISABLED,
            length=LengthSemantics.TEXT_CHARS_EXCLUDING_EMOJI,
        )
        self.assertFalse(whatsapp_like.usable_as_topology_oracle)
        self.assertEqual(whatsapp_like.boundary_uncertainty_seconds, 60.0)
        with self.assertRaises(TopologyOracleRefused):
            assert_topology_oracle_usable(whatsapp_like, "seufert-like")

        from extractor.adapters.maichat import SEMANTICS
        assert_topology_oracle_usable(SEMANTICS, "maichat")   # does not raise

    def test_order_and_identity_answer_different_questions(self):
        """A source that guarantees its own emission order knows its topology
        exactly while giving no ids at all — dedup impossible, oracle fine. The
        reverse also holds: ids alone order nothing."""
        from extractor.adapters.semantics import (
            Deduplication,
            LengthSemantics,
            MessageIdentity,
            OrderingEvidence,
            OrderingSemantics,
            SourceSemantics,
            TimestampResolution,
            TimestampSemantics,
        )

        ordered_but_anonymous = SourceSemantics(
            timestamp_meaning=TimestampSemantics.EXPORT_RENDERED,
            timestamp_resolution=TimestampResolution.MINUTE,
            ordering=OrderingSemantics.TOTAL,
            ordering_evidence=OrderingEvidence.EXPORTED_POSITION,
            message_identity=MessageIdentity.NONE,
            deduplication=Deduplication.DISABLED,
            length=LengthSemantics.TEXT_CHARS,
        )
        self.assertTrue(ordered_but_anonymous.usable_as_topology_oracle)
        self.assertFalse(ordered_but_anonymous.deduplication_possible)
        # ordered by the EXPORT, so the claim narrows rather than disappearing
        self.assertEqual(ordered_but_anonymous.topology_claim_scope, "exported_sequence")

        identified_but_unordered = SourceSemantics(
            timestamp_meaning=TimestampSemantics.UNKNOWN,
            timestamp_resolution=TimestampResolution.MINUTE,
            ordering=OrderingSemantics.PARTIAL_WITHIN_EQUAL_TIMESTAMP,
            ordering_evidence=OrderingEvidence.NONE,
            message_identity=MessageIdentity.SOURCE_STABLE_ID,
            deduplication=Deduplication.BY_STABLE_ID,
            length=LengthSemantics.TEXT_CHARS,
        )
        self.assertFalse(identified_but_unordered.usable_as_topology_oracle)
        self.assertTrue(identified_but_unordered.deduplication_possible)
