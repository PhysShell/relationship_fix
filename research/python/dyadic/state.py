"""Hypothesis ledger and transition model.

There is no `current_state` variable anywhere in here, and that is the central
design claim: a dyad is represented as a set of competing hypotheses, each with
its own evidence ledger (docs/research/dyadic-state-model.md §3).

Forbidden by construction:
  - a latest-LLM-summary-wins update path (invariant 1);
  - a single scalar confidence (safety-policy §3 forbids relationship scores);
  - silence counted as evidence of disengagement (WITHDRAWAL research);
  - any person-level label (invariant 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .model import (
    ConfidenceComponents,
    EvidenceStatus,
    HypothesisStatus,
    RelationalEvent,
    StateHypothesis,
    derive_status,
    retire,
)

# Candidate patterns. Named after RESCUE-Bench's couple relation patterns so the
# crosswalk stays honest, but NOT adopted as validated: that benchmark's labels
# come from LLM pre-annotation verified by three annotators with no inter-annotator
# agreement reported, over multimodal therapy video. See
# docs/research/dyadic-state-model.md §2 for what that does and does not license.
PATTERNS = (
    "pursue_withdraw",
    "attack_attack",
    "withdraw_withdraw",
    "repair_softening",
    "constructive_alignment",
    "mixed_transition",
)

# Slots that a text-only observer cannot fill for each pattern. Kept explicit
# rather than discovered at runtime, so that "we did not look" is a property of
# the design and shows up in every trace.
TEXT_UNOBSERVABLE_SLOTS: dict[str, tuple[str, ...]] = {
    "pursue_withdraw": ("withdrawer_internal_disengagement",),
    "withdraw_withdraw": ("both_internal_disengagement",),
}


@dataclass
class HypothesisLedger:
    """Mutable holder of immutable hypotheses. Every update is additive."""

    hypotheses: dict[str, StateHypothesis] = field(default_factory=dict)
    episode_order: list[str] = field(default_factory=list)
    transitions: list[dict] = field(default_factory=list)

    # --- reading -------------------------------------------------------------

    def competing(self, min_status: HypothesisStatus = HypothesisStatus.CANDIDATE) -> list[StateHypothesis]:
        """All live hypotheses, most-supported first. Ties are broken by id so the
        ordering is deterministic and a trace can be diffed across runs."""
        order = list(HypothesisStatus)
        live = [h for h in self.hypotheses.values() if h.status is not HypothesisStatus.RETIRED]
        live = [h for h in live if order.index(h.status) >= order.index(min_status)]
        return sorted(live, key=lambda h: (-h.components.support_count, h.hypothesis_id))

    # --- writing -------------------------------------------------------------

    def observe_episode(self, episode_id: str, events: list[RelationalEvent]) -> None:
        """Fold one episode's events into the ledger.

        Order of operations is fixed: register the episode, apply every event,
        then re-derive status for every hypothesis — including ones this episode
        said nothing about, because staleness is a function of elapsed observable
        episodes, not of wall-clock time.
        """
        if episode_id not in self.episode_order:
            self.episode_order.append(episode_id)

        for event in events:
            self._apply(episode_id, event)

        for hid, h in list(self.hypotheses.items()):
            before = h.status
            since = self._episodes_since(h.last_supported_episode)
            after = derive_status(h.components, since)
            if after is not before and h.status is not HypothesisStatus.RETIRED:
                self.hypotheses[hid] = replace(h, status=after)
                self.transitions.append({
                    "episode_id": episode_id,
                    "hypothesis_id": hid,
                    "from": before.value,
                    "to": after.value,
                    "episodes_since_support": since,
                })

    def _apply(self, episode_id: str, event: RelationalEvent) -> None:
        pattern = event.event_type
        hid = f"{pattern}:{'+'.join(event.participants)}"
        h = self.hypotheses.get(hid) or StateHypothesis(
            hypothesis_id=hid,
            pattern=pattern,
            participants=event.participants,
            status=HypothesisStatus.CANDIDATE,
            unobserved_slots=TEXT_UNOBSERVABLE_SLOTS.get(pattern, ()),
        )
        c = h.components

        if event.status is EvidenceStatus.SUPPORTING:
            # Recurrence counts DISTINCT supporting episodes, held explicitly.
            # Deriving it from first_seen/last_supported silently caps at 2-3 and
            # makes a twenty-episode pattern indistinguishable from a two-episode
            # one — caught by the spike trace, see dyadic-state-model.md §8.
            episodes = h.supporting_episodes
            if episode_id not in episodes:
                episodes = episodes + (episode_id,)
            h = replace(
                h,
                evidence_for=h.evidence_for + (event.event_id,),
                supporting_episodes=episodes,
                first_seen_episode=h.first_seen_episode or episode_id,
                last_supported_episode=episode_id,
                components=replace(
                    c,
                    support_count=c.support_count + 1,
                    observed_slots=c.observed_slots + 1,
                    distinct_episodes=len(episodes),
                ),
            )
        elif event.status is EvidenceStatus.COUNTER:
            # Counterevidence never deletes support; it accumulates beside it and
            # can move the hypothesis to WEAKENED via derive_status.
            h = replace(
                h,
                evidence_against=h.evidence_against + (event.event_id,),
                components=replace(c, counter_count=c.counter_count + 1,
                                   observed_slots=c.observed_slots + 1),
            )
        elif event.status in (EvidenceStatus.ABSENT, EvidenceStatus.INSUFFICIENT_OBSERVATION):
            # THE load-bearing branch. Not-observed lowers coverage; it is never
            # written into evidence_against and never advances the hypothesis.
            h = replace(h, components=replace(c, unobservable_slots=c.unobservable_slots + 1))
        # NOT_APPLICABLE touches nothing at all: the slot did not apply here.

        self.hypotheses[hid] = h

    def retire_hypothesis(self, hypothesis_id: str, reason: str) -> None:
        h = self.hypotheses.get(hypothesis_id)
        if h is not None:
            self.hypotheses[hypothesis_id] = retire(h, reason)

    # --- helpers -------------------------------------------------------------

    def _episodes_since(self, episode_id: str | None) -> int:
        if episode_id is None or episode_id not in self.episode_order:
            return 0
        return len(self.episode_order) - 1 - self.episode_order.index(episode_id)


# --- safety accumulation -----------------------------------------------------

# Deliberately higher than pattern recurrence: safety gating must not fire on a
# single ambiguous message, and must not be reachable within one episode.
SAFETY_MIN_EPISODES = 3
SAFETY_MIN_EVENTS = 4


@dataclass
class SafetyAccumulator:
    """Accumulates coercive-control-relevant events across episodes.

    Kept structurally separate from PATTERNS because it is not a relational
    pattern and must never be traded off against one. It produces a capability
    gate, not a verdict about a person: safety-policy §12 and invariant 7.
    """

    events: list[str] = field(default_factory=list)
    episodes: set[str] = field(default_factory=set)

    def add(self, episode_id: str, event: RelationalEvent) -> None:
        if event.status is not EvidenceStatus.SUPPORTING:
            return
        self.events.append(event.event_id)
        self.episodes.add(episode_id)

    @property
    def gate_open(self) -> bool:
        """True = the ordinary symmetric-advice class is suppressed.

        Requires accumulation across distinct episodes, so no single exchange —
        however ugly — can open it.
        """
        return len(self.episodes) >= SAFETY_MIN_EPISODES and len(self.events) >= SAFETY_MIN_EVENTS

    def as_flags(self) -> dict:
        return {
            "coercive_control_accumulation": {
                "n_events": len(self.events),
                "n_episodes": len(self.episodes),
                "gate_open": self.gate_open,
                "meaning": (
                    "capability gate: when open, symmetric couples advice and joint "
                    "mediation are suppressed. NOT a determination about any person."
                ),
            }
        }
