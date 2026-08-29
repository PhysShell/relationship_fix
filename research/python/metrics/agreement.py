"""annotation-pilot-v0 agreement report.

Read-only analytical consumer (ADR-0001 §Python): читает items/strata/manifest/
response-слои, пишет pilot-report.json + pilot-report.md. Ничего не мутирует.

Методология (annotation-protocol-v0 §4):
- Krippendorff alpha, per label, бинарно, по стратам (challenge/natural/all).
- Pairable unit для label = оба решения in {assigned, none_observed};
  abstained исключается из alpha этого label и учитывается отдельно
  (decision matrix + abstention reasons) — право «не решать» не наказывается.
- positive_agreement (Dice: 2*both/(pos_a+pos_b)) — диагностика рядом с alpha,
  не замена: ловит «согласны на negatives, не умеем одинаково находить positives».
- estimability_status: not_applicable (label не входил в sampling frame — из
  manifest.deferred_labels; это «не искали») != underpowered_not_estimable
  («искали, но positives слишком мало для оценки»).
- bootstrap CI: resample pairable units, percentile 2.5/97.5, fixed seed.

Запуск (гейтящие числа — только отсюда, не из notebook):
    uv run python -m metrics.agreement --pilot-dir ../../data/pilot/v0
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ALPHA_FAIL_THRESHOLD = 0.67   # protocol §4: ниже — label на доработку
ALPHA_TARGET = 0.80           # protocol §4: целевой рабочий уровень
MIN_PAIRABLE_UNITS = 10       # ниже — underpowered
MIN_POSITIVE_UNION = 5        # ниже — underpowered
BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_SEED = 42

DECISIONS = ("assigned", "none_observed", "abstained")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def krippendorff_alpha_binary(pairs: list[tuple[int, int]]) -> float | None:
    """Nominal Krippendorff alpha для двух кодировщиков, бинарные значения, без пропусков."""
    if not pairs:
        return None
    o = {(0, 0): 0.0, (0, 1): 0.0, (1, 0): 0.0, (1, 1): 0.0}
    for a, b in pairs:
        o[(a, b)] += 1
        o[(b, a)] += 1
    total = 2.0 * len(pairs)
    n0 = o[(0, 0)] + o[(0, 1)]
    n1 = o[(1, 1)] + o[(1, 0)]
    d_observed = (o[(0, 1)] + o[(1, 0)]) / total
    if total <= 1:
        return None
    d_expected = (2.0 * n0 * n1) / (total * (total - 1.0))
    if d_expected == 0:
        return None  # все значения одинаковы — alpha не определён
    return 1.0 - d_observed / d_expected


def bootstrap_ci(pairs: list[tuple[int, int]]) -> tuple[float, float] | None:
    if not pairs:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    samples = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        resampled = [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]
        alpha = krippendorff_alpha_binary(resampled)
        if alpha is not None:
            samples.append(alpha)
    if not samples:
        return None
    samples.sort()
    lo = samples[int(0.025 * (len(samples) - 1))]
    hi = samples[int(0.975 * (len(samples) - 1))]
    return (round(lo, 4), round(hi, 4))


def label_stats(label: str, unit_rows: list[dict]) -> dict:
    """unit_rows: [{'decision_a', 'decision_b', 'labels_a', 'labels_b'}] одного stratum."""
    pairable = [
        r for r in unit_rows
        if r["decision_a"] in ("assigned", "none_observed")
        and r["decision_b"] in ("assigned", "none_observed")
    ]
    pairs = [(int(label in r["labels_a"]), int(label in r["labels_b"])) for r in pairable]
    n = len(pairs)
    pos_a = sum(a for a, _ in pairs)
    pos_b = sum(b for _, b in pairs)
    both = sum(1 for a, b in pairs if a == 1 and b == 1)
    union = sum(1 for a, b in pairs if a == 1 or b == 1)
    alpha = krippendorff_alpha_binary(pairs)
    ci = bootstrap_ci(pairs)

    if n < MIN_PAIRABLE_UNITS or union < MIN_POSITIVE_UNION or alpha is None:
        status = "underpowered_not_estimable"
    elif alpha < ALPHA_FAIL_THRESHOLD:
        status = "failed"
    else:
        status = "passed"

    return {
        "n_units": n,
        "n_positive_a": pos_a,
        "n_positive_b": pos_b,
        "positive_union": union,
        "prevalence": round((pos_a + pos_b) / (2 * n), 4) if n else None,
        "alpha": round(alpha, 4) if alpha is not None else None,
        "bootstrap_ci_95": ci,
        "positive_agreement_dice": round(2 * both / (pos_a + pos_b), 4) if (pos_a + pos_b) else None,
        "estimability_status": status,
        "meets_target": (alpha is not None and alpha >= ALPHA_TARGET) if status == "passed" else False,
    }


def confusion_analysis(unit_rows: list[dict]) -> dict:
    """Матрица путаницы важнее среднего alpha: где именно проходит неработающая граница."""
    label_vs_label: Counter = Counter()
    label_vs_none: Counter = Counter()
    decision_matrix: Counter = Counter()

    for r in unit_rows:
        decision_matrix[f"{r['decision_a']}|{r['decision_b']}"] += 1
        a_set, b_set = set(r["labels_a"]), set(r["labels_b"])

        if r["decision_a"] == "assigned" and r["decision_b"] == "assigned":
            for la in sorted(a_set - b_set):
                for lb in sorted(b_set - a_set):
                    label_vs_label[" <-> ".join(sorted((la, lb)))] += 1
        elif {r["decision_a"], r["decision_b"]} == {"assigned", "none_observed"}:
            assigned_side = a_set if r["decision_a"] == "assigned" else b_set
            for label in sorted(assigned_side):
                label_vs_none[f"{label} <-> NONE_OBSERVED"] += 1

    return {
        "decision_matrix": dict(sorted(decision_matrix.items())),
        "label_vs_label_disagreements": dict(label_vs_label.most_common()),
        "label_vs_none_disagreements": dict(label_vs_none.most_common()),
    }


def build_unit_rows(items: list[dict], responses_a: list[dict], responses_b: list[dict]) -> list[dict]:
    by_a = {r["item_id"]: r for r in responses_a}
    by_b = {r["item_id"]: r for r in responses_b}
    rows = []
    for item in items:
        item_id = item["item_id"]
        ra, rb = by_a[item_id], by_b[item_id]
        rows.append({
            "item_id": item_id,
            "decision_a": ra["decision"],
            "decision_b": rb["decision"],
            "labels_a": set(ra.get("labels") or []),
            "labels_b": set(rb.get("labels") or []),
            "reason_a": ra.get("abstention_reason"),
            "reason_b": rb.get("abstention_reason"),
        })
    return rows


def validate_responses(items: list[dict], responses: list[dict], layer: str, active: set[str]) -> list[str]:
    issues = []
    item_ids = {i["item_id"] for i in items}
    seen: Counter = Counter(r["item_id"] for r in responses)
    for item_id, count in seen.items():
        if count > 1:
            issues.append(f"{layer}: item '{item_id}' annotated {count} times")
        if item_id not in item_ids:
            issues.append(f"{layer}: unknown item '{item_id}'")
    for missing in sorted(item_ids - set(seen)):
        issues.append(f"{layer}: item '{missing}' not annotated")

    targets = {
        i["item_id"]: next(m["text"] for m in i["messages"] if m["message_id"] == i["target_message_id"])
        for i in items
    }
    for r in responses:
        if r.get("schema_version") != "rf.pilot-response.v1":
            issues.append(f"{layer}/{r.get('item_id')}: bad schema_version")
        decision = r.get("decision")
        if decision not in DECISIONS:
            issues.append(f"{layer}/{r.get('item_id')}: unknown decision '{decision}'")
        if decision == "assigned":
            labels = r.get("labels") or []
            if not labels:
                issues.append(f"{layer}/{r['item_id']}: assigned without labels")
            for label in labels:
                if label not in active:
                    issues.append(f"{layer}/{r['item_id']}: label '{label}' is not active in this pilot")
            quoted = {q["label"]: q["quote"] for q in (r.get("quotes") or [])}
            for label in labels:
                quote = quoted.get(label)
                if not quote:
                    issues.append(f"{layer}/{r['item_id']}: no quote for '{label}'")
                elif r["item_id"] in targets and quote not in targets[r["item_id"]]:
                    issues.append(f"{layer}/{r['item_id']}: quote for '{label}' is not a verbatim substring of target")
        if decision == "abstained" and not r.get("abstention_reason"):
            issues.append(f"{layer}/{r['item_id']}: abstained without reason")
    return issues


def run(pilot_dir: Path) -> int:
    manifest = json.loads((pilot_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
    items = load_jsonl(pilot_dir / manifest["items_file"])
    strata = json.loads((pilot_dir / manifest["strata_file"]).read_text(encoding="utf-8"))["strata"]
    active = set(manifest["active_labels"])

    layers = {}
    for annotator in manifest["annotators"]:
        path = pilot_dir / manifest["responses_dir"] / f"{annotator}.jsonl"
        if not path.exists():
            print(f"MISSING LAYER: {path} — pilot не завершён, отчёт не строится.", file=sys.stderr)
            return 2
        layers[annotator] = load_jsonl(path)

    (a_id, b_id) = manifest["annotators"][:2]
    issues = (validate_responses(items, layers[a_id], a_id, active)
              + validate_responses(items, layers[b_id], b_id, active))
    if issues:
        print("RESPONSE VALIDATION FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    rows = build_unit_rows(items, layers[a_id], layers[b_id])
    strata_names = ["all", "challenge", "natural"]
    per_label: dict = {}
    for label in sorted(active):
        per_label[label] = {}
        for stratum in strata_names:
            selected = rows if stratum == "all" else [r for r in rows if strata[r["item_id"]] == stratum]
            per_label[label][stratum] = label_stats(label, selected)
    for label, info in manifest.get("deferred_labels", {}).items():
        per_label[label] = {
            s: {"estimability_status": "not_applicable", "pilot_status": info["pilot_status"]}
            for s in strata_names
        }

    abstention_reasons = {
        a_id: dict(Counter(r["reason_a"] for r in rows if r["reason_a"]).most_common()),
        b_id: dict(Counter(r["reason_b"] for r in rows if r["reason_b"]).most_common()),
    }

    report = {
        "schema_version": "rf.pilot-report.v1",
        "pilot_id": manifest["pilot_id"],
        "ontology_version": manifest["ontology_version"],
        "ontology_sha256": manifest["ontology_sha256"],
        "n_items": len(items),
        "thresholds": {
            "alpha_fail": ALPHA_FAIL_THRESHOLD,
            "alpha_target": ALPHA_TARGET,
            "min_pairable_units": MIN_PAIRABLE_UNITS,
            "min_positive_union": MIN_POSITIVE_UNION,
        },
        "per_label": per_label,
        "confusion": {
            "all": confusion_analysis(rows),
            "challenge": confusion_analysis([r for r in rows if strata[r["item_id"]] == "challenge"]),
            "natural": confusion_analysis([r for r in rows if strata[r["item_id"]] == "natural"]),
        },
        "abstention_reasons": abstention_reasons,
    }

    out_dir = pilot_dir / "report"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "pilot-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "pilot-report.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"OK: report written to {out_dir}")
    return 0


def render_markdown(report: dict) -> str:
    lines = [
        f"# Pilot report — {report['pilot_id']}",
        "",
        f"Ontology: {report['ontology_version']} (`{report['ontology_sha256'][:12]}…`), items: {report['n_items']}.",
        "",
        "| label | stratum | n | pos A/B | union | prev | alpha | CI95 | posAgr | status |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for label, strata in report["per_label"].items():
        for stratum, s in strata.items():
            if s.get("estimability_status") == "not_applicable":
                lines.append(f"| {label} | {stratum} | — | — | — | — | — | — | — | not_applicable ({s.get('pilot_status', '')}) |")
                continue
            ci = s.get("bootstrap_ci_95")
            lines.append(
                f"| {label} | {stratum} | {s['n_units']} | {s['n_positive_a']}/{s['n_positive_b']} "
                f"| {s['positive_union']} | {s['prevalence']} | {s['alpha']} "
                f"| {ci[0]}–{ci[1] if ci else '—'} | {s['positive_agreement_dice']} | {s['estimability_status']} |"
                if ci else
                f"| {label} | {stratum} | {s['n_units']} | {s['n_positive_a']}/{s['n_positive_b']} "
                f"| {s['positive_union']} | {s['prevalence']} | {s['alpha']} | — | {s['positive_agreement_dice']} | {s['estimability_status']} |")
    lines += ["", "## Confusion (all)", "```json",
              json.dumps(report["confusion"]["all"], ensure_ascii=False, indent=2), "```",
              "", "## Abstentions", "```json",
              json.dumps(report["abstention_reasons"], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    return run(parser.parse_args().pilot_dir)


if __name__ == "__main__":
    sys.exit(main())
