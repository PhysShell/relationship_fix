"""Update policy: when one piece of feedback is allowed to change anything.

The mechanics are the deliverable; the numbers are placeholders
(`model.PROVENANCE`). Three properties are meant to survive any later
re-estimation of the constants, and `tests/test_calibration.py` pins all three:

  1. one observation never acts like four;
  2. a contradicting observation never narrows uncertainty and never raises a
     tier — contradiction WIDENS, it does not average two realities into soup;
  3. a record with no established reference frame is skipped, not counted as
     agreement.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import (
    PROVENANCE,
    SkippedObservation,
    CalibrationHypothesis,
    CalibrationSignal,
    DivergenceDirection,
    DivergenceRecord,
    HypothesisStatus,
    ObserverEstimate,
    PersonalCalibrationProfile,
    Tier,
)

#: Supporting records needed before a tendency may be acted on at all.
USABLE_MIN_SUPPORT = 4
#: Recency is measured on the RECIPIENT'S WHOLE TIMELINE, not within the move
#: signature's own records. Counting "the last five times this move happened"
#: would call a pattern recent that stopped two years ago, which is the exact
#: staleness hole this window exists to close.
RECENCY_WINDOW_EVENTS = 10
RECENT_MIN_SUPPORT = 2
#: Below this share of agreement the signal is CONTESTED and never usable.
CONSISTENCY_FLOOR = 0.75
#: Uncertainty band. Shrinks with supporting evidence, widens with contradiction.
BASE_UNCERTAINTY = 0.5
CONTRADICTION_WIDENING = 0.25
#: A vignette guess dies after this many contradicting observations.
HYPOTHESIS_KILL_COUNT = 2


def _uncertainty(supporting: int, contradicting: int) -> float:
    if supporting == 0:
        return 1.0
    return min(1.0, BASE_UNCERTAINTY / (supporting ** 0.5) + CONTRADICTION_WIDENING * contradicting)


def _tier(supporting: int, contradicting: int, consistency: float, recent_supporting: int) -> Tier:
    if supporting == 0:
        return Tier.CONTESTED
    if contradicting and consistency < CONSISTENCY_FLOOR:
        return Tier.CONTESTED
    if supporting >= USABLE_MIN_SUPPORT and consistency >= CONSISTENCY_FLOOR and recent_supporting >= RECENT_MIN_SUPPORT:
        return Tier.USABLE_CALIBRATION
    if supporting >= 2:
        return Tier.WEAK_TENDENCY
    return Tier.ANECDOTE


def summarise(
    records: list[DivergenceRecord],
    recent_event_ids: frozenset[str] = frozenset(),
) -> CalibrationSignal | None:
    """Turn one recipient's records for one move signature into a signal.

    The dominant direction is whichever resolved direction occurs most often;
    every OTHER resolved direction contradicts it, ALIGNED included. Treating
    "the two sides agreed here" as neutral would let a signal claiming a
    divergence survive a pile of evidence that there is none.

    `recent_event_ids` comes from the recipient's whole timeline (see
    RECENCY_WINDOW_EVENTS) and is what stops a dead pattern from staying usable.
    """
    evidence = [r for r in records if r.is_evidence]
    if not evidence:
        return None

    counts: dict[DivergenceDirection, int] = {}
    for record in evidence:
        counts[record.direction] = counts.get(record.direction, 0) + 1
    dominant = max(sorted(counts, key=lambda d: d.value), key=lambda d: counts[d])

    ordered = sorted(evidence, key=lambda r: r.observed_at)
    supporting = tuple(r.event_id for r in ordered if r.direction is dominant)
    contradicting = tuple(r.event_id for r in ordered if r.direction is not dominant)
    recent_supporting = sum(
        1 for r in ordered if r.direction is dominant and r.event_id in recent_event_ids
    )
    consistency = len(supporting) / (len(supporting) + len(contradicting))

    return CalibrationSignal(
        recipient=ordered[0].recipient,
        move_signature=ordered[0].move_signature,
        direction=dominant,
        supporting=supporting,
        contradicting=contradicting,
        tier=_tier(len(supporting), len(contradicting), consistency, recent_supporting),
        consistency=consistency,
        uncertainty_width=_uncertainty(len(supporting), len(contradicting)),
        latest_at=ordered[-1].observed_at,
        recent_supporting=recent_supporting,
    )


def resolve_hypotheses(
    hypotheses: tuple[CalibrationHypothesis, ...],
    records: list[DivergenceRecord],
) -> tuple[CalibrationHypothesis, ...]:
    """Real feedback confirms or kills a vignette guess. It never promotes it.

    A SUPPORTED hypothesis adds nothing to any signal: the signal is built from
    the divergence records, which exist independently of whether anyone ever
    answered a vignette.
    """
    resolved = []
    for hypothesis in hypotheses:
        relevant = [r for r in records if r.is_evidence and r.move_signature == hypothesis.move_signature]
        supporting = tuple(r.event_id for r in relevant if r.direction is hypothesis.expected_direction)
        contradicting = tuple(r.event_id for r in relevant if r.direction is not hypothesis.expected_direction)
        if len(contradicting) >= HYPOTHESIS_KILL_COUNT and not supporting:
            status = HypothesisStatus.KILLED
        elif supporting and not contradicting:
            status = HypothesisStatus.SUPPORTED
        else:
            status = HypothesisStatus.OPEN
        resolved.append(
            CalibrationHypothesis(
                recipient=hypothesis.recipient,
                move_signature=hypothesis.move_signature,
                expected_direction=hypothesis.expected_direction,
                origin=hypothesis.origin,
                status=status,
                supporting=supporting,
                contradicting=contradicting,
            )
        )
    return tuple(resolved)


def build_profile(
    recipient: str,
    records: list[DivergenceRecord],
    hypotheses: tuple[CalibrationHypothesis, ...] = (),
) -> PersonalCalibrationProfile:
    """The only constructor of a profile. Takes divergence records and nothing else.

    Note what is missing from the signature: no trait scores, no vignette
    answers, no free-form attributes, no observer estimates on their own. A
    profile that cannot be built from those cannot accidentally contain them.
    """
    for record in records:
        if not isinstance(record, DivergenceRecord):
            raise TypeError(
                f"a calibration profile is built from DivergenceRecord only, got "
                f"{type(record).__name__}: an observation about a person is not a claim about them"
            )
        if record.recipient != recipient:
            raise ValueError("a profile is scoped to one recipient; records from another do not belong")

    by_signature: dict[str, list[DivergenceRecord]] = {}
    skipped = []
    used = []
    for record in sorted(records, key=lambda r: (r.observed_at, r.event_id)):
        if not record.is_evidence:
            skipped.append(SkippedObservation(record.event_id, record.move_signature,
                                              record.insufficiency_reason))
            continue
        by_signature.setdefault(record.move_signature, []).append(record)
        used.append(record.event_id)

    recent_event_ids = frozenset(used[-RECENCY_WINDOW_EVENTS:])
    signals = tuple(
        signal
        for signature in sorted(by_signature)
        if (signal := summarise(by_signature[signature], recent_event_ids)) is not None
    )
    return PersonalCalibrationProfile(
        recipient=recipient,
        signals=signals,
        hypotheses=resolve_hypotheses(hypotheses, records),
        built_from=tuple(used),
        skipped_insufficient=tuple(skipped),
    )


@dataclass(frozen=True, slots=True)
class EventReading:
    """What the system is allowed to say about ONE new event.

    `impact` is always UNKNOWN here and that is not a placeholder: a new event
    has no recipient feedback by definition, and the whole architecture exists
    so that this stays UNKNOWN instead of being filled by a prediction.
    """

    event_id: str
    observer_estimate: ObserverEstimate
    impact: str                       # always 'UNKNOWN'
    calibration: CalibrationSignal | None
    may_state: tuple[str, ...]
    must_not_state: tuple[str, ...]

    def render(self) -> str:  # pragma: no cover - formatting only
        head = f"[{self.event_id}] observer: {self.observer_estimate.move_signature} " \
               f"= {self.observer_estimate.value:.2f} | impact: {self.impact}"
        if self.calibration is None:
            return head + "\n    calibration: none for this move signature"
        return (head + f"\n    calibration: {self.calibration.tier.value} "
                       f"(support {len(self.calibration.supporting)}, "
                       f"contra {len(self.calibration.contradicting)}, "
                       f"uncertainty {self.calibration.uncertainty_width:.2f})"
                       f"\n    may state: {self.may_state[-1] if self.may_state else '-'}")


#: Things no tier ever unlocks. Kept as data so the demo prints them and a test
#: can assert they are present in every reading.
NEVER_STATABLE = (
    "what the recipient felt (no feedback exists for this event)",
    "a score for the relationship or for either person",
)


def read_event(estimate: ObserverEstimate, profile: PersonalCalibrationProfile | None) -> EventReading:
    """Apply a profile to one new observation. Nothing here produces advice."""
    may = [f"observed: {estimate.move_signature}"]
    signal = profile.signal_for(estimate.move_signature) if profile else None

    if signal is None:
        may.append("no personal history for this move signature; read it as ambiguous")
    elif signal.tier is Tier.USABLE_CALIBRATION:
        may.append(signal.statement())
    elif signal.tier is Tier.CONTESTED:
        may.append(f"this recipient's history for '{estimate.move_signature}' is contradictory; "
                   f"treat the system's reading as less certain, not as corrected")
    else:
        may.append(f"'{estimate.move_signature}' is at tier {signal.tier.value} for this recipient "
                   f"({len(signal.supporting)} observation(s)); not enough to act on")

    return EventReading(
        event_id=estimate.event_id,
        observer_estimate=estimate,
        impact="UNKNOWN",
        calibration=signal,
        may_state=tuple(may),
        must_not_state=NEVER_STATABLE,
    )


POLICY_PROVENANCE = PROVENANCE
