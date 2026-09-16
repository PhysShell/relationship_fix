"""Empirical spike: can the proposed representation hold evidence deterministically?

What this DOES test: whether the four-level model can store evidence,
counterevidence, unobservable slots, transitions and competing hypotheses without
losing any of them, and whether the same input reproduces the same trace.

What this does NOT test: psychological validity, detection quality, or whether
these patterns exist in real couples. The corpus is synthetic and is Tier 3
(docs/research/corpus-strategy.md §3): edge cases and falsification only, never
evidence of ecological or construct validity.

Behaviour detection is out of scope by design. The corpus supplies L2
observations directly, so a failure here is a failure of the representation and
cannot be blamed on a classifier.

    uv run python -m dyadic.spike --corpus ../../data/research/dyadic-spike/episodes.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .interface import build_context, decide
from .model import (
    BehaviorObservation,
    EvidenceSpan,
    EvidenceStatus,
    RelationalEvent,
    content_hash,
    to_jsonable,
)
from .segmentation import Message, segment
from .state import HypothesisLedger, SafetyAccumulator

# --- deterministic L2 -> L3 derivation ---------------------------------------
#
# Every rule below is decidable from labels + ordering + authorship alone. None
# of them consults intent, tone or anything a text log does not carry.

NEGATIVE = {"BLAME_CRITICISM", "PRESSURE_FOR_CHANGE", "CONTEMPT", "DEFENSIVENESS"}
SOFTENING = {"APOLOGY", "TAKING_RESPONSIBILITY", "VALIDATION", "SOFTENING"}
ALIGNING = {"AGREEMENT", "JOINT_PLAN"}
PURSUING = {"PRESSURE_FOR_CHANGE", "RAISE_TOPIC", "BLAME_CRITICISM"}
SAFETY_RELEVANT = {"MONITORING", "ISOLATION_PRESSURE", "THREAT", "FINANCIAL_CONTROL"}

# Non-uptake WITH continued presence is observable in text; plain silence is not.
# That distinction is the single most important thing this spike encodes.
NON_UPTAKE_PRESENT = {"TOPIC_SHIFT", "OFF_TOPIC_MESSAGE"}
ON_TOPIC_UPTAKE = {"VALIDATION", "TAKING_RESPONSIBILITY", "ON_TOPIC_REPLY", "AGREEMENT", "JOINT_PLAN"}


def _event(eid, etype, parts, episode_id, obs, status, evidence=(), counter=()):
    return RelationalEvent(
        event_id=eid, event_type=etype, participants=tuple(parts), episode_id=episode_id,
        source_observations=tuple(o.observation_id for o in obs),
        supporting_evidence=tuple(evidence), counterevidence=tuple(counter), status=status,
    )


def derive_events(
    episode_id: str,
    observations: list[BehaviorObservation],
    actors: tuple[str, ...],
    silence_after: str | None,
) -> tuple[list[RelationalEvent], list[RelationalEvent]]:
    """Return (pattern_events, safety_events) for one episode.

    `silence_after`: the actor who stopped producing messages entirely. Handled
    below as ABSENT, never as disengagement.
    """
    events: list[RelationalEvent] = []
    safety: list[RelationalEvent] = []
    a, b = actors
    by_actor = {actor: [o for o in observations if o.actor == actor] for actor in actors}
    ev = lambda os: tuple(s for o in os for s in o.evidence)  # noqa: E731

    def labels(actor):
        return {o.label for o in by_actor.get(actor, [])}

    # attack_attack: both sides produce negativity within the same episode.
    if labels(a) & NEGATIVE and labels(b) & NEGATIVE:
        obs = [o for o in observations if o.label in NEGATIVE]
        events.append(_event(f"{episode_id}:aa", "attack_attack", actors, episode_id,
                             obs, EvidenceStatus.SUPPORTING, ev(obs)))

    # pursue_withdraw: asymmetric. Only ever claimed when the withdrawing side's
    # non-uptake is POSITIVELY observable, i.e. they kept messaging about
    # something else. Otherwise the slot is recorded as unfilled.
    for pursuer, other in ((a, b), (b, a)):
        pursuit = [o for o in by_actor.get(pursuer, []) if o.label in PURSUING]
        if len(pursuit) < 2:
            continue
        non_uptake = [o for o in by_actor.get(other, []) if o.label in NON_UPTAKE_PRESENT]
        uptake = [o for o in by_actor.get(other, []) if o.label in ON_TOPIC_UPTAKE]
        parts = (pursuer, other)
        if uptake:
            # The other side engaged on topic: this argues against the pattern.
            events.append(_event(f"{episode_id}:pw-counter:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, uptake, EvidenceStatus.COUNTER, counter=ev(uptake)))
        elif non_uptake:
            obs = pursuit + non_uptake
            events.append(_event(f"{episode_id}:pw:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, obs, EvidenceStatus.SUPPORTING, ev(obs)))
        elif silence_after == other:
            # Silence. Observable absence of messages is NOT observable withdrawal:
            # three independent coding systems define withdrawal through a
            # nonverbal channel text does not have. Recorded as ABSENT so it
            # lowers coverage and advances nothing.
            events.append(_event(f"{episode_id}:pw-absent:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, pursuit, EvidenceStatus.ABSENT))
        else:
            events.append(_event(f"{episode_id}:pw-insuff:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, pursuit, EvidenceStatus.INSUFFICIENT_OBSERVATION))

    # repair_softening: a softening move followed by the partner producing no
    # further negativity in this episode. "Followed by" is positional, not
    # interpretive.
    for o in observations:
        if o.label not in SOFTENING:
            continue
        idx = observations.index(o)
        partner = b if o.actor == a else a
        later_negative = [x for x in observations[idx + 1:]
                          if x.actor == partner and x.label in NEGATIVE]
        if later_negative:
            events.append(_event(f"{episode_id}:rs-counter:{o.observation_id}", "repair_softening",
                                 actors, episode_id, later_negative, EvidenceStatus.COUNTER,
                                 counter=ev(later_negative)))
        else:
            events.append(_event(f"{episode_id}:rs:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o], EvidenceStatus.SUPPORTING, ev([o])))

    # constructive_alignment: both sides produce an aligning move.
    if labels(a) & ALIGNING and labels(b) & ALIGNING:
        obs = [o for o in observations if o.label in ALIGNING]
        events.append(_event(f"{episode_id}:ca", "constructive_alignment", actors, episode_id,
                             obs, EvidenceStatus.SUPPORTING, ev(obs)))

    # mixed_transition: both a negative and a softening signal are live at once.
    # RESCUE-Bench needed this label too; ambiguity is a state, not a failure.
    if any(o.label in NEGATIVE for o in observations) and any(o.label in SOFTENING for o in observations):
        obs = [o for o in observations if o.label in NEGATIVE | SOFTENING]
        events.append(_event(f"{episode_id}:mx", "mixed_transition", actors, episode_id,
                             obs, EvidenceStatus.SUPPORTING, ev(obs)))

    for o in observations:
        if o.label in SAFETY_RELEVANT:
            safety.append(_event(f"{episode_id}:safety:{o.observation_id}", "safety_relevant",
                                 (o.actor,), episode_id, [o], EvidenceStatus.SUPPORTING, ev([o])))
    return events, safety


# --- runner ------------------------------------------------------------------

def run(corpus_path: Path, out_path: Path) -> dict:
    ledger = HypothesisLedger()
    safety_acc = SafetyAccumulator()
    per_episode = []

    for line in corpus_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        actors = tuple(case["actors"])
        texts = {m["message_id"]: m["text"] for m in case["messages"]}
        messages = [Message(m["message_id"], m["author"], m["text"], m.get("timestamp"))
                    for m in case["messages"]]
        episodes = segment(messages)

        observations = []
        for o in case["observations"]:
            spans = tuple(EvidenceSpan(o["message_id"], q) for q in o["quotes"])
            for s in spans:
                s.validate(texts[s.message_id])
            observations.append(BehaviorObservation(
                observation_id=o["observation_id"], label=o["label"],
                actor=o["actor"], message_id=o["message_id"], evidence=spans))

        # One case is one segmentation input; episodes carry the case id so a
        # multi-episode case still folds in order.
        for ep in episodes:
            member = set(ep.member_message_ids)
            ep_obs = [o for o in observations if o.message_id in member]
            ep_id = f"{case['case_id']}/{ep.episode_id}"
            events, safety_events = derive_events(
                ep_id, ep_obs, actors, case.get("silence_after"))
            ledger.observe_episode(ep_id, events)
            for se in safety_events:
                safety_acc.add(ep_id, se)
            ctx = build_context(ep_id, ledger, safety_acc)
            per_episode.append({
                "case_id": case["case_id"],
                "designed_for": case.get("designed_for"),
                "episode_id": ep_id,
                "timing_available": ep.timing_available,
                "n_observations": len(ep_obs),
                "events": [to_jsonable(e) for e in events],
                "context": to_jsonable(ctx),
                "decision": to_jsonable(decide(ctx)),
            })

    trace = {
        "schema_version": "rf.dyadic-spike-trace.v0",
        "corpus_sha256": content_hash(corpus_path.read_text(encoding="utf-8")),
        "n_cases": len({e["case_id"] for e in per_episode}),
        "n_episodes": len(per_episode),
        "final_hypotheses": [to_jsonable(h) for h in ledger.competing()],
        "all_hypotheses": [to_jsonable(h) for h in ledger.hypotheses.values()],
        "transitions": ledger.transitions,
        "safety": safety_acc.as_flags(),
        "per_episode": per_episode,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trace


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("../../data/research/dyadic-spike/trace.json"))
    args = ap.parse_args()
    trace = run(args.corpus, args.out)
    print(f"OK: {trace['n_cases']} cases, {trace['n_episodes']} episodes, "
          f"{len(trace['final_hypotheses'])} live hypotheses, "
          f"{len(trace['transitions'])} transitions -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
