"""Four acquisition modes against nine synthetic histories.

Synthetic throughout: no real conversation, no real person, no RNG. Recipient
behaviour is a fixed pattern per scenario so the table is reproducible by
reading it.

What the table is for: showing that a strict interaction budget still reduces
calibration uncertainty, and showing what each mode costs in prompts to get
there. It is NOT evidence about real completion rates — those come from a real
experiment, and the metrics that experiment should compare are listed in
docs/research/feedback-acquisition-policy.md §7.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .acquisition import (
    COOLDOWN_MINUTES_AFTER_EPISODE,
    AcquisitionMode,
    CalibrationCandidate,
    ConversationState,
    PromptOutcome,
    RecipientState,
    RequestDecision,
    evaluate,
    information_value,
    issue,
    produces_observation,
    register_outcome,
)
from .demo import OBSERVER_READING, PERSONAS, RECIPIENT_SCALE
from .model import (
    EstimatorKind,
    ObserverEstimate,
    RecipientFeedback,
    ReferenceFrame,
    Tier,
    record_divergence,
)
from .policy import build_profile


@dataclass(frozen=True, slots=True)
class ScenarioEvent:
    hour: float
    move_signature: str
    conflict: bool = False
    safety: bool = False
    participated: bool = True


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    persona: str
    events: tuple[ScenarioEvent, ...]
    #: 'always' | 'never' | 'every_other' | 'opt_out' — a fixed pattern, not a rate.
    responder: str = "always"


def _stream(days: int, per_day: int, signatures: tuple[str, ...],
            conflict_days: tuple[int, ...] = (), safety_days: tuple[int, ...] = (),
            start_hour: float = 9.0, spacing: float = 0.25) -> tuple[ScenarioEvent, ...]:
    events = []
    index = 0
    for day in range(days):
        for slot in range(per_day):
            events.append(ScenarioEvent(
                hour=day * 24 + start_hour + slot * spacing,
                move_signature=signatures[index % len(signatures)],
                conflict=day in conflict_days,
                safety=day in safety_days,
            ))
            index += 1
    return tuple(events)


MIXED = ("terse_acknowledgement", "apology", "long_explanation", "question",
         "terse_acknowledgement", "advice_giving")

SCENARIOS = (
    Scenario("active_chat", "terse_lands_well", _stream(21, 8, MIXED)),
    Scenario("sparse_chat", "terse_lands_well", _stream(21, 1, MIXED)),
    Scenario("conflict_series", "terse_lands_well",
             _stream(21, 4, MIXED, conflict_days=(2, 3, 4, 9, 10, 15, 16))),
    Scenario("always_answers", "terse_lands_well", _stream(21, 4, MIXED), "always"),
    Scenario("always_ignores", "terse_lands_well", _stream(21, 4, MIXED), "never"),
    Scenario("flat_responder", "flat_responder", _stream(21, 4, MIXED)),
    Scenario("contested_calibration", "terse_contested", _stream(21, 4, MIXED)),
    Scenario("new_move_signature", "advice_lands_well",
             _stream(21, 4, ("advice_giving",) + MIXED)),
    Scenario("safety_sensitive", "terse_lands_well",
             _stream(21, 4, MIXED, safety_days=tuple(range(6, 15)))),
)


@dataclass
class Run:
    prompts: int = 0
    answered: int = 0
    opted_out: int = 0
    unanswered: int = 0
    records: list = field(default_factory=list)
    prompt_days: set = field(default_factory=set)
    max_per_day: int = 0


def _conversation_at(events, index, now) -> ConversationState:
    event = events[index]
    following = [e for e in events if e.hour > event.hour]
    next_gap = (following[0].hour - event.hour) * 60 if following else 999.0
    since_conflict = 999.0
    for e in events:
        if e.conflict and e.hour <= now:
            since_conflict = min(since_conflict, now - e.hour)
    return ConversationState(
        active=next_gap < 30 and now < (following[0].hour if following else now),
        minutes_since_last_message=(now - event.hour) * 60,
        hours_since_conflict=since_conflict,
        safety_flag=any(e.safety and abs(e.hour - now) < 24 for e in events),
    )


def _outcome(responder: str, sequence: int) -> PromptOutcome:
    if responder == "never":
        return PromptOutcome.IGNORED
    if responder == "every_other":
        return PromptOutcome.ANSWERED if sequence % 2 == 0 else PromptOutcome.IGNORED
    if responder == "opt_out":
        return PromptOutcome.OPTED_OUT
    return PromptOutcome.ANSWERED


def simulate(scenario: Scenario, mode: AcquisitionMode) -> Run:
    state = RecipientState(scenario.name, mode=mode)
    run = Run()
    observer_seen: list[float] = []
    recipient_seen: list[float] = []
    occurrences: dict[str, int] = {}
    per_day: dict[int, int] = {}
    sequence = 0

    # Decision points: DELAYED asks once the cooldown has passed; END_OF_DAY
    # looks at the whole day at 22:00 and takes the single most informative one.
    if mode is AcquisitionMode.END_OF_DAY_SAMPLE:
        days = sorted({int(e.hour // 24) for e in scenario.events})
        checkpoints = [(day * 24 + 22.0, day) for day in days]
    else:
        checkpoints = [(e.hour + COOLDOWN_MINUTES_AFTER_EPISODE / 60, i)
                       for i, e in enumerate(scenario.events)]

    for now, marker in checkpoints:
        profile = build_profile(scenario.name, run.records) if run.records else None
        if mode is AcquisitionMode.END_OF_DAY_SAMPLE:
            pool = [(i, e) for i, e in enumerate(scenario.events) if int(e.hour // 24) == marker]
        else:
            pool = [(marker, scenario.events[marker])]

        best = None
        for index, event in pool:
            candidate = CalibrationCandidate(
                event_id=f"{scenario.name}-e{index:03d}",
                recipient=scenario.name,
                estimate=ObserverEstimate(
                    f"{scenario.name}-e{index:03d}", scenario.name, event.move_signature,
                    OBSERVER_READING[event.move_signature], "spike-reader-v0",
                    EstimatorKind.MODEL, event.hour),
                occurred_at=event.hour,
                recipient_participated=event.participated,
            )
            verdict = evaluate(candidate, state, _conversation_at(scenario.events, index, now),
                               profile, now)
            if verdict.decision is not RequestDecision.ELIGIBLE_NOW:
                continue
            value, _ = information_value(candidate, profile)
            if best is None or value > best[0]:
                best = (value, candidate)

        if best is None:
            continue

        prompt = issue(best[1], state, now)
        run.prompts += 1
        day = int(now // 24)
        run.prompt_days.add(day)
        per_day[day] = per_day.get(day, 0) + 1
        run.max_per_day = max(run.max_per_day, per_day[day])

        outcome = _outcome(scenario.responder, sequence)
        sequence += 1
        register_outcome(state, outcome, now)

        if not produces_observation(outcome):
            if outcome is PromptOutcome.OPTED_OUT:
                run.opted_out += 1
            else:
                run.unanswered += 1
            continue

        run.answered += 1
        signature = best[1].estimate.move_signature
        occurrences[signature] = occurrences.get(signature, 0) + 1
        table = PERSONAS[scenario.persona][signature]
        recipient_value = table[(occurrences[signature] - 1) % len(table)]
        observer_value = best[1].estimate.value

        feedback = RecipientFeedback(
            event_id=best[1].event_id, recipient=scenario.name, dimension="FELT_HEARD",
            value=recipient_value, scale=RECIPIENT_SCALE, observed_at=now,
            respondent_is_recipient=True, channel="passive_sampled")
        run.records.append(record_divergence(
            best[1].estimate, feedback,
            ReferenceFrame("spike-reader-v0", tuple(observer_seen)),
            ReferenceFrame(scenario.name, tuple(recipient_seen))))
        observer_seen.append(observer_value)
        recipient_seen.append(recipient_value)

    return run


def simulate_user_initiated(scenario: Scenario) -> Run:
    """No prompt ever. The person corrects the app when it annoys them.

    Modelled as exactly that, on purpose: corrections land only where the
    system's reading is farthest from how the event actually went for them. The
    resulting sample is self-selected in the strongest possible way, which is
    why `channel` travels with every observation.
    """
    run = Run()
    observer_seen: list[float] = []
    recipient_seen: list[float] = []
    occurrences: dict[str, int] = {}

    for index, event in enumerate(scenario.events):
        signature = event.move_signature
        table = PERSONAS[scenario.persona][signature]
        occurrence = occurrences.get(signature, 0)
        recipient_value = table[occurrence % len(table)]
        observer_value = OBSERVER_READING[signature]
        # the annoyance rule: only when the two readings are far apart
        if abs((recipient_value / 7.0) - (observer_value / 7.0)) < 0.45:
            continue
        occurrences[signature] = occurrence + 1
        event_id = f"{scenario.name}-u{index:03d}"
        estimate = ObserverEstimate(event_id, scenario.name, signature, observer_value,
                                    "spike-reader-v0", EstimatorKind.MODEL, event.hour)
        feedback = RecipientFeedback(event_id, scenario.name, "FELT_HEARD", recipient_value,
                                     RECIPIENT_SCALE, event.hour, True, channel="user_initiated")
        run.answered += 1
        run.records.append(record_divergence(
            estimate, feedback,
            ReferenceFrame("spike-reader-v0", tuple(observer_seen)),
            ReferenceFrame(scenario.name, tuple(recipient_seen))))
        observer_seen.append(observer_value)
        recipient_seen.append(recipient_value)
    return run


def run_all() -> None:  # pragma: no cover - reporting only
    header = (f"{'scenario':23s} {'mode':22s} {'evts':>5s} {'ask':>4s} {'ans':>4s} "
              f"{'skip':>4s} {'rec':>4s} {'usable':>6s} {'d/pr':>5s} {'max':>4s}")
    print(header)
    print("-" * len(header))
    for scenario in SCENARIOS:
        for mode in AcquisitionMode:
            if mode is AcquisitionMode.USER_INITIATED:
                run = simulate_user_initiated(scenario)
            else:
                run = simulate(scenario, mode)
            profile = build_profile(scenario.name, run.records)
            usable = sum(1 for s in profile.signals if s.tier is Tier.USABLE_CALIBRATION)
            print(f"{scenario.name:23s} {mode.value:22s} {len(scenario.events):5d} "
                  f"{run.prompts:4d} {run.answered:4d} {run.opted_out + run.unanswered:4d} "
                  f"{profile.evidence_count:4d} {usable:6d} {len(run.prompt_days):5d} "
                  f"{run.max_per_day:4d}")
        print()


if __name__ == "__main__":  # pragma: no cover
    run_all()
