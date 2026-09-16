"""L1.5 — conversation topology over RAW messages.

Built before any labelling and independent of it. The previous spike derived
"who answered whom" from the BehaviorObservation list, which meant the ontology
silently decided the shape of the conversation: an unlabelled message in between
disappeared, and two labels on one message made topology depend on listing order.

Nothing here knows what a behaviour is.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import MessageEdge, MessageNode, MessageRelation
from .segmentation import Message


def build_nodes(messages: list[Message], topics: dict[str, str] | None = None,
                reply_to: dict[str, str] | None = None) -> list[MessageNode]:
    topics = topics or {}
    reply_to = reply_to or {}
    return [
        MessageNode(m.message_id, m.author, order=i, timestamp=m.timestamp,
                    topic=topics.get(m.message_id), reply_to=reply_to.get(m.message_id))
        for i, m in enumerate(messages)
    ]


def build_topology(nodes: list[MessageNode]) -> list[MessageEdge]:
    """Edges over every message, labelled or not.

    `next_by_other_actor` is the only structural response relation: it is the
    first message after this one written by somebody else. Topic edges ride on
    top of it and say only whether the recorded topic changed — they make no
    claim about engagement.
    """
    edges: list[MessageEdge] = []
    by_id = {n.message_id: n for n in nodes}

    for i, src in enumerate(nodes):
        if src.reply_to and src.reply_to in by_id:
            edges.append(MessageEdge(src.reply_to, src.message_id,
                                     MessageRelation.EXPLICIT_REPLY_TO, "reply_to field"))

        nxt = next((n for n in nodes[i + 1:] if n.actor != src.actor), None)
        if nxt is None:
            continue
        edges.append(MessageEdge(src.message_id, nxt.message_id,
                                 MessageRelation.NEXT_BY_OTHER_ACTOR,
                                 "first later message by another actor"))
        if src.topic is not None and nxt.topic is not None:
            same = src.topic == nxt.topic
            edges.append(MessageEdge(
                src.message_id, nxt.message_id,
                MessageRelation.TOPIC_CONTINUITY if same else MessageRelation.TOPIC_DISCONTINUITY,
                f"recorded topic {'==' if same else '!='} ({src.topic} -> {nxt.topic})"))
    return edges


@dataclass(frozen=True, slots=True)
class ResponseCandidate:
    """One possible answer to a message, with the reason it is a candidate.

    Returned as a LIST rather than a single winner: L1.5 already knows a strong
    signal (explicit reply_to) and a weak one (adjacency), and an evaluator that
    silently takes the adjacent turn throws the strong one away. No probabilities;
    just the basis, so the caller decides in the open.
    """

    node: MessageNode
    basis: MessageRelation


def response_candidates(nodes: list[MessageNode], message_id: str) -> list[ResponseCandidate]:
    """Canonical response-resolution policy: explicit reply first, adjacency after.

    Both are returned when both exist, explicit first, so a caller that takes
    `[0]` gets the strong signal and a caller that wants the full picture can see
    that they disagreed.
    """
    idx = next((i for i, n in enumerate(nodes) if n.message_id == message_id), None)
    if idx is None:
        return []
    src = nodes[idx]
    out: list[ResponseCandidate] = []

    explicit = [n for n in nodes[idx + 1:] if n.reply_to == message_id and n.actor != src.actor]
    out.extend(ResponseCandidate(n, MessageRelation.EXPLICIT_REPLY_TO) for n in explicit)

    adjacent = next((n for n in nodes[idx + 1:] if n.actor != src.actor), None)
    if adjacent is not None and all(c.node.message_id != adjacent.message_id for c in out):
        out.append(ResponseCandidate(adjacent, MessageRelation.NEXT_BY_OTHER_ACTOR))
    return out


def resolve_response(nodes: list[MessageNode], message_id: str) -> ResponseCandidate | None:
    """The single best candidate under the canonical policy, or None if censored."""
    candidates = response_candidates(nodes, message_id)
    return candidates[0] if candidates else None


def window_is_observable(nodes: list[MessageNode], message_id: str) -> bool:
    """Was there any chance to see a response at all?

    True iff the other actor sent at least one message afterwards inside this
    episode. If not, the outcome is right-censored: we know the record ended, not
    that the partner stayed silent.
    """
    return bool(response_candidates(nodes, message_id))
