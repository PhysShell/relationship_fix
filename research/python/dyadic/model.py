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

    SUPPORTING = "supporting"                  # observed, supports the hypothesis
    COUNTER = "counter"                        # observed, argues against it
    OBSERVED_ABSENCE = "observed_absence"      # the window WAS observable and the thing was not there
    RIGHT_CENSORED = "right_censored"          # the record ended before the outcome could appear
    INSUFFICIENT_OBSERVATION = "insufficient"  # could not look at all (no window, no timestamps)
    NOT_APPLICABLE = "not_applicable"          # slot does not apply to this unit

    @property
    def is_observation(self) -> bool:
        """OBSERVED_ABSENCE is an observation. We looked, the window was open, and
        the thing was not there. Filing it as 'unobservable' — as the first version
        did — quietly conflated 'we checked and it did not happen' with 'we could
        not check', which are the two things this enum exists to keep apart."""
        return self in (EvidenceStatus.SUPPORTING, EvidenceStatus.COUNTER,
                        EvidenceStatus.OBSERVED_ABSENCE)


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
    # topic lives on MessageNode, not here: it is a property of what was said, not
    # of the behaviour someone coded on top of it.

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
    basis: str = ""            # which rule fired, so a trace can be audited
    provenance: str = "deterministic_spike"


class MessageRelation(str, Enum):
    """L1.5 — raw conversation topology, computed over EVERY message.

    This layer exists because the previous version built interaction topology over
    BehaviorObservations, i.e. over the subset of the conversation the ontology
    found interesting. An unlabelled message in between vanished from the
    topology, so a topic shift two turns later became a direct answer to an
    accusation; and two labels on one message made the topology depend on the
    order observations happened to be listed in. That is selection bias: recover
    conversation structure from raw messages first, attach behaviour afterwards.
    """

    NEXT_BY_OTHER_ACTOR = "next_by_other_actor"
    EXPLICIT_REPLY_TO = "explicit_reply_to"
    TOPIC_CONTINUITY = "topic_continuity"
    TOPIC_DISCONTINUITY = "topic_discontinuity"


@dataclass(frozen=True, slots=True)
class MessageNode:
    """A message as conversation structure, independent of any labelling."""

    message_id: str
    actor: str
    order: int
    timestamp: float | None = None
    topic: str | None = None
    reply_to: str | None = None


@dataclass(frozen=True, slots=True)
class MessageEdge:
    from_message: str
    to_message: str
    relation: MessageRelation
    basis: str


class InteractionRelation(str, Enum):
    """L2.5 — the missing floor.

    An event used to be built from labels co-occurring inside one episode, which
    made L3 a bag of labels wearing an interaction model's coat: two people being
    negative anywhere in forty messages became `attack_attack` even if neither
    turn answered the other. Events are now built from RELATIONS between
    observations, so ordering and direction are load-bearing.

    Every relation must be decidable from ordering, actor and the observations'
    own recorded topic — never from an inferred motive. `topic` is supplied by the
    corpus exactly as labels are: topic continuity is not deterministically
    decidable from raw text, and pretending otherwise would hide a classifier
    inside a predicate.
    """

    # DETERMINISTIC — computable from the log, safe to assert.
    ADJACENT_CROSS_ACTOR_TURN = "adjacent_cross_actor_turn"  # the next turn by someone else
    EXPLICIT_REPLY = "explicit_reply"                        # the log itself says what it answers
    TOPIC_CONTINUITY = "topic_continuity"                    # same RECORDED topic
    TOPIC_DISCONTINUITY = "topic_discontinuity"              # different RECORDED topic
    NEGATIVE_RESPONSE = "negative_response"                  # negative turn adjacent to a negative turn
    SOFTENING_RESPONSE = "softening_response"                # softening turn adjacent to a negative turn

    # DELIBERATELY ABSENT, and this is the point of the enum:
    #
    # RESPONDS_TO. "The next turn by the other person" licenses only
    #   `adjacent_cross_actor_turn`. It may be an answer, or a new message, or a
    #   parallel thread, or a reaction to something much older. Deriving
    #   RESPONDS_TO from adjacency asserted the very thing we want people to
    #   judge, so it is an EMPIRICAL relation for the primitives pilot, not a
    #   deterministic one. Only EXPLICIT_REPLY is asserted, because there the log
    #   says so.
    #
    # NON_UPTAKE. "Different topic" is not "present but not engaging": a reply can
    #   accept a topic and then widen it. Argued at the event layer with extra
    #   observable conditions.
    #
    # ESCALATES. A negative answered by a negative is NEGATIVE_RESPONSE.
    #   Escalation implies conflict sustained or intensified over time, which a
    #   single adjacent pair cannot show: "you ruined it" answered by "it was
    #   unpleasant for me too" is negative-negative and need not be escalation.
    #   Escalation stays an L3 candidate, not a primitive anyone is asked to see.


@dataclass(frozen=True, slots=True)
class RelationEdge:
    """L2.5 = a MessageRelation plus the observations sitting on its endpoints.

    `via_message_relation` names the topology edge that grounds this one, so no
    interaction relation can exist without a conversation-structure fact under it.
    """

    from_observation: str
    to_observation: str
    relation: InteractionRelation
    basis: str
    via_message_relation: MessageRelation | None = None


@dataclass(frozen=True, slots=True)
class ConfidenceComponents:
    """Named components, never summed into one number.

    `observation_coverage` is the share of slots that were actually observable;
    ABSENT and INSUFFICIENT_OBSERVATION lower it instead of counting against the
    hypothesis. That is the structural form of "absence is not counterevidence".
    """

    observed_support: int = 0
    observed_counter: int = 0
    observed_absence: int = 0
    insufficient_observation: int = 0
    distinct_episodes: int = 0

    @property
    def observable(self) -> int:
        """Times we actually got to look. An observed absence counts here."""
        return self.observed_support + self.observed_counter + self.observed_absence

    @property
    def observation_coverage(self) -> float | None:
        total = self.observable + self.insufficient_observation
        return round(self.observable / total, 4) if total else None

    def _derived(self) -> dict:
        # Coverage is derived, but it must survive serialisation: a trace that
        # drops it lets a reader mistake "we could not look" for "we looked and
        # found nothing", which is the exact confusion this model exists to stop.
        return {"observable": self.observable,
                "observation_coverage": self.observation_coverage}


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
    opportunity_episodes: tuple[str, ...] = ()  # episodes where this pattern COULD have shown
    unobserved_slots: tuple[str, ...] = ()   # named slots we could not fill
    first_seen_episode: str | None = None
    last_supported_episode: str | None = None
    components: ConfidenceComponents = field(default_factory=ConfidenceComponents)
    retired_reason: str | None = None


# --- status derivation -------------------------------------------------------

RECURRENCE_EPISODES = 2   # a pattern claimed from one episode is not a pattern
STALENESS_OPPORTUNITIES = 3

# Explicit methodological policy, not a side effect of episode numbering.
# An OBSERVED_ABSENCE means we looked inside an observable window and found nothing,
# so that episode WAS a chance for the pattern to show and did not take it.
# RIGHT_CENSORED, INSUFFICIENT_OBSERVATION and NOT_APPLICABLE mean we could not
# look at all (the record ended, or there was no window), so
# they must never age a hypothesis — otherwise "we did not observe" quietly
# becomes "the pattern weakened", which is the inference this whole model exists
# to refuse.
OBSERVED_ABSENCE_IS_AN_OPPORTUNITY = True


def derive_status(c: ConfidenceComponents, opportunities_since_support: int) -> HypothesisStatus:
    """Explicit, testable rules. No model self-report anywhere.

    Ordering matters: counterevidence is checked before recurrence so that a
    pattern cannot 'outvote' contradicting observations by sheer repetition.

    `opportunities_since_support` counts ELIGIBLE OBSERVATION OPPORTUNITIES, not
    elapsed episodes. An episode in which the pattern could not have shown itself
    is not evidence that it went away.
    """
    if c.observed_support == 0:
        return HypothesisStatus.CANDIDATE
    if c.observed_counter > c.observed_support:
        return HypothesisStatus.WEAKENED
    if opportunities_since_support >= STALENESS_OPPORTUNITIES:
        return HypothesisStatus.WEAKENED
    if c.distinct_episodes >= RECURRENCE_EPISODES:
        return HypothesisStatus.RECURRING
    if c.observed_support >= 2:
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
