"""Person-period aggregates → the quantities an analysis compares.

The export deliberately carries no ratios: only sums and counts leave the
device. That is the right choice — but it means the weighting decision is made
later, by whoever writes the analysis, in one line that looks like arithmetic
and is actually a choice of estimand:

    Σ B_i / Σ N_i        every OPPORTUNITY weighs the same
    mean_i(B_i / N_i)    every PERSON-PERIOD weighs the same

They are not close. Measured on MaiChat person-period cells, the second is
1.24× the first at H = 1 min and 4.83× at H = 24 h. Under treatment-dependent
`N` the gap is not a nuisance, it is the treatment's own footprint: an arm that
produces more opportunities per person is down-weighted per opportunity by the
first and not by the second.

So both live here, under names that cannot be confused, and the analysis spec
has to say which one it meant.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import Enum

from .model import HorizonAggregate, PeriodAggregate


class WindowMismatch(ValueError):
    """Person-periods of different length were pooled into an unconditional total.

    Burden is a sum over a window, so its scale is the window. Comparing arms on
    a burden summed over unequal windows compares calendars. RMTR normalises
    itself and survives this; burden does not, so it refuses.
    """


@dataclass(frozen=True, slots=True)
class Estimate:
    """A number, plus everything needed to know what it is a number ABOUT."""

    value: float | None
    #: cells offered to the estimator
    person_periods: int
    #: cells that actually entered the value
    contributing: int
    #: cells with N = 0: burden is defined there, RMTR is not
    zero_incidence: int
    #: total eligible opportunities behind the value
    opportunities: int
    #: the common observation window, or None when the cells disagree
    window_seconds: float | None

    @property
    def zero_incidence_share(self) -> float | None:
        if self.person_periods == 0:
            return None
        return self.zero_incidence / self.person_periods

    @property
    def conditions_on_occurrence(self) -> bool:
        """True when cells were dropped for having produced no episode.

        Not a warning about this estimate being wrong — a statement about which
        population it describes. If the treatment moves P(N = 0), the two arms'
        surviving cells are not the same kind of period.
        """
        return self.zero_incidence > 0


def cells(aggregates, horizon_hours: float) -> list[HorizonAggregate]:
    return [a.horizon(horizon_hours) for a in aggregates]


def _window(aggregates) -> float | None:
    windows = {a.observation_window_seconds for a in aggregates}
    return windows.pop() if len(windows) == 1 else None


def _frame(aggregates, horizon_hours: float, contributing: list[HorizonAggregate]) -> dict:
    rows = cells(aggregates, horizon_hours)
    return {
        "person_periods": len(rows),
        "contributing": len(contributing),
        "zero_incidence": sum(1 for c in rows if c.opportunities_eligible == 0),
        "opportunities": sum(c.opportunities_eligible for c in contributing),
        "window_seconds": _window(aggregates),
    }


def opportunity_weighted_rmtr(aggregates, horizon_hours: float) -> Estimate:
    """Σ B_i / Σ N_i — the mean over OPPORTUNITIES, pooled across people.

    A person who produced twenty opportunities counts twenty times as much as a
    person who produced one. Empty cells contribute 0 to both sums, so they fall
    out silently: the estimate still describes only periods in which something
    happened. `zero_incidence` is reported for exactly that reason.
    """
    rows = [c for c in cells(aggregates, horizon_hours) if c.opportunities_eligible > 0]
    frame = _frame(aggregates, horizon_hours, rows)
    if not rows:
        return Estimate(value=None, **frame)
    total_burden = sum(c.reentry_burden_seconds for c in rows)
    return Estimate(value=total_burden / frame["opportunities"], **frame)


def person_period_weighted_rmtr(aggregates, horizon_hours: float) -> Estimate:
    """mean_i(B_i / N_i) over cells with N > 0 — the mean over PEOPLE-PERIODS.

    Every person's period weighs the same regardless of how much traffic it
    carried. This is the more natural unit for a randomised comparison, and it
    is also the one that conditions TWICE: on an episode having arisen within
    the cell, and on the cell having produced any episode at all. Both are
    post-treatment when the treatment can move incidence.
    """
    rows = [c for c in cells(aggregates, horizon_hours) if c.opportunities_eligible > 0]
    frame = _frame(aggregates, horizon_hours, rows)
    if not rows:
        return Estimate(value=None, **frame)
    return Estimate(value=statistics.fmean(c.rmtr_seconds for c in rows), **frame)


def mean_burden(aggregates, horizon_hours: float) -> Estimate:
    """mean_i(B_i) over ALL cells — the unconditional one.

    Empty cells enter as 0, which is what happened: no episode arose, no
    re-entry time accumulated. Nothing is dropped, so nothing is conditioned on,
    so `zero_incidence` here is a description of the sample rather than a
    caveat on the estimate.

    Refuses unequal windows: see `WindowMismatch`.
    """
    rows = cells(aggregates, horizon_hours)
    frame = _frame(aggregates, horizon_hours, rows)
    if frame["window_seconds"] is None and rows:
        raise WindowMismatch(
            "burden pooled over person-periods of different length; "
            "the common-window requirement of reentry_burden_H is not met"
        )
    if not rows:
        return Estimate(value=None, **frame)
    return Estimate(value=statistics.fmean(c.reentry_burden_seconds for c in rows), **frame)


def mean_incidence(aggregates, horizon_hours: float) -> Estimate:
    """mean_i(N_i) over ALL cells — the incidence component, empty cells included."""
    rows = cells(aggregates, horizon_hours)
    frame = _frame(aggregates, horizon_hours, rows)
    if not rows:
        return Estimate(value=None, **frame)
    return Estimate(value=statistics.fmean(c.opportunities_eligible for c in rows), **frame)


# --------------------------------------------------------------------------
# Arm-level algebra: which decomposition is exact, and which one is a story
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BurdenDecomposition:
    """`mean_burden = mean_incidence × opportunity_weighted_rmtr`, exactly.

    Per cell, `B_i = N_i × R_i`. After averaging over an arm that identity does
    NOT survive elementwise, because

        E[N R] = E[N] E[R] + Cov(N, R)

    so `mean(B) != mean(N) × mean(R_person)` whenever incidence and duration are
    associated. Measured on MaiChat, among ACTIVE cells, `Cov(N, R)` runs from
    −28% of the mean burden at H = 1 min to −202% at H = 12 h: person-periods
    with many opportunities carry short conditional durations. The naive product
    overstates the mean burden by a factor of three at the product grid. That is
    not a rounding difference, it is a third thing the treatment can move.

    The ratio-of-sums weighting has no such term, because the M cancels:

        Σ B / M  =  (Σ N / M) × (Σ B / Σ N)

    which gives `opportunity_weighted_rmtr` its own job and stops it looking
    like a duplicate of the inferential estimand. The two are NOT
    interchangeable and must not be merged:

        person_period_weighted_rmtr — inferential; one vote per person-period,
                                      matching the unit of randomisation
        opportunity_weighted_rmtr   — algebraic; the exact duration factor of
                                      the frequency × duration decomposition
    """

    mean_burden: float | None
    mean_incidence: float | None
    opportunity_weighted_rmtr: float | None
    person_periods: int
    zero_incidence: int
    #: `mean_incidence × opportunity_weighted_rmtr − mean_burden`; None when the
    #: identity is degenerate (no opportunities at all, so the factor does not
    #: exist). Never rebuild the burden from the factors: see
    #: `HorizonAggregate.reentry_burden_seconds` on the 1-ulp round trip.
    residual: float | None

    @property
    def holds_exactly(self) -> bool | None:
        """True / False / None — None meaning the identity was not testable."""
        if self.residual is None:
            return None
        return self.residual == 0.0


def burden_decomposition(aggregates, horizon_hours: float) -> BurdenDecomposition:
    """The exact frequency × duration split of the unconditional burden."""
    burden = mean_burden(aggregates, horizon_hours)          # raises on mixed windows
    incidence = mean_incidence(aggregates, horizon_hours)
    duration = opportunity_weighted_rmtr(aggregates, horizon_hours)
    residual = None
    if None not in (burden.value, incidence.value, duration.value):
        residual = incidence.value * duration.value - burden.value
    return BurdenDecomposition(
        mean_burden=burden.value,
        mean_incidence=incidence.value,
        opportunity_weighted_rmtr=duration.value,
        person_periods=burden.person_periods,
        zero_incidence=burden.zero_incidence,
        residual=residual,
    )


# --------------------------------------------------------------------------
# Structural invariant
# --------------------------------------------------------------------------

class CheckStatus(Enum):
    CHECKED = "checked"
    #: The source's time axis does not support the check. NOT a pass: a coarse
    #: or partial clock cannot certify that intervals do not overlap, and
    #: pretending otherwise is how absence turns into evidence.
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class StructuralCheck:
    status: CheckStatus
    violations: tuple[str, ...]

    @property
    def passed(self) -> bool | None:
        if self.status is CheckStatus.NOT_APPLICABLE:
            return None
        return not self.violations


def burden_fits_window(aggregate: PeriodAggregate, *, time_axis_total: bool) -> StructuralCheck:
    """`0 <= B_H <= observation_window_seconds`, for every horizon.

    Structural, not statistical. Opportunities are disjoint by construction —
    the next one cannot open until the participant has answered the last — each
    contributes at most `H`, and every eligible one is clipped inside the
    period. So the capped intervals tile a subset of the window and their sum
    cannot exceed it.

    A failure therefore means one of: overlapping opportunities, double
    counting, clipping applied at the wrong boundary, or a time source that
    broke an assumption the extractor made about it. All four are worth a human.

    Gated on `time_axis_total` (a source whose ordering is total and evidenced —
    `SourceSemantics.usable_as_topology_oracle`). Under a coarse or partial
    clock an ambiguous tie can manufacture an overlapping opportunity, and the
    invariant would then accuse the extractor of a fault belonging to the
    timestamps. There the honest answer is NOT_APPLICABLE.
    """
    if not time_axis_total:
        return StructuralCheck(status=CheckStatus.NOT_APPLICABLE, violations=())
    window = aggregate.observation_window_seconds
    violations = []
    for cell in aggregate.horizons:
        burden = cell.reentry_burden_seconds
        if burden < 0:
            violations.append(f"H={cell.horizon_hours}: negative burden {burden}")
        elif burden > window:
            violations.append(
                f"H={cell.horizon_hours}: burden {burden} exceeds observation window {window}"
            )
    return StructuralCheck(status=CheckStatus.CHECKED, violations=tuple(violations))
