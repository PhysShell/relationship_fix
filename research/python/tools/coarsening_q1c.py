"""S4-Q1c runner: парный эксперимент по деградации временного разрешения.

    python -m tools.coarsening_q1c /path/to/json_files.zip /path/to/census.tsv

Корпус не вендорится; оба пути передаются. Всё, что печатается ниже,
объявлено в `coarsening.prereg` ДО первого прогона: оператор, исходы,
предикторы, сетка фаз, число розыгрышей tie-break и три порога второго этажа.

Считается ровно первый этаж. Второй (partial-order bounds) строится только
если сработал объявленный порог, и не в этом скрипте.
"""

from __future__ import annotations

import csv
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

from coarsening import prereg
from coarsening.paired import apply_operator, pair, transfer_rows
from extractor.adapters.share_multiply import NotADyad, adapt, chats


def subset(census_path: str) -> tuple[list[str], list[dict]]:
    """520 диад целевого подмножества — по ИЗМЕРЕННЫМ актёрам, не по полю."""
    with open(census_path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    target = [r for r in rows
              if int(r["measured_users"]) == 2 and r["resolution"] == "SECONDS"]
    return [r["name"] for r in target], rows


def quantiles(values: list[float]) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values)
    def q(p): return ordered[int(p * (len(ordered) - 1))]
    return (f"p05={q(.05):+.3f} p25={q(.25):+.3f} p50={q(.5):+.3f} "
            f"p75={q(.75):+.3f} p95={q(.95):+.3f}")


def primary(archive: str, names: list[str]) -> tuple[list, list[str]]:
    """Возвращает результаты и список диад, доживших до анализа.

    Отсев здесь один и объявленный: `DYADIC_AFTER_EXCLUSION`. Чат, у которого
    второй актёр существует только в строках типа 10, после их удаления имеет
    одного говорящего — топологии там нет, и место в выборке ему не по праву.
    """
    results, kept, dropped = [], [], 0
    for index, (name, chat) in enumerate(chats(archive, names)):
        try:
            stream = adapt(chat)
        except NotADyad:
            dropped += 1
            continue
        results.append(pair(name, stream, phase=prereg.PRIMARY_PHASE_SECONDS))
        kept.append(name)
        if index % 100 == 0:
            print(f"    {index}/{len(names)}", flush=True)
    print(f"  dropped as non-dyadic AFTER excluding message_type 10: {dropped}")
    print(f"  analysed dyads: {len(kept)} of {len(names)} admitted")
    return results, kept


def report_primary(results: list) -> dict:
    print("\n=== §4 PRIMARY: 1 s -> 60 s, phase 0, all dyads ===", flush=True)
    added = [r.added_strict_loss for r in results]
    print(f"  dyads: {len(results)}   messages: "
          f"{sum(r.reference.messages for r in results):,}")
    print(f"  STRICT loss, reference 1 s : "
          f"{quantiles([r.reference.strict_loss_share for r in results])}")
    print(f"  STRICT loss, observed 60 s : "
          f"{quantiles([r.observed.strict_loss_share for r in results])}")
    print(f"  ADDED loss (paired)        : {quantiles(added)}")
    print(f"  cross-actor TIED STAMP share, 60 s: "
          f"{quantiles([r.observed.tied_stamp_share for r in results])}")
    print("    (доля МЕТОК, не доля возможностей — разные величины)")
    up = sum(1 for r in results if r.run_reduction < 0)
    print(f"  runs: reduced in {sum(1 for r in results if r.run_reduction > 0)} "
          f"dyads, INCREASED in {up}, unchanged in "
          f"{sum(1 for r in results if r.run_reduction == 0)}")
    print(f"  merged reference-runs per dyad: "
          f"{quantiles([float(r.merged_run_events) for r in results])}")
    for position, hours in enumerate(prereg.HORIZONS_HOURS):
        deltas = []
        for r in results:
            _, n_ref, ref = r.reference.rmtr_by_horizon[position]
            _, n_obs, obs = r.observed.rmtr_by_horizon[position]
            if ref is not None and obs is not None and n_ref and n_obs:
                deltas.append((obs - ref) / 60.0)
        print(f"  ΔRMTR H={hours * 60:6.0f} min : {quantiles(deltas)} "
              f"(minutes, n={len(deltas)})")
    return {"added": added}


def report_density(results: list) -> float:
    print("\n=== §6 DENSITY RELATION (window-free predictor) ===", flush=True)
    key = prereg.PRIMARY_PREDICTOR
    ordered = sorted(results, key=lambda r: r.predictors[key])
    size = len(ordered) // 4
    gaps = []
    for number in range(4):
        chunk = ordered[number * size:(number + 1) * size] if number < 3 else ordered[3 * size:]
        loss = statistics.median(r.added_strict_loss for r in chunk)
        gaps.append(loss)
        lo = chunk[0].predictors[key]
        hi = chunk[-1].predictors[key]
        print(f"  Q{number + 1}  {key} {lo:6.2f}..{hi:7.2f}   "
              f"median added loss {loss:+.3f}  (n={len(chunk)})")
    spread = (gaps[-1] - gaps[0]) * 100.0
    print(f"  top-vs-bottom quartile gap: {spread:+.1f} pp")
    return spread


def report_phase(archive: str, names: list[str]) -> None:
    print("\n=== §5 PHASE SENSITIVITY (secondary) ===", flush=True)
    rng = random.Random(prereg.PHASE_SUBSAMPLE_SEED)
    sample = rng.sample(names, min(prereg.PHASE_SUBSAMPLE_DYADS, len(names)))
    per_phase: dict[float, list[float]] = defaultdict(list)
    for name, chat in chats(archive, sample):
        stream = adapt(chat)
        for phase in prereg.PHASE_GRID_SECONDS:
            per_phase[phase].append(pair(name, stream, phase=phase).added_strict_loss)
    medians = {p: statistics.median(v) for p, v in per_phase.items()}
    for phase in prereg.PHASE_GRID_SECONDS:
        print(f"  φ={phase:4.0f}s   median added loss {medians[phase]:+.3f}")
    print(f"  range over phases: "
          f"{(max(medians.values()) - min(medians.values())) * 100:.1f} pp "
          f"— эффект свойство процесса, а не положения границы минуты"
          if max(medians.values()) - min(medians.values()) < 0.05 else
          f"  range over phases: "
          f"{(max(medians.values()) - min(medians.values())) * 100:.1f} pp")


def report_tie_break(archive: str, names: list[str]) -> float:
    print("\n=== §7c TIE-BREAK SENSITIVITY (identification, not noise) ===",
          flush=True)
    rng = random.Random(prereg.PHASE_SUBSAMPLE_SEED)
    sample = rng.sample(names, min(prereg.PHASE_SUBSAMPLE_DYADS, len(names)))
    draws = random.Random(prereg.TIE_BREAK_SEED)
    salts = [b"draw-%d" % draws.randrange(10 ** 9)
             for _ in range(prereg.TIE_BREAK_DRAWS)]
    per_draw: list[float] = []
    collected: dict[bytes, list[float]] = defaultdict(list)
    for name, chat in chats(archive, sample):
        for salt in salts:
            collected[salt].append(
                pair(name, adapt(chat, salt=salt)).added_strict_loss)
    for salt in salts:
        per_draw.append(statistics.median(collected[salt]))
    spread = (max(per_draw) - min(per_draw)) * 100.0
    print(f"  {len(salts)} seeded draws, median added loss per draw:")
    print("    " + "  ".join(f"{v:+.3f}" for v in per_draw))
    print(f"  spread across draws: {spread:.2f} pp")
    return spread


def report_transport(rows: list[dict], names: set[str]) -> None:
    print("\n=== §6a TRANSPORTABILITY: seconds vs minutes subpopulation ===",
          flush=True)
    def year(row):
        return datetime.fromtimestamp(int(row["first_ms"]) / 1000,
                                      tz=timezone.utc).year
    groups = {"SECONDS": [], "MINUTES": []}
    for row in rows:
        if row["resolution"] in groups and int(row["measured_users"]) == 2:
            groups[row["resolution"]].append(row)
    for label, rowset in groups.items():
        sizes = sorted(int(r["measured_n"]) for r in rowset)
        spans = sorted((int(r["last_ms"]) - int(r["first_ms"])) / 86_400_000
                       for r in rowset)
        years = Counter(year(r) for r in rowset)
        share = statistics.fmean(
            int(r["type10"]) / max(int(r["measured_n"]), 1) for r in rowset)
        def q(a, p): return a[int(p * (len(a) - 1))]
        print(f"  {label:<8} n={len(rowset):<5} messages p50={q(sizes, .5):>7,} "
              f"p90={q(sizes, .9):>7,}   span p50={q(spans, .5):6.1f}d   "
              f"type10 {share:.4f}   modal first year {years.most_common(1)[0]}")
    print("  ЕСЛИ подвыборки различаются, вывод формулируется как:")
    print(f"    «{prereg.TRANSPORT_CLAIM_IF_DIFFERENT}»")


def report_transfer(archive: str, names: list[str]) -> None:
    """P(возможность неоднозначна | сколько сообщений было в этой минуте).

    Это и есть передаточная функция часов — то, что имеет смысл тащить
    обратно в генератор вместо одной магической доли ties.
    """
    print("\n=== §6b TRANSFER FUNCTION: P(ambiguous | bin occupancy) ===",
          flush=True)
    hit: Counter = Counter()
    total: Counter = Counter()
    for index, (name, chat) in enumerate(chats(archive, names)):
        try:
            stream = adapt(chat)
        except NotADyad:
            continue
        for occupancy, ambiguous in transfer_rows(
                stream, prereg.PRIMARY_PHASE_SECONDS):
            total[occupancy] += 1
            if ambiguous:
                hit[occupancy] += 1
        if index % 200 == 0:
            print(f"    {index}/{len(names)}", flush=True)
    print("  messages in the opening bin -> P(opportunity ambiguous)")
    tail_hit = tail_total = 0
    for occupancy in sorted(total):
        if occupancy <= 12:
            share = hit[occupancy] / total[occupancy]
            print(f"    {occupancy:>3}  {share:6.3f}   (n={total[occupancy]:,})")
        else:
            tail_hit += hit[occupancy]
            tail_total += total[occupancy]
    if tail_total:
        print(f"    13+  {tail_hit / tail_total:6.3f}   (n={tail_total:,})")
    print(f"  pooled opportunities: {sum(total.values()):,}")


def report_triggers(added: list[float], quartile_gap: float,
                    tie_spread: float) -> None:
    print("\n=== §7 STAGE-TWO TRIGGERS (declared before the run) ===", flush=True)
    median_pp = statistics.median(added) * 100.0
    checks = (
        ("median_added_strict_loss_pp", median_pp),
        ("density_quartile_gap_pp", quartile_gap),
        ("tie_break_spread_pp", tie_spread),
    )
    fired = []
    for key, value in checks:
        threshold = prereg.STAGE_TWO_TRIGGERS[key]
        hit = abs(value) > threshold
        fired.append(hit)
        print(f"  {key:<32} observed {value:+8.2f}  threshold {threshold:5.1f}"
              f"  {'FIRED' if hit else 'quiet'}")
    print(f"  stage two (partial-order bounds): "
          f"{'REQUIRED' if any(fired) else 'not required'}")


def main(argv: list[str]) -> int:
    if not 3 <= len(argv) <= 4:
        print(__doc__)
        return 2
    archive, census_path = argv[1], argv[2]
    names, rows = subset(census_path)
    if len(argv) == 4 and argv[3] == "--transfer":
        report_transfer(archive, names)
        return 0
    print(f"Q1C COARSENING OPERATOR — {len(names)} dyads, reference "
          f"{prereg.REFERENCE_RESOLUTION_SECONDS:.0f} s -> observed "
          f"{prereg.OBSERVED_RESOLUTION_SECONDS:.0f} s", flush=True)
    print(f"  observer model: {prereg.OBSERVER_MODEL}", flush=True)
    results, names = primary(archive, names)
    measured = report_primary(results)
    quartile_gap = report_density(results)
    report_transport(rows, set(names))
    report_phase(archive, names)
    tie_spread = report_tie_break(archive, names)
    report_triggers(measured["added"], quartile_gap, tie_spread)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
