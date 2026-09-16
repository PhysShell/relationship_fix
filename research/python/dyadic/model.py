"""Immutable domain representation for the dyadic-state research spike.

ADR-0001 §Python role 1 (research, JSONL in → JSONL out). NOT production code and
NOT a trusted-state implementation: invariant 1 says trusted state lives outside
any model output, and this module exists to test whether the proposed
representation can hold evidence deterministically at all.

Four levels, deliberately not collapsible into each other
(docs/research/dyadic-state-model.md §1):

    L1 Evidence             what is literally in the source
    L2 BehaviorObservation  locally observable behaviour, carries evidence
    L3 RelationalEvent      several observations linked in time
    L4 StateHypothesis      a competing hypothesis about the unfolding pattern

Nothing here produces advice, a score, or a judgement about a person.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum


class EvidenceStatus(str, Enum):
    """Why a slot in a pattern is or is not filled.

    The whole point of this enum is that ABSENT and COUNTER are different things
    (docs/research/dyadic-state-model.md §4). The WITHDRAWAL research says text
    silence is not observable disengagement, so "we saw nothing" must never be
    stored as "we saw the opposite".

    The vocabulary deliberately mirrors metrics.agreement's estimability states,
    where `not_applicable` ("did not look") is already kept distinct from
    `underpowered_not_estimable` ("looked, too little found").
    """

    SUPPORTING = "supporting"                 # observed, supports the hypothesis
    COUNTER = "counter"                       # observed, argues against it
    ABSENT = "absent"                         # looked for in an observable window, not found
    INSUFFICIENT_OBSERVATION = "insufficient" # could not look (window truncated, no timestamps)
    NOT_APPLICABLE = "not_applicable"         # slot does not apply to this unit


class HypothesisStatus(str, Enum):
    """Ordinal status of a hypothesis, derived by explicit rules — never a score.

    A single scalar "confidence" is what turns into a relationship score, which
    safety-policy §3 forbids. Status is computed from named components by
    `derive_status`, so the derivation is auditable and testable.
    """

    CANDIDATE = "candidate"     # seen once; not yet a pattern
    SUPPORTED = "supported"     # supported within one episode, repeatedly
    RECURRING = "recurring"     # supported across distinct episodes
    WEAKENED = "weakened"       # counterevidence arrived, or support went stale
    RETIRED = "retired"         # withdrawn; kept in the record, never deleted


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    """L1. A verbatim pointer into the source. Never paraphrase."""

    message_id: str
    quote: str

    def validate(self, message_text: str) -> None:
        if self.quote not in message_text:
            raise ValueError(f"evidence for {self.message_id} is not a verbatim substring")


@dataclass(frozen=True, slots=True)
class BehaviorObservation:
    """L2. Locally observable behaviour. Carries its own evidence or does not exist.

    `label` is an opaque string here on purpose: this spike must not import,
    extend or otherwise touch BehaviorOntology v0.1, which is frozen.
    """

    observation_id: str
    label: str
    actor: str
    message_id: str
    evidence: tuple[EvidenceSpan, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError(f"{self.observation_id}: observation without evidence is not admissible")


@dataclass(frozen=True, slots=True)
class RelationalEvent:
    """L3. Several observations linked in time. Still not a state.

    `counterevidence` lives on the event, not only on the hypothesis, because an
    event can be locally well-evidenced and still argue against a larger pattern.
    """

    event_id: str
    event_type: str
    participants: tuple[str, ...]
    episode_id: str
    source_observations: tuple[str, ...]
    supporting_evidence: tuple[EvidenceSpan, ...] = ()
    counterevidence: tuple[EvidenceSpan, ...] = ()
    status: EvidenceStatus = EvidenceStatus.SUPPORTING
    provenance: str = "deterministic_spike"


class EventRelation(str, Enum):
    """How two events relate. Kept small; each must be decidable from ordering
    plus the events' own types, never from an inferred motive."""

    FOLLOWS = "follows"
    RESPONDS_TO = "responds_to"
    ESCALATES = "escalates"
    SOFTENS = "softens"
    REPEATS = "repeats"
    CONTRADICTS = "contradicts"
    REPAIRS = "repairs"
    INTERRUPTS = "interrupts"


@dataclass(frozen=True, slots=True)
class EventEdge:
    from_event: str
    to_event: str
    relation: EventRelation


@dataclass(frozen=True, slots=True)
class ConfidenceComponents:
    """Named components, never summed into one number.

    `observation_coverage` is the share of slots that were actually observable;
    ABSENT and INSUFFICIENT_OBSERVATION lower it instead of counting against the
    hypothesis. That is the structural form of "absence is not counterevidence".
    """

    support_count: int = 0
    counter_count: int = 0
    distinct_episodes: int = 0
    unobservable_slots: int = 0
    observed_slots: int = 0

    @property
    def observation_coverage(self) -> float | None:
        total = self.observed_slots + self.unobservable_slots
        return round(self.observed_slots / total, 4) if total else None

    def _derived(self) -> dict:
        # Coverage is derived, but it must survive serialisation: a trace that
        # drops it lets a reader mistake "we could not look" for "we looked and
        # found nothing", which is the exact confusion this model exists to stop.
        return {"observation_coverage": self.observation_coverage}


@dataclass(frozen=True, slots=True)
class StateHypothesis:
    """L4. One competing hypothesis. There is no single 'current state' anywhere
    in this model — see docs/research/dyadic-state-model.md §3 (Q4)."""

    hypothesis_id: str
    pattern: str
    participants: tuple[str, ...]
    status: HypothesisStatus
    evidence_for: tuple[str, ...] = ()       # event ids
    evidence_against: tuple[str, ...] = ()   # event ids
    supporting_episodes: tuple[str, ...] = ()  # ordered, deduplicated; recurrence is counted from here
    unobserved_slots: tuple[str, ...] = ()   # named slots we could not fill
    first_seen_episode: str | None = None
    last_supported_episode: str | None = None
    components: ConfidenceComponents = field(default_factory=ConfidenceComponents)
    retired_reason: str | None = None


# --- status derivation -------------------------------------------------------

RECURRENCE_EPISODES = 2   # a pattern claimed from one episode is not a pattern
STALENESS_EPISODES = 3    # observable episodes without support before weakening


def derive_status(c: ConfidenceComponents, episodes_since_support: int) -> HypothesisStatus:
    """Explicit, testable rules. No model self-report anywhere.

    Ordering matters: counterevidence is checked before recurrence so that a
    pattern cannot 'outvote' contradicting observations by sheer repetition.
    """
    if c.support_count == 0:
        return HypothesisStatus.CANDIDATE
    if c.counter_count > c.support_count:
        return HypothesisStatus.WEAKENED
    if episodes_since_support >= STALENESS_EPISODES:
        return HypothesisStatus.WEAKENED
    if c.distinct_episodes >= RECURRENCE_EPISODES:
        return HypothesisStatus.RECURRING
    if c.support_count >= 2:
        return HypothesisStatus.SUPPORTED
    return HypothesisStatus.CANDIDATE


def retire(h: StateHypothesis, reason: str) -> StateHypothesis:
    """Retirement is a status change, never a delete: invariant 8 wants findings
    to stay checkable, which includes the ones we withdrew."""
    return replace(h, status=HypothesisStatus.RETIRED, retired_reason=reason)


# --- serialisation -----------------------------------------------------------

def to_jsonable(obj) -> object:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, tuple):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, list):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        # Shallow field walk, NOT dataclasses.asdict: asdict deep-converts nested
        # dataclasses to plain dicts before we get to them, which silently drops
        # every nested _derived() field (observation_coverage was lost this way).
        out = {name: to_jsonable(getattr(obj, name)) for name in obj.__dataclass_fields__}
        derived = getattr(obj, "_derived", None)
        if callable(derived):
            out.update({k: to_jsonable(v) for k, v in derived().items()})
        return out
    return obj


def content_hash(payload: object) -> str:
    """Stable identity for reproducible artifacts (episode ids, traces)."""
    blob = json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
