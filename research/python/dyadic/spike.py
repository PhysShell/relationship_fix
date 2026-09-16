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
    InteractionRelation,
    RelationalEvent,
    RelationEdge,
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
UPTAKE = {"VALIDATION", "TAKING_RESPONSIBILITY", "ON_TOPIC_REPLY", "AGREEMENT", "JOINT_PLAN"}
SAFETY_RELEVANT = {"MONITORING", "ISOLATION_PRESSURE", "THREAT", "FINANCIAL_CONTROL"}


def derive_relations(observations: list[BehaviorObservation]) -> list[RelationEdge]:
    """L2 -> L2.5. Relations between adjacent cross-actor observations.

    Only the NEXT observation by the other actor counts as a response. That is
    deliberately strict: without it, "responds to" degenerates into "appears
    later in the same episode", which is how co-occurrence sneaks back in.
    """
    edges: list[RelationEdge] = []
    for i, src in enumerate(observations):
        nxt = next((o for o in observations[i + 1:] if o.actor != src.actor), None)
        if nxt is None:
            continue
        edges.append(RelationEdge(src.observation_id, nxt.observation_id,
                                  InteractionRelation.RESPONDS_TO, "next observation by other actor"))
        if src.topic is not None and nxt.topic is not None:
            same = src.topic == nxt.topic
            edges.append(RelationEdge(
                src.observation_id, nxt.observation_id,
                InteractionRelation.CONTINUES_TOPIC if same else InteractionRelation.NON_UPTAKE,
                f"topic {'==' if same else '!='} ({src.topic} -> {nxt.topic})"))
        if src.label in NEGATIVE and nxt.label in NEGATIVE:
            edges.append(RelationEdge(src.observation_id, nxt.observation_id,
                                      InteractionRelation.ESCALATES, "negative answered by negative"))
        if src.label in NEGATIVE and nxt.label in SOFTENING:
            edges.append(RelationEdge(src.observation_id, nxt.observation_id,
                                      InteractionRelation.SOFTENS, "negative answered by softening"))
    return edges


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
) -> tuple[list[RelationalEvent], list[RelationalEvent], set[str], list[RelationEdge]]:
    """L2.5 -> L3. Every predicate is a statement about RELATIONS, never about
    labels co-occurring somewhere in the episode.

    Returns (pattern_events, safety_events, opportunities, relations).
    `opportunities` names the patterns that could have shown themselves here, so
    only those may age (see model.derive_status).
    """
    events: list[RelationalEvent] = []
    safety: list[RelationalEvent] = []
    opportunities: set[str] = set()
    relations = derive_relations(observations)
    by_id = {o.observation_id: o for o in observations}
    a, b = actors
    ev = lambda os: tuple(sp for o in os for sp in o.evidence)  # noqa: E731

    def rel(kind):
        return [(by_id[e.from_observation], by_id[e.to_observation])
                for e in relations if e.relation is kind]

    labels_present = {o.label for o in observations}
    if labels_present & NEGATIVE:
        opportunities |= {"attack_attack", "pursue_withdraw"}
    if labels_present & (SOFTENING | ALIGNING):
        opportunities |= {"repair_softening", "constructive_alignment"}

    # attack_attack: a negative turn ANSWERED BY a negative turn from the other
    # side. Two people merely being negative in the same episode is not a cycle.
    escalations = rel(InteractionRelation.ESCALATES)
    if escalations:
        obs = [o for pair in escalations for o in pair]
        events.append(_event(f"{episode_id}:aa", "attack_attack", actors, episode_id,
                             obs, EvidenceStatus.SUPPORTING, ev(obs)))

    # pursue_withdraw: repeated pursuit by one side, and the OTHER side's
    # response to a specific pursuit is non-uptake-with-presence.
    for pursuer, other in ((a, b), (b, a)):
        pursuit = [o for o in observations if o.actor == pursuer and o.label in PURSUING]
        if len(pursuit) < 2:
            continue
        parts = (pursuer, other)
        answered = [(src, dst) for src, dst in rel(InteractionRelation.CONTINUES_TOPIC)
                    if src.actor == pursuer and dst.label in UPTAKE]
        not_taken = [(src, dst) for src, dst in rel(InteractionRelation.NON_UPTAKE)
                     if src.actor == pursuer and src.label in PURSUING]
        if answered:
            obs = [o for pair in answered for o in pair]
            events.append(_event(f"{episode_id}:pw-counter:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, obs, EvidenceStatus.COUNTER, counter=ev(obs)))
        elif not_taken:
            obs = [o for pair in not_taken for o in pair]
            events.append(_event(f"{episode_id}:pw:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, obs, EvidenceStatus.SUPPORTING, ev(obs)))
        elif silence_after == other:
            # Silence: observable absence of messages is NOT observable withdrawal.
            events.append(_event(f"{episode_id}:pw-absent:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, pursuit, EvidenceStatus.ABSENT))
        else:
            events.append(_event(f"{episode_id}:pw-insuff:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, pursuit, EvidenceStatus.INSUFFICIENT_OBSERVATION))

    # repair_softening: a softening move plus the PARTNER'S OBSERVED RESPONSE.
    # A softening move that nobody answered is ABSENT, not support: "I said sorry
    # and nothing bad happened afterwards" is exactly the silence-as-evidence
    # inference this model refuses everywhere else.
    for o in observations:
        if o.label not in SOFTENING:
            continue
        response = next((dst for src, dst in rel(InteractionRelation.RESPONDS_TO)
                         if src.observation_id == o.observation_id), None)
        if response is None:
            events.append(_event(f"{episode_id}:rs-absent:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o], EvidenceStatus.ABSENT))
        elif response.label in NEGATIVE:
            events.append(_event(f"{episode_id}:rs-counter:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o, response], EvidenceStatus.COUNTER,
                                 counter=ev([response])))
        elif response.label in UPTAKE | SOFTENING | ALIGNING:
            events.append(_event(f"{episode_id}:rs:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o, response], EvidenceStatus.SUPPORTING,
                                 ev([o, response])))
        else:
            events.append(_event(f"{episode_id}:rs-insuff:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o, response],
                                 EvidenceStatus.INSUFFICIENT_OBSERVATION))

    # constructive_alignment: an aligning move ANSWERED BY an aligning move.
    aligned = [(src, dst) for src, dst in rel(InteractionRelation.RESPONDS_TO)
               if src.label in ALIGNING and dst.label in ALIGNING]
    if aligned:
        obs = [o for pair in aligned for o in pair]
        events.append(_event(f"{episode_id}:ca", "constructive_alignment", actors, episode_id,
                             obs, EvidenceStatus.SUPPORTING, ev(obs)))

    # NOTE: no mixed_transition event. It is derived from which hypotheses are
    # concurrently live (state.HypothesisLedger.is_mixed_transition).

    for o in observations:
        if o.label in SAFETY_RELEVANT:
            safety.append(_event(f"{episode_id}:safety:{o.observation_id}", "safety_relevant",
                                 (o.actor,), episode_id, [o], EvidenceStatus.SUPPORTING, ev([o])))
    return events, safety, opportunities, relations


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
                actor=o["actor"], message_id=o["message_id"], evidence=spans,
                topic=o.get("topic")))

        # One case is one segmentation input; episodes carry the case id so a
        # multi-episode case still folds in order.
        for ep in episodes:
            member = set(ep.member_message_ids)
            ep_obs = [o for o in observations if o.message_id in member]
            ep_id = f"{case['case_id']}/{ep.episode_id}"
            events, safety_events, opportunities, relations = derive_events(
                ep_id, ep_obs, actors, case.get("silence_after"))
            ledger.observe_episode(ep_id, events, opportunities)
            for se in safety_events:
                safety_acc.add(ep_id, se)
            ctx = build_context(ep_id, ledger, safety_acc)
            per_episode.append({
                "case_id": case["case_id"],
                "designed_for": case.get("designed_for"),
                "episode_id": ep_id,
                "timing_available": ep.timing_available,
                "n_observations": len(ep_obs),
                "relations": [to_jsonable(r) for r in relations],
                "opportunities": sorted(opportunities),
                "events": [to_jsonable(e) for e in events],
                "snapshot_is_mixed_transition": ledger.is_mixed_transition(),  # cumulative, not per-episode
                "context": to_jsonable(ctx),
                "decision": to_jsonable(decide(ctx)),
            })

    trace = {
        "schema_version": "rf.dyadic-spike-trace.v0",
        "corpus_sha256": content_hash(corpus_path.read_text(encoding="utf-8")),
        "n_cases": len({e["case_id"] for e in per_episode}),
        "n_episodes": len(per_episode),
        "final_hypotheses": [to_jsonable(h) for h in ledger.concurrent()],
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
