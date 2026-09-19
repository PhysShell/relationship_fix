"""S4-Q1c, второй этаж: partial identification против STRICT на живых данных.

    python -m tools.bounded_q1c /path/to/json_files.zip /path/to/census.tsv

Считает по каждой диаде ИДЕНТИФИЦИРОВАННОЕ МНОЖЕСТВО для N и для
RMTR — то есть все значения, совместимые хоть с одним допустимым порядком
внутри минутных корзин, — и кладёт рядом точечную оценку `TiePolicy.STRICT`.

Главный вопрос не «широки ли границы», а: ЛЕЖИТ ЛИ ОЦЕНКА STRICT ВНУТРИ
идентифицированного множества. Если нет — это не шумная оценка нужной
величины, а число, не совместимое с наблюдениями ни при каком порядке.
"""

from __future__ import annotations

import csv
import statistics
import sys

from coarsening.bounded import (
    burden_bounds, count_bounds, ratio_bounds, to_bins,
)
from coarsening.paired import apply_operator, opportunities, rmtr
from coarsening.prereg import OBSERVED_RESOLUTION_SECONDS
from extractor.adapters.share_multiply import NotADyad, adapt, chats

#: Горизонты: сессионный, промежуточный и продуктовый. Временной слой
#: существен на первом и декоративен на третьем — ровно это и проверяем.
HORIZONS_SECONDS = (300.0, 3600.0, 86_400.0)


def subset(census_path: str) -> list[str]:
    with open(census_path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [r["name"] for r in rows
            if int(r["measured_users"]) == 2 and r["resolution"] == "SECONDS"]


def one(stream, horizon: float):
    """Одна диада, один горизонт: (STRICT N, STRICT R, границы N, границы R)."""
    bins = to_bins(stream, 0, delta=OBSERVED_RESOLUTION_SECONDS)
    window = stream.stamps[-1] + horizon
    coarse = apply_operator(stream, OBSERVED_RESOLUTION_SECONDS)
    survivors = [o for o in opportunities(coarse, 0) if not o.ambiguous]
    strict_n, strict_r = rmtr(survivors, horizon / 3600.0, window)
    counts = count_bounds(bins, horizon=horizon, window_end=window)
    ratio = ratio_bounds(bins, horizon=horizon, window_end=window)
    order_only = ratio_bounds(bins, horizon=horizon, window_end=window,
                              time_layer=False)
    return strict_n, strict_r, counts, ratio, order_only


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    archive, census_path = argv[1], argv[2]
    names = subset(census_path)
    print(f"BOUNDED vs STRICT — {len(names)} admitted dyads, "
          f"minute bins, two-actor exact DP", flush=True)

    tally = {h: {"outside": 0, "inside": 0, "undefined": 0,
                 "widths": [], "order_widths": [], "n_ratio": []}
             for h in HORIZONS_SECONDS}
    analysed = 0
    for index, (name, chat) in enumerate(chats(archive, names)):
        try:
            stream = adapt(chat)
        except NotADyad:
            continue
        analysed += 1
        for horizon in HORIZONS_SECONDS:
            strict_n, strict_r, counts, ratio, order_only = one(stream, horizon)
            row = tally[horizon]
            if ratio is None or strict_r is None:
                row["undefined"] += 1
                continue
            if ratio.low <= strict_r <= ratio.high:
                row["inside"] += 1
            else:
                row["outside"] += 1
            row["widths"].append(ratio.width / 60.0)
            if order_only is not None:
                row["order_widths"].append(order_only.width / 60.0)
            if strict_n:
                row["n_ratio"].append(counts.low / strict_n)
        if index % 25 == 0:
            print(f"    {index}/{len(names)}", flush=True)

    print(f"\n  analysed dyads: {analysed}")
    for horizon in HORIZONS_SECONDS:
        row = tally[horizon]
        decided = row["inside"] + row["outside"]
        print(f"\n=== H = {horizon / 60:.0f} min ===")
        print(f"  STRICT estimate OUTSIDE the identified set: "
              f"{row['outside']} of {decided} "
              f"({100 * row['outside'] / max(decided, 1):.1f}%)")
        if row["widths"]:
            widths = sorted(row["widths"])
            def q(a, p): return a[int(p * (len(a) - 1))]
            print(f"  identified width, minutes: p25={q(widths, .25):.2f} "
                  f"p50={q(widths, .5):.2f} p75={q(widths, .75):.2f} "
                  f"p95={q(widths, .95):.2f}")
        if row["order_widths"]:
            order_widths = sorted(row["order_widths"])
            def q(a, p): return a[int(p * (len(a) - 1))]
            share = statistics.median(row["order_widths"]) / max(
                statistics.median(row["widths"]), 1e-9)
            print(f"  ORDER layer alone, minutes: p50={q(order_widths, .5):.2f} "
                  f"({100 * share:.0f}% of the total width)")
        if row["n_ratio"]:
            print(f"  N_min / N_strict: p50="
                  f"{statistics.median(row['n_ratio']):.2f}  "
                  f"(STRICT занижает даже против НИЖНЕЙ границы)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
