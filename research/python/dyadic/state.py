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
    OBSERVED_ABSENCE_IS_AN_OPPORTUNITY,
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
)

# `mixed_transition` is deliberately NOT here. RESCUE-Bench needed it because a
# single categorical state forces one label and loses the rest; we allow several
# concurrent hypotheses instead, so keeping a mixed_transition hypothesis would
# be abolishing the escape hatch and then housing it next door. It is a DERIVED
# presentation property (see `is_mixed_transition`) with no ledger of its own.
NEGATIVE_PATTERNS = ("attack_attack", "pursue_withdraw", "withdraw_withdraw")
SOFTENING_PATTERNS = ("repair_softening", "constructive_alignment")

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

    def concurrent(self, min_status: HypothesisStatus = HypothesisStatus.CANDIDATE) -> list[StateHypothesis]:
        """All live hypotheses, most-supported first. Ties broken by id so the
        ordering is deterministic and traces diff cleanly.

        Named `concurrent`, not `competing`: `attack_attack` and `repair_softening`
        routinely hold at once and are not rivals for one slot. Genuine rivalry is
        a special case, not the general shape.
        """
        order = list(HypothesisStatus)
        live = [h for h in self.hypotheses.values() if h.status is not HypothesisStatus.RETIRED]
        live = [h for h in live if order.index(h.status) >= order.index(min_status)]
        return sorted(live, key=lambda h: (-h.components.observed_support, h.hypothesis_id))

    # --- writing -------------------------------------------------------------

    def observe_episode(self, episode_id: str, events: list[RelationalEvent]) -> None:
        """Fold one episode's events into the ledger.

        EVENTS ARE THE ONLY INPUT. There is no parallel `opportunities` channel,
        and nothing is inferred from an event's absence. A hypothesis ages only
        when an event explicitly says OBSERVED_ABSENCE for that pattern — i.e.
        only when a response was resolved, was inside the coding frame, and did
        not carry the outcome. That makes "absence is not counterevidence" a
        property of this method rather than an agreement between two functions.
        """
        if episode_id not in self.episode_order:
            self.episode_order.append(episode_id)

        opportunities: set[str] = set()
        for event in events:
            if (OBSERVED_ABSENCE_IS_AN_OPPORTUNITY
                    and event.status is EvidenceStatus.OBSERVED_ABSENCE):
                opportunities.add(event.event_type)
            self._apply(episode_id, event)

        for hid, h in list(self.hypotheses.items()):
            if h.pattern in opportunities and episode_id not in h.opportunity_episodes:
                h = replace(h, opportunity_episodes=h.opportunity_episodes + (episode_id,))
                self.hypotheses[hid] = h
            before = h.status
            since = self._opportunities_since_support(h)
            after = derive_status(h.components, since)
            if after is not before and h.status is not HypothesisStatus.RETIRED:
                self.hypotheses[hid] = replace(h, status=after)
                self.transitions.append({
                    "episode_id": episode_id,
                    "hypothesis_id": hid,
                    "from": before.value,
                    "to": after.value,
                    "opportunities_since_support": since,
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
                    observed_support=c.observed_support + 1,
                    distinct_episodes=len(episodes),
                ),
            )
        elif event.status is EvidenceStatus.COUNTER:
            # Counterevidence never deletes support; it accumulates beside it and
            # can move the hypothesis to WEAKENED via derive_status.
            h = replace(
                h,
                evidence_against=h.evidence_against + (event.event_id,),
                components=replace(c, observed_counter=c.observed_counter + 1),
            )
        elif event.status is EvidenceStatus.OBSERVED_ABSENCE:
            # We looked, the window was open, the thing was not there. That IS an
            # observation: it keeps coverage high and counts as an opportunity.
            # Still never written into evidence_against, still advances nothing.
            h = replace(h, components=replace(c, observed_absence=c.observed_absence + 1))
        elif event.status in (EvidenceStatus.RIGHT_CENSORED,
                              EvidenceStatus.INSUFFICIENT_OBSERVATION):
            # We could not look: the record ended, or there was no window. Lowers
            # coverage and must NOT age the hypothesis.
            h = replace(h, components=replace(
                c, insufficient_observation=c.insufficient_observation + 1))
        # NOT_APPLICABLE touches nothing at all: the slot did not apply here.

        self.hypotheses[hid] = h

    def retire_hypothesis(self, hypothesis_id: str, reason: str) -> None:
        h = self.hypotheses.get(hypothesis_id)
        if h is not None:
            self.hypotheses[hypothesis_id] = retire(h, reason)

    # --- helpers -------------------------------------------------------------

    def _opportunities_since_support(self, h: StateHypothesis) -> int:
        """Count episodes that WERE a chance for this pattern and came after its
        last support. Episodes where the pattern could not have been observed are
        not counted, so a quiet week cannot weaken a hypothesis by itself."""
        if h.last_supported_episode is None:
            return 0
        try:
            cutoff = self.episode_order.index(h.last_supported_episode)
        except ValueError:
            return 0
        return sum(
            1 for ep in h.opportunity_episodes
            if ep in self.episode_order and self.episode_order.index(ep) > cutoff
        )

    def is_mixed_transition(self) -> bool:
        """DERIVED, not a hypothesis: an ESTABLISHED negative and an ESTABLISHED
        softening hypothesis are both live. No ledger, no evidence of its own,
        nothing to age.

        Candidates do not count: a single unanswered softening move should not
        make the whole snapshot 'mixed', or the property is true from episode
        three onwards forever and says nothing.
        """
        live = {h.pattern for h in self.concurrent(HypothesisStatus.SUPPORTED)}
        return bool(live & set(NEGATIVE_PATTERNS)) and bool(live & set(SOFTENING_PATTERNS))


# --- safety accumulation -----------------------------------------------------

# SPIKE-ONLY PLACEHOLDERS. These numbers are NOT a validated safety threshold and
# were never derived from anything: they are set higher than pattern recurrence so
# the gate cannot fire on one ambiguous message, and that is their entire
# justification. Named this way on purpose, because in six months someone will find
# a ready-made boolean `gate_open` and assume that code existing makes a number
# scientific. A real threshold needs a safety review and evidence neither of which
# exists yet.
SPIKE_ONLY_SAFETY_MIN_EPISODES = 3
SPIKE_ONLY_SAFETY_MIN_EVENTS = 4
SAFETY_POLICY_PROVENANCE = "synthetic_placeholder"


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
        return (len(self.episodes) >= SPIKE_ONLY_SAFETY_MIN_EPISODES
                and len(self.events) >= SPIKE_ONLY_SAFETY_MIN_EVENTS)

    def as_flags(self) -> dict:
        return {
            "coercive_control_accumulation": {
                "n_events": len(self.events),
                "n_episodes": len(self.episodes),
                "gate_open": self.gate_open,
                "policy_provenance": SAFETY_POLICY_PROVENANCE,
                "thresholds_are_placeholders": True,
                "meaning": (
                    "capability gate: when open, symmetric couples advice and joint "
                    "mediation are suppressed. NOT a determination about any person."
                ),
            }
        }
