"""S3 runner: синтетический процесс против MaiChat по зарегистрированным вопросам.

    python -m tools.compare_corpus /path/to/maichat_dataset/conversations

Корпус не вендорится (CC BY-SA 4.0), поэтому путь передаётся. Печатается
манифест запуска, затем tie pressure, затем таблица сравнимости — в том
порядке, в каком вопросы зарегистрированы.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from extractor.adapters.maichat import adapt_file
from simulation.corpus_compare import (
    QUANTILES, Comparability, Sample, Verdict, coarsen, compare, observe,
    summarise, total_variation,
)
from simulation.manifest import RunManifest
from simulation.process import DAY, PARTICIPANT, Population, TrueEffect, generate_arm

SESSION_HORIZONS = (1 / 60, 5 / 60, 0.5)
PRODUCT_HORIZONS = (6.0, 12.0, 24.0)
HORIZONS = SESSION_HORIZONS + PRODUCT_HORIZONS

SYNTHETIC_DYADS = 200
SYNTHETIC_DAYS = 14.0
SYNTHETIC_SEED = 20260918


def maichat_sample(directory: Path, resolution: float) -> tuple[Sample, int]:
    sample = Sample.empty(HORIZONS)
    conversations = 0
    for path in sorted(directory.glob("*.json")):
        messages, provenance = adapt_file(path)
        if not messages:
            continue
        conversations += 1
        messages = coarsen(messages, resolution)
        times = [m.timestamp for m in messages]
        start, end = min(times), max(times) + 1.0
        for participant in provenance.participants:
            sample.absorb(observe(messages, participant, start, end, HORIZONS))
    return sample, conversations


def synthetic_sample(population: Population) -> Sample:
    sample = Sample.empty(HORIZONS)
    arm = generate_arm(SYNTHETIC_SEED, population, TrueEffect(),
                       dyads=SYNTHETIC_DYADS, days=SYNTHETIC_DAYS)
    for trace in arm:
        sample.absorb(observe(trace, PARTICIPANT, 0.0, SYNTHETIC_DAYS * DAY, HORIZONS))
    return sample


def _pressure_block(title: str, sample: Sample) -> None:
    p = sample.pressure
    print(f"  {title}")
    print(f"    messages in window            {p.messages}")
    print(f"    same-timestamp groups         {p.timestamp_groups}")
    print(f"    of them cross-actor           {p.cross_actor_groups}")
    print(f"    opportunities in period       {p.opportunities_in_period}")
    print(f"    ambiguous (dropped by STRICT) {p.ambiguous_in_period}")
    for hours in HORIZONS:
        clean, ambiguous = p.by_horizon[hours]
        cost = p.cost(hours)
        label = f"{hours*60:.0f}min" if hours < 1 else f"{hours:.0f}h"
        shown = "—" if cost is None else f"{cost:.4%}"
        print(f"      H={label:<6} eligible clean {clean:6d}  ambiguous {ambiguous:4d}"
              f"  STRICT cost {shown}")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m tools.compare_corpus <maichat_dataset/conversations>")
    directory = Path(sys.argv[1])
    population = Population()

    manifest = RunManifest.build(
        "PHASE S3 — MaiChat calibration/stress (NOT a validation set)",
        master_seed=SYNTHETIC_SEED,
        replicates=1,
        dyads=SYNTHETIC_DYADS,
        days=SYNTHETIC_DAYS,
        horizon_hours=24.0,
        paired=False,
        population=population,
        corpus=f"MaiChat v1.0 · {directory}",
        notes=(
            "calibration corpus: may never later confirm what it tuned (prereg §0)",
            "MaiChat clock is server-receive at millisecond precision; coarsened "
            "to 1s for the comparable tie measurement (prereg §1.1)",
        ),
    )
    print(manifest.render())
    print()

    synthetic = synthetic_sample(population)
    native, conversations = maichat_sample(directory, 0.0)
    coarse, _ = maichat_sample(directory, 1.0)

    print(f"== Q1 TIE PRESSURE ==  ({conversations} conversations)")
    _pressure_block("MaiChat, native resolution (milliseconds, server-receive)", native)
    _pressure_block("MaiChat, coarsened to 1 second (comparable to Telegram)", coarse)
    _pressure_block(f"synthetic, {SYNTHETIC_DYADS} dyads x {SYNTHETIC_DAYS:.0f}d, 1s clock",
                    synthetic)
    print()

    print("== Q2/Q3/Q4 PROCESS SHAPE ==")
    print(f"{'quantity':<34} {'verdict':<16} {'D':>6}  ratios synthetic/MaiChat")
    for row in compare(synthetic, coarse):
        d = "—" if row.distance is None else f"{row.distance:.2f}"
        ratios = "  ".join(
            f"p{int(p*100)}={row.ratio(p):.2f}" if row.ratio(p) is not None else f"p{int(p*100)}=—"
            for p in QUANTILES)
        mark = "" if row.quantity.comparability is Comparability.FULL else "*"
        print(f"{row.quantity.name+mark:<34} {row.verdict.value:<16} {d:>6}  {ratios}")
    print("  * verdict computed on p50/p75 only, or not computed at all — see prereg §2")
    print()

    print("== DISTRIBUTIONS, BOTH SIDES ==")
    for row in compare(synthetic, coarse):
        print(f"  {row.quantity.name}")
        print(f"     synthetic: {summarise(synthetic.values[row.quantity.name])}")
        print(f"     MaiChat  : {summarise(coarse.values[row.quantity.name])}")
    tv = total_variation(synthetic.values["hour_of_day"], coarse.values["hour_of_day"])
    print(f"  hour-of-day total variation: {tv:.3f}  (NOT COMPARABLE — prereg §1.3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
