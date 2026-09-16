"""InterventionOntology interface contract — the input shape only.

This module defines WHAT DyadicState must hand a future intervention layer. It
deliberately contains no strategy taxonomy, no policy and no text generation:
docs/research/intervention-interface.md §0. Nothing here produces user-facing
advice, and `decide()` is a stub that always abstains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .model import HypothesisStatus, to_jsonable
from .state import HypothesisLedger, SafetyAccumulator


class Act(str, Enum):
    INTERVENE = "intervene"
    ABSTAIN = "abstain"


class StrategyClass(str, Enum):
    """Five classes, matching docs/research/intervention-ontology-review.md §2.
    Kept this short on purpose: PCA over 31 CIRS+SSIRS items yields 4 factors, so
    an eleven-way taxonomy is not something we can estimate."""

    REFLECT = "reflect"
    REFRAME = "reframe"
    SLOW_DOWN = "slow_down"
    SURFACE_PERSPECTIVE = "surface_perspective"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class InterventionContext:
    """Everything the intervention layer is allowed to see, and nothing else.

    Note what is absent: no relationship score, no person attributes, no
    predicted outcome, no free-text summary. If a future layer needs something
    that is not here, that is a change to this contract, reviewed on its own.
    """

    episode_id: str
    candidate_hypotheses: tuple[dict, ...]
    recent_transitions: tuple[dict, ...]
    evidence_event_ids: tuple[str, ...]
    counterevidence_event_ids: tuple[str, ...]
    uncertainty: dict
    safety_flags: dict


@dataclass(frozen=True, slots=True)
class InterventionDecision:
    """Outcome fields are NOT set here — they are measured afterwards as a shift
    in DyadicState. `abstain` is recorded as explicitly as `intervene`, because
    unnecessary and missed intervention are computed from the two together and
    vanish from the data if holds go unrecorded."""

    act: Act
    target: str | None
    strategy_class: StrategyClass
    rationale_evidence: tuple[str, ...] = ()
    contraindications: tuple[str, ...] = field(default_factory=tuple)


def build_context(
    episode_id: str,
    ledger: HypothesisLedger,
    safety: SafetyAccumulator,
) -> InterventionContext:
    live = ledger.competing()
    evidence: list[str] = []
    counter: list[str] = []
    coverages: list[float] = []
    unobserved: set[str] = set()

    for h in live:
        evidence.extend(h.evidence_for)
        counter.extend(h.evidence_against)
        cov = h.components.observation_coverage
        if cov is not None:
            coverages.append(cov)
        unobserved.update(h.unobserved_slots)

    recent = [t for t in ledger.transitions if t["episode_id"] == episode_id]

    return InterventionContext(
        episode_id=episode_id,
        candidate_hypotheses=tuple(to_jsonable(h) for h in live),
        recent_transitions=tuple(recent),
        evidence_event_ids=tuple(evidence),
        counterevidence_event_ids=tuple(counter),
        uncertainty={
            # A list, not an average: collapsing coverage into one number is the
            # first step towards the score this project forbids.
            "observation_coverage_per_hypothesis": coverages,
            "unobservable_slots": sorted(unobserved),
            "n_competing_hypotheses": len(live),
            "has_recurring_hypothesis": any(
                h.status is HypothesisStatus.RECURRING for h in live
            ),
        },
        safety_flags=safety.as_flags(),
    )


def contraindications(context: InterventionContext) -> list[str]:
    """Reasons a future layer must not act. Computed, not authored per-case."""
    out: list[str] = []
    gate = context.safety_flags.get("coercive_control_accumulation", {})
    if gate.get("gate_open"):
        # safety-policy §9-§10: no forced symmetry, no joint mediation loop.
        out.append("safety_gate_open__symmetric_advice_suppressed")
    if not context.uncertainty["has_recurring_hypothesis"]:
        out.append("no_recurring_pattern__single_episode_is_not_a_pattern")
    if context.uncertainty["n_competing_hypotheses"] > 1:
        out.append("competing_hypotheses_unresolved")
    if context.uncertainty["unobservable_slots"]:
        out.append("pattern_depends_on_unobservable_slots")
    return out


def decide(context: InterventionContext) -> InterventionDecision:
    """Stub. Always abstains, and records why.

    Present so the contract is exercised end-to-end by the spike, not because a
    decision policy exists. Writing one before DyadicState has been falsified
    would be building the advice generator this phase explicitly excludes.
    """
    blockers = contraindications(context)
    return InterventionDecision(
        act=Act.ABSTAIN,
        target=None,
        strategy_class=StrategyClass.NONE,
        rationale_evidence=context.evidence_event_ids,
        contraindications=tuple(blockers),
    )
