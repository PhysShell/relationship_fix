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
