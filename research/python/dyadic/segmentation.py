"""Deterministic episode segmentation baseline.

Explicitly NOT an LLM segmenter and not trying to be good. Its job is to be a
baseline a semantic segmenter must later beat, and to make episode identity
reproducible (docs/research/episode-segmentation.md).

The contrast worth keeping in view: RESCUE-Bench opens a new interaction unit on
"a change in speaker, addressee, interactional function, emotional meaning, or
salient nonverbal behavior". Three of those five are annotator judgements and one
needs video. None of them is decidable from a text log by a deterministic rule,
so this baseline uses only what a log actually carries.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import content_hash

SEGMENTATION_VERSION = "rf.episode-segmentation.v0-deterministic"

# Both are baseline parameters, not findings. They are recorded in every episode
# so a re-run with different values is a different segmentation, not a silent one.
DEFAULT_GAP_SECONDS = 3600
DEFAULT_MAX_MESSAGES = 40


@dataclass(frozen=True, slots=True)
class Message:
    message_id: str
    author: str
    text: str
    timestamp: float | None = None   # epoch seconds; None = no timing available


@dataclass(frozen=True, slots=True)
class Episode:
    episode_id: str
    member_message_ids: tuple[str, ...]
    segmentation_version: str
    gap_seconds: int
    max_messages: int
    boundary_reasons: tuple[str, ...]
    timing_available: bool

    @property
    def n_messages(self) -> int:
        return len(self.member_message_ids)


def segment(
    messages: list[Message],
    gap_seconds: int = DEFAULT_GAP_SECONDS,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> list[Episode]:
    """Split an ordered message list into episodes.

    Boundary rules, in order, all decidable from the log alone:
      1. temporal gap >= gap_seconds between consecutive messages;
      2. hard cap at max_messages, so one long thread cannot become one episode.

    Speaker alternation is deliberately NOT a boundary rule: alternation is the
    normal texture of a conversation, and cutting on it would make every
    adjacency pair its own episode, which destroys exactly the exchange-level
    context the ontology crosswalk says most constructs need.

    Messages without timestamps never produce a temporal boundary; the episode
    records `timing_available=False` so downstream code can refuse to reason
    about latency rather than silently assuming co-presence.
    """
    if not messages:
        return []

    episodes: list[Episode] = []
    current: list[Message] = []
    reasons: list[str] = []

    def flush() -> None:
        if not current:
            return
        ids = tuple(m.message_id for m in current)
        timing = all(m.timestamp is not None for m in current)
        payload = {
            "v": SEGMENTATION_VERSION,
            "ids": list(ids),
            "gap": gap_seconds,
            "max": max_messages,
        }
        episodes.append(Episode(
            episode_id=f"ep-{content_hash(payload)[:12]}",
            member_message_ids=ids,
            segmentation_version=SEGMENTATION_VERSION,
            gap_seconds=gap_seconds,
            max_messages=max_messages,
            boundary_reasons=tuple(reasons),
            timing_available=timing,
        ))

    for i, msg in enumerate(messages):
        if current:
            prev = current[-1]
            gapped = (
                prev.timestamp is not None
                and msg.timestamp is not None
                and msg.timestamp - prev.timestamp >= gap_seconds
            )
            capped = len(current) >= max_messages
            if gapped or capped:
                flush()
                current = []
                reasons = ["temporal_gap" if gapped else "max_messages"]
        current.append(msg)
        if i == len(messages) - 1:
            flush()

    return episodes


def episode_identity(episode: Episode) -> str:
    """Identity is a function of (version, ordered membership, parameters).

    Re-running the same segmenter over the same log yields the same ids; changing
    a parameter yields different ids, which is the intended behaviour — it makes
    an accidental re-segmentation visible instead of silently re-anchoring every
    hypothesis that pointed at the old episodes.
    """
    return content_hash({
        "v": episode.segmentation_version,
        "ids": list(episode.member_message_ids),
        "gap": episode.gap_seconds,
        "max": episode.max_messages,
    })
