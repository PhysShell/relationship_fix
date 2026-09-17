"""Property tests over generated person-periods, checked against an independent
oracle.

The generator builds a WORLD — window, horizon, an ordered message stream with
runs, replies and non-replies — and the production code derives the sufficient
statistics from it. It deliberately does not generate `B`, `N` and `R`
separately: a generator that emits `B = N x R` and a property that asserts
`B = N x R` is a computer confirming its own premise, at scale, with a progress
bar.

The oracle below is written from the definitions and calls nothing in
`extract.py`. It is slow and stupid on purpose. An "oracle" that reuses the
implementation's helpers is a mirror, and mirrors agree with everything.
"""

import math
import random
import unittest

from tools import propcheck as pc
from tools.propcheck import Outcome
from extractor import estimands as es
from extractor import extract as ex
from extractor.model import Mode, RawMessage

HOUR = 3600.0
P = "participant"
Q = "partner"
SEED = 20260917          # fixed, so a failure is reproducible and a pass is not luck
CASES = 300


# ---------------------------------------------------------------------------
# the world
# ---------------------------------------------------------------------------

class Scenario:
    """window + horizon + a message stream that may start before the period."""

    __slots__ = ("window_seconds", "horizon_hours", "lead_seconds", "steps", "offset_minutes")

    def __init__(self, window_seconds, horizon_hours, lead_seconds, steps, offset_minutes=0):
        self.window_seconds = window_seconds
        self.horizon_hours = horizon_hours
        self.lead_seconds = lead_seconds
        self.steps = steps                      # ((actor, gap_seconds), ...)
        self.offset_minutes = offset_minutes

    def replace(self, **kw):
        return Scenario(
            kw.get("window_seconds", self.window_seconds),
            kw.get("horizon_hours", self.horizon_hours),
            kw.get("lead_seconds", self.lead_seconds),
            kw.get("steps", self.steps),
            kw.get("offset_minutes", self.offset_minutes),
        )

    @property
    def horizon_seconds(self):
        return self.horizon_hours * HOUR

    def messages(self):
        at = -self.lead_seconds
        out = []
        for i, (actor, gap) in enumerate(self.steps):
            at += gap
            out.append(RawMessage(
                message_id=f"m{i}",
                actor=actor,
                local_time=at + self.offset_minutes * 60.0,
                utc_offset_minutes=self.offset_minutes,
                char_count=1,
                device_id="d0",
                deleted=False,
                synced_at=None,
            ))
        return out

    def __repr__(self):
        return (f"Scenario(window={self.window_seconds}, H={self.horizon_hours}h, "
                f"lead={self.lead_seconds}, offset={self.offset_minutes}, "
                f"steps={self.steps})")


def generate(rng: random.Random) -> Scenario:
    horizon_hours = rng.choice([1 / 60, 0.5, 1.0, 6.0, 12.0])
    horizon = horizon_hours * HOUR
    # window pinned to the horizon often enough that `window == H`,
    # `window < H` (nothing can ever be eligible) and `window = H + one tick`
    # all actually occur
    window = pc.biased_float(
        rng,
        (horizon, horizon - 1.0, horizon + 1.0, horizon / 2.0, 2 * horizon, 24 * HOUR),
        low=1.0, high=48 * HOUR,
    )
    lead = pc.biased_float(rng, (0.0, 1.0, horizon, window), low=0.0, high=2 * horizon)
    steps = []
    for i in range(rng.randrange(0, 12)):
        actor = Q if rng.random() < 0.5 else P
        gap = pc.biased_float(
            rng,
            (0.0, 1.0, horizon, horizon - 1.0, horizon + 1.0, window, window - 1.0),
            low=0.0, high=2 * horizon,
        )
        steps.append((actor, gap))
    return Scenario(window, horizon_hours, lead, tuple(steps),
                    rng.choice([0, 0, 0, -480, 330]))


def shrink(case: Scenario):
    for steps in pc.shrink_sequence(case.steps):
        yield case.replace(steps=steps)
    for window in pc.shrink_float(case.window_seconds, (case.horizon_seconds, 1.0)):
        if window > 0:
            yield case.replace(window_seconds=window)
    for lead in pc.shrink_float(case.lead_seconds, (0.0,)):
        if lead >= 0:
            yield case.replace(lead_seconds=lead)
    if case.offset_minutes:
        yield case.replace(offset_minutes=0)
    if case.steps:
        head, tail = case.steps[0], case.steps[1:]
        for gap in pc.shrink_float(head[1], (0.0,)):
            if gap >= 0:
                yield case.replace(steps=((head[0], gap),) + tail)


# ---------------------------------------------------------------------------
# the oracle — from the definitions, no shared code
# ---------------------------------------------------------------------------

def oracle(scenario: Scenario):
    """Returns (eligible_count, burden) the long way round.

    Definitions restated, not imported: a run is a maximal block of consecutive
    same-actor messages; an opportunity is a partner run, opened at its first
    message, answered by the participant's next message if one exists; topology
    is built on the WHOLE stream and only then selected by period; an
    opportunity is eligible when its whole window fits inside the period; a
    non-reply contributes the full horizon; and an opportunity touching a
    timestamp shared by more than one actor is dropped, because the source does
    not order inside a second and neither do we.
    """
    horizon = scenario.horizon_seconds
    start, end = 0.0, scenario.window_seconds
    stamped = sorted(
        (m.local_time - m.utc_offset_minutes * 60.0, m.message_id, m.actor)
        for m in scenario.messages()
    )
    runs = []
    for at, _mid, actor in stamped:
        if runs and runs[-1][0] == actor:
            continue
        runs.append((actor, at))

    # timestamps where more than one actor appears: order not established
    by_stamp: dict[float, set[str]] = {}
    for at, _mid, actor in stamped:
        by_stamp.setdefault(at, set()).add(actor)
    ambiguous = {at for at, actors in by_stamp.items() if len(actors) > 1}

    # the run's last message, needed to know which timestamps an opportunity touches
    run_end = {}
    for position, (actor, opened) in enumerate(runs):
        last = opened
        for at, _mid, who in stamped:
            if at >= opened and who == actor and (position + 1 >= len(runs)
                                                  or at < runs[position + 1][1]):
                last = max(last, at)
        run_end[position] = last

    burden, count = 0.0, 0
    for index, (actor, opened) in enumerate(runs):
        if actor == P:
            continue
        if not (start <= opened < end):
            continue
        if opened + horizon > end:            # calendar censoring
            continue
        touched = {opened, run_end[index]}
        if index + 1 < len(runs):
            touched.add(runs[index + 1][1])
        if touched & ambiguous:               # order inside a second is unknown
            continue
        count += 1
        if index + 1 < len(runs):
            latency = runs[index + 1][1] - opened
            burden += latency if latency < horizon else horizon
        else:
            burden += horizon                 # never answered
    return count, burden


def produced(scenario: Scenario, mode=Mode.PRODUCTION, consent=False):
    return ex.extract(scenario.messages(), P, "w1", 0.0, scenario.window_seconds,
                      mode=mode, consent_to_share_trace=consent,
                      horizons_hours=(scenario.horizon_hours,))


def close(a, b, ulps=8):
    return math.isclose(a, b, rel_tol=ulps * 2.22e-16, abs_tol=ulps * 1e-9)


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------

class ExtractorProperties(unittest.TestCase):

    def run_property(self, name, holds, *, min_effective=30):
        pc.check(name, generate, holds, shrink, cases=CASES, seed=SEED,
                 min_effective=min_effective)

    def test_sufficient_statistics_match_an_independent_oracle(self):
        def holds(case):
            cell = produced(case).aggregate.horizon(case.horizon_hours)
            want_n, want_b = oracle(case)
            if cell.opportunities_eligible != want_n:
                return Outcome.fail(f"N: got {cell.opportunities_eligible}, oracle {want_n}")
            if not close(cell.reentry_burden_seconds, want_b):
                return Outcome.fail(f"B: got {cell.reentry_burden_seconds}, oracle {want_b}")
            return Outcome.ok()
        self.run_property("aggregates == oracle", holds, min_effective=200)

    def test_an_empty_risk_set_gives_zero_burden_and_no_rmtr(self):
        def holds(case):
            cell = produced(case).aggregate.horizon(case.horizon_hours)
            if cell.opportunities_eligible != 0:
                return Outcome.vacuous()
            if cell.reentry_burden_seconds != 0.0:
                return Outcome.fail(f"burden {cell.reentry_burden_seconds} with no opportunities")
            if cell.rmtr_seconds is not None:
                return Outcome.fail(f"rmtr {cell.rmtr_seconds} with no opportunities")
            return Outcome.ok()
        self.run_property("N=0 => B=0, R undefined", holds)

    def test_rmtr_is_the_quotient_within_floating_point(self):
        """Stated with a tolerance on purpose: `B == N * R` is the wrong
        assertion, it fails on 1 ulp for perfectly correct arithmetic."""
        def holds(case):
            cell = produced(case).aggregate.horizon(case.horizon_hours)
            n = cell.opportunities_eligible
            if n == 0:
                return Outcome.vacuous()
            if cell.rmtr_seconds is None:
                return Outcome.fail("rmtr undefined with a non-empty risk set")
            if not close(n * cell.rmtr_seconds, cell.reentry_burden_seconds):
                return Outcome.fail(f"N*R={n * cell.rmtr_seconds} vs B={cell.reentry_burden_seconds}")
            return Outcome.ok()
        self.run_property("N>0 => R = B/N", holds)

    def test_burden_never_outgrows_the_observation_window(self):
        def holds(case):
            aggregate = produced(case).aggregate
            check = es.burden_fits_window(aggregate, time_axis_total=True)
            if check.violations:
                return Outcome.fail(check.violations[0])
            return Outcome.ok()
        self.run_property("0 <= B <= window", holds, min_effective=200)

    def test_each_contribution_saturates_at_the_horizon(self):
        """If nobody answered inside H, the burden is exactly N x H."""
        def holds(case):
            result = produced(case, mode=Mode.QUALIFICATION, consent=True)
            cell = result.aggregate.horizon(case.horizon_hours)
            if cell.opportunities_eligible == 0 or cell.replied_within != 0:
                return Outcome.vacuous()
            want = cell.opportunities_eligible * case.horizon_seconds
            if not close(cell.reentry_burden_seconds, want):
                return Outcome.fail(f"B={cell.reentry_burden_seconds}, N*H={want}")
            return Outcome.ok()
        self.run_property("all non-replies => B = N*H", holds, min_effective=20)

    def test_input_order_is_semantically_irrelevant(self):
        """Metamorphic: no oracle needed, only the claim that the export is a
        function of the stream and not of the order it arrived in."""
        def holds(case):
            messages = case.messages()
            if len(messages) < 2:
                return Outcome.vacuous()
            first = ex.production_export(produced(case).aggregate)
            shuffled = list(messages)
            random.Random(7).shuffle(shuffled)
            again = ex.extract(shuffled, P, "w1", 0.0, case.window_seconds,
                               horizons_hours=(case.horizon_hours,))
            if ex.production_export(again.aggregate) != first:
                return Outcome.fail("export changed under permutation")
            return Outcome.ok()
        self.run_property("permutation invariance", holds, min_effective=150)

    def test_the_burden_is_monotone_in_H_over_a_FIXED_risk_set(self):
        """The honest version of "more time, more burden".

        Comparing whole aggregates across horizons would be a true statement
        about the wrong object: raising H also moves `period_end - H` and
        therefore the risk set. So the comparison is made over the opportunities
        eligible at the LARGER horizon, taken from the real trace.
        """
        def holds(case):
            big = case.horizon_seconds
            small = big / 2.0
            trace = produced(case, mode=Mode.QUALIFICATION, consent=True).export_trace()
            fixed = [o for o in trace if o.opened_at + big <= case.window_seconds]
            if not fixed:
                return Outcome.vacuous()
            at_small = sum(o.restricted_latency(small) for o in fixed)
            at_big = sum(o.restricted_latency(big) for o in fixed)
            if at_big < at_small:
                return Outcome.fail(f"H={big}: {at_big} < H={small}: {at_small}")
            return Outcome.ok()
        self.run_property("B non-decreasing in H at fixed risk set", holds, min_effective=50)


# ---------------------------------------------------------------------------
# population-level properties (estimands)
# ---------------------------------------------------------------------------

def generate_population(rng: random.Random):
    """Several person-periods sharing one window — the arm-level unit."""
    horizon_hours = rng.choice([1 / 60, 1.0, 6.0])
    window = rng.choice([2.0, 4.0, 24.0]) * HOUR
    people = []
    for _ in range(rng.randrange(1, 7)):
        case = generate(rng)
        people.append(case.replace(window_seconds=window, horizon_hours=horizon_hours))
    return tuple(people)


def shrink_population(cases):
    for smaller in pc.shrink_sequence(cases):
        if smaller:
            yield smaller


class EstimandProperties(unittest.TestCase):

    def aggregates(self, cases):
        return [produced(c).aggregate for c in cases], cases[0].horizon_hours

    def test_the_arm_level_decomposition_is_exact(self):
        def holds(cases):
            aggregates, h = self.aggregates(cases)
            got = es.burden_decomposition(aggregates, h)
            if got.holds_exactly is None:
                return Outcome.vacuous()
            if not close(got.mean_incidence * got.opportunity_weighted_rmtr, got.mean_burden):
                return Outcome.fail(f"residual {got.residual}")
            return Outcome.ok()
        pc.check("mean_burden = mean_N * opp_rmtr", generate_population, holds,
                 shrink_population, cases=150, seed=SEED, min_effective=60)

    def test_the_two_weightings_coincide_exactly_when_incidence_is_constant(self):
        """One direction only — the true one. Equal N kills Cov(N, R); unequal N
        does not guarantee a visible gap, so the converse is not asserted."""
        def holds(cases):
            aggregates, h = self.aggregates(cases)
            counts = {a.horizon(h).opportunities_eligible for a in aggregates}
            if len(counts) != 1 or counts == {0}:
                return Outcome.vacuous()
            pooled = es.opportunity_weighted_rmtr(aggregates, h).value
            per_person = es.person_period_weighted_rmtr(aggregates, h).value
            if not close(pooled, per_person):
                return Outcome.fail(f"equal N but {pooled} != {per_person}")
            return Outcome.ok()
        pc.check("equal N => weightings agree", generate_population, holds,
                 shrink_population, cases=200, seed=SEED, min_effective=15)

    def test_mixed_windows_are_refused_rather_than_averaged(self):
        def holds(cases):
            aggregates, h = self.aggregates(cases)
            if len(aggregates) < 2:
                return Outcome.vacuous()
            mixed = aggregates[:1] + [
                type(a)(**{**{f: getattr(a, f) for f in a.__dataclass_fields__},
                           "observation_window_seconds": a.observation_window_seconds + 1.0})
                for a in aggregates[1:]
            ]
            try:
                es.mean_burden(mixed, h)
            except es.WindowMismatch:
                return Outcome.ok()
            return Outcome.fail("unequal windows were pooled into a burden")
        pc.check("mixed windows => WindowMismatch", generate_population, holds,
                 shrink_population, cases=100, seed=SEED, min_effective=40)


if __name__ == "__main__":
    unittest.main()
