"""Counterfactual demo: does the same episode read differently with history?

Synthetic data only, generated deterministically here. No real user, no real
partner, nothing learned from any corpus. The point is not to show that the
system is right — it is to show that the SHAPE of what it says changes with
personal evidence and stays UNKNOWN where it should.

The episode held fixed across every profile:

    A: Прости, я перегнул.          (apology)
    B: Ладно.                       (terse_acknowledgement)

The system's own reading of B is identical in all cases: a terse acknowledgement
scores low on uptake. What differs is only the recipient's own history.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import (
    CalibrationHypothesis,
    DivergenceDirection,
    EstimatorKind,
    ObserverEstimate,
    RecipientFeedback,
    ReferenceFrame,
    record_divergence,
)
from .policy import build_profile, read_event

#: How the system reads each move signature, on its own 1-7 scale. Fixed across
#: every persona, because the whole demo is about the OTHER side varying.
OBSERVER_READING = {
    "terse_acknowledgement": 2.0,
    "apology": 5.5,
    "long_explanation": 6.0,
    "question": 5.0,
    "advice_giving": 3.5,
    "topic_shift": 2.5,
}

RECIPIENT_SCALE = (1.0, 7.0)

#: Each persona maps a move signature to how that recipient tends to report
#: feeling heard afterwards. Alternating tuples mean an inconsistent history.
PERSONAS: dict[str, dict[str, tuple[float, ...]]] = {
    "terse_lands_well": {
        "terse_acknowledgement": (6.5,),
        "long_explanation": (4.0,),
        "apology": (6.0,),
        "question": (5.5,),
        "advice_giving": (2.5,),
    },
    "terse_lands_badly": {
        "terse_acknowledgement": (2.0,),
        "long_explanation": (6.5,),
        "apology": (5.0,),
        "question": (6.0,),
        "advice_giving": (3.0,),
    },
    "terse_contested": {
        "terse_acknowledgement": (6.5, 2.0),
        "long_explanation": (5.0,),
        "apology": (5.5,),
        "question": (5.0,),
        "advice_giving": (3.0,),
    },
    "tracks_the_system": {
        "terse_acknowledgement": (2.5,),
        "long_explanation": (6.0,),
        "apology": (5.5,),
        "question": (5.0,),
        "advice_giving": (3.5,),
    },
    "advice_lands_well": {
        "terse_acknowledgement": (3.0,),
        "long_explanation": (5.0,),
        "apology": (5.0,),
        "question": (5.0,),
        "advice_giving": (6.5,),
    },
    "flat_responder": {
        "terse_acknowledgement": (6.0,),
        "long_explanation": (6.0,),
        "apology": (6.0,),
        "question": (6.0,),
        "advice_giving": (6.0,),
    },
}

#: Which signatures each history cycles through, and how long it runs.
CYCLE = ("terse_acknowledgement", "long_explanation", "apology", "question",
         "terse_acknowledgement", "advice_giving")


@dataclass(frozen=True, slots=True)
class History:
    recipient: str
    persona: str
    length: int
    #: Events after this index are the 'recent' ones. A history whose terse
    #: evidence all sits before the cutoff is stale by construction.
    terse_stops_at: int | None = None


#: 16 synthetic longitudinal histories. Short ones exist on purpose: a profile
#: that cannot be built is a result, not a gap to fill.
HISTORIES = (
    History("newcomer", "terse_lands_well", 0),
    History("one_event", "terse_lands_well", 1),
    History("three_events", "terse_lands_well", 3),
    History("terse_well_short", "terse_lands_well", 6),
    History("terse_well_long", "terse_lands_well", 18),
    History("terse_badly_short", "terse_lands_badly", 6),
    History("terse_badly_long", "terse_lands_badly", 18),
    History("terse_contested", "terse_contested", 18),
    History("tracks_system", "tracks_the_system", 18),
    History("advice_well", "advice_lands_well", 26),
    History("flat_responder", "flat_responder", 18),
    History("terse_stale", "terse_lands_well", 26, terse_stops_at=13),
    History("terse_well_mid", "terse_lands_well", 12),
    History("terse_badly_mid", "terse_lands_badly", 12),
    History("contested_short", "terse_contested", 8),
    History("advice_well_short", "advice_lands_well", 8),
)


def _recipient_value(persona: str, signature: str, occurrence: int) -> float:
    table = PERSONAS[persona]
    values = table[signature]
    return values[occurrence % len(values)]


def generate(history: History):
    """Build one recipient's stream of paired observations, oldest first.

    Reference frames are built ONLINE from the values that source has produced
    so far, which is the honest version: at event n the system knows only what
    it has already seen, so early events legitimately have no frame.
    """
    records = []
    observer_seen: list[float] = []
    recipient_seen: list[float] = []
    occurrences: dict[str, int] = {}

    for index in range(history.length):
        signature = CYCLE[index % len(CYCLE)]
        if (history.terse_stops_at is not None
                and signature == "terse_acknowledgement"
                and index >= history.terse_stops_at):
            signature = "question"

        occurrences[signature] = occurrences.get(signature, 0) + 1
        observer_value = OBSERVER_READING[signature]
        recipient_value = _recipient_value(history.persona, signature, occurrences[signature] - 1)

        estimate = ObserverEstimate(
            event_id=f"{history.recipient}-e{index:02d}",
            recipient=history.recipient,
            move_signature=signature,
            value=observer_value,
            estimator="spike-reader-v0",
            estimator_kind=EstimatorKind.MODEL,
            observed_at=float(index),
        )
        feedback = RecipientFeedback(
            event_id=estimate.event_id,
            recipient=history.recipient,
            dimension="FELT_HEARD",
            value=recipient_value,
            scale=RECIPIENT_SCALE,
            observed_at=float(index),
            respondent_is_recipient=True,
            believed_source="partner",
        )
        records.append(
            record_divergence(
                estimate,
                feedback,
                ReferenceFrame(estimate.estimator, tuple(observer_seen)),
                ReferenceFrame(history.recipient, tuple(recipient_seen)),
            )
        )
        observer_seen.append(observer_value)
        recipient_seen.append(recipient_value)
    return records


#: The one episode every profile is asked to read.
EPISODE = ObserverEstimate(
    event_id="apology-then-ladno",
    recipient="<filled per profile>",
    move_signature="terse_acknowledgement",
    value=OBSERVER_READING["terse_acknowledgement"],
    estimator="spike-reader-v0",
    estimator_kind=EstimatorKind.MODEL,
    observed_at=999.0,
)


def run() -> None:  # pragma: no cover - reporting only
    print("Episode held fixed for every profile:")
    print("    A: Прости, я перегнул.   (apology)")
    print("    B: Ладно.                (terse_acknowledgement)")
    print(f"System's own reading of B: {OBSERVER_READING['terse_acknowledgement']:.1f}/7 "
          f"— identical in all rows below.\n")
    header = f"{'recipient':20s} {'evts':>4s} {'used':>4s} {'skip':>4s} {'tier':<20s} {'sup/con':>8s} {'unc':>5s}  reading"
    print(header)
    print("-" * len(header))
    for history in HISTORIES:
        records = generate(history)
        profile = build_profile(history.recipient, records)
        reading = read_event(
            ObserverEstimate(
                event_id=EPISODE.event_id,
                recipient=history.recipient,
                move_signature=EPISODE.move_signature,
                value=EPISODE.value,
                estimator=EPISODE.estimator,
                estimator_kind=EPISODE.estimator_kind,
                observed_at=EPISODE.observed_at,
            ),
            profile,
        )
        signal = reading.calibration
        tier = signal.tier.value if signal else "—"
        counts = f"{len(signal.supporting)}/{len(signal.contradicting)}" if signal else "—"
        unc = f"{signal.uncertainty_width:.2f}" if signal else "—"
        print(f"{history.recipient:20s} {history.length:4d} {profile.evidence_count:4d} "
              f"{len(profile.skipped_insufficient):4d} {tier:<20s} {counts:>8s} {unc:>5s}  "
              f"{reading.may_state[-1]}")

    print()
    for recipient in ("terse_well_long", "advice_well", "flat_responder"):
        history = next(h for h in HISTORIES if h.recipient == recipient)
        profile = build_profile(recipient, generate(history))
        usable = profile.known_preferences or ("(none usable)",)
        print(f"  everything usable for {recipient}: " + "; ".join(usable))

    print(f"\nimpact for this episode, every single row: "
          f"{read_event(EPISODE, None).impact} — no recipient feedback exists for a new event")
    print("never statable, at any tier:")
    for line in read_event(EPISODE, None).must_not_state:
        print(f"    - {line}")

    print("\n-- a vignette guess meeting real evidence --")
    for recipient in ("terse_well_long", "terse_badly_long"):
        history = next(h for h in HISTORIES if h.recipient == recipient)
        guess = CalibrationHypothesis(
            recipient=recipient,
            move_signature="terse_acknowledgement",
            expected_direction=DivergenceDirection.OBSERVER_UNDER,
            origin="vignette",
        )
        profile = build_profile(recipient, generate(history), (guess,))
        resolved = profile.hypotheses[0]
        print(f"  {recipient:18s} vignette said OBSERVER_UNDER -> {resolved.status.value:9s} "
              f"(support {len(resolved.supporting)}, contra {len(resolved.contradicting)}, "
              f"weight {resolved.evidence_weight})")


if __name__ == "__main__":  # pragma: no cover
    run()
