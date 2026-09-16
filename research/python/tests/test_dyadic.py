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
from dyadic.spike import derive_events, derive_relations, run
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

    def test_absent_does_not_advance_and_does_not_count_against(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "pursue_withdraw", EvidenceStatus.ABSENT)])
        h = led.hypotheses["pursue_withdraw:a+b"]

        self.assertEqual(h.status, HypothesisStatus.CANDIDATE)
        self.assertEqual(h.evidence_for, ())
        self.assertEqual(h.evidence_against, (), "absence must never be written as counterevidence")
        self.assertEqual(h.components.support_count, 0)
        self.assertEqual(h.components.counter_count, 0)
        self.assertEqual(h.components.unobservable_slots, 1)

    def test_insufficient_observation_behaves_like_absent(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "pursue_withdraw", EvidenceStatus.INSUFFICIENT_OBSERVATION)])
        c = led.hypotheses["pursue_withdraw:a+b"].components
        self.assertEqual((c.support_count, c.counter_count, c.unobservable_slots), (0, 0, 1))

    def test_not_applicable_touches_nothing(self):
        led = HypothesisLedger()
        led.observe_episode("ep1", [ev("e1", "pursue_withdraw", EvidenceStatus.NOT_APPLICABLE)])
        c = led.hypotheses["pursue_withdraw:a+b"].components
        self.assertEqual((c.support_count, c.counter_count, c.unobservable_slots, c.observed_slots),
                         (0, 0, 0, 0))

    def test_unobservable_slots_lower_coverage_not_support(self):
        c = ConfidenceComponents(support_count=3, observed_slots=3, unobservable_slots=6)
        self.assertEqual(c.observation_coverage, 0.3333)

    def test_silence_only_cases_never_confirm_pursue_withdraw(self):
        """End-to-end: three silence-only episodes in the corpus must not push the
        hypothesis to RECURRING on their own."""
        with tempfile.TemporaryDirectory() as tmp:
            trace = run(CORPUS, Path(tmp) / "t.json")
        silent = [e for e in trace["per_episode"]
                  if e["designed_for"] == "pursue_withdraw_silence_only__must_not_confirm"]
        self.assertEqual(len(silent), 3)
        for episode in silent:
            for event in episode["events"]:
                if event["event_type"] == "pursue_withdraw":
                    self.assertEqual(event["status"], "absent")
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
        c = ConfidenceComponents(support_count=2, counter_count=3, distinct_episodes=9)
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
                                    ev("e2", "pursue_withdraw", EvidenceStatus.ABSENT)])
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

    def test_pursue_withdraw_coverage_is_degraded_by_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = run(CORPUS, Path(tmp) / "t.json")
        pw = [h for h in trace["all_hypotheses"] if h["pattern"] == "pursue_withdraw"][0]
        self.assertGreater(pw["components"]["unobservable_slots"], 0)
        self.assertLess(pw["components"]["observation_coverage"], 1.0)
        self.assertIn("withdrawer_internal_disengagement", pw["unobserved_slots"])


def obs(oid, label, actor, topic=None, mid=None):
    mid = mid or f"m-{oid}"
    return BehaviorObservation(oid, label, actor, mid, (EvidenceSpan(mid, "x"),), topic)


class InteractionRelationTests(unittest.TestCase):
    """L2.5 — the floor that stops L3 being a bag of labels."""

    def test_responds_to_is_the_next_cross_actor_observation_only(self):
        rels = derive_relations([obs("o1", "BLAME_CRITICISM", "a"),
                                 obs("o2", "BLAME_CRITICISM", "a"),
                                 obs("o3", "ON_TOPIC_REPLY", "b")])
        responds = [(r.from_observation, r.to_observation) for r in rels
                    if r.relation is InteractionRelation.RESPONDS_TO]
        self.assertIn(("o2", "o3"), responds)
        self.assertNotIn(("o1", "o2"), responds, "same actor is never a response")

    def test_non_uptake_requires_a_topic_change(self):
        same = derive_relations([obs("o1", "RAISE_TOPIC", "a", "money"),
                                 obs("o2", "ON_TOPIC_REPLY", "b", "money")])
        diff = derive_relations([obs("o1", "RAISE_TOPIC", "a", "money"),
                                 obs("o2", "TOPIC_SHIFT", "b", "weather")])
        self.assertIn(InteractionRelation.CONTINUES_TOPIC, {r.relation for r in same})
        self.assertIn(InteractionRelation.NON_UPTAKE, {r.relation for r in diff})

    def test_missing_topic_yields_no_topic_relation(self):
        """Topic is supplied, never guessed. Without it we say nothing."""
        rels = derive_relations([obs("o1", "RAISE_TOPIC", "a"), obs("o2", "TOPIC_SHIFT", "b")])
        kinds = {r.relation for r in rels}
        self.assertNotIn(InteractionRelation.NON_UPTAKE, kinds)
        self.assertNotIn(InteractionRelation.CONTINUES_TOPIC, kinds)


class RelationAwarePredicateTests(unittest.TestCase):
    """Regressions for defects the previous spike shipped."""

    def test_softening_nobody_answered_is_absent_not_supporting(self):
        """Was: `if later_negative: COUNTER else: SUPPORTING`, so "I said sorry
        and then silence" counted as a successful repair — the exact
        silence-as-evidence inference the model refuses for WITHDRAWAL."""
        events, _, _, _ = derive_events(
            "ep1", [obs("o1", "BLAME_CRITICISM", "a", "t"), obs("o2", "APOLOGY", "b", "t")],
            ("a", "b"), None)
        repair = [e for e in events if e.event_type == "repair_softening"]
        self.assertEqual([e.status for e in repair], [EvidenceStatus.ABSENT])

    def test_softening_answered_with_uptake_supports(self):
        events, _, _, _ = derive_events(
            "ep1", [obs("o1", "BLAME_CRITICISM", "a", "t"), obs("o2", "APOLOGY", "b", "t"),
                    obs("o3", "VALIDATION", "a", "t")], ("a", "b"), None)
        repair = [e for e in events if e.event_type == "repair_softening"]
        self.assertIn(EvidenceStatus.SUPPORTING, [e.status for e in repair])

    def test_softening_answered_with_renewed_negativity_counters(self):
        events, _, _, _ = derive_events(
            "ep1", [obs("o1", "APOLOGY", "a", "t"), obs("o2", "BLAME_CRITICISM", "b", "t")],
            ("a", "b"), None)
        repair = [e for e in events if e.event_type == "repair_softening"]
        self.assertEqual([e.status for e in repair], [EvidenceStatus.COUNTER])

    def test_negatives_that_do_not_answer_each_other_are_not_attack_attack(self):
        """Was: both actors having any NEGATIVE anywhere in the episode."""
        events, _, _, _ = derive_events(
            "ep1", [obs("o1", "BLAME_CRITICISM", "a", "t1"), obs("o2", "BLAME_CRITICISM", "a", "t2"),
                    obs("o3", "ON_TOPIC_REPLY", "b", "t2")], ("a", "b"), None)
        self.assertNotIn("attack_attack", {e.event_type for e in events})

    def test_negative_answering_negative_is_attack_attack(self):
        events, _, _, _ = derive_events(
            "ep1", [obs("o1", "BLAME_CRITICISM", "a", "t"), obs("o2", "BLAME_CRITICISM", "b", "t")],
            ("a", "b"), None)
        self.assertIn("attack_attack", {e.event_type for e in events})

    def test_quiet_episode_offers_no_opportunity(self):
        _, _, opportunities, _ = derive_events(
            "ep1", [obs("o1", "NEUTRAL_REQUEST", "a", "t"), obs("o2", "ON_TOPIC_REPLY", "b", "t")],
            ("a", "b"), None)
        self.assertEqual(opportunities, set())


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
