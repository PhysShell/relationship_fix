"""Types for the path AROUND the frozen extractor.

Instrumentation qualification asks a different question from everything before
it. Not "does the engine compute correctly" — 109 mutants answered that — but
"does the fuel line deliver the petrol named on the label, and does the exhaust
contain only what the protocol allows".

Five states travel this path, and the whole point is that they arrive intact.
`REFUSED` turning into `0` somewhere in the middle is the failure this module
exists to make impossible, because a zero is indistinguishable from a quiet
person and the study would publish the difference as a finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(Enum):
    """What an acquisition attempt produced. Three of these are not data."""

    ACCEPTED = "accepted"          # the artifact qualified and was measured
    REFUSED = "refused"            # the artifact is unusable; NOT an empty result
    OUT_OF_SCOPE = "out_of_scope"  # readable, but not the target (wrong chat type)
    INCOMPLETE = "incomplete"      # readable, measured, coverage cannot be trusted
    NOT_ATTEMPTED = "not_attempted"  # nothing ran; also not an empty result

    @property
    def carries_measurements(self) -> bool:
        return self in (Verdict.ACCEPTED, Verdict.INCOMPLETE)


class Layer(Enum):
    """Which seam decided. A refusal attributed to the wrong layer is a
    debugging lie, and the ledger checks that each failure is caught where it
    belongs rather than wherever the exception happened to surface."""

    IMPORT = "import"              # bytes → document
    QUALIFICATION = "qualification"  # document → is this our target at all
    ADAPTER = "adapter"            # document → RawMessage, contracts applied
    EXTRACTOR = "extractor"        # the frozen engine
    BOUNDARY = "boundary"          # aggregate → what may leave


@dataclass(frozen=True, slots=True)
class ProtocolWindow:
    """The observation window, supplied BY THE PROTOCOL.

    Never derived from file contents. `coverage.window_provenance` is
    UNAVAILABLE and `coverage.requested_range_honored` is UNAVAILABLE across
    four Telegram Desktop versions spanning seven years, so the first and last
    message in an export say nothing about what was observed.
    """

    participant_id: str
    period_id: str
    start: float
    end: float

    def __post_init__(self):
        if not (self.end > self.start):
            raise ValueError("an observation window must have positive length")

    @property
    def seconds(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class ProducerProvenance:
    """Captured OUT OF BAND, because the export does not record it.

    The writer emits no version field, and semantics demonstrably move between
    versions (tdesktop#30647). A file without a declared producer is undeclared
    semantics, so the pipeline refuses rather than assuming the current build.
    """

    application: str
    version: str
    platform: str
    consent_recorded: bool

    def __post_init__(self):
        for name in ("application", "version", "platform"):
            if not getattr(self, name):
                raise ValueError(f"producer provenance requires {name}")


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing the path noticed. Carries no content, ever."""

    layer: Layer
    code: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class OutwardResult:
    """Everything that may leave the device, and the verdict that explains it.

    `aggregate` is None whenever the verdict does not carry measurements. That
    is deliberate and load-bearing: there is no representation of "refused" that
    also looks like a period in which nothing happened.
    """

    verdict: Verdict
    window: ProtocolWindow
    producer: ProducerProvenance | None
    source_type: str | None
    findings: tuple[Finding, ...] = ()
    aggregate: dict | None = None

    def __post_init__(self):
        if self.aggregate is not None and not self.verdict.carries_measurements:
            raise ValueError(
                f"{self.verdict.value} must not carry an aggregate — a refusal that "
                f"looks like data is the failure this type exists to prevent"
            )
        if self.aggregate is None and self.verdict.carries_measurements:
            raise ValueError(f"{self.verdict.value} must carry an aggregate")

    def codes(self) -> tuple[str, ...]:
        return tuple(f.code for f in self.findings)
