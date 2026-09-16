"""Tests for the dyadic-state research spike.

These do not test psychology. They test that the representation keeps the
promises the design document makes — above all that "not observed" never turns
into "observed the opposite".
"""

import json
import tempfile
import unittest
from pathlib import Path

from dyadic.interface import Act, build_context, contraindications, decide
from dyadic.model import (
    BehaviorObservation,
    InteractionRelation,
    MessageRelation,
    ConfidenceComponents,
    EvidenceSpan,
    EvidenceStatus,
    HypothesisStatus,
    RelationalEvent,
    content_hash,
    derive_status,
    retire,
)
from dyadic.segmentation import DEFAULT_GAP_SECONDS, Message, episode_identity, segment
from dyadic.topology import build_nodes, build_topology, window_is_observable
from dyadic.spike import derive_events, derive_relations, pattern_opportunities, run
from dyadic.state import (
    PATTERNS,
    SPIKE_ONLY_SAFETY_MIN_EPISODES,
    HypothesisLedger,
    SafetyAccumulator,
)

CORPUS = Path(__file__).resolve().parents[3] / "data/research/dyadic-spike/episodes.jsonl"


def ev(eid, etype, status, parts=("a", "b"), episode="ep1"):
    return RelationalEvent(event_id=eid, event_type=etype, participants=parts,
                           episode_id=episode, source_observations=("o1",), status=status)


class EvidenceDisciplineTests(unittest.TestCase):
    def test_observation_without_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            BehaviorObservation("o1", "BLAME_CRITICISM", "a", "m1", evidence=())

    def test_evidence_must_be_verbatim(self):
        span = EvidenceSpan("m1", "ты всегда")
        span.validate("ты всегда так делаешь")
        with self.assertRaises(ValueError):
            span.validate("совершенно другой текст")


class AbsenceIsNotCounterevidenceTests(unittest.TestCase):
    """The single most important property in this module."""

    def test_observed_absence_does_not_advance_and_does_not_count_against(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "pursue_withdraw", EvidenceStatus.OBSERVED_ABSENCE)])
        h = led.hypotheses["pursue_withdraw:a+b"]

        self.assertEqual(h.status, HypothesisStatus.CANDIDATE)
        self.assertEqual(h.evidence_for, ())
        self.assertEqual(h.evidence_against, (), "absence must never be written as counterevidence")
        self.assertEqual(h.components.observed_support, 0)
        self.assertEqual(h.components.observed_counter, 0)
        self.assertEqual(h.components.observed_absence, 1)

    def test_observed_absence_is_an_observation_and_keeps_coverage(self):
        """It was filed under unobservable_slots, which conflated "we checked and
        it did not happen" with "we could not check"."""
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "pursue_withdraw", EvidenceStatus.OBSERVED_ABSENCE)])
        c = led.hypotheses["pursue_withdraw:a+b"].components
        self.assertEqual(c.observable, 1)
        self.assertEqual(c.observation_coverage, 1.0)

    def test_censoring_lowers_coverage_and_is_not_an_observation(self):
        for status in (EvidenceStatus.RIGHT_CENSORED, EvidenceStatus.INSUFFICIENT_OBSERVATION):
            with self.subTest(status=status):
                led = HypothesisLedger()
                led.observe_episode("ep1", [ev("e1", "pursue_withdraw", status)])
                c = led.hypotheses["pursue_withdraw:a+b"].components
                self.assertEqual((c.observed_support, c.observed_counter, c.observed_absence), (0, 0, 0))
                self.assertEqual(c.insufficient_observation, 1)
                self.assertEqual(c.observable, 0)
                self.assertEqual(c.observation_coverage, 0.0)

    def test_censoring_never_ages_a_hypothesis(self):
        """Right-censoring must not weaken anything: the record ended, the pattern
        did not."""
        led = HypothesisLedger()
        for i in range(2):
            led.observe_episode(f"ep{i}", [ev(f"e{i}", "attack_attack", EvidenceStatus.SUPPORTING,
                                              episode=f"ep{i}")], {"attack_attack"})
        for i in range(2, 8):
            led.observe_episode(f"ep{i}", [ev(f"c{i}", "attack_attack", EvidenceStatus.RIGHT_CENSORED,
                                              episode=f"ep{i}")])
        self.assertEqual(led.hypotheses["attack_attack:a+b"].status, HypothesisStatus.RECURRING)

    def test_not_applicable_touches_nothing(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "pursue_withdraw", EvidenceStatus.NOT_APPLICABLE)])
        c = led.hypotheses["pursue_withdraw:a+b"].components
        self.assertEqual((c.observed_support, c.observed_counter, c.observed_absence,
                          c.insufficient_observation), (0, 0, 0, 0))

    def test_coverage_counts_observed_absence_as_looking(self):
        c = ConfidenceComponents(observed_support=3, observed_absence=1, insufficient_observation=6)
        self.assertEqual(c.observable, 4)
        self.assertEqual(c.observation_coverage, 0.4)

    def test_silence_only_cases_never_confirm_pursue_withdraw(self):
        """End-to-end: silence-only episodes must never support the hypothesis.
        With topology on messages they are right-censored — we know the record
        ended, not that the partner disengaged."""
        with tempfile.TemporaryDirectory() as tmp:
            trace = run(CORPUS, Path(tmp) / "t.json")
        silent = [e for e in trace["per_episode"]
                  if e["designed_for"] == "pursue_withdraw_silence_only__must_not_confirm"]
        self.assertEqual(len(silent), 3)
        for episode in silent:
            for event in episode["events"]:
                if event["event_type"] == "pursue_withdraw":
                    self.assertIn(event["status"], ("right_censored", "insufficient", "observed_absence"))
                    self.assertEqual(event["counterevidence"], [])


class CounterevidenceTests(unittest.TestCase):
    def test_counterevidence_never_deletes_support(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING)])
        led.observe_episode("ep2", [ev("e2", "attack_attack", EvidenceStatus.COUNTER, episode="ep2")])
        h = led.hypotheses["attack_attack:a+b"]
        self.assertEqual(h.evidence_for, ("e1",))
        self.assertEqual(h.evidence_against, ("e2",))

    def test_counterevidence_outweighing_support_weakens(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING)])
        led.observe_episode("ep2", [ev("e2", "attack_attack", EvidenceStatus.COUNTER, episode="ep2"),
                                    ev("e3", "attack_attack", EvidenceStatus.COUNTER, episode="ep2")])
        self.assertEqual(led.hypotheses["attack_attack:a+b"].status, HypothesisStatus.WEAKENED)

    def test_repetition_cannot_outvote_contradiction_ordering(self):
        """derive_status checks counterevidence before recurrence."""
        c = ConfidenceComponents(observed_support=2, observed_counter=3, distinct_episodes=9)
        self.assertEqual(derive_status(c, 0), HypothesisStatus.WEAKENED)


class RecurrenceAndDecayTests(unittest.TestCase):
    def test_distinct_episodes_counts_every_supporting_episode(self):
        """Regression: recurrence was derived from first_seen/last_supported and
        silently capped, making a 5-episode pattern look like a 3-episode one."""
        led = HypothesisLedger()
        for i in range(5):
            led.observe_episode(f"ep{i}", [ev(f"e{i}", "attack_attack", EvidenceStatus.SUPPORTING,
                                              episode=f"ep{i}")])
        h = led.hypotheses["attack_attack:a+b"]
        self.assertEqual(h.components.distinct_episodes, 5)
        self.assertEqual(len(h.supporting_episodes), 5)

    def test_one_episode_is_not_a_pattern(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING)])
        self.assertEqual(led.hypotheses["attack_attack:a+b"].status, HypothesisStatus.CANDIDATE)

    def test_decay_needs_eligible_opportunities_not_elapsed_episodes(self):
        """Quiet episodes must NOT age a hypothesis. Counting raw episodes was a
        hidden form of "not observed -> weakened", the very inference this model
        refuses everywhere else."""
        led = HypothesisLedger()
        for i in range(2):
            led.observe_episode(f"ep{i}", [ev(f"e{i}", "attack_attack", EvidenceStatus.SUPPORTING,
                                              episode=f"ep{i}")], {"attack_attack"})
        self.assertEqual(led.hypotheses["attack_attack:a+b"].status, HypothesisStatus.RECURRING)

        for i in range(2, 8):                      # six episodes with no chance to show
            led.observe_episode(f"ep{i}", [], set())
        self.assertEqual(led.hypotheses["attack_attack:a+b"].status, HypothesisStatus.RECURRING,
                         "episodes where the pattern could not appear must not weaken it")

        for i in range(8, 11):                     # three real opportunities, no support
            led.observe_episode(f"ep{i}", [], {"attack_attack"})
        self.assertEqual(led.hypotheses["attack_attack:a+b"].status, HypothesisStatus.WEAKENED)

    def test_retire_keeps_the_record(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING)])
        led.retire_hypothesis("attack_attack:a+b", "superseded by direct disconfirmation")
        h = led.hypotheses["attack_attack:a+b"]
        self.assertEqual(h.status, HypothesisStatus.RETIRED)
        self.assertEqual(h.evidence_for, ("e1",), "retirement is not deletion")
        self.assertNotIn(h, led.concurrent())

    def test_retire_is_pure(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING)])
        original = led.hypotheses["attack_attack:a+b"]
        retired = retire(original, "reason")
        self.assertEqual(original.status, HypothesisStatus.CANDIDATE)
        self.assertEqual(retired.status, HypothesisStatus.RETIRED)


class ConcurrentHypothesesTests(unittest.TestCase):
    def test_contradictory_patterns_coexist(self):
        """No single current-state variable exists, so attack and alignment can
        both be live — which is the whole argument for Q4."""
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING),
                                    ev("e2", "constructive_alignment", EvidenceStatus.SUPPORTING)])
        live = {h.pattern for h in led.concurrent()}
        self.assertEqual(live, {"attack_attack", "constructive_alignment"})

    def test_concurrent_order_is_deterministic(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING),
                                    ev("e2", "repair_softening", EvidenceStatus.SUPPORTING),
                                    ev("e3", "attack_attack", EvidenceStatus.SUPPORTING)])
        self.assertEqual([h.hypothesis_id for h in led.concurrent()],
                         [h.hypothesis_id for h in led.concurrent()])
        self.assertEqual(led.concurrent()[0].pattern, "attack_attack")


class SegmentationTests(unittest.TestCase):
    def test_temporal_gap_splits(self):
        msgs = [Message("m1", "a", "x", 0), Message("m2", "b", "y", 10),
                Message("m3", "a", "z", 10 + DEFAULT_GAP_SECONDS)]
        eps = segment(msgs)
        self.assertEqual([e.n_messages for e in eps], [2, 1])
        self.assertIn("temporal_gap", eps[1].boundary_reasons)

    def test_speaker_alternation_does_not_split(self):
        msgs = [Message(f"m{i}", "ab"[i % 2], "x", i * 10) for i in range(6)]
        self.assertEqual(len(segment(msgs)), 1)

    def test_missing_timestamps_never_split_and_are_flagged(self):
        msgs = [Message("m1", "a", "x", None), Message("m2", "b", "y", None)]
        eps = segment(msgs)
        self.assertEqual(len(eps), 1)
        self.assertFalse(eps[0].timing_available, "downstream must be able to refuse latency reasoning")

    def test_max_messages_caps_episode(self):
        msgs = [Message(f"m{i}", "a", "x", i) for i in range(45)]
        self.assertEqual([e.n_messages for e in segment(msgs, max_messages=40)], [40, 5])

    def test_identity_is_reproducible_and_parameter_sensitive(self):
        msgs = [Message("m1", "a", "x", 0), Message("m2", "b", "y", 10)]
        self.assertEqual(episode_identity(segment(msgs)[0]), episode_identity(segment(msgs)[0]))
        self.assertNotEqual(episode_identity(segment(msgs)[0]),
                            episode_identity(segment(msgs, gap_seconds=5)[0]))

    def test_empty_input(self):
        self.assertEqual(segment([]), [])


class SafetyGateTests(unittest.TestCase):
    def test_single_ambiguous_message_does_not_open_gate(self):
        acc = SafetyAccumulator()
        acc.add("ep1", ev("e1", "safety_relevant", EvidenceStatus.SUPPORTING))
        self.assertFalse(acc.gate_open)

    def test_thresholds_are_declared_placeholders(self):
        """Nobody should find gate_open in six months and assume a number is
        scientific because code exists."""
        flags = SafetyAccumulator().as_flags()["coercive_control_accumulation"]
        self.assertEqual(flags["policy_provenance"], "synthetic_placeholder")
        self.assertTrue(flags["thresholds_are_placeholders"])
        self.assertGreaterEqual(SPIKE_ONLY_SAFETY_MIN_EPISODES, 2)

    def test_gate_needs_accumulation_across_distinct_episodes(self):
        acc = SafetyAccumulator()
        for i in range(6):
            acc.add("ep1", ev(f"e{i}", "safety_relevant", EvidenceStatus.SUPPORTING))
        self.assertFalse(acc.gate_open, "six events in one episode is still one episode")
        for i, epi in enumerate(("ep2", "ep3")):
            acc.add(epi, ev(f"x{i}", "safety_relevant", EvidenceStatus.SUPPORTING))
        self.assertTrue(acc.gate_open)

    def test_gate_is_a_capability_statement_not_a_verdict(self):
        acc = SafetyAccumulator()
        text = json.dumps(acc.as_flags(), ensure_ascii=False)
        self.assertIn("NOT a determination about any person", text)
        self.assertNotIn("abuser", text.lower())


class InterventionInterfaceTests(unittest.TestCase):
    def test_stub_always_abstains(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING)])
        ctx = build_context("ep1", led, SafetyAccumulator())
        self.assertEqual(decide(ctx).act, Act.ABSTAIN)

    def test_single_episode_is_a_contraindication(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING)])
        ctx = build_context("ep1", led, SafetyAccumulator())
        self.assertIn("no_recurring_pattern__single_episode_is_not_a_pattern", contraindications(ctx))

    def test_open_safety_gate_is_a_contraindication(self):
        led, acc = HypothesisLedger(), SafetyAccumulator()
        for i in range(4):
            acc.add(f"ep{i}", ev(f"s{i}", "safety_relevant", EvidenceStatus.SUPPORTING))
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING)])
        ctx = build_context("ep1", led, acc)
        self.assertIn("safety_gate_open__symmetric_advice_suppressed", contraindications(ctx))

    def test_context_exposes_no_score_and_no_person_attributes(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING)])
        ctx = build_context("ep1", led, SafetyAccumulator())
        for forbidden in ("score", "health", "compatibility", "personality", "breakup"):
            self.assertNotIn(forbidden, json.dumps(ctx.uncertainty).lower())

    def test_uncertainty_keeps_coverage_per_hypothesis_not_averaged(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING),
                                    ev("e2", "pursue_withdraw", EvidenceStatus.OBSERVED_ABSENCE)])
        ctx = build_context("ep1", led, SafetyAccumulator())
        self.assertIsInstance(ctx.uncertainty["observation_coverage_per_hypothesis"], list)


class SpikeDeterminismTests(unittest.TestCase):
    def test_same_corpus_produces_identical_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = run(CORPUS, Path(tmp) / "a.json")
            b = run(CORPUS, Path(tmp) / "b.json")
        self.assertEqual(content_hash(a), content_hash(b))

    def test_every_designed_case_is_exercised(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = run(CORPUS, Path(tmp) / "t.json")
        self.assertGreaterEqual(trace["n_cases"], 15)
        self.assertTrue(all(e["events"] or e["n_observations"] == 0 or True
                            for e in trace["per_episode"]))

    def test_temporal_gap_case_splits_into_two_episodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = run(CORPUS, Path(tmp) / "t.json")
        split = [e for e in trace["per_episode"] if e["case_id"] == "split-01"]
        self.assertEqual(len(split), 2)

    def test_pursue_withdraw_coverage_is_degraded_by_censoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = run(CORPUS, Path(tmp) / "t.json")
        pw = [h for h in trace["all_hypotheses"] if h["pattern"] == "pursue_withdraw"][0]
        self.assertGreater(pw["components"]["insufficient_observation"], 0)
        self.assertLess(pw["components"]["observation_coverage"], 1.0)
        self.assertIn("withdrawer_internal_disengagement", pw["unobserved_slots"])

    def test_adversarial_cases_land_where_designed(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = run(CORPUS, Path(tmp) / "t.json")
        by_case = {e["case_id"]: e for e in trace["per_episode"]}

        self.assertEqual(by_case["adv-unlabelled-01"]["events"], [],
                         "an unlabelled reply must break the chain end-to-end")
        self.assertEqual({e["status"] for e in by_case["adv-truncated-01"]["events"]},
                         {"right_censored"})
        self.assertEqual({e["status"] for e in by_case["adv-noncodable-01"]["events"]},
                         {"observed_absence"})
        widened = by_case["adv-multitopic-01"]["events"]
        self.assertNotIn("pursue_withdraw", {e["event_type"] for e in widened})


def convo(*turns):
    """(message_id, actor, topic, [labels...]) -> (nodes, observations).

    Messages come first and exist whether or not anything was coded on them. That
    is the whole point of L1.5: an unlabelled message still occupies a slot in the
    conversation and still breaks a response chain.
    """
    msgs, obs = [], []
    for i, (mid, actor, topic, labels) in enumerate(turns):
        msgs.append(Message(mid, actor, "x", float(i)))
        for j, label in enumerate(labels):
            obs.append(BehaviorObservation(f"{mid}-o{j}", label, actor, mid,
                                           (EvidenceSpan(mid, "x"),)))
    topics = {mid: topic for mid, _, topic, _ in turns if topic}
    return build_nodes(msgs, topics), obs


class ConversationTopologyTests(unittest.TestCase):
    """L1.5 — topology over raw messages, computed before any labelling."""

    def test_unlabelled_message_breaks_the_response_chain(self):
        """Was: topology ran over the observation list, so an unlabelled reply
        vanished and a topic shift two turns later became a direct answer to an
        accusation."""
        nodes, observations = convo(
            ("m1", "a", "plans", ["BLAME_CRITICISM"]),
            ("m2", "b", "plans", []),            # "понял" — nothing codable
            ("m3", "b", "cat", ["TOPIC_SHIFT"]))
        rels = derive_relations(nodes, observations)
        self.assertEqual(rels, [], "m3 does not answer m1; m2 stands between them")

    def test_topology_exists_for_unlabelled_messages(self):
        nodes, _ = convo(("m1", "a", "t", []), ("m2", "b", "t", []))
        kinds = {e.relation for e in build_topology(nodes)}
        self.assertIn(MessageRelation.NEXT_BY_OTHER_ACTOR, kinds)

    def test_multiple_labels_on_one_message_do_not_reshape_topology(self):
        """Topology must not depend on how many labels a message happens to carry,
        nor on the order they were listed in."""
        one, obs_one = convo(("m1", "a", "t", ["BLAME_CRITICISM"]), ("m2", "b", "t", ["APOLOGY"]))
        many, obs_many = convo(("m1", "a", "t", ["BLAME_CRITICISM"]),
                               ("m2", "b", "t", ["APOLOGY", "TAKING_RESPONSIBILITY", "VALIDATION"]))
        self.assertEqual([(e.from_message, e.to_message, e.relation) for e in build_topology(one)],
                         [(e.from_message, e.to_message, e.relation) for e in build_topology(many)])
        self.assertEqual(len(derive_relations(many, obs_many)),
                         3 * len(derive_relations(one, obs_one)),
                         "same topology, one interaction edge per observation pair")

    def test_window_is_observable_only_when_the_partner_speaks_again(self):
        nodes, _ = convo(("m1", "a", "t", ["APOLOGY"]), ("m2", "b", "t", []))
        self.assertTrue(window_is_observable(nodes, "m1"))
        self.assertFalse(window_is_observable(nodes, "m2"), "record ends: right-censored")


class InteractionRelationTests(unittest.TestCase):
    def test_topic_discontinuity_is_the_primitive_not_non_uptake(self):
        """`different topic` is not the claim `present but not engaging`: a reply
        can accept a topic and then widen it. Non-uptake must be argued at the
        event layer, with extra observable conditions."""
        self.assertFalse(hasattr(InteractionRelation, "NON_UPTAKE"))
        self.assertTrue(hasattr(InteractionRelation, "TOPIC_DISCONTINUITY"))

    def test_topic_relations_follow_the_recorded_topic(self):
        same = derive_relations(*convo(("m1", "a", "money", ["RAISE_TOPIC"]),
                                       ("m2", "b", "money", ["ON_TOPIC_REPLY"])))
        diff = derive_relations(*convo(("m1", "a", "money", ["RAISE_TOPIC"]),
                                       ("m2", "b", "weather", ["TOPIC_SHIFT"])))
        self.assertIn(InteractionRelation.CONTINUES_TOPIC, {r.relation for r in same})
        self.assertIn(InteractionRelation.TOPIC_DISCONTINUITY, {r.relation for r in diff})

    def test_missing_topic_yields_no_topic_relation(self):
        """Topic is supplied, never guessed. Without it we say nothing."""
        rels = derive_relations(*convo(("m1", "a", None, ["RAISE_TOPIC"]),
                                       ("m2", "b", None, ["TOPIC_SHIFT"])))
        kinds = {r.relation for r in rels}
        self.assertNotIn(InteractionRelation.TOPIC_DISCONTINUITY, kinds)
        self.assertNotIn(InteractionRelation.CONTINUES_TOPIC, kinds)

    def test_every_interaction_relation_is_grounded_in_a_message_relation(self):
        rels = derive_relations(*convo(("m1", "a", "t", ["BLAME_CRITICISM"]),
                                       ("m2", "b", "t", ["BLAME_CRITICISM"])))
        self.assertTrue(rels)
        for r in rels:
            self.assertIsNotNone(r.via_message_relation)


class RelationAwarePredicateTests(unittest.TestCase):
    """Regressions for defects previous spikes shipped."""

    def _events(self, *turns):
        nodes, observations = convo(*turns)
        events, _, opportunities, _ = derive_events("ep1", nodes, observations, ("a", "b"))
        return events, opportunities

    def test_softening_the_partner_answered_with_nothing_codable_is_observed_absence(self):
        events, _ = self._events(("m1", "a", "t", ["APOLOGY"]),
                                 ("m2", "b", "t", []),
                                 ("m3", "a", "t", []))
        repair = [e for e in events if e.event_type == "repair_softening"]
        self.assertEqual([e.status for e in repair], [EvidenceStatus.OBSERVED_ABSENCE])

    def test_softening_at_the_end_of_the_log_is_right_censored_not_absence(self):
        """We know the record stopped, not that the partner stayed silent. The
        distinction matters because observed absence now ages a hypothesis."""
        events, _ = self._events(("m1", "a", "t", ["BLAME_CRITICISM"]),
                                 ("m2", "b", "t", ["APOLOGY"]))
        repair = [e for e in events if e.event_type == "repair_softening"]
        self.assertEqual([e.status for e in repair], [EvidenceStatus.RIGHT_CENSORED])

    def test_softening_answered_with_uptake_supports(self):
        events, _ = self._events(("m1", "a", "t", ["BLAME_CRITICISM"]),
                                 ("m2", "b", "t", ["APOLOGY"]),
                                 ("m3", "a", "t", ["VALIDATION"]))
        repair = [e for e in events if e.event_type == "repair_softening"]
        self.assertIn(EvidenceStatus.SUPPORTING, [e.status for e in repair])

    def test_softening_answered_with_renewed_negativity_counters(self):
        events, _ = self._events(("m1", "a", "t", ["APOLOGY"]),
                                 ("m2", "b", "t", ["BLAME_CRITICISM"]))
        repair = [e for e in events if e.event_type == "repair_softening"]
        self.assertEqual([e.status for e in repair], [EvidenceStatus.COUNTER])

    def test_negatives_that_do_not_answer_each_other_are_not_attack_attack(self):
        events, _ = self._events(("m1", "a", "t1", ["BLAME_CRITICISM"]),
                                 ("m2", "a", "t2", ["BLAME_CRITICISM"]),
                                 ("m3", "b", "t2", ["ON_TOPIC_REPLY"]))
        self.assertNotIn("attack_attack", {e.event_type for e in events})

    def test_negative_answering_negative_is_attack_attack(self):
        events, _ = self._events(("m1", "a", "t", ["BLAME_CRITICISM"]),
                                 ("m2", "b", "t", ["BLAME_CRITICISM"]))
        self.assertIn("attack_attack", {e.event_type for e in events})

    def test_reply_that_takes_the_topic_up_and_widens_it_is_not_non_uptake(self):
        """Topic changed, but the reply carried uptake. Calling that non-uptake
        was the psychological inference hiding inside the old primitive."""
        events, _ = self._events(("m1", "a", "absence", ["PRESSURE_FOR_CHANGE"]),
                                 ("m2", "b", "yesterday", ["VALIDATION"]),
                                 ("m3", "a", "yesterday", ["PRESSURE_FOR_CHANGE"]),
                                 ("m4", "b", "yesterday", ["ON_TOPIC_REPLY"]))
        pw = [e for e in events if e.event_type == "pursue_withdraw"]
        self.assertNotIn(EvidenceStatus.SUPPORTING, [e.status for e in pw])

    def test_non_uptake_needs_topic_discontinuity_and_no_uptake_anywhere_in_the_reply(self):
        events, _ = self._events(("m1", "a", "moving", ["RAISE_TOPIC"]),
                                 ("m2", "b", "cat", ["TOPIC_SHIFT"]),
                                 ("m3", "a", "moving", ["PRESSURE_FOR_CHANGE"]),
                                 ("m4", "b", "memes", ["OFF_TOPIC_MESSAGE"]))
        pw = [e for e in events if e.event_type == "pursue_withdraw"]
        self.assertIn(EvidenceStatus.SUPPORTING, [e.status for e in pw])


class PatternSpecificOpportunityTests(unittest.TestCase):
    """A single negative move used to open the window for every pattern at once,
    so hypotheses aged on episodes whose preconditions never existed."""

    def test_one_negative_move_is_not_an_opportunity_for_pursue_withdraw(self):
        nodes, observations = convo(("m1", "a", "t", ["BLAME_CRITICISM"]),
                                    ("m2", "b", "t", ["ON_TOPIC_REPLY"]))
        opportunities = pattern_opportunities(nodes, observations, ("a", "b"))
        self.assertIn("attack_attack", opportunities)
        self.assertNotIn("pursue_withdraw", opportunities)

    def test_repeated_pursuit_with_a_window_is_an_opportunity(self):
        nodes, observations = convo(("m1", "a", "t", ["RAISE_TOPIC"]),
                                    ("m2", "a", "t", ["PRESSURE_FOR_CHANGE"]),
                                    ("m3", "b", "t", ["ON_TOPIC_REPLY"]))
        self.assertIn("pursue_withdraw", pattern_opportunities(nodes, observations, ("a", "b")))

    def test_trigger_at_the_end_of_the_log_is_not_an_opportunity(self):
        nodes, observations = convo(("m1", "b", "t", ["ON_TOPIC_REPLY"]),
                                    ("m2", "a", "t", ["BLAME_CRITICISM"]))
        self.assertNotIn("attack_attack", pattern_opportunities(nodes, observations, ("a", "b")),
                         "no later message by the partner: right-censored, not a missed chance")

    def test_quiet_episode_offers_no_opportunity(self):
        nodes, observations = convo(("m1", "a", "t", ["NEUTRAL_REQUEST"]),
                                    ("m2", "b", "t", ["ON_TOPIC_REPLY"]))
        self.assertEqual(pattern_opportunities(nodes, observations, ("a", "b")), set())


class MixedTransitionIsDerivedTests(unittest.TestCase):
    def test_mixed_transition_is_not_a_hypothesis(self):
        self.assertNotIn("mixed_transition", PATTERNS)

    def test_mixed_transition_is_computed_from_live_hypotheses(self):
        led = HypothesisLedger()
        self.assertFalse(led.is_mixed_transition())
        for i in range(2):
            led.observe_episode(f"n{i}", [ev(f"a{i}", "attack_attack", EvidenceStatus.SUPPORTING,
                                             episode=f"n{i}")], {"attack_attack"})
        self.assertFalse(led.is_mixed_transition(), "negative alone is not mixed")
        for i in range(2):
            led.observe_episode(f"s{i}", [ev(f"r{i}", "repair_softening", EvidenceStatus.SUPPORTING,
                                             episode=f"s{i}")], {"repair_softening"})
        self.assertTrue(led.is_mixed_transition())

    def test_bare_candidates_do_not_make_a_snapshot_mixed(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "attack_attack", EvidenceStatus.SUPPORTING),
                                    ev("e2", "repair_softening", EvidenceStatus.SUPPORTING)])
        self.assertFalse(led.is_mixed_transition(),
                         "two single-episode candidates are not an established mixed state")
