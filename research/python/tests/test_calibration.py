"""Personal Calibration Loop v0.

Most of these tests do not check that the numbers are right — the numbers are
placeholders (`model.PROVENANCE`). They check the three things that must survive
any later re-estimation: the forbidden edges stay inexpressible, one observation
never acts like four, and contradiction widens uncertainty instead of averaging
two realities into one.
"""

import dataclasses
import inspect
import unittest
from pathlib import Path

from calibration import model, policy
from calibration.model import (
    CalibrationHypothesis,
    DivergenceDirection,
    EstimatorKind,
    HypothesisStatus,
    ObserverEstimate,
    OnboardingContext,
    PersonalCalibrationProfile,
    RecipientFeedback,
    ReferenceFrame,
    Tier,
    record_divergence,
)
from calibration.policy import build_profile, read_event, summarise

SPREAD = (1.0, 3.0, 5.0, 7.0)          # an established frame
FLAT = (6.0, 6.0, 6.0, 6.0)            # four observations, no spread


def estimate(event_id, value=2.0, signature="terse_acknowledgement", recipient="r", at=0.0):
    return ObserverEstimate(event_id, recipient, signature, value, "m", EstimatorKind.MODEL, at)


def feedback(event_id, value=6.0, recipient="r", at=0.0):
    return RecipientFeedback(event_id, recipient, "FELT_HEARD", value, (1.0, 7.0), at, True)


def diverge(event_id, observer_value=2.0, recipient_value=6.0, signature="terse_acknowledgement",
            at=0.0, observer_frame=SPREAD, recipient_frame=SPREAD, recipient="r"):
    return record_divergence(
        estimate(event_id, observer_value, signature, recipient, at),
        feedback(event_id, recipient_value, recipient, at),
        ReferenceFrame("m", observer_frame),
        ReferenceFrame(recipient, recipient_frame),
    )


class ForbiddenEdgeTests(unittest.TestCase):
    """The separation has to be physical. Documentation has lost before."""

    def test_feedback_cannot_be_an_observer_answering_about_the_recipient(self):
        with self.assertRaises(ValueError):
            RecipientFeedback("e1", "r", "FELT_HEARD", 6.0, (1.0, 7.0), 0.0, respondent_is_recipient=False)

    def test_the_update_path_never_constructs_recipient_feedback(self):
        source = Path(policy.__file__).read_text(encoding="utf-8")
        self.assertNotIn("RecipientFeedback(", source)

    def test_the_update_path_never_touches_traits_or_vignette_answers(self):
        source = Path(policy.__file__).read_text(encoding="utf-8")
        for forbidden in ("OnboardingContext", "trait_scores", "vignette_answers"):
            self.assertNotIn(forbidden, source)

    def test_a_profile_is_built_from_divergence_records_and_nothing_else(self):
        self.assertEqual(
            list(inspect.signature(build_profile).parameters),
            ["recipient", "records", "hypotheses"],
        )

    def test_onboarding_context_is_rejected_by_the_builder(self):
        context = OnboardingContext("r", {"IRI": 4.2})
        with self.assertRaises(TypeError):
            build_profile("r", [context])

    def test_trait_scores_produce_no_hypotheses_at_all(self):
        context = OnboardingContext("r", trait_scores={"IRI": 4.2, "TEQ": 3.1})
        self.assertEqual(context.as_hypotheses(), ())
        self.assertEqual(context.self_description_panel(), {"IRI": 4.2, "TEQ": 3.1})

    def test_a_profile_has_no_free_attribute_slot(self):
        profile = build_profile("r", [])
        # frozen + slots: the exact type varies by CPython version, the refusal does not
        with self.assertRaises((AttributeError, dataclasses.FrozenInstanceError, TypeError)):
            profile.user_is_sensitive = True
        self.assertFalse(hasattr(profile, "user_is_sensitive"))

    def test_a_divergence_needs_both_sides_and_one_event(self):
        with self.assertRaises(TypeError):
            record_divergence(estimate("e1"))                     # observer alone
        with self.assertRaises(ValueError):
            record_divergence(estimate("e1"), feedback("e2"),
                              ReferenceFrame("m", SPREAD), ReferenceFrame("r", SPREAD))

    def test_a_divergence_is_scoped_to_one_recipient(self):
        with self.assertRaises(ValueError):
            record_divergence(estimate("e1", recipient="a"), feedback("e1", recipient="b"),
                              ReferenceFrame("m", SPREAD), ReferenceFrame("a", SPREAD))

    def test_a_profile_rejects_another_recipients_records(self):
        with self.assertRaises(ValueError):
            build_profile("someone_else", [diverge("e1")])


class ReferenceFrameTests(unittest.TestCase):
    """A divergence is never a subtraction — the two sides are on different scales."""

    def test_a_short_history_has_no_position(self):
        frame = ReferenceFrame("m", (1.0, 2.0))
        self.assertFalse(frame.established)
        self.assertIsNone(frame.position(1.5))

    def test_four_identical_values_are_not_a_distribution(self):
        """The flat responder: says 6 to everything, so nothing is placeable."""
        frame = ReferenceFrame("r", FLAT)
        self.assertFalse(frame.established)
        self.assertIsNone(frame.position(6.0))

    def test_position_is_relative_to_the_sources_own_spread(self):
        frame = ReferenceFrame("m", SPREAD)
        self.assertLess(frame.position(1.0), 0.5)
        self.assertGreater(frame.position(7.0), 0.5)

    def test_an_unplaceable_side_is_insufficient_not_aligned(self):
        record = diverge("e1", recipient_frame=FLAT)
        self.assertIs(record.direction, DivergenceDirection.INSUFFICIENT_REFERENCE)
        self.assertFalse(record.is_evidence)

    def test_a_raw_offset_between_the_sides_is_not_a_divergence(self):
        """Observer sits two points below the recipient on every event and they
        still agree about ordering. Subtracting would call that a divergence."""
        records = [
            diverge(f"e{i}", observer_value=o, recipient_value=o + 2.0, at=float(i))
            for i, o in enumerate((1.0, 3.0, 5.0))
        ]
        self.assertTrue(all(r.direction is DivergenceDirection.ALIGNED for r in records))


class SkippingTests(unittest.TestCase):
    def test_insufficient_records_are_skipped_not_counted_as_agreement(self):
        profile = build_profile("r", [diverge("e1", recipient_frame=FLAT), diverge("e2", at=1.0)])
        self.assertEqual(profile.skipped_insufficient, ("e1",))
        self.assertEqual(profile.built_from, ("e2",))
        self.assertEqual(profile.evidence_count, 1)

    def test_a_profile_with_no_evidence_has_no_signals_and_no_preferences(self):
        profile = build_profile("r", [diverge("e1", recipient_frame=FLAT)])
        self.assertEqual(profile.signals, ())
        self.assertEqual(profile.known_preferences, ())
        self.assertIsNone(profile.uncertainty)


class TierLadderTests(unittest.TestCase):
    """One observation must never act like four."""

    def _records(self, n, start=0):
        return [diverge(f"e{i}", at=float(i)) for i in range(start, start + n)]

    def test_one_observation_is_an_anecdote(self):
        signal = summarise(self._records(1), frozenset({"e0"}))
        self.assertIs(signal.tier, Tier.ANECDOTE)
        self.assertFalse(signal.usable)

    def test_two_or_three_are_a_weak_tendency(self):
        for n in (2, 3):
            signal = summarise(self._records(n), frozenset(f"e{i}" for i in range(n)))
            self.assertIs(signal.tier, Tier.WEAK_TENDENCY, n)
            self.assertFalse(signal.usable)

    def test_four_consistent_and_recent_are_usable(self):
        signal = summarise(self._records(4), frozenset(f"e{i}" for i in range(4)))
        self.assertIs(signal.tier, Tier.USABLE_CALIBRATION)
        self.assertTrue(signal.usable)

    def test_stale_evidence_does_not_become_usable(self):
        """Enough observations, none of them recent on the recipient's timeline."""
        signal = summarise(self._records(4), frozenset())
        self.assertIs(signal.tier, Tier.WEAK_TENDENCY)

    def test_recency_is_measured_on_the_whole_timeline_not_within_the_signature(self):
        terse = [diverge(f"t{i}", at=float(i)) for i in range(4)]
        later = [diverge(f"q{i}", signature="question", recipient_value=2.0, at=float(10 + i))
                 for i in range(policy.RECENCY_WINDOW_EVENTS)]
        profile = build_profile("r", terse + later)
        self.assertIs(profile.signal_for("terse_acknowledgement").tier, Tier.WEAK_TENDENCY)


class ContradictionTests(unittest.TestCase):
    """Contradiction widens uncertainty. It never averages reality into soup."""

    def _mixed(self, supporting, contradicting):
        records = [diverge(f"s{i}", recipient_value=7.0, at=float(i)) for i in range(supporting)]
        records += [diverge(f"c{i}", recipient_value=1.0, at=float(100 + i)) for i in range(contradicting)]
        return records

    def test_adding_a_contradiction_never_narrows_uncertainty(self):
        widths = []
        for contra in range(4):
            records = self._mixed(4, contra)
            signal = summarise(records, frozenset(r.event_id for r in records))
            widths.append(signal.uncertainty_width)
        self.assertEqual(widths, sorted(widths))
        self.assertLess(widths[0], widths[-1])

    def test_adding_a_contradiction_never_raises_a_tier(self):
        order = [Tier.CONTESTED, Tier.ANECDOTE, Tier.WEAK_TENDENCY, Tier.USABLE_CALIBRATION]
        previous = None
        for contra in range(4):
            records = self._mixed(4, contra)
            signal = summarise(records, frozenset(r.event_id for r in records))
            rank = order.index(signal.tier)
            if previous is not None:
                self.assertLessEqual(rank, previous)
            previous = rank

    def test_a_contested_signal_keeps_both_sides_rather_than_a_middle(self):
        records = self._mixed(3, 2)
        signal = summarise(records, frozenset(r.event_id for r in records))
        self.assertIs(signal.tier, Tier.CONTESTED)
        self.assertEqual(len(signal.supporting), 3)
        self.assertEqual(len(signal.contradicting), 2)
        self.assertIn(signal.direction, (DivergenceDirection.OBSERVER_UNDER,
                                         DivergenceDirection.OBSERVER_OVER))
        self.assertFalse(signal.usable)

    def test_alignment_contradicts_a_claimed_divergence(self):
        """'The two sides agreed here' is evidence against a divergence signal,
        not neutral filler."""
        records = [diverge(f"d{i}", recipient_value=7.0, at=float(i)) for i in range(3)]
        records += [diverge(f"a{i}", recipient_value=2.0, at=float(10 + i)) for i in range(3)]
        signal = summarise(records, frozenset(r.event_id for r in records))
        self.assertTrue(signal.contradicting)
        self.assertFalse(signal.usable)

    def test_a_contested_signal_is_never_stated_as_a_correction(self):
        records = self._mixed(3, 2)
        profile = build_profile("r", records)
        reading = read_event(estimate("new"), profile)
        self.assertEqual(profile.known_preferences, ())
        self.assertIn("less certain, not as corrected", reading.may_state[-1])


class HypothesisTests(unittest.TestCase):
    """A vignette answer may propose a signal and may never be one."""

    def test_a_vignette_hypothesis_carries_zero_weight(self):
        context = OnboardingContext("r", vignette_answers=(
            ("terse_acknowledgement", DivergenceDirection.OBSERVER_UNDER),))
        hypothesis, = context.as_hypotheses()
        self.assertEqual(hypothesis.evidence_weight, 0.0)
        self.assertIs(hypothesis.status, HypothesisStatus.OPEN)

    def test_only_vignettes_may_originate_a_hypothesis(self):
        with self.assertRaises(ValueError):
            CalibrationHypothesis("r", "apology", DivergenceDirection.ALIGNED, origin="IRI")

    def test_a_supported_hypothesis_adds_nothing_to_the_signals(self):
        records = [diverge(f"e{i}", recipient_value=7.0, at=float(i)) for i in range(4)]
        guess = CalibrationHypothesis("r", "terse_acknowledgement",
                                      DivergenceDirection.OBSERVER_UNDER, "vignette")
        without = build_profile("r", records)
        with_guess = build_profile("r", records, (guess,))
        self.assertEqual(without.signals, with_guess.signals)
        self.assertIs(with_guess.hypotheses[0].status, HypothesisStatus.SUPPORTED)

    def test_real_feedback_kills_a_wrong_vignette_guess(self):
        records = [diverge(f"e{i}", recipient_value=1.0, at=float(i)) for i in range(3)]
        guess = CalibrationHypothesis("r", "terse_acknowledgement",
                                      DivergenceDirection.OBSERVER_UNDER, "vignette")
        profile = build_profile("r", records, (guess,))
        self.assertIs(profile.hypotheses[0].status, HypothesisStatus.KILLED)

    def test_a_hypothesis_with_no_evidence_stays_open_and_is_never_a_preference(self):
        guess = CalibrationHypothesis("r", "apology", DivergenceDirection.OBSERVER_UNDER, "vignette")
        profile = build_profile("r", [], (guess,))
        self.assertIs(profile.hypotheses[0].status, HypothesisStatus.OPEN)
        self.assertEqual(profile.known_preferences, ())


class ReadingTests(unittest.TestCase):
    def test_impact_of_a_new_event_is_unknown_at_every_tier(self):
        for records in ([], [diverge("e0")], [diverge(f"e{i}", at=float(i)) for i in range(6)]):
            profile = build_profile("r", records)
            self.assertEqual(read_event(estimate("new"), profile).impact, "UNKNOWN")

    def test_the_never_statable_list_is_attached_to_every_reading(self):
        reading = read_event(estimate("new"), None)
        self.assertEqual(reading.must_not_state, policy.NEVER_STATABLE)
        self.assertTrue(any("what the recipient felt" in line for line in reading.must_not_state))

    def test_no_history_reads_as_ambiguous_rather_than_as_low_uptake(self):
        reading = read_event(estimate("new"), build_profile("r", []))
        self.assertIn("ambiguous", reading.may_state[-1])
        self.assertIsNone(reading.calibration)

    def test_only_usable_signals_become_stated_preferences(self):
        few = build_profile("r", [diverge(f"e{i}", recipient_value=7.0, at=float(i)) for i in range(2)])
        many = build_profile("r", [diverge(f"e{i}", recipient_value=7.0, at=float(i)) for i in range(4)])
        self.assertEqual(few.known_preferences, ())
        self.assertEqual(len(many.known_preferences), 1)

    def test_the_serialised_profile_carries_its_placeholder_provenance(self):
        payload = build_profile("r", [diverge("e0")]).to_jsonable()
        self.assertEqual(payload["policy_provenance"], model.PROVENANCE)
        self.assertEqual(payload["policy_provenance"], "synthetic_placeholder")


class ProfileViewTests(unittest.TestCase):
    """Every field the brief asked for is a view over signals, so each one can
    name the observations it came from."""

    def setUp(self):
        records = [diverge(f"e{i}", recipient_value=7.0, at=float(i)) for i in range(4)]
        records += [diverge(f"a{i}", signature="apology", recipient_value=2.0, at=float(10 + i))
                    for i in range(4)]
        self.profile = build_profile("r", records)

    def test_every_signal_names_its_events(self):
        for signal in self.profile.signals:
            self.assertTrue(signal.supporting or signal.contradicting)
            for event_id in signal.supporting + signal.contradicting:
                self.assertIn(event_id, self.profile.built_from)

    def test_the_briefs_fields_resolve_to_signals(self):
        self.assertIsNotNone(self.profile.terse_acknowledgement_history)
        self.assertEqual(len(self.profile.repair_style_history), 2)
        self.assertEqual(self.profile.evidence_count, 8)
        self.assertEqual(self.profile.recency, 13.0)

    def test_uncertainty_is_the_widest_band_not_an_average(self):
        widths = [s.uncertainty_width for s in self.profile.signals]
        self.assertEqual(self.profile.uncertainty, max(widths))


class DemoTests(unittest.TestCase):
    def test_the_same_episode_reads_differently_with_and_without_history(self):
        from calibration import demo

        readings = {}
        for history in demo.HISTORIES:
            profile = build_profile(history.recipient, demo.generate(history))
            readings[history.recipient] = read_event(
                ObserverEstimate(demo.EPISODE.event_id, history.recipient,
                                 demo.EPISODE.move_signature, demo.EPISODE.value,
                                 demo.EPISODE.estimator, demo.EPISODE.estimator_kind,
                                 demo.EPISODE.observed_at),
                profile,
            )
        self.assertIsNone(readings["newcomer"].calibration)
        self.assertIs(readings["terse_well_long"].calibration.tier, Tier.USABLE_CALIBRATION)
        self.assertIs(readings["terse_well_long"].calibration.direction,
                      DivergenceDirection.OBSERVER_UNDER)
        self.assertIs(readings["terse_contested"].calibration.tier, Tier.CONTESTED)
        self.assertIs(readings["terse_stale"].calibration.tier, Tier.WEAK_TENDENCY)
        self.assertTrue(all(r.impact == "UNKNOWN" for r in readings.values()))

    def test_a_recipient_who_answers_flat_yields_nothing_learnable(self):
        from calibration import demo

        history = next(h for h in demo.HISTORIES if h.recipient == "flat_responder")
        profile = build_profile("flat_responder", demo.generate(history))
        self.assertEqual(profile.signals, ())
        self.assertEqual(len(profile.skipped_insufficient), history.length)


if __name__ == "__main__":
    unittest.main()
