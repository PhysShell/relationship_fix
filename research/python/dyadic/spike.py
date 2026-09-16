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
from .topology import build_nodes, build_topology, resolve_response
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
                                          (InteractionRelation.EXPLICIT_REPLY
                     if edge.relation is MessageRelation.EXPLICIT_REPLY_TO
                     else InteractionRelation.ADJACENT_CROSS_ACTOR_TURN),
                    edge.basis, edge.relation))
                if topic_known:
                    edges.append(RelationEdge(
                        src.observation_id, dst.observation_id,
                        InteractionRelation.TOPIC_CONTINUITY if same_topic
                        else InteractionRelation.TOPIC_DISCONTINUITY,
                        f"recorded topic {'==' if same_topic else '!='}"
                        f" ({src_node.topic} -> {dst_node.topic})", edge.relation))
                if src.label in NEGATIVE and dst.label in NEGATIVE:
                    edges.append(RelationEdge(src.observation_id, dst.observation_id,
                                              InteractionRelation.NEGATIVE_RESPONSE,
                                              "negative turn adjacent to a negative turn", edge.relation))
                if src.label in NEGATIVE and dst.label in SOFTENING:
                    edges.append(RelationEdge(src.observation_id, dst.observation_id,
                                              InteractionRelation.SOFTENING_RESPONSE,
                                              "softening turn adjacent to a negative turn", edge.relation))
    return edges


def _adjacent_or_reply(rel):
    """Both deterministic response relations, explicit reply first."""
    return rel(InteractionRelation.EXPLICIT_REPLY) + rel(InteractionRelation.ADJACENT_CROSS_ACTOR_TURN)


def _event(eid, etype, parts, episode_id, obs, status, evidence=(), counter=(), basis=""):
    return RelationalEvent(
        event_id=eid, event_type=etype, participants=tuple(parts), episode_id=episode_id,
        source_observations=tuple(o.observation_id for o in obs),
        supporting_evidence=tuple(evidence), counterevidence=tuple(counter), status=status,
        basis=basis,
    )


def _outcome(nodes, coded: set[str], obs_by_message, anchor_message: str,
             wanted: set[str], unwanted: set[str] = frozenset()):
    """The one response-resolution ladder every pattern goes through.

    Returns (status, reply_observations, basis). The ladder exists so that an
    opportunity can never be asserted without an event carrying its outcome:

        no response at all            -> RIGHT_CENSORED      (record ended)
        response outside coding frame -> INSUFFICIENT        (we cannot tell
                                         "checked, nothing" from "not coded")
        response carries `unwanted`   -> COUNTER
        response carries `wanted`     -> SUPPORTING
        response coded, neither       -> OBSERVED_ABSENCE    (we looked, the frame
                                         applied, it was not there)

    The third rung is the one that matters. A label missing from a message means
    either "coded and absent" or "never coded here", and only an explicit coding
    frame can tell those apart. Inferring absence from an empty label list was
    how "not observed" used to become "pattern weakened".
    """
    candidate = resolve_response(nodes, anchor_message)
    if candidate is None:
        return EvidenceStatus.RIGHT_CENSORED, [], "record ends before a response could appear"
    reply_id = candidate.node.message_id
    if reply_id not in coded:
        return (EvidenceStatus.INSUFFICIENT_OBSERVATION, [],
                f"response {reply_id} is outside the coding frame")
    replies = obs_by_message.get(reply_id, [])
    via = f"via {candidate.basis.value}"
    hit_bad = [r for r in replies if r.label in unwanted]
    if hit_bad:
        return EvidenceStatus.COUNTER, hit_bad, f"response carries {sorted({r.label for r in hit_bad})} ({via})"
    hit_good = [r for r in replies if r.label in wanted]
    if hit_good:
        return EvidenceStatus.SUPPORTING, hit_good, f"response carries {sorted({r.label for r in hit_good})} ({via})"
    return EvidenceStatus.OBSERVED_ABSENCE, replies, f"response coded, neither outcome present ({via})"


def derive_events(
    episode_id: str,
    nodes: list[MessageNode],
    observations: list[BehaviorObservation],
    actors: tuple[str, ...],
    coded_messages: set[str] | None = None,
) -> tuple[list[RelationalEvent], list[RelationalEvent], list[RelationEdge]]:
    """L2.5 -> L3. One event per triggered pattern, always carrying an outcome.

    There is no separate `opportunities` channel any more. A pattern that had a
    chance to show itself produces an event saying what happened; the ledger reads
    only events and never infers anything from their absence. That turns
    "absence is not counterevidence" from an agreement between two functions into
    an algebraic property of the ledger.
    """
    events: list[RelationalEvent] = []
    safety: list[RelationalEvent] = []
    relations = derive_relations(nodes, observations)
    by_id = {o.observation_id: o for o in observations}
    obs_by_message: dict[str, list[BehaviorObservation]] = {}
    for o in observations:
        obs_by_message.setdefault(o.message_id, []).append(o)
    coded = coded_messages if coded_messages is not None else set(obs_by_message)
    a, b = actors
    ev = lambda os: tuple(sp for o in os for sp in o.evidence)  # noqa: E731

    def rel(kind):
        return [(by_id[e.from_observation], by_id[e.to_observation])
                for e in relations if e.relation is kind]

    def emit(pattern, parts, anchor_obs, wanted, unwanted=frozenset(), suffix=""):
        status, replies, basis = _outcome(nodes, coded, obs_by_message,
                                          anchor_obs.message_id, wanted, unwanted)
        obs = [anchor_obs] + list(replies)
        events.append(_event(
            f"{episode_id}:{pattern}{suffix}:{anchor_obs.observation_id}", pattern, parts,
            episode_id, obs, status,
            evidence=ev(obs) if status is EvidenceStatus.SUPPORTING else (),
            counter=ev(replies) if status is EvidenceStatus.COUNTER else (),
            basis=basis))

    # attack_attack: a negative move, and whatever the partner's response was.
    # NOTE: NEGATIVE_RESPONSE, not "escalation" — a single adjacent negative pair
    # cannot show conflict sustained over time.
    for o in observations:
        if o.label in NEGATIVE:
            emit("attack_attack", actors, o, wanted=NEGATIVE)

    # pursue_withdraw: triggered only by REPEATED pursuit from one side.
    for pursuer, other in ((a, b), (b, a)):
        pursuit = [o for o in observations if o.actor == pursuer and o.label in PURSUING]
        if len(pursuit) < 2:
            continue
        anchor = pursuit[-1]
        status, replies, basis = _outcome(nodes, coded, obs_by_message, anchor.message_id,
                                          wanted=set(), unwanted=UPTAKE)
        if status is EvidenceStatus.OBSERVED_ABSENCE:
            # Coded reply with no uptake. Non-uptake still has to be ARGUED: the
            # recorded topic must also have diverged.
            diverged = any(src.observation_id == anchor.observation_id
                           for src, _ in rel(InteractionRelation.TOPIC_DISCONTINUITY))
            if diverged:
                status, basis = EvidenceStatus.SUPPORTING, "topic diverged AND reply carries no uptake"
            else:
                basis = "reply carries no uptake, but the topic did not diverge"
        obs = [anchor] + list(replies)
        events.append(_event(f"{episode_id}:pursue_withdraw:{pursuer}", "pursue_withdraw",
                             (pursuer, other), episode_id, obs, status,
                             evidence=ev(obs) if status is EvidenceStatus.SUPPORTING else (),
                             counter=ev(replies) if status is EvidenceStatus.COUNTER else (),
                             basis=basis))

    # repair_softening: a softening move + the partner's observed response.
    for o in observations:
        if o.label in SOFTENING:
            emit("repair_softening", actors, o,
                 wanted=UPTAKE | SOFTENING | ALIGNING, unwanted=NEGATIVE)

    # constructive_alignment: an aligning move + the partner's response.
    for o in observations:
        if o.label in ALIGNING:
            emit("constructive_alignment", actors, o, wanted=ALIGNING)

    # No mixed_transition event: derived from which hypotheses are live.

    for o in observations:
        if o.label in SAFETY_RELEVANT:
            safety.append(_event(f"{episode_id}:safety:{o.observation_id}", "safety_relevant",
                                 (o.actor,), episode_id, [o], EvidenceStatus.SUPPORTING, ev([o])))
    return events, safety, relations


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
            declared = case.get("coded_messages")
            coded = set(declared) & member if declared is not None else None
            events, safety_events, relations = derive_events(
                ep_id, nodes, ep_obs, actors, coded)
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
                "topology": [to_jsonable(e) for e in build_topology(nodes)],
                "relations": [to_jsonable(r) for r in relations],
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
