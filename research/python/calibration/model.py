"""Personal Calibration Loop v0 — the objects, and what they refuse to be.

ADR-0001 §Python role 1 (research spike, JSONL in → JSONL out). Not production
code, no advice, no score, no judgement about a person.

The chain this module exists to make expressible:

    ObserverEstimate + RecipientFeedback  →  DivergenceRecord
    several DivergenceRecords             →  CalibrationSignal
    several CalibrationSignals            →  PersonalCalibrationProfile

and the three edges it exists to make INEXPRESSIBLE:

    ObserverEstimate   ↛  RecipientFeedback / PerceivedImpact
    PsychometricTrait  ↛  PersonalCalibrationProfile
    VignetteAnswer     ↛  a claim about actual behaviour

The separation is physical, not documentary. `RecipientFeedback` cannot be built
without `respondent_is_recipient=True`; `DivergenceRecord` cannot be built from
one side; `PersonalCalibrationProfile.build` takes divergence records and
nothing else. `tests/test_calibration.py` also scans this package's source for
the forbidden edges, because this project has a rich history of "we simply will
not confuse these two fields" becoming an inference hole three commits later.

Two empirical constraints from TRACK 4 are baked in rather than commented on
(docs/research/perceived-impact-audit.md):

  - the two sides sit on different scales with a systematic offset, so a
    divergence is NEVER a subtraction. Each side is placed inside its OWN prior
    distribution and only relative positions are compared.
  - a side with too little history has no distribution, so there is no position
    and therefore no divergence — INSUFFICIENT_REFERENCE, never "aligned".
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum

#: A source needs this many prior observations before its own scale use is known
#: well enough to place a new value inside it. Spike-only; see PROVENANCE.
MIN_REFERENCE_OBSERVATIONS = 4

#: How far apart two relative positions must sit to count as a divergence rather
#: than noise. Spike-only; see PROVENANCE.
DIVERGENCE_POSITION_GAP = 0.34

#: Every threshold in this package is a placeholder chosen to make the mechanics
#: testable. None of them is estimated from data, and none may be shipped.
#: Same discipline as dyadic.state.SAFETY_POLICY_PROVENANCE.
PROVENANCE = "synthetic_placeholder"

#: Observable move signatures, from L2 labels only. A signature says what was in
#: the message, never what it meant to anyone.
MOVE_SIGNATURES = (
    "terse_acknowledgement",
    "apology",
    "long_explanation",
    "question",
    "advice_giving",
    "topic_shift",
)


class EstimatorKind(str, Enum):
    HUMAN_OBSERVER = "human_observer"
    MODEL = "model"


class DivergenceDirection(str, Enum):
    """What the two sides did relative to their own distributions.

    INSUFFICIENT_REFERENCE is the important member. It is not a weak ALIGNED:
    it means at least one side has no established scale use yet, so the
    comparison has no meaning. It carries no evidence weight anywhere.
    """

    OBSERVER_UNDER = "observer_under"   # observer ranked it low, recipient high
    OBSERVER_OVER = "observer_over"     # observer ranked it high, recipient low
    ALIGNED = "aligned"
    INSUFFICIENT_REFERENCE = "insufficient_reference"


class Tier(str, Enum):
    """How much a body of evidence is allowed to be used for.

    The ladder is the whole point: one observation may never act like four, and
    contradicted evidence may never act like consistent evidence.
    """

    ANECDOTE = "anecdote"
    WEAK_TENDENCY = "weak_tendency"
    USABLE_CALIBRATION = "usable_calibration"
    CONTESTED = "contested"             # widen uncertainty; never usable


@dataclass(frozen=True, slots=True)
class ObserverEstimate:
    """What the system (or a human observer) read off the message.

    About the message and its author. Never about the recipient's experience —
    that is `PredictedImpact` in docs/research/perceived-impact-schema.md, and
    it is deliberately absent from this module because the calibration loop has
    no use for it.
    """

    event_id: str
    recipient: str              # whom the move was addressed to; NOT who rated it
    move_signature: str
    value: float                # on the estimator's own scale
    estimator: str
    estimator_kind: EstimatorKind
    observed_at: float

    def __post_init__(self) -> None:
        if self.move_signature not in MOVE_SIGNATURES:
            raise ValueError(f"unknown move signature {self.move_signature!r}")


@dataclass(frozen=True, slots=True)
class RecipientFeedback:
    """What the recipient said about receiving it. The only source of impact.

    `respondent_is_recipient` is required and must be True. It is the boolean
    fuse against the one way foreign data gets into the wrong table: an observer
    asked "would this make the discloser feel heard?" produces a row that is
    indistinguishable in shape from a recipient's own answer, and differs only
    in who answered.
    """

    event_id: str
    recipient: str
    dimension: str              # FELT_HEARD; see perceived-impact-schema.md §2
    value: float
    scale: tuple[float, float]
    observed_at: float
    respondent_is_recipient: bool
    believed_source: str | None = None   # what the recipient thought at the time

    def __post_init__(self) -> None:
        if not self.respondent_is_recipient:
            raise ValueError(
                "RecipientFeedback requires respondent_is_recipient=True; "
                "an observer's estimate of the recipient's experience is a "
                "PredictedImpact and does not belong in this chain"
            )
        low, high = self.scale
        if not low <= self.value <= high:
            raise ValueError(f"value {self.value} outside its own scale {self.scale}")


@dataclass(frozen=True, slots=True)
class ReferenceFrame:
    """One source's own prior values, used to place a new one inside them.

    Exists because of the 2.2-point offset between recipients and experts in
    docs/research/perceived-impact-audit.md §3.2: comparing raw values across
    sides measures calibration, not agreement.
    """

    source_id: str
    values: tuple[float, ...]

    @property
    def established(self) -> bool:
        return len(self.values) >= MIN_REFERENCE_OBSERVATIONS and len(set(self.values)) > 1

    def position(self, value: float) -> float | None:
        """Where `value` sits in this source's own spread, in [0, 1].

        None when the frame is not established — a source that has said the same
        thing four times has no spread to place anything inside.
        """
        if not self.established:
            return None
        below = sum(1 for v in self.values if v < value)
        ties = sum(1 for v in self.values if v == value)
        return (below + 0.5 * ties) / len(self.values)


@dataclass(frozen=True, slots=True)
class DivergenceRecord:
    """One event where the two sides were compared. Requires BOTH sides.

    There is no constructor taking a single side, and `direction` is computed,
    never passed in. The recipient's scope travels with it: a divergence is
    always about this recipient, never about people in general.
    """

    event_id: str
    recipient: str
    move_signature: str
    observer: ObserverEstimate
    feedback: RecipientFeedback
    observer_position: float | None
    recipient_position: float | None
    direction: DivergenceDirection
    observed_at: float

    @property
    def is_evidence(self) -> bool:
        """Only a resolved comparison is evidence. INSUFFICIENT_REFERENCE is not."""
        return self.direction is not DivergenceDirection.INSUFFICIENT_REFERENCE


def record_divergence(
    observer: ObserverEstimate,
    feedback: RecipientFeedback,
    observer_frame: ReferenceFrame,
    recipient_frame: ReferenceFrame,
) -> DivergenceRecord:
    """The only way a DivergenceRecord comes into existence."""
    if observer.event_id != feedback.event_id:
        raise ValueError("a divergence compares the two sides of ONE event")
    if observer.recipient != feedback.recipient:
        raise ValueError("a divergence is scoped to one recipient")

    observer_position = observer_frame.position(observer.value)
    recipient_position = recipient_frame.position(feedback.value)

    if observer_position is None or recipient_position is None:
        direction = DivergenceDirection.INSUFFICIENT_REFERENCE
    else:
        gap = recipient_position - observer_position
        if gap >= DIVERGENCE_POSITION_GAP:
            direction = DivergenceDirection.OBSERVER_UNDER
        elif gap <= -DIVERGENCE_POSITION_GAP:
            direction = DivergenceDirection.OBSERVER_OVER
        else:
            direction = DivergenceDirection.ALIGNED

    return DivergenceRecord(
        event_id=observer.event_id,
        recipient=observer.recipient,
        move_signature=observer.move_signature,
        observer=observer,
        feedback=feedback,
        observer_position=observer_position,
        recipient_position=recipient_position,
        direction=direction,
        observed_at=max(observer.observed_at, feedback.observed_at),
    )


@dataclass(frozen=True, slots=True)
class CalibrationSignal:
    """One reusable correction, with the observations it came from attached.

    `supporting` and `contradicting` are event ids, not counts, so the question
    "from which concrete observations did this arise?" is answerable by reading
    the object rather than by trusting a summary.
    """

    recipient: str
    move_signature: str
    direction: DivergenceDirection
    supporting: tuple[str, ...]
    contradicting: tuple[str, ...]
    tier: Tier
    consistency: float
    uncertainty_width: float
    latest_at: float
    recent_supporting: int

    @property
    def usable(self) -> bool:
        return self.tier is Tier.USABLE_CALIBRATION

    def statement(self) -> str:
        """Plain reading. Never a number about a person."""
        if self.direction is DivergenceDirection.OBSERVER_UNDER:
            return (f"for this recipient, '{self.move_signature}' has historically landed "
                    f"better than the system reads it")
        if self.direction is DivergenceDirection.OBSERVER_OVER:
            return (f"for this recipient, '{self.move_signature}' has historically landed "
                    f"worse than the system reads it")
        return (f"for this recipient, '{self.move_signature}' has historically landed about "
                f"where the system reads it — the system's reading has held up here")


class HypothesisStatus(str, Enum):
    OPEN = "open"
    SUPPORTED = "supported"
    KILLED = "killed"


@dataclass(frozen=True, slots=True)
class CalibrationHypothesis:
    """Where a vignette answer is allowed to live. Carries ZERO evidence weight.

    A vignette answer is a statement about how someone reads a constructed
    example. It is not a fact about their relationship and not a prediction of
    their behaviour, so it may propose a signal and may never be one. Real
    feedback confirms it or kills it; confirmation produces a signal built from
    the divergence records, not from the vignette.
    """

    recipient: str
    move_signature: str
    expected_direction: DivergenceDirection
    origin: str                      # 'vignette' — the only origin v0 accepts
    status: HypothesisStatus = HypothesisStatus.OPEN
    supporting: tuple[str, ...] = ()
    contradicting: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.origin != "vignette":
            raise ValueError("v0 accepts hypotheses from vignettes only")

    @property
    def evidence_weight(self) -> float:
        """Always zero. A hypothesis never competes with an observation."""
        return 0.0


@dataclass(frozen=True, slots=True)
class PersonalCalibrationProfile:
    """Empirical corrections for one recipient. Not a personality profile.

    Every field the brief asked for is a VIEW over signals rather than a stored
    attribute, so each one answers "from which observations?" by construction.
    There is no place to write `user_is_sensitive = true`, because there is no
    free attribute slot at all.
    """

    recipient: str
    signals: tuple[CalibrationSignal, ...]
    hypotheses: tuple[CalibrationHypothesis, ...] = ()
    built_from: tuple[str, ...] = ()          # event ids of every record used
    skipped_insufficient: tuple[str, ...] = ()  # seen, but no established frame

    # -- the brief's fields, as views -------------------------------------

    @property
    def evidence_count(self) -> int:
        return len(self.built_from)

    @property
    def observer_recipient_divergences(self) -> tuple[CalibrationSignal, ...]:
        return tuple(s for s in self.signals if s.direction in
                     (DivergenceDirection.OBSERVER_UNDER, DivergenceDirection.OBSERVER_OVER))

    @property
    def terse_acknowledgement_history(self) -> CalibrationSignal | None:
        return self.signal_for("terse_acknowledgement")

    @property
    def repair_style_history(self) -> tuple[CalibrationSignal, ...]:
        return tuple(s for s in self.signals if s.move_signature in ("apology", "terse_acknowledgement"))

    @property
    def known_preferences(self) -> tuple[str, ...]:
        """Only what is usable, stated in words, with nothing inferred."""
        return tuple(s.statement() for s in self.signals if s.usable)

    @property
    def contested(self) -> tuple[CalibrationSignal, ...]:
        return tuple(s for s in self.signals if s.tier is Tier.CONTESTED)

    @property
    def recency(self) -> float | None:
        return max((s.latest_at for s in self.signals), default=None)

    @property
    def uncertainty(self) -> float | None:
        """Widest band across signals. No single number stands for the person."""
        return max((s.uncertainty_width for s in self.signals), default=None)

    def signal_for(self, move_signature: str) -> CalibrationSignal | None:
        for signal in self.signals:
            if signal.move_signature == move_signature:
                return signal
        return None

    def to_jsonable(self) -> dict:
        return {
            "recipient": self.recipient,
            "evidence_count": self.evidence_count,
            "built_from": list(self.built_from),
            "skipped_insufficient": list(self.skipped_insufficient),
            "policy_provenance": PROVENANCE,
            "signals": [
                {
                    "move_signature": s.move_signature,
                    "direction": s.direction.value,
                    "tier": s.tier.value,
                    "supporting": list(s.supporting),
                    "contradicting": list(s.contradicting),
                    "consistency": round(s.consistency, 3),
                    "uncertainty_width": round(s.uncertainty_width, 3),
                    "recent_supporting": s.recent_supporting,
                    "statement": s.statement(),
                }
                for s in self.signals
            ],
            "hypotheses": [
                {
                    "move_signature": h.move_signature,
                    "expected_direction": h.expected_direction.value,
                    "origin": h.origin,
                    "status": h.status.value,
                    "evidence_weight": h.evidence_weight,
                }
                for h in self.hypotheses
            ],
        }


@dataclass(frozen=True, slots=True)
class OnboardingContext:
    """Questionnaires and vignettes. Deliberately NOT an input to the profile.

    `PersonalCalibrationProfile.build` does not accept this type. Trait scores
    are self-description shown back to the person; they are not an
    interpretation modifier, and Lend an Ear puts R² = 0.000-0.004 between trait
    empathy and actual behaviour on 968 participants behind that refusal.
    """

    recipient: str
    trait_scores: dict[str, float] = field(default_factory=dict)   # IRI / TEQ / …
    vignette_answers: tuple[tuple[str, DivergenceDirection], ...] = ()

    def as_hypotheses(self) -> tuple[CalibrationHypothesis, ...]:
        """Vignettes become OPEN hypotheses. Trait scores become nothing."""
        return tuple(
            CalibrationHypothesis(
                recipient=self.recipient,
                move_signature=signature,
                expected_direction=direction,
                origin="vignette",
            )
            for signature, direction in self.vignette_answers
        )

    def self_description_panel(self) -> dict[str, float]:
        """The only thing trait scores are for: showing them back, unchanged."""
        return dict(self.trait_scores)
