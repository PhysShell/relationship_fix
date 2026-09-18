"""S5a runner: квалификация механики K0 на замороженном генераторе.

    python -m tools.simulate_k0

Числа отсюда — про модель, не про людей. Запрещённые после S5 формулировки
перечислены в prereg §2; pilot N и `δ` здесь не выбираются.
"""

from __future__ import annotations

import statistics

from simulation.experiment import (
    PRIMARY, REGIMES, Decision, analyse, operating_characteristics, run_trial,
)
from simulation.manifest import RunManifest
from simulation.process import Population, TrueEffect

DYADS = 60
DAYS = 14.0
H = 24.0
TRIALS = 80


def line(label, result):
    ci = "—" if not result.estimable else f"[{result.low:9.1f}, {result.high:9.1f}]"
    diff = "—" if result.difference is None else f"{result.difference:9.1f}"
    print(f"  {label:<34} {diff}  {ci}  {result.decision.value}")


def main() -> int:
    print(RunManifest.build(
        "PHASE S5a — K0 machinery qualification (model numbers, not people)",
        master_seed=500_000, replicates=TRIALS, dyads=DYADS, days=DAYS,
        horizon_hours=H, paired=False,
        notes=("S5b (delta, variance, power, pilot N) is BLOCKED_ON_S4",
               "generator frozen; 0 of 8 parameters calibrated"),
    ).render())
    print()

    print("== Q1/Q2 SIGN AND MAGNITUDE BY REGIME (single trial, seed 7) ==")
    for name, regime in REGIMES.items():
        assignment, aggregates = run_trial(regime, 7, dyads=DYADS, days=DAYS)
        print(f"{name}: {regime.description[:70]}")
        for estimand in ("person_period_rmtr", "mean_incidence", "mean_burden"):
            result = analyse(assignment, aggregates, estimand=estimand,
                             horizon_hours=H, delta=0.0)
            line(estimand, result)
    print()

    print("== Q3 ITT vs PER-PROTOCOL UNDER SELECTIVE NON-COMPLIANCE ==")
    assignment, aggregates = run_trial(REGIMES["R1"], 11, dyads=240, days=DAYS,
                                       compliance=0.6, selective=True)
    print(f"  compliance among assigned: {assignment.compliance_rate:.2f}")
    for by_receipt in (False, True):
        result = analyse(assignment, aggregates, horizon_hours=H, delta=0.0,
                         by_receipt=by_receipt)
        line(result.analysis, result)
    print()

    print("== Q4/Q5 N=0, MISSINGNESS, ARM IMBALANCE ==")
    for label, kwargs in (
        ("baseline", {}),
        ("missing 30% of periods", {"missing_share": 0.3}),
        ("arm imbalance 25/75", {"treated_share": 0.25}),
        ("short window (N=0 common)", {"days": 1.5}),
    ):
        days = kwargs.pop("days", DAYS)
        assignment, aggregates = run_trial(REGIMES["R1"], 13, dyads=DYADS,
                                           days=days, **kwargs)
        result = analyse(assignment, aggregates, horizon_hours=H, delta=0.0)
        zero = result.treated.cells_zero_incidence + result.control.cells_zero_incidence
        missing = result.treated.cells_missing + result.control.cells_missing
        line(f"{label} (N=0: {zero}, missing: {missing})", result)
    print()

    print("== Q6 DECISION GATE ACROSS delta (R0 null and R1 latency) ==")
    print(f"  {'regime':<8} {'delta':>8}  {'signal':>8} {'negligible':>11} {'inconclusive':>13}")
    for name in ("R0", "R1"):
        for delta in (0.0, 300.0, 3000.0, 30000.0):
            oc = operating_characteristics(REGIMES[name], trials=TRIALS, dyads=DYADS,
                                           days=DAYS, delta=delta, horizon_hours=H)
            print(f"  {name:<8} {delta:8.0f}  {oc.share(Decision.REACTIVITY_SIGNAL):8.0%}"
                  f" {oc.share(Decision.PRACTICALLY_NEGLIGIBLE):11.0%}"
                  f" {oc.share(Decision.INCONCLUSIVE):13.0%}")
    print()

    print("== Q6b POWER MACHINERY: does precision improve with N? ==")
    print(f"  {'dyads':>7} {'mean diff':>12} {'mean half-width':>16}")
    for dyads in (30, 60, 120, 240):
        oc = operating_characteristics(REGIMES["R1"], trials=30, dyads=dyads,
                                       days=DAYS, delta=0.0, horizon_hours=H)
        print(f"  {dyads:7d} {oc.mean_difference:12.1f} {oc.mean_half_width:16.1f}")
    print("  (monotonicity only — choosing pilot N is S5b, BLOCKED_ON_S4)")
    print()

    print("== Q7 ALGEBRA: which channel moves which estimand ==")
    print(f"  {'regime':<8} {'rmtr':>12} {'incidence':>12} {'burden':>14}")
    for name in ("R0", "R1", "R2", "R3", "R4"):
        row = []
        for estimand in ("person_period_rmtr", "mean_incidence", "mean_burden"):
            oc = operating_characteristics(REGIMES[name], trials=40, dyads=DYADS,
                                           days=DAYS, delta=0.0, estimand=estimand,
                                           horizon_hours=H)
            row.append(oc.mean_difference)
        print(f"  {name:<8} {row[0]:12.1f} {row[1]:12.2f} {row[2]:14.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
