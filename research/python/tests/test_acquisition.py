"""Feedback Acquisition Policy v0.

Six invariants the user's brief named, plus the one that makes the sampled data
usable at all: the sampling rule may read the past and the observer side, and
may never read the answer it is about to ask for. Everything else here is
budget arithmetic.
"""

import unittest
from pathlib import Path

from calibration import acquisition, model, policy
from calibration.acquisition import (
    BACKOFF_DAYS,
    IGNORED_STREAK_BACKOFF,
    MAX_ITEMS_PER_PROMPT,
    MAX_PROMPTS_PER_DAY,
    MAX_RECALL_AGE_HOURS,
    UNPRODUCTIVE_ANSWER_LIMIT,
    AcquisitionMode,
    CalibrationCandidate,
    ConversationState,
    DenyReason,
    Prompt,
    PromptOutcome,
    RecipientState,
    RequestDecision,
    evaluate,
    information_value,
    issue,
    may_disclose_to_partner,
    produces_observation,
    register_outcome,
)
from calibration.model import (
    EstimatorKind,
    ObserverEstimate,
    RecipientFeedback,
    ReferenceFrame,
    Tier,
    record_divergence,
)
from calibration.policy import build_profile

SPREAD = (1.0, 3.0, 5.0, 7.0)
CALM = ConversationState()


def candidate(event_id="e1", signature="terse_acknowledgement", at=0.0, participated=True):
    return CalibrationCandidate(
        event_id=event_id,
        recipient="r",
        estimate=ObserverEstimate(event_id, "r", signature, 2.0, "m", EstimatorKind.MODEL, at),
        occurred_at=at,
        recipient_participated=participated,
    )


def diverge(event_id, recipient_value=7.0, at=0.0, signature="terse_acknowledgement"):
    estimate = ObserverEstimate(event_id, "r", signature, 2.0, "m", EstimatorKind.MODEL, at)
    feedback = RecipientFeedback(event_id, "r", "FELT_HEARD", recipient_value, (1.0, 7.0), at, True)
    return record_divergence(estimate, feedback, ReferenceFrame("m", SPREAD), ReferenceFrame("r", SPREAD))


class SelectionIndependenceTests(unittest.TestCase):
    """The sampling rule must not depend on the answer being sought."""

    def test_a_candidate_has_nowhere_to_put_an_answer(self):
        fields = {f.name for f in CalibrationCandidate.__dataclass_fields__.values()}
        self.assertEqual(fields, {"event_id", "recipient", "estimate", "occurred_at",
                                  "recipient_participated"})

    def test_the_acquisition_policy_never_touches_recipient_feedback(self):
        source = Path(acquisition.__file__).read_text(encoding="utf-8")
        body = source.split('"""', 2)[-1]           # skip the module docstring
        self.assertNotIn("RecipientFeedback", body)

    def test_a_prompt_carries_no_value_field(self):
        fields = {f.name for f in Prompt.__dataclass_fields__.values()}
        self.assertNotIn("value", fields)
        self.assertNotIn("rating", fields)

    def test_information_value_is_not_an_evidence_weight(self):
        """It exists only in acquisition; the profile builder has never heard of it."""
        for module in (policy, model):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertNotIn("information_value", source)

    def test_a_well_chosen_question_yields_the_same_single_observation(self):
        eager = build_profile("r", [diverge(f"e{i}", at=float(i)) for i in range(4)])
        signal = eager.signals[0]
        self.assertEqual(len(signal.supporting), 4)
        self.assertEqual(signal.uncertainty_width, policy._uncertainty(4, 0))


class NoPromptChangesBeliefTests(unittest.TestCase):
    def test_issuing_a_prompt_creates_no_observation(self):
        state = RecipientState("r")
        before = build_profile("r", [])
        issue(candidate(), state, 10.0)
        self.assertEqual(build_profile("r", []).signals, before.signals)

    def test_three_of_four_outcomes_produce_nothing(self):
        self.assertTrue(produces_observation(PromptOutcome.ANSWERED))
        for outcome in acquisition.NO_OBSERVATION_OUTCOMES:
            self.assertFalse(produces_observation(outcome), outcome)

    def test_an_ignored_prompt_is_not_negative_feedback(self):
        records = [diverge(f"e{i}", at=float(i)) for i in range(4)]
        state = RecipientState("r")
        for hour in (100.0, 130.0):
            issue(candidate(f"ignored{hour}", at=hour), state, hour)
            register_outcome(state, PromptOutcome.IGNORED, hour)
        self.assertEqual(build_profile("r", records).signals,
                         build_profile("r", records).signals)
        self.assertEqual(build_profile("r", records).evidence_count, 4)

    def test_an_expired_prompt_is_not_neutral_feedback(self):
        self.assertFalse(produces_observation(PromptOutcome.EXPIRED))
        self.assertIn(PromptOutcome.EXPIRED, acquisition.NO_OBSERVATION_OUTCOMES)

    def test_opting_out_is_unknown_not_a_midpoint(self):
        self.assertFalse(produces_observation(PromptOutcome.OPTED_OUT))
        self.assertNotIn("4", acquisition.PRIMARY_OPT_OUT)

    def test_a_verdict_carries_no_impact_at_all(self):
        verdict = evaluate(candidate(), RecipientState("r"), CALM, None, 2.0)
        fields = {f.name for f in type(verdict).__dataclass_fields__.values()}
        self.assertEqual(fields, {"decision", "reasons", "information_value", "rationale"})


class SamplingOnceTests(unittest.TestCase):
    def test_the_same_event_cannot_be_asked_about_twice(self):
        state = RecipientState("r")
        issue(candidate("e1"), state, 2.0)
        with self.assertRaises(ValueError):
            issue(candidate("e1"), state, 40.0)

    def test_an_already_sampled_event_is_denied_not_deferred(self):
        state = RecipientState("r")
        issue(candidate("e1"), state, 2.0)
        verdict = evaluate(candidate("e1"), state, CALM, None, 30.0)
        self.assertIs(verdict.decision, RequestDecision.DO_NOT_ASK)
        self.assertIn(DenyReason.ALREADY_SAMPLED, verdict.reasons)


class HardDenyTests(unittest.TestCase):
    """Nothing about information value overrides these."""

    def test_safety_beats_a_maximally_informative_candidate(self):
        value, _ = information_value(candidate(), None)
        self.assertEqual(value, 1.0)
        verdict = evaluate(candidate(), RecipientState("r"),
                           ConversationState(safety_flag=True), None, 2.0)
        self.assertIs(verdict.decision, RequestDecision.DO_NOT_ASK)
        self.assertIn(DenyReason.SAFETY_CONCERN, verdict.reasons)
        self.assertEqual(verdict.information_value, 1.0)   # value is reported, not obeyed

    def test_a_live_conversation_is_ask_later_not_never(self):
        verdict = evaluate(candidate(), RecipientState("r"),
                           ConversationState(active=True, minutes_since_last_message=1.0),
                           None, 2.0)
        self.assertIs(verdict.decision, RequestDecision.ASK_LATER)

    def test_a_recent_conflict_defers_rather_than_denies(self):
        verdict = evaluate(candidate(), RecipientState("r"),
                           ConversationState(hours_since_conflict=1.0), None, 2.0)
        self.assertIs(verdict.decision, RequestDecision.ASK_LATER)
        self.assertIn(DenyReason.HIGH_CONFLICT_COOLDOWN, verdict.reasons)

    def test_an_event_the_recipient_was_not_in_is_denied(self):
        verdict = evaluate(candidate(participated=False), RecipientState("r"), CALM, None, 2.0)
        self.assertIn(DenyReason.RECIPIENT_NOT_IN_EVENT, verdict.reasons)

    def test_an_event_too_old_to_recall_is_denied(self):
        verdict = evaluate(candidate(at=0.0), RecipientState("r"), CALM, None,
                           MAX_RECALL_AGE_HOURS + 1)
        self.assertIn(DenyReason.EVENT_TOO_OLD, verdict.reasons)

    def test_a_snoozed_user_is_not_asked(self):
        state = RecipientState("r", snoozed_until=100.0)
        verdict = evaluate(candidate(), state, CALM, None, 2.0)
        self.assertIn(DenyReason.USER_SNOOZED, verdict.reasons)

    def test_never_ask_and_user_initiated_modes_never_prompt(self):
        for mode in (AcquisitionMode.NEVER_ASK, AcquisitionMode.USER_INITIATED):
            verdict = evaluate(candidate(), RecipientState("r", mode=mode), CALM, None, 2.0)
            self.assertIs(verdict.decision, RequestDecision.DO_NOT_ASK, mode)


class BudgetTests(unittest.TestCase):
    def test_one_prompt_a_day(self):
        state = RecipientState("r")
        issue(candidate("e1"), state, 9.0)
        verdict = evaluate(candidate("e2"), state, CALM, None, 14.0)
        self.assertIs(verdict.decision, RequestDecision.ASK_LATER)
        self.assertIn(DenyReason.PROMPT_BUDGET_SPENT, verdict.reasons)
        self.assertEqual(MAX_PROMPTS_PER_DAY, 1)

    def test_the_next_day_reopens_the_budget(self):
        state = RecipientState("r")
        issue(candidate("e1"), state, 9.0)
        verdict = evaluate(candidate("e2", at=33.0), state, CALM, None, 34.0)
        self.assertIs(verdict.decision, RequestDecision.ELIGIBLE_NOW)

    def test_two_ignored_prompts_buy_a_week_of_silence(self):
        state = RecipientState("r")
        for _ in range(IGNORED_STREAK_BACKOFF):
            register_outcome(state, PromptOutcome.IGNORED, 10.0)
        self.assertEqual(state.backoff_until, 10.0 + BACKOFF_DAYS * 24)
        verdict = evaluate(candidate("e9", at=50.0), state, CALM, None, 51.0)
        self.assertIn(DenyReason.IGNORED_BACKOFF, verdict.reasons)

    def test_answering_clears_the_streak(self):
        state = RecipientState("r")
        register_outcome(state, PromptOutcome.IGNORED, 10.0)
        register_outcome(state, PromptOutcome.ANSWERED, 34.0)
        self.assertEqual(state.ignored_streak, 0)
        self.assertIsNone(state.backoff_until)
        self.assertEqual(state.answered_count, 1)

    def test_answers_that_teach_nothing_stop_the_asking(self):
        """The flat responder: prompted daily, answers every time, yields no evidence."""
        state = RecipientState("r", answered_count=UNPRODUCTIVE_ANSWER_LIMIT)
        empty = build_profile("r", [])
        verdict = evaluate(candidate("e9", at=50.0), state, CALM, empty, 51.0)
        self.assertIs(verdict.decision, RequestDecision.DO_NOT_ASK)
        self.assertIn(DenyReason.NO_LEARNABLE_SIGNAL, verdict.reasons)

    def test_a_prompt_carries_at_most_two_items(self):
        self.assertEqual(Prompt("p", "r", "e1", 0.0).items, 2)
        self.assertEqual(MAX_ITEMS_PER_PROMPT, 2)

    def test_the_expiry_window_is_generous_not_a_45_minute_sprint(self):
        prompt = Prompt("p", "r", "e1", 10.0)
        self.assertGreaterEqual(prompt.expires_at - prompt.sent_at, 12.0)


class InformationValueTests(unittest.TestCase):
    def test_an_unstudied_signature_is_the_most_informative(self):
        value, _ = information_value(candidate(), None)
        self.assertEqual(value, 1.0)

    def test_a_settled_signature_is_not_worth_asking_about(self):
        profile = build_profile("r", [diverge(f"e{i}", at=float(i)) for i in range(4)])
        self.assertIs(profile.signals[0].tier, Tier.USABLE_CALIBRATION)
        value, _ = information_value(candidate(), profile)
        self.assertLess(value, acquisition.INFORMATION_VALUE_FLOOR)
        verdict = evaluate(candidate("new", at=50.0), RecipientState("r"), CALM, profile, 51.0)
        self.assertIn(DenyReason.NO_INFORMATION_VALUE, verdict.reasons)

    def test_a_contested_history_is_worth_another_observation(self):
        records = [diverge(f"s{i}", 7.0, float(i)) for i in range(3)]
        records += [diverge(f"c{i}", 1.0, float(10 + i)) for i in range(2)]
        profile = build_profile("r", records)
        self.assertIs(profile.signals[0].tier, Tier.CONTESTED)
        value, _ = information_value(candidate(), profile)
        self.assertGreater(value, acquisition.INFORMATION_VALUE_FLOOR)

    def test_a_weak_tendency_is_worth_one_more(self):
        profile = build_profile("r", [diverge(f"e{i}", at=float(i)) for i in range(2)])
        value, _ = information_value(candidate(), profile)
        self.assertGreater(value, acquisition.INFORMATION_VALUE_FLOOR)


class OwnershipTests(unittest.TestCase):
    def test_feedback_is_private_by_default(self):
        feedback = RecipientFeedback("e1", "r", "FELT_HEARD", 6.0, (1.0, 7.0), 0.0, True)
        self.assertEqual(feedback.visibility, "private_to_recipient")
        self.assertFalse(may_disclose_to_partner(feedback.visibility, explicit_consent=True))

    def test_consent_alone_does_not_disclose_and_neither_does_visibility_alone(self):
        self.assertFalse(may_disclose_to_partner("shared_with_partner", explicit_consent=False))
        self.assertFalse(may_disclose_to_partner("private_to_recipient", explicit_consent=True))
        self.assertTrue(may_disclose_to_partner("shared_with_partner", explicit_consent=True))

    def test_the_channel_travels_with_the_observation(self):
        volunteered = RecipientFeedback("e1", "r", "FELT_HEARD", 6.0, (1.0, 7.0), 0.0, True,
                                        channel="user_initiated")
        self.assertEqual(volunteered.channel, "user_initiated")
        with self.assertRaises(ValueError):
            RecipientFeedback("e2", "r", "FELT_HEARD", 6.0, (1.0, 7.0), 0.0, True, channel="guessed")


class WordingTests(unittest.TestCase):
    def test_nobody_is_asked_to_rate_our_ontology(self):
        text = acquisition.PRIMARY_QUESTION + acquisition.FOLLOW_UP_QUESTION
        for jargon in ("uptake", "validation", "FELT_HEARD", "observer", "divergence", "signature"):
            self.assertNotIn(jargon.lower(), text.lower())

    def test_the_follow_up_is_exploratory_metadata_not_part_of_the_construct(self):
        self.assertTrue(acquisition.FOLLOW_UP_IS_EXPLORATORY)
        source = Path(policy.__file__).read_text(encoding="utf-8")
        self.assertNotIn("FOLLOW_UP", source)


class SimulationTests(unittest.TestCase):
    def test_never_ask_learns_nothing_and_asks_nothing(self):
        from calibration import budget_demo

        scenario = next(s for s in budget_demo.SCENARIOS if s.name == "active_chat")
        run = budget_demo.simulate(scenario, AcquisitionMode.NEVER_ASK)
        self.assertEqual((run.prompts, run.answered), (0, 0))
        self.assertEqual(build_profile(scenario.name, run.records).evidence_count, 0)

    def test_the_budget_holds_in_every_scenario_and_mode(self):
        from calibration import budget_demo

        for scenario in budget_demo.SCENARIOS:
            for mode in (AcquisitionMode.END_OF_DAY_SAMPLE, AcquisitionMode.DELAYED_EVENT_SAMPLE):
                run = budget_demo.simulate(scenario, mode)
                self.assertLessEqual(run.max_per_day, MAX_PROMPTS_PER_DAY,
                                     f"{scenario.name}/{mode.value}")

    def test_a_safety_window_is_never_prompted_through(self):
        from calibration import budget_demo

        scenario = next(s for s in budget_demo.SCENARIOS if s.name == "safety_sensitive")
        quiet = budget_demo.simulate(scenario, AcquisitionMode.DELAYED_EVENT_SAMPLE)
        busy = budget_demo.simulate(
            next(s for s in budget_demo.SCENARIOS if s.name == "always_answers"),
            AcquisitionMode.DELAYED_EVENT_SAMPLE)
        self.assertLess(quiet.prompts, busy.prompts)

    def test_an_ignoring_recipient_is_asked_a_handful_of_times_not_daily(self):
        from calibration import budget_demo

        scenario = next(s for s in budget_demo.SCENARIOS if s.name == "always_ignores")
        run = budget_demo.simulate(scenario, AcquisitionMode.DELAYED_EVENT_SAMPLE)
        self.assertEqual(run.answered, 0)
        self.assertLessEqual(run.prompts, 8)

    def test_pure_self_selection_destroys_the_reference_frame(self):
        """USER_INITIATED corrections cluster where the model is most wrong, so the
        observer side of the sampled set has no spread and nothing is placeable."""
        from calibration import budget_demo

        scenario = next(s for s in budget_demo.SCENARIOS if s.name == "active_chat")
        run = budget_demo.simulate_user_initiated(scenario)
        profile = build_profile(scenario.name, run.records)
        self.assertGreater(run.answered, 20)
        self.assertEqual(profile.evidence_count, 0)
        self.assertEqual(len(profile.skipped_insufficient), run.answered)

    def test_answering_everything_still_teaches_nothing_about_a_flat_responder(self):
        from calibration import budget_demo

        scenario = next(s for s in budget_demo.SCENARIOS if s.name == "flat_responder")
        run = budget_demo.simulate(scenario, AcquisitionMode.END_OF_DAY_SAMPLE)
        self.assertEqual(run.answered, run.prompts)
        self.assertEqual(build_profile(scenario.name, run.records).evidence_count, 0)
        self.assertLessEqual(run.prompts, UNPRODUCTIVE_ANSWER_LIMIT + 1)


if __name__ == "__main__":
    unittest.main()
