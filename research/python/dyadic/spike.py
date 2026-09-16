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
    MessageNode,
    MessageRelation,
    RelationalEvent,
    RelationEdge,
    content_hash,
    to_jsonable,
)
from .topology import build_nodes, build_topology, response_message, window_is_observable
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


def derive_relations(nodes: list[MessageNode], observations: list[BehaviorObservation]
                     ) -> list[RelationEdge]:
    """L1.5 + L2 -> L2.5.

    Every interaction relation is grounded in a MESSAGE relation. Observations
    only enrich edges that conversation structure already established, so an
    unlabelled message in between breaks the chain exactly as it should, and the
    number of labels on a message cannot reshape the topology.
    """
    edges: list[RelationEdge] = []
    obs_by_message: dict[str, list[BehaviorObservation]] = {}
    for o in observations:
        obs_by_message.setdefault(o.message_id, []).append(o)

    for edge in build_topology(nodes):
        if edge.relation not in (MessageRelation.NEXT_BY_OTHER_ACTOR,
                                 MessageRelation.EXPLICIT_REPLY_TO):
            continue
        src_node = next((n for n in nodes if n.message_id == edge.from_message), None)
        dst_node = next((n for n in nodes if n.message_id == edge.to_message), None)
        if src_node is None or dst_node is None:
            continue
        topic_known = src_node.topic is not None and dst_node.topic is not None
        same_topic = topic_known and src_node.topic == dst_node.topic

        for src in obs_by_message.get(edge.from_message, []):
            for dst in obs_by_message.get(edge.to_message, []):
                edges.append(RelationEdge(src.observation_id, dst.observation_id,
                                          InteractionRelation.RESPONDS_TO, edge.basis, edge.relation))
                if topic_known:
                    edges.append(RelationEdge(
                        src.observation_id, dst.observation_id,
                        InteractionRelation.CONTINUES_TOPIC if same_topic
                        else InteractionRelation.TOPIC_DISCONTINUITY,
                        f"recorded topic {'==' if same_topic else '!='}"
                        f" ({src_node.topic} -> {dst_node.topic})", edge.relation))
                if src.label in NEGATIVE and dst.label in NEGATIVE:
                    edges.append(RelationEdge(src.observation_id, dst.observation_id,
                                              InteractionRelation.ESCALATES,
                                              "negative answered by negative", edge.relation))
                if src.label in NEGATIVE and dst.label in SOFTENING:
                    edges.append(RelationEdge(src.observation_id, dst.observation_id,
                                              InteractionRelation.SOFTENS,
                                              "negative answered by softening", edge.relation))
    return edges


def _event(eid, etype, parts, episode_id, obs, status, evidence=(), counter=(), basis=""):
    return RelationalEvent(
        event_id=eid, event_type=etype, participants=tuple(parts), episode_id=episode_id,
        source_observations=tuple(o.observation_id for o in obs),
        supporting_evidence=tuple(evidence), counterevidence=tuple(counter), status=status,
        basis=basis,
    )


def pattern_opportunities(nodes: list[MessageNode],
                          observations: list[BehaviorObservation],
                          actors: tuple[str, ...]) -> set[str]:
    """Which patterns COULD have shown themselves here.

    Pattern-specific, not "any negative move opens everything". The previous
    version let a single negative turn count as a chance for both attack_attack
    and pursue_withdraw, so a hypothesis could age on episodes whose structural
    preconditions never existed.

    Every clause requires an OBSERVABLE RESPONSE WINDOW: a trigger with no later
    message by the other actor is right-censored, not a missed chance.
    """
    out: set[str] = set()
    a, b = actors

    def triggered(labels: set[str], min_count: int = 1) -> list[BehaviorObservation]:
        return [o for o in observations if o.label in labels][:] if min_count == 1 else []

    def window(o: BehaviorObservation) -> bool:
        return window_is_observable(nodes, o.message_id)

    if any(o.label in NEGATIVE and window(o) for o in observations):
        out.add("attack_attack")
    for pursuer in (a, b):
        pursuit = [o for o in observations if o.actor == pursuer and o.label in PURSUING]
        partner_present = any(n.actor != pursuer for n in nodes)
        if len(pursuit) >= 2 and partner_present and any(window(o) for o in pursuit):
            out.add("pursue_withdraw")
    if any(o.label in SOFTENING and window(o) for o in observations):
        out.add("repair_softening")
    if any(o.label in ALIGNING and window(o) for o in observations):
        out.add("constructive_alignment")
    return out


def derive_events(
    episode_id: str,
    nodes: list[MessageNode],
    observations: list[BehaviorObservation],
    actors: tuple[str, ...],
) -> tuple[list[RelationalEvent], list[RelationalEvent], set[str], list[RelationEdge]]:
    """L2.5 -> L3. Predicates are statements about relations, never about labels
    co-occurring somewhere in the episode."""
    events: list[RelationalEvent] = []
    safety: list[RelationalEvent] = []
    relations = derive_relations(nodes, observations)
    by_id = {o.observation_id: o for o in observations}
    obs_by_message: dict[str, list[BehaviorObservation]] = {}
    for o in observations:
        obs_by_message.setdefault(o.message_id, []).append(o)
    a, b = actors
    ev = lambda os: tuple(sp for o in os for sp in o.evidence)  # noqa: E731

    def rel(kind):
        return [(by_id[e.from_observation], by_id[e.to_observation])
                for e in relations if e.relation is kind]

    opportunities = pattern_opportunities(nodes, observations, actors)

    # attack_attack: negative ANSWERED BY negative.
    escalations = rel(InteractionRelation.ESCALATES)
    if escalations:
        obs = [o for pair in escalations for o in pair]
        events.append(_event(f"{episode_id}:aa", "attack_attack", actors, episode_id,
                             obs, EvidenceStatus.SUPPORTING, ev(obs),
                             basis="negative answered by negative"))

    # pursue_withdraw. NON-UPTAKE IS ARGUED FOR, NOT ASSUMED: topic discontinuity
    # alone is not enough, the responding message must also carry no uptake
    # observation. Topic difference by itself can be "yes, and also...".
    for pursuer, other in ((a, b), (b, a)):
        pursuit = [o for o in observations if o.actor == pursuer and o.label in PURSUING]
        if len(pursuit) < 2:
            continue
        parts = (pursuer, other)
        answered = [(src, dst) for src, dst in rel(InteractionRelation.CONTINUES_TOPIC)
                    if src.actor == pursuer and dst.label in UPTAKE]
        non_uptake = []
        for src, dst in rel(InteractionRelation.TOPIC_DISCONTINUITY):
            if src.actor != pursuer or src.label not in PURSUING:
                continue
            siblings = obs_by_message.get(dst.message_id, [])
            if any(sib.label in UPTAKE for sib in siblings):
                continue   # the same message did take the topic up elsewhere
            non_uptake.append((src, dst))
        censored = [o for o in pursuit if not window_is_observable(nodes, o.message_id)]

        if answered:
            obs = [o for pair in answered for o in pair]
            events.append(_event(f"{episode_id}:pw-counter:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, obs, EvidenceStatus.COUNTER, counter=ev(obs),
                                 basis="pursuit taken up on topic"))
        elif non_uptake:
            obs = [o for pair in non_uptake for o in pair]
            events.append(_event(f"{episode_id}:pw:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, obs, EvidenceStatus.SUPPORTING, ev(obs),
                                 basis="topic discontinuity AND no uptake anywhere in the reply"))
        elif censored:
            events.append(_event(f"{episode_id}:pw-censored:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, pursuit, EvidenceStatus.RIGHT_CENSORED,
                                 basis="record ends before a response could appear"))
        else:
            events.append(_event(f"{episode_id}:pw-insuff:{pursuer}", "pursue_withdraw", parts,
                                 episode_id, pursuit, EvidenceStatus.INSUFFICIENT_OBSERVATION,
                                 basis="no topic recorded, or no codable response"))

    # repair_softening: softening + the partner's OBSERVED response.
    for o in observations:
        if o.label not in SOFTENING:
            continue
        reply_node = response_message(nodes, o.message_id)
        if reply_node is None:
            events.append(_event(f"{episode_id}:rs-censored:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o], EvidenceStatus.RIGHT_CENSORED,
                                 basis="record ends right after the softening move"))
            continue
        replies = obs_by_message.get(reply_node.message_id, [])
        if not replies:
            # They DID reply; nothing codable came back. Observed, not censored.
            events.append(_event(f"{episode_id}:rs-absence:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o], EvidenceStatus.OBSERVED_ABSENCE,
                                 basis="partner replied but no codable uptake"))
        elif any(r.label in NEGATIVE for r in replies):
            neg = [r for r in replies if r.label in NEGATIVE]
            events.append(_event(f"{episode_id}:rs-counter:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o] + neg, EvidenceStatus.COUNTER,
                                 counter=ev(neg), basis="softening answered by renewed negativity"))
        elif any(r.label in UPTAKE | SOFTENING | ALIGNING for r in replies):
            good = [r for r in replies if r.label in UPTAKE | SOFTENING | ALIGNING]
            events.append(_event(f"{episode_id}:rs:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o] + good, EvidenceStatus.SUPPORTING,
                                 ev([o] + good), basis="softening answered by observed uptake"))
        else:
            events.append(_event(f"{episode_id}:rs-absence:{o.observation_id}", "repair_softening",
                                 actors, episode_id, [o] + replies, EvidenceStatus.OBSERVED_ABSENCE,
                                 basis="partner replied with neither uptake nor negativity"))

    # constructive_alignment: aligning ANSWERED BY aligning.
    aligned = [(src, dst) for src, dst in rel(InteractionRelation.RESPONDS_TO)
               if src.label in ALIGNING and dst.label in ALIGNING]
    if aligned:
        obs = [o for pair in aligned for o in pair]
        events.append(_event(f"{episode_id}:ca", "constructive_alignment", actors, episode_id,
                             obs, EvidenceStatus.SUPPORTING, ev(obs),
                             basis="aligning move answered by aligning move"))

    # No mixed_transition event: it is derived from which hypotheses are live.

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
        # topic and reply_to belong to the MESSAGE, supplied like labels are.
        topics = {m["message_id"]: m["topic"] for m in case["messages"] if m.get("topic")}
        replies = {m["message_id"]: m["reply_to"] for m in case["messages"] if m.get("reply_to")}
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
            ep_messages = [m for m in messages if m.message_id in member]
            nodes = build_nodes(ep_messages, topics, replies)
            events, safety_events, opportunities, relations = derive_events(
                ep_id, nodes, ep_obs, actors)
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
                "topology": [to_jsonable(e) for e in build_topology(nodes)],
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
