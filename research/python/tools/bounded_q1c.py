"""S4-Q1c, второй этаж: partial identification против STRICT на всём корпусе.

    python -m tools.bounded_q1c /path/to/json_files.zip /path/to/census.tsv [rows.tsv]

Считает по каждой диаде:

    N     SHARP identified set — слой порядка точен;
    RMTR  VALID OUTER ENVELOPE — слой времени оболочка, не резкая граница.

Различие терминов существенно и работает НА УСИЛЕНИЕ вывода: если оценка
STRICT лежит вне заведомо слишком широкой оболочки, она тем более не
принадлежит неизвестному резкому множеству внутри неё.

Все правила агрегации объявлены в `coarsening.verdict` ДО просмотра
распределений. Здесь только счёт и печать.
"""

from __future__ import annotations

import csv
import random
import statistics
import sys

from coarsening import verdict
from coarsening.bounded import count_bounds, ratio_bounds, to_bins
from coarsening.paired import apply_operator, local_density, opportunities, rmtr
from coarsening.prereg import OBSERVED_RESOLUTION_SECONDS as DELTA
from extractor.adapters.share_multiply import NotADyad, adapt, chats

HORIZONS_SECONDS = (300.0, 3600.0, 86_400.0)
COLUMNS = ("dyad", "horizon", "density", "strict_n", "strict_r",
           "n_lo", "n_hi", "r_lo", "r_hi", "ro_lo", "ro_hi")


def subset(census_path: str) -> list[str]:
    with open(census_path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [r["name"] for r in rows
            if int(r["measured_users"]) == 2 and r["resolution"] == "SECONDS"]


def measure(stream, horizon: float, delta: float = DELTA):
    bins = to_bins(stream, 0, delta=delta)
    window = stream.stamps[-1] + horizon
    coarse = apply_operator(stream, delta)
    survivors = [o for o in opportunities(coarse, 0) if not o.ambiguous]
    strict_n, strict_r = rmtr(survivors, horizon / 3600.0, window)
    counts = count_bounds(bins, horizon=horizon, window_end=window)
    envelope = ratio_bounds(bins, horizon=horizon, window_end=window,
                            delta=delta)
    order_only = ratio_bounds(bins, horizon=horizon, window_end=window,
                              delta=delta, time_layer=False)
    return strict_n, strict_r, counts, envelope, order_only


def quantiles(values, scale: float = 1.0) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values)
    def q(p): return ordered[int(p * (len(ordered) - 1))] * scale
    return (f"p25={q(.25):.2f} p50={q(.5):.2f} p75={q(.75):.2f} "
            f"p95={q(.95):.2f}")


def main(argv: list[str]) -> int:
    if not 3 <= len(argv) <= 4:
        print(__doc__)
        return 2
    archive, census_path = argv[1], argv[2]
    names = subset(census_path)
    sink = open(argv[3], "w", encoding="utf-8") if len(argv) == 4 else None
    if sink:
        sink.write("\t".join(COLUMNS) + "\n")

    print(f"BOUNDED vs STRICT — {len(names)} admitted dyads", flush=True)
    print(f"  N: sharp identified set   RMTR: {verdict.RMTR_TERM}", flush=True)

    rows = {h: [] for h in HORIZONS_SECONDS}
    analysed = 0
    for index, (name, chat) in enumerate(chats(archive, names)):
        try:
            stream = adapt(chat)
        except NotADyad:
            continue
        analysed += 1
        density = local_density(stream)[verdict.DENSITY_PREDICTOR]
        for horizon in HORIZONS_SECONDS:
            strict_n, strict_r, counts, envelope, order_only = measure(
                stream, horizon)
            rows[horizon].append((name, density, strict_n, strict_r, counts,
                                  envelope, order_only))
            if sink:
                sink.write("\t".join(str(x) for x in (
                    name, horizon, density, strict_n, strict_r,
                    counts.low, counts.high,
                    envelope.low if envelope else "",
                    envelope.high if envelope else "",
                    order_only.low if order_only else "",
                    order_only.high if order_only else "")) + "\n")
        if index % 25 == 0:
            print(f"    {index}/{len(names)}", flush=True)
            if sink:
                sink.flush()
    if sink:
        sink.close()
    print(f"\n  analysed dyads: {analysed}", flush=True)

    for horizon in HORIZONS_SECONDS:
        data = rows[horizon]
        print(f"\n=== H = {horizon / 60:.0f} min ===", flush=True)

        # 1-2. как часто снаружи и насколько далеко
        n_out, r_out, defined = [], [], 0
        n_rel, r_rel = [], []
        for _, _, strict_n, strict_r, counts, envelope, _ in data:
            hit = verdict.violation(float(strict_n), counts.low, counts.high)
            if hit.outside:
                n_out.append(hit.absolute_seconds)
                n_rel.append(hit.relative_to_width)
            if envelope is None or strict_r is None:
                continue
            defined += 1
            hit = verdict.violation(strict_r, envelope.low, envelope.high)
            if hit.outside:
                r_out.append(hit.absolute_seconds)
                r_rel.append(hit.relative_to_width)
        print(f"  STRICT N outside the SHARP set:      {len(n_out)}/{len(data)}"
              f"  ({100 * len(n_out) / max(len(data), 1):.1f}%)")
        print(f"    miss, opportunities: {quantiles(n_out)}")
        print(f"    miss, envelope widths: {quantiles(n_rel)}")
        print(f"  STRICT RMTR outside the OUTER envelope: {len(r_out)}/{defined}"
              f"  ({100 * len(r_out) / max(defined, 1):.1f}%)")
        print(f"    miss, minutes: {quantiles(r_out, 1 / 60)}")
        print(f"    miss, envelope widths: {quantiles(r_rel)}")

        # 3. информативность
        widths_n = [verdict.relative_width(c.low, c.high)
                    for _, _, _, _, c, _, _ in data]
        widths_r = [verdict.multiplicative_width(e.low, e.high)
                    for _, _, _, _, _, e, _ in data if e and e.low > 0]
        print(f"  N relative width: {quantiles(widths_n)}")
        print(f"  RMTR envelope, multiplicative width: {quantiles(widths_r)}")

        # 4. кто раздувает
        shares = [verdict.order_share(o.width, e.width)
                  for _, _, _, _, _, e, o in data if e and o and e.width > 0]
        print(f"  share of width from ORDER uncertainty: {quantiles(shares)}")
        if shares:
            median = statistics.median(shares)
            need = median < verdict.SHARPEN_TIME_IF_ORDER_SHARE_BELOW
            print(f"    sharper TIME layer: "
                  f"{'WORTH BUILDING' if need else 'not worth building'} "
                  f"(median order share {median:.2f} vs declared threshold "
                  f"{verdict.SHARPEN_TIME_IF_ORDER_SHARE_BELOW})")

        # 6. связь с локальной плотностью
        ordered = sorted(data, key=lambda row: row[1])
        size = len(ordered) // verdict.DENSITY_QUARTILES
        print("  by local density (window-free predictor):")
        for number in range(verdict.DENSITY_QUARTILES):
            last = number == verdict.DENSITY_QUARTILES - 1
            chunk = ordered[number * size:] if last else \
                ordered[number * size:(number + 1) * size]
            if not chunk:
                continue
            outside = sum(
                1 for _, _, _, sr, _, e, _ in chunk
                if e and sr is not None
                and verdict.violation(sr, e.low, e.high).outside)
            mult = [verdict.multiplicative_width(e.low, e.high)
                    for _, _, _, _, _, e, _ in chunk if e and e.low > 0]
            print(f"    Q{number + 1}  density "
                  f"{chunk[0][1]:5.2f}..{chunk[-1][1]:6.2f}  "
                  f"STRICT outside {100 * outside / len(chunk):5.1f}%  "
                  f"envelope x{statistics.median(mult) if mult else float('nan'):.2f}")

    # 5. измельчение на живых данных
    print(f"\n=== refinement certificate: I(1 s) ⊆ I(60 s) ===", flush=True)
    print(f"  reference: {verdict.REFINEMENT_REFERENCE}")
    rng = random.Random(verdict.REFINEMENT_SEED)
    sample = rng.sample(names, min(verdict.REFINEMENT_SUBSAMPLE_DYADS, len(names)))
    held = broken = skipped = 0
    for name, chat in chats(archive, sample):
        try:
            stream = adapt(chat)
        except NotADyad:
            continue
        for horizon in HORIZONS_SECONDS:
            fine_n, _, fine_counts, fine_r, _ = measure(stream, horizon, 1.0)
            _, _, coarse_counts, coarse_r, _ = measure(stream, horizon, DELTA)
            if fine_r is None or coarse_r is None:
                skipped += 1
                continue
            ok = (fine_counts in coarse_counts) and (fine_r in coarse_r)
            held += ok
            broken += not ok
            if not ok:
                print(f"    BROKEN {name} H={horizon:.0f}: "
                      f"N {fine_counts} vs {coarse_counts}, "
                      f"R {fine_r} vs {coarse_r}")
    print(f"  held {held}, broken {broken}, skipped {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
