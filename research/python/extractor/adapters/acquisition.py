"""Target acquisition qualification: what the real device actually gives us.

The corpus ledger (`SourceSemantics`) asks what a published dataset guarantees.
This asks the same of the acquisition path the pilot will really run on, and it
exists because the human fifth status — "well, WhatsApp usually does that" —
already cost this project once: `user_count` was read as dyad membership
because it sounded like it, and 159 of 400 chats disagreed.

Four statuses, and `PARTIAL` is not a polite synonym for "seems fine". A
`PARTIAL` property must state what downstream may still be computed and what
the adapter does about it. If that consequence cannot be written, the property
is not partial — it is UNKNOWN, and `effective_status` says so out loud rather
than letting the optimistic label stand.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(Enum):
    QUALIFIED = "QUALIFIED"        # the source guarantees it, with evidence
    PARTIAL = "PARTIAL"            # bounded guarantee + a written contract
    UNKNOWN = "UNKNOWN"            # not established; must not be assumed
    UNAVAILABLE = "UNAVAILABLE"    # the source does not provide it at all


class ClaimScope(Enum):
    """How far a claim reaches. Added because `EXPORTED_POSITION` taught us how
    quickly "the source gives an order" becomes "we know the true chronology of
    the universe"."""

    ARTIFACT = "artifact"                    # true of the exported file
    DEVICE_STATE = "device_state"            # true of what the device held
    PHYSICAL_CHRONOLOGY = "physical"         # true of what actually happened


class LedgerError(ValueError):
    """A property that claims more than its evidence carries."""


@dataclass(frozen=True, slots=True)
class Property:
    key: str
    question: str
    claim: str
    status: Status
    claim_scope: ClaimScope
    #: what the claim rests on — a document, a file, a line of source. Never a
    #: forum post, never "everyone knows".
    primary_evidence: tuple[str, ...]
    observed_limitations: tuple[str, ...]
    #: what may still be computed downstream. Mandatory for PARTIAL.
    downstream_consequence: str
    #: what the adapter does, mechanically. Mandatory for PARTIAL and UNAVAILABLE.
    adapter_behavior: str
    #: the fixture or observation that would move the status
    fixture_needed: str

    def __post_init__(self):
        if self.status is Status.QUALIFIED and not self.primary_evidence:
            raise LedgerError(f"{self.key}: QUALIFIED without primary evidence")
        if self.claim_scope is ClaimScope.PHYSICAL_CHRONOLOGY and self.status is not Status.QUALIFIED:
            raise LedgerError(
                f"{self.key}: a claim about physical chronology cannot rest on "
                f"{self.status.value} — narrow the scope or raise the evidence"
            )
        if self.status is Status.UNAVAILABLE and not self.adapter_behavior:
            raise LedgerError(f"{self.key}: UNAVAILABLE without a stated refusal")

    @property
    def effective_status(self) -> Status:
        """`PARTIAL` decays to `UNKNOWN` when no consequence is written.

        Not a silent repair: `demoted` reports it, and the ledger prints both.
        A status is a promise about what may be built; a promise with no stated
        consequence is a mood.
        """
        if self.status is Status.PARTIAL and not (
                self.downstream_consequence and self.adapter_behavior):
            return Status.UNKNOWN
        return self.status

    @property
    def demoted(self) -> bool:
        return self.effective_status is not self.status

    @property
    def usable(self) -> bool:
        """QUALIFIED, or PARTIAL with a contract. Nothing else may be built on."""
        return self.effective_status in (Status.QUALIFIED, Status.PARTIAL)


@dataclass(frozen=True, slots=True)
class Assumption:
    """Something the extractor already does. The TRACK is finished when every
    one of these names the observable property that supports it — or the
    feature that refuses because nothing does."""

    key: str
    made_by: str
    supported_by: str          # Property.key
    if_unsupported: str        # what stops working, concretely
    #: Set when the extractor stopped making the assumption at all, because the
    #: adapter fails closed instead. Then the property behind it may stay
    #: UNKNOWN forever without blocking a freeze: there is nothing left to be
    #: wrong about. An unproved guarantee and an unneeded guarantee are not the
    #: same state, and only the first one is a hole.
    eliminated_by_refusal: str = ""


@dataclass(frozen=True, slots=True)
class Ledger:
    target: str
    acquisition_path: str
    properties: tuple[Property, ...]
    assumptions: tuple[Assumption, ...]

    def __post_init__(self):
        keys = [p.key for p in self.properties]
        if len(keys) != len(set(keys)):
            raise LedgerError("duplicate property keys")
        for assumption in self.assumptions:
            if assumption.supported_by not in keys:
                raise LedgerError(
                    f"{assumption.key}: supported_by {assumption.supported_by!r} "
                    f"is not a property in this ledger"
                )

    def property(self, key: str) -> Property:
        for candidate in self.properties:
            if candidate.key == key:
                return candidate
        raise KeyError(key)

    def by_status(self, status: Status) -> tuple[Property, ...]:
        return tuple(p for p in self.properties if p.effective_status is status)

    def unresolved_assumptions(self) -> tuple[Assumption, ...]:
        """Extractor assumptions with nothing observable behind them.

        The TRACK's exit criterion, and deliberately not "we understood the
        format": for every assumption, either an observable property of the
        target supports it, or it is known why the feature refuses to work.

        Three ways an assumption stops being a hole:

        1. an observable property supports it (QUALIFIED, or PARTIAL with a
           contract);
        2. the source demonstrably does not provide it (UNAVAILABLE) and the
           consequence is written down;
        3. the extractor stopped making it — `eliminated_by_refusal`.

        `UNKNOWN` alone is none of those: it is the state where the extractor
        keeps assuming and nobody has checked.
        """
        return tuple(a for a in self.assumptions
                     if not a.eliminated_by_refusal
                     and self.property(a.supported_by).effective_status is Status.UNKNOWN)

    def summary(self) -> str:
        counts = {s: len(self.by_status(s)) for s in Status}
        parts = [f"{counts[s]} {s.value}" for s in Status if counts[s]]
        demoted = sum(1 for p in self.properties if p.demoted)
        tail = f"; {demoted} demoted from PARTIAL" if demoted else ""
        return (f"{self.target} via {self.acquisition_path}: "
                f"{len(self.properties)} properties — {' · '.join(parts)}{tail}; "
                f"{len(self.unresolved_assumptions())} unresolved assumptions")
