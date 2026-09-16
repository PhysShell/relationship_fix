"""Representation-compatibility probe against real human annotation schemas.

These tests do not check that our model is right. They check what it can and
cannot hold, using the annotation guideline of a corpus humans actually labelled.
A failure here is a finding, not a bug to patch — the spike is frozen.
"""

import json
import unittest

from dyadic.segmentation import Message
from external.kummerfeld_probe import ReplyAnnotation, adapt


def convo(*turns):
    """(message_id, author) -> messages"""
    return [Message(mid, author, "x", float(i)) for i, (mid, author) in enumerate(turns)]


class SingleAntecedentTests(unittest.TestCase):
    def test_a_plain_reply_survives(self):
        msgs = convo(("m1", "a"), ("m2", "b"))
        nodes, report = adapt(msgs, [ReplyAnnotation("m2", ("m1",))])
        self.assertTrue(report.lossless)
        self.assertEqual({n.message_id: n.reply_to for n in nodes}["m2"], "m1")

    def test_cross_turn_link_is_carried_but_flagged(self):
        """Expressible, but any consumer falling back to adjacency gets it wrong —
        which is exactly the defect we found in our own repair evaluator."""
        msgs = convo(("m1", "a"), ("m2", "a"), ("m3", "b"))
        _, report = adapt(msgs, [ReplyAnnotation("m3", ("m1",))])
        self.assertIn("m3", report.expressible)
        self.assertIn("m3", report.lost_cross_turn)
        self.assertFalse(report.lossless)


class MultipleAntecedentTests(unittest.TestCase):
    """The reference guideline says 'one OR MORE messages it is a response to'."""

    def test_second_antecedent_is_silently_dropped(self):
        msgs = convo(("m1", "a"), ("m2", "a"), ("m3", "b"))
        nodes, report = adapt(msgs, [ReplyAnnotation("m3", ("m1", "m2"))])
        self.assertIn("m3", report.lost_multi_antecedent)
        self.assertFalse(report.lossless)
        self.assertEqual({n.message_id: n.reply_to for n in nodes}["m3"], "m1",
                         "only the first antecedent can be represented")

    def test_loss_is_reported_not_scored(self):
        msgs = convo(("m1", "a"), ("m2", "a"), ("m3", "b"))
        d = adapt(msgs, [ReplyAnnotation("m3", ("m1", "m2"))])[1].as_dict()
        self.assertEqual(d["losses"]["multi_antecedent"]["n"], 1)
        self.assertIn("one OR MORE", d["losses"]["multi_antecedent"]["why"])
        self.assertNotIn("score", json.dumps(d).lower())


class ConversationStartTests(unittest.TestCase):
    def test_self_link_has_no_representation(self):
        """A self-link means 'starts a new conversation'. reply_to=None means 'no
        reply metadata'. Those are different claims and we can only store one."""
        msgs = convo(("m1", "a"), ("m2", "b"))
        nodes, report = adapt(msgs, [ReplyAnnotation("m1", ("m1",))])
        self.assertIn("m1", report.lost_conversation_start)
        self.assertIsNone({n.message_id: n.reply_to for n in nodes}["m1"])
        self.assertFalse(report.lossless)


class ProbeVerdictTests(unittest.TestCase):
    def test_l15_is_not_lossless_against_the_reference_schema(self):
        """The headline result of TRACK 1's first probe."""
        msgs = convo(("m1", "a"), ("m2", "a"), ("m3", "b"), ("m4", "b"))
        _, report = adapt(msgs, [
            ReplyAnnotation("m1", ("m1",)),          # thread opener
            ReplyAnnotation("m3", ("m1", "m2")),     # two antecedents
            ReplyAnnotation("m4", ("m1",)),          # cross-turn
        ])
        self.assertFalse(report.lossless)
        self.assertEqual(report.lost_conversation_start, ["m1"])
        self.assertEqual(report.lost_multi_antecedent, ["m3"])
        # Losses are NOT mutually exclusive: m3 is both multi-antecedent and
        # cross-turn, so a single annotation can be dropped in more than one way.
        # That is why the report is a list of losses and not a percentage.
        self.assertEqual(report.lost_cross_turn, ["m3", "m4"])
        self.assertEqual(report.n_annotations, 3)
        self.assertEqual(len(report.expressible), 2, "the thread opener carried nothing")

    def test_probe_does_not_mutate_the_frozen_spike(self):
        import dyadic.model as model
        self.assertEqual(
            [f for f in model.MessageNode.__dataclass_fields__],
            ["message_id", "actor", "order", "timestamp", "topic", "reply_to"],
            "the probe must observe the frozen representation, never widen it")
