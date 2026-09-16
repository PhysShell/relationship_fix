"""Probe: can our frozen L1.5 express real human reply-graph annotations?

External Measurement & Calibration Audit, TRACK 1. This is a REPRESENTATION
compatibility check, not a model: before training anything on human-annotated
conversation structure, find out whether our representation can hold that
structure at all without silently dropping part of it.

Reference annotation: Kummerfeld et al., "A Large-Scale Corpus for Conversation
Disentanglement" (ACL 2019), https://aclanthology.org/P19-1374/. Their guideline,
verbatim: "link each message to the ONE OR MORE messages it is a response to. If
a message started a new conversation it was linked to itself."

This module imports `dyadic` read-only and changes nothing in it: the spike is
frozen at 852d3c2 and a probe that repaired the thing it is probing would be
worthless.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dyadic.model import MessageNode          # noqa: E402
from dyadic.segmentation import Message       # noqa: E402
from dyadic.topology import build_nodes       # noqa: E402

SOURCE = "Kummerfeld et al. 2019, ACL P19-1374"


@dataclass(frozen=True, slots=True)
class ReplyAnnotation:
    """One human annotation in the reference schema.

    `antecedents` is a tuple because the guideline explicitly permits more than
    one. A self-link (antecedent == message_id) means "this starts a new
    conversation" — a third thing that is neither a reply nor an absence of one.
    """

    message_id: str
    antecedents: tuple[str, ...]

    @property
    def is_conversation_start(self) -> bool:
        return self.antecedents == (self.message_id,)

    @property
    def is_multi_antecedent(self) -> bool:
        return len(self.antecedents) > 1


@dataclass
class LosslessnessReport:
    """What survived the adapter and what did not.

    Deliberately shaped as a list of losses rather than a score. A percentage
    would let a representation that drops one critical construct look 97% fine.
    """

    n_annotations: int = 0
    expressible: list[str] = field(default_factory=list)
    lost_multi_antecedent: list[str] = field(default_factory=list)
    lost_conversation_start: list[str] = field(default_factory=list)
    lost_cross_turn: list[str] = field(default_factory=list)

    @property
    def lossless(self) -> bool:
        return not (self.lost_multi_antecedent
                    or self.lost_conversation_start
                    or self.lost_cross_turn)

    def as_dict(self) -> dict:
        return {
            "source": SOURCE,
            "n_annotations": self.n_annotations,
            "n_expressible": len(self.expressible),
            "lossless": self.lossless,
            "losses": {
                "multi_antecedent": {
                    "n": len(self.lost_multi_antecedent),
                    "message_ids": self.lost_multi_antecedent,
                    "why": ("MessageNode.reply_to holds a single id; the reference "
                            "guideline permits linking a message to one OR MORE "
                            "antecedents, so every extra link is dropped"),
                },
                "conversation_start": {
                    "n": len(self.lost_conversation_start),
                    "message_ids": self.lost_conversation_start,
                    "why": ("a self-link marks 'starts a new conversation'. Our "
                            "representation has no third value: reply_to=None is "
                            "read as 'no reply metadata', which is a different "
                            "claim from 'annotated as a thread opener'"),
                },
                "cross_turn": {
                    "n": len(self.lost_cross_turn),
                    "message_ids": self.lost_cross_turn,
                    "why": ("the antecedent is not the adjacent cross-actor turn; "
                            "expressible via reply_to, but any consumer that falls "
                            "back to adjacency resolves it wrongly"),
                },
            },
        }


def adapt(messages: list[Message],
          annotations: list[ReplyAnnotation]) -> tuple[list[MessageNode], LosslessnessReport]:
    """Project reference annotations onto our L1.5 and report what is lost."""
    report = LosslessnessReport(n_annotations=len(annotations))
    order = {m.message_id: i for i, m in enumerate(messages)}
    actor = {m.message_id: m.author for m in messages}
    reply_to: dict[str, str] = {}

    for ann in annotations:
        if ann.is_conversation_start:
            # Nothing to carry: we cannot say "annotated as a thread opener".
            report.lost_conversation_start.append(ann.message_id)
            continue
        if ann.is_multi_antecedent:
            report.lost_multi_antecedent.append(ann.message_id)
        if not ann.antecedents:
            continue

        primary = ann.antecedents[0]
        reply_to[ann.message_id] = primary
        report.expressible.append(ann.message_id)

        idx = order.get(ann.message_id)
        adjacent = None
        if idx is not None:
            adjacent = next((m.message_id for m in messages[:idx][::-1]
                             if actor.get(m.message_id) != actor.get(ann.message_id)), None)
        if adjacent is not None and primary != adjacent:
            report.lost_cross_turn.append(ann.message_id)

    return build_nodes(messages, {}, reply_to), report
