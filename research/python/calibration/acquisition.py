"""Feedback Acquisition Policy v0 — calibration under a strict interaction budget.

The Calibration Loop runs on recipient feedback, so the question that decides
whether it is a product or a lab rig is not "what else can we model" but "how do
we obtain that feedback without turning a relationship into an instrumented
apartment".

The shape, deliberately not `event → prompt`:

    interaction happens
            ↓
    system marks a calibration CANDIDATE
            ↓
    no prompt yet
            ↓
    cooldown / episode ends
            ↓
    sampling policy: skip, or ask later
            ↓
    private recipient check-in
            ↓
    RecipientFeedback

Two external priors sit behind the numbers, and both are recorded in
docs/research/feedback-acquisition-policy.md rather than smuggled in here:

  - Williams et al. 2021 (JMIR, 105 mEMA datasets): pooled compliance 81.9%
    [79.1, 84.4], and in non-clinical data 1-3 prompts/day ran near 87% against
    76.9% for 4-5, while surveys over 26 items fell to 63%. Hence one prompt a
    day and at most two items.
  - the marital event-contingent diary literature: fifteen days of diaries left
    OBSERVED conflict behaviour unchanged while self-reported marital quality
    drifted over the recording period. We are measuring self-report. That is the
    first-order threat to this whole design and NEVER_ASK exists as its control.

Every constant here is a product-spike placeholder (`PROVENANCE`), not a
scientific finding.

THE INVARIANT THAT MAKES THE SAMPLED DATA USABLE: the sampling rule may read the
past and the observer side, and may NEVER read the answer it is about to ask
for. Selection that depends on the outcome would bias every signal built from
sampled events. This module therefore never imports or constructs
`RecipientFeedback`, and a test scans the source to keep it that way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .model import PROVENANCE, ObserverEstimate, PersonalCalibrationProfile, Tier

# ---------------------------------------------------------------------------
# product-spike constants
# ---------------------------------------------------------------------------

MAX_PROMPTS_PER_DAY = 1
MIN_HOURS_BETWEEN_PROMPTS = 20
#: Never during a live exchange, and not the moment an episode ends either.
COOLDOWN_MINUTES_AFTER_EPISODE = 90
#: A fight is not a survey opportunity.
CONFLICT_COOLDOWN_HOURS = 12
#: Older than this and the answer is reconstruction, not recall.
MAX_RECALL_AGE_HOURS = 36
#: A prompt sits quietly for a day. The 45-minute windows people complain about
#: buy compliance by making the app the urgent party in someone's evening.
PROMPT_EXPIRY_HOURS = 24
#: Ignore two in a row and we stop asking for a week. Silence is an answer about
#: the prompting, not about the partner.
IGNORED_STREAK_BACKOFF = 2
BACKOFF_DAYS = 7
#: One question, at most one optional follow-up.
MAX_ITEMS_PER_PROMPT = 2
#: Below this, asking costs the person more than it buys the calibration.
INFORMATION_VALUE_FLOOR = 0.3
#: If this many answers have produced no usable evidence at all, stop asking.
#: Found by the simulation rather than designed: a recipient whose own reference
#: frame never establishes (see budget_demo's `flat_responder`) can be prompted
#: every day for three weeks, answer every time, and teach the system nothing.
#: Burden without information is the worst cell in the table.
UNPRODUCTIVE_ANSWER_LIMIT = 6

# ---------------------------------------------------------------------------
# what a person is actually shown
# ---------------------------------------------------------------------------

#: Deliberately not in our ontology's words. Nobody is asked to rate "uptake".
PRIMARY_QUESTION = "После этого ответа вы скорее почувствовали себя услышанным?"
PRIMARY_SCALE = (1.0, 7.0)
#: The opt-out is a first-class answer and produces NO observation. It is
#: UNKNOWN, not a 4.
PRIMARY_OPT_OUT = "Не могу сказать / не помню"

FOLLOW_UP_QUESTION = "Что здесь было важнее всего?"
FOLLOW_UP_OPTIONS = ("тон", "краткость", "признание моей позиции", "объяснение", "другое")
#: The follow-up is exploratory metadata. It is not part of FELT_HEARD and does
#: not enter any signal.
FOLLOW_UP_IS_EXPLORATORY = True


class AcquisitionMode(str, Enum):
    NEVER_ASK = "never_ask"                      # baseline / reactivity control
    END_OF_DAY_SAMPLE = "end_of_day_sample"      # at most one candidate, batched
    DELAYED_EVENT_SAMPLE = "delayed_event_sample"  # after cooldown, max 1/day
    USER_INITIATED = "user_initiated"            # no prompt ever; user corrects us


class RequestDecision(str, Enum):
    DO_NOT_ASK = "do_not_ask"
    ASK_LATER = "ask_later"
    ELIGIBLE_NOW = "eligible_now"


class DenyReason(str, Enum):
    MODE_NEVER_ASK = "mode_never_ask"
    MODE_USER_INITIATED = "mode_user_initiated"
    CONVERSATION_ACTIVE = "conversation_active"
    SAFETY_CONCERN = "safety_concern"
    HIGH_CONFLICT_COOLDOWN = "high_conflict_cooldown"
    EPISODE_COOLDOWN = "episode_cooldown"
    PROMPT_BUDGET_SPENT = "prompt_budget_spent"
    USER_SNOOZED = "user_snoozed"
    IGNORED_BACKOFF = "ignored_backoff"
    RECIPIENT_NOT_IN_EVENT = "recipient_not_in_event"
    EVENT_TOO_OLD = "event_too_old"
    ALREADY_SAMPLED = "already_sampled"
    NO_INFORMATION_VALUE = "no_information_value"
    NO_LEARNABLE_SIGNAL = "no_learnable_signal"


class PromptOutcome(str, Enum):
    ANSWERED = "answered"
    OPTED_OUT = "opted_out"     # "не могу сказать" — an answer, not a value
    IGNORED = "ignored"
    EXPIRED = "expired"


#: Outcomes that produce no observation at all. None of them is a low rating,
#: a neutral rating, or a weak rating. They are the absence of a measurement.
NO_OBSERVATION_OUTCOMES = (PromptOutcome.OPTED_OUT, PromptOutcome.IGNORED, PromptOutcome.EXPIRED)


@dataclass(frozen=True, slots=True)
class CalibrationCandidate:
    """An event that MIGHT be worth asking about. Carries no answer, ever.

    There is no field here for the recipient's rating, because a candidate is
    chosen before any rating exists. That is not a convenience — it is what
    keeps the selection independent of the outcome.
    """

    event_id: str
    recipient: str
    estimate: ObserverEstimate
    occurred_at: float                    # hours on the simulation clock
    recipient_participated: bool = True


@dataclass(frozen=True, slots=True)
class ConversationState:
    """What is happening around the candidate right now."""

    active: bool = False
    minutes_since_last_message: float = 999.0
    hours_since_conflict: float = 999.0
    safety_flag: bool = False


@dataclass
class RecipientState:
    """Everything the policy remembers about asking THIS person."""

    recipient: str
    mode: AcquisitionMode = AcquisitionMode.DELAYED_EVENT_SAMPLE
    prompts_sent_at: list[float] = field(default_factory=list)
    answered_count: int = 0
    ignored_streak: int = 0
    snoozed_until: float | None = None
    sampled_event_ids: set[str] = field(default_factory=set)
    backoff_until: float | None = None

    def prompts_on_day(self, hour: float) -> int:
        day = int(hour // 24)
        return sum(1 for t in self.prompts_sent_at if int(t // 24) == day)

    def hours_since_last_prompt(self, hour: float) -> float:
        if not self.prompts_sent_at:
            return float("inf")
        return hour - max(self.prompts_sent_at)


@dataclass(frozen=True, slots=True)
class RequestVerdict:
    decision: RequestDecision
    reasons: tuple[DenyReason, ...]
    information_value: float
    rationale: str

    @property
    def eligible(self) -> bool:
        return self.decision is RequestDecision.ELIGIBLE_NOW


def information_value(
    candidate: CalibrationCandidate,
    profile: PersonalCalibrationProfile | None,
) -> tuple[float, str]:
    """How much asking about THIS event would reduce calibration uncertainty.

    Reads the observer side and the person's past. It does not — and structurally
    cannot — read the answer being sought.

    Deliberately not a probability and not an evidence weight: a well-chosen
    question and a lucky one produce exactly the same single observation
    downstream (see `policy.summarise`, which has never heard of this function).
    """
    signature = candidate.estimate.move_signature
    signal = profile.signal_for(signature) if profile else None

    if signal is None:
        return 1.0, f"'{signature}' has no history for this person yet"
    if signal.tier is Tier.CONTESTED:
        return 0.9, f"'{signature}' is contested; another observation may resolve or confirm it"
    if signal.tier is Tier.ANECDOTE:
        return 0.8, f"'{signature}' rests on a single observation"
    if signal.tier is Tier.WEAK_TENDENCY:
        return 0.7, f"'{signature}' is a weak tendency; one more may make it usable"
    return 0.1, f"'{signature}' is already settled for this person; asking buys little"


def evaluate(
    candidate: CalibrationCandidate,
    state: RecipientState,
    conversation: ConversationState,
    profile: PersonalCalibrationProfile | None,
    now: float,
) -> RequestVerdict:
    """Decide whether this person may be asked about this event, and when.

    DO_NOT_ASK never means "impact is neutral". It means there is no measurement,
    which is the same UNKNOWN the whole architecture is built to preserve.
    """
    value, rationale = information_value(candidate, profile)
    deny: list[DenyReason] = []
    later: list[DenyReason] = []

    if state.mode is AcquisitionMode.NEVER_ASK:
        deny.append(DenyReason.MODE_NEVER_ASK)
    if state.mode is AcquisitionMode.USER_INITIATED:
        deny.append(DenyReason.MODE_USER_INITIATED)

    # --- hard denies: nothing about information value overrides these ---
    if conversation.safety_flag:
        deny.append(DenyReason.SAFETY_CONCERN)
    if not candidate.recipient_participated:
        deny.append(DenyReason.RECIPIENT_NOT_IN_EVENT)
    if state.snoozed_until is not None and now < state.snoozed_until:
        deny.append(DenyReason.USER_SNOOZED)
    if state.backoff_until is not None and now < state.backoff_until:
        deny.append(DenyReason.IGNORED_BACKOFF)
    if candidate.event_id in state.sampled_event_ids:
        deny.append(DenyReason.ALREADY_SAMPLED)
    if now - candidate.occurred_at > MAX_RECALL_AGE_HOURS:
        deny.append(DenyReason.EVENT_TOO_OLD)
    if value < INFORMATION_VALUE_FLOOR:
        deny.append(DenyReason.NO_INFORMATION_VALUE)
    if state.answered_count >= UNPRODUCTIVE_ANSWER_LIMIT and (profile is None or profile.evidence_count == 0):
        deny.append(DenyReason.NO_LEARNABLE_SIGNAL)

    # --- timing: these say "not yet", which is a different answer ---
    if conversation.active:
        later.append(DenyReason.CONVERSATION_ACTIVE)
    if conversation.minutes_since_last_message < COOLDOWN_MINUTES_AFTER_EPISODE:
        later.append(DenyReason.EPISODE_COOLDOWN)
    if conversation.hours_since_conflict < CONFLICT_COOLDOWN_HOURS:
        later.append(DenyReason.HIGH_CONFLICT_COOLDOWN)
    if state.prompts_on_day(now) >= MAX_PROMPTS_PER_DAY:
        later.append(DenyReason.PROMPT_BUDGET_SPENT)
    if state.hours_since_last_prompt(now) < MIN_HOURS_BETWEEN_PROMPTS:
        later.append(DenyReason.PROMPT_BUDGET_SPENT)

    if deny:
        return RequestVerdict(RequestDecision.DO_NOT_ASK, tuple(deny), value, rationale)
    if later:
        return RequestVerdict(RequestDecision.ASK_LATER, tuple(later), value, rationale)
    return RequestVerdict(RequestDecision.ELIGIBLE_NOW, (), value, rationale)


@dataclass(frozen=True, slots=True)
class Prompt:
    """One question actually put to one person. Producing it changes nothing.

    A Prompt is not evidence and has no value field. Only an ANSWERED prompt
    yields an observation, and the observation is built elsewhere, by the caller
    who has the person's actual answer.
    """

    prompt_id: str
    recipient: str
    event_id: str
    sent_at: float
    question: str = PRIMARY_QUESTION
    scale: tuple[float, float] = PRIMARY_SCALE
    opt_out: str = PRIMARY_OPT_OUT
    follow_up: str | None = FOLLOW_UP_QUESTION

    @property
    def items(self) -> int:
        return 1 + (1 if self.follow_up else 0)

    @property
    def expires_at(self) -> float:
        return self.sent_at + PROMPT_EXPIRY_HOURS

    def __post_init__(self) -> None:
        if self.items > MAX_ITEMS_PER_PROMPT:
            raise ValueError(f"a check-in carries at most {MAX_ITEMS_PER_PROMPT} items")


def issue(candidate: CalibrationCandidate, state: RecipientState, now: float) -> Prompt:
    """Record that we asked. Mutates only the asking state, never any belief."""
    if candidate.event_id in state.sampled_event_ids:
        raise ValueError("an event is asked about once; a second ask is a second sample of one answer")
    state.sampled_event_ids.add(candidate.event_id)
    state.prompts_sent_at.append(now)
    return Prompt(
        prompt_id=f"p-{candidate.recipient}-{candidate.event_id}",
        recipient=candidate.recipient,
        event_id=candidate.event_id,
        sent_at=now,
    )


def register_outcome(state: RecipientState, outcome: PromptOutcome, now: float) -> None:
    """Silence is information about the prompting, never about the partner."""
    if outcome in (PromptOutcome.IGNORED, PromptOutcome.EXPIRED):
        state.ignored_streak += 1
        if state.ignored_streak >= IGNORED_STREAK_BACKOFF:
            state.backoff_until = now + BACKOFF_DAYS * 24
            state.ignored_streak = 0
    else:
        state.ignored_streak = 0
        if outcome is PromptOutcome.ANSWERED:
            state.answered_count += 1


def produces_observation(outcome: PromptOutcome) -> bool:
    """The whole point, in one function: three of four outcomes produce nothing."""
    return outcome is PromptOutcome.ANSWERED


def may_disclose_to_partner(visibility: str, explicit_consent: bool) -> bool:
    """Sharing is a separate feature with its own consent, and defaults to no.

    If one partner uses the product and the other must confirm daily how things
    landed, the product has turned the second person into a free sensor for the
    first. Calibration may use a private answer to personalise the experience of
    the person who gave it; it may not hand the partner a score.
    """
    return bool(explicit_consent) and visibility == "shared_with_partner"


ACQUISITION_PROVENANCE = PROVENANCE
