"""interaction-primitives-v0 (Pilot B) — presentation, validation, agreement.

Read-only analytical consumer (ADR-0001 §Python). Separate from `metrics.agreement`,
which belongs to Pilot A and is not touched: the two pilots are different
experiments and must not share gating code.

Methodology is fixed in docs/research/interaction-primitives-v0-prereg.md BEFORE
any human response exists. Anything not listed there is POST_HOC.

Subcommands:
    materialize --corpus-dir DIR     deterministic presentation layers + seal
    validate    --corpus-dir DIR     structural checks over corpus and responses
    report      --corpus-dir DIR     agreement report (refuses if layers missing)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

# --- preregistered constants (prereg §8) -------------------------------------

ANNOTATORS = ("annotator-1", "annotator-2", "annotator-3")
PRESENTATION_SEED_PREFIX = "rf-primitives-v0"

ALPHA_FAIL = 0.67          # protocol convention, same thresholds as Pilot A
ALPHA_TARGET = 0.80
MIN_PAIRABLE_UNITS = 10
MIN_CATEGORY_UNION = 5
BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_SEED = 42

# Boundary tolerance is FIXED HERE, before any response is seen. Choosing it after
# looking at the data would turn a preregistered metric into a tuned one.
BOUNDARY_TOLERANCE = 1

# Construct names. P3's human question is "is there negativity in B?", which is
# ATOMIC: because P1 is answered independently, `P1=NO, P3=YES` is a perfectly
# legal result — B does not answer A, but B is negative on its own. So P3 measures
# NEGATIVE_IN_B, not a relation, and the relational construct is a COMPOSITION:
#     P1 responds_to = YES  AND  P3 negative_in_B = YES  ->  candidate negative_response
# That decomposition is the point of the whole layered exercise, so the variable is
# named for what it actually measures.
PRIMITIVE_NAMES = {
    "P1": "SEMANTIC_RESPONSE",
    "P2": "TOPIC_RELATION",
    "P3": "NEGATIVE_IN_B",
    "P4": "SOFTENING_UPTAKE_IN_B",
    "P5": "EPISODE_BOUNDARY",
}

# Preregistered groupings for C2/C3. Individual strata hold 5 items, below
# MIN_PAIRABLE_UNITS, so a per-stratum comparison would sit under our own
# estimability gate; "five is where a breakdown stops being an anecdote" is a
# statement of taste, not of power. Per-stratum numbers are still reported, but
# only as DESCRIPTIVE.
SUPER_STRATA = {
    "easy": ("easy_positive", "easy_negative"),
    "challenge": ("adjacency_trap", "explicit_reply_trap", "intervening_neutral_turn",
                  "multi_topic", "multi_target", "insufficient_context"),
    "single_signal": ("easy_positive", "easy_negative"),
    "multi_signal": ("multi_topic", "multi_target"),
}

ANSWERS = {
    "P1": ("YES", "NO", "INSUFFICIENT"),
    "P2": ("SAME", "DIFFERENT", "MIXED", "INSUFFICIENT"),
    "P3": ("YES", "NO", "INSUFFICIENT"),
    "P4": ("YES", "NO", "INSUFFICIENT"),
}
BOUNDARY_ANSWERS = ("BOUNDARY", "NO_BOUNDARY", "INSUFFICIENT")
ABSTENTION = "INSUFFICIENT"
FEEDBACK_FLAGS = ("unnatural_example", "insufficient_context", "wording_or_translation", "other")


# --- agreement ---------------------------------------------------------------

def krippendorff_alpha_nominal(units: list[list[str]]) -> float | None:
    """Nominal Krippendorff alpha, any number of coders, missing values allowed.

    Coincidence-matrix form, so it degrades correctly when a unit was coded by
    two people and another by three. `metrics.agreement`'s binary two-coder
    version cannot express P2's four categories or a third layer, so this is a
    separate implementation rather than a widened one — and a test pins the two
    against each other on the binary two-coder case they both cover.
    """
    o: dict[tuple[str, str], float] = defaultdict(float)
    for values in units:
        vals = [v for v in values if v is not None]
        m = len(vals)
        if m < 2:
            continue                      # a unit one person coded carries no agreement
        for i, c in enumerate(vals):
            for j, k in enumerate(vals):
                if i != j:
                    o[(c, k)] += 1.0 / (m - 1)
    if not o:
        return None

    categories = sorted({c for pair in o for c in pair})
    n_c = {c: sum(o[(c, k)] for k in categories) for c in categories}
    n = sum(n_c.values())
    if n <= 1:
        return None

    d_observed = sum(v for (c, k), v in o.items() if c != k)
    d_expected = sum(n_c[c] * n_c[k] for c in categories for k in categories if c != k)
    if d_expected == 0:
        return None                       # one category only: alpha undefined
    return 1.0 - (n - 1) * d_observed / d_expected


def bootstrap_ci(units: list[list[str]], iterations: int = BOOTSTRAP_ITERATIONS
                 ) -> tuple[float, float] | None:
    """Percentile CI, resampling UNITS (not individual ratings), per Hayes &
    Krippendorff. A point estimate without an interval overstates the precision a
    60-item sample supports."""
    if len(units) < 2:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    samples = []
    for _ in range(iterations):
        resampled = [units[rng.randrange(len(units))] for _ in units]
        a = krippendorff_alpha_nominal(resampled)
        if a is not None:
            samples.append(a)
    if len(samples) < 2:
        return None
    samples.sort()
    return (round(samples[int(0.025 * (len(samples) - 1))], 4),
            round(samples[int(0.975 * (len(samples) - 1))], 4))


def raw_agreement(units: list[list[str]]) -> float | None:
    """Share of coder PAIRS that match. Reported beside alpha, never instead of
    it: on a skewed category alpha can collapse while raw agreement stays high."""
    agree = total = 0
    for values in units:
        vals = [v for v in values if v is not None]
        for x, y in combinations(vals, 2):
            total += 1
            agree += int(x == y)
    return round(agree / total, 4) if total else None


def pairwise_confusion(units: list[list[str]]) -> dict[str, int]:
    """Unordered category pairs that coders split on. This localises WHERE a
    boundary fails, which a single alpha cannot."""
    out: Counter = Counter()
    for values in units:
        vals = [v for v in values if v is not None]
        for x, y in combinations(vals, 2):
            if x != y:
                out[" <-> ".join(sorted((x, y)))] += 1
    return dict(out.most_common())


def estimability(units: list[list[str]], alpha: float | None) -> str:
    pairable = [u for u in units if len([v for v in u if v is not None]) >= 2]
    if len(pairable) < MIN_PAIRABLE_UNITS or alpha is None:
        return "underpowered_not_estimable"
    return "passed" if alpha >= ALPHA_FAIL else "failed"


def _layer(units: list[list[str]]) -> dict:
    pairable = [u for u in units if len([v for v in u if v is not None]) >= 2]
    alpha = krippendorff_alpha_nominal(pairable)
    return {
        "n_units": len(pairable),
        "alpha": round(alpha, 4) if alpha is not None else None,
        "bootstrap_ci_95": bootstrap_ci(pairable),
        "raw_agreement": raw_agreement(pairable),
        "confusion": pairwise_confusion(pairable),
        "estimability_status": estimability(pairable, alpha),
        "meets_target": alpha is not None and alpha >= ALPHA_TARGET,
    }


def primitive_stats(units: list[list[str]], categories: tuple[str, ...]) -> dict:
    """TWO alphas, reported side by side and never collapsed.

        decision     INSUFFICIENT is a full category
                     = do people agree about what to do with the task at all
        substantive  INSUFFICIENT -> missing; only units with >=2 substantive
                     ratings survive
                     = do people agree about the relation WHEN they think it is
                       observable

    Both are needed because either alone is gameable. Keeping INSUFFICIENT in is
    right — agreeing that a task is undecidable is itself informative — but on its
    own it lets an excellent alpha arise from everyone reliably pressing "don't
    know", and an estimability guard that only counts units where SOMEBODY was
    substantive does not stop that. Reproducibility of the "don't know" button is
    not a licence to build the next floor.
    """
    pairable = [u for u in units if len([v for v in u if v is not None]) >= 2]
    flat = [v for u in pairable for v in u if v is not None]

    masked = [[None if v == ABSTENTION else v for v in u] for u in pairable]
    substantive_units = [u for u in masked if len([v for v in u if v is not None]) >= 2]

    decision = _layer(pairable)
    substantive = _layer(substantive_units)
    if len(substantive_units) < MIN_PAIRABLE_UNITS:
        substantive["estimability_status"] = "underpowered_not_estimable"

    return {
        "n_units": len(pairable),
        "n_ratings": len(flat),
        "distribution": {c: flat.count(c) for c in categories},
        "abstention_rate": round(flat.count(ABSTENTION) / len(flat), 4) if flat else None,
        "n_substantive_units": len(substantive_units),
        "decision": decision,
        "substantive": substantive,
        # Convenience mirrors of the decision layer; `substantive` is never mirrored
        # here, so nothing can read a single `alpha` and skip the second question.
        "alpha": decision["alpha"],
        "bootstrap_ci_95": decision["bootstrap_ci_95"],
        "confusion": decision["confusion"],
        "estimability_status": decision["estimability_status"],
    }


# --- boundary metrics (prereg §8) --------------------------------------------

def cluster_bootstrap_ci(clusters: list[list[list[str]]],
                         iterations: int = BOOTSTRAP_ITERATIONS) -> tuple[float, float] | None:
    """Resample WHOLE CHAINS, not individual positions.

    Boundary positions inside a chain are not independent — a coder who moves one
    boundary by a message changes two positions — so resampling positions treats
    56 correlated observations as 56 independent ones and returns an interval that
    is cheerfully narrower than the data supports. Statistics is always happy to
    pretend we have more data than we do; the unit of resampling has to be the
    unit of independence, which here is the chain.
    """
    if len(clusters) < 2:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    samples = []
    for _ in range(iterations):
        picked = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        a = krippendorff_alpha_nominal([u for cluster in picked for u in cluster])
        if a is not None:
            samples.append(a)
    if len(samples) < 2:
        return None
    samples.sort()
    return (round(samples[int(0.025 * (len(samples) - 1))], 4),
            round(samples[int(0.975 * (len(samples) - 1))], 4))


def match_boundaries(a: set[int], b: set[int], tol: int) -> int:
    """ONE-TO-ONE greedy matching by distance; each boundary is used at most once.

    "Is there any boundary of the other coder within tolerance" allows many-to-one
    matches: A marking {4, 5} against B marking {4} would score near-perfect at
    tolerance 1, even though the two disagreed about how many boundaries exist.
    Greedy nearest-first over all admissible pairs is the standard fix and is
    deterministic given the tie-break on position.
    """
    pairs = sorted(((abs(x - y), x, y) for x in sorted(a) for y in sorted(b)
                    if abs(x - y) <= tol))
    used_a: set[int] = set()
    used_b: set[int] = set()
    matched = 0
    for _, x, y in pairs:
        if x in used_a or y in used_b:
            continue
        used_a.add(x)
        used_b.add(y)
        matched += 1
    return matched


def boundary_stats(per_chain: dict[str, dict[str, list[str]]]) -> dict:
    """per_chain: {chain_id: {boundary_key: [value per coder]}}.

    Reported STRICT and TOLERANT separately and never merged. Positions inside a
    chain are not independent — a coder who moves one boundary by a message
    changes two positions — so position-level alpha is an underestimate of
    whether they saw the same segmentation, and tolerant F1 is an overestimate.
    Both are preregistered; neither is the single headline.
    """
    strict_units, per_coder_sets, chain_lengths = [], defaultdict(dict), {}
    clusters: list[list[list[str]]] = []
    for chain_id, positions in per_chain.items():
        keys = list(positions)
        chain_lengths[chain_id] = len(keys)
        cluster = [positions[key] for key in keys]
        clusters.append(cluster)
        strict_units.extend(cluster)
        n_coders = max((len(v) for v in positions.values()), default=0)
        for coder in range(n_coders):
            per_coder_sets[coder][chain_id] = {
                i for i, key in enumerate(keys)
                if coder < len(positions[key]) and positions[key][coder] == "BOUNDARY"
            }

    def f1(a: set[int], b: set[int], tol: int) -> float | None:
        if not a and not b:
            return None                   # nobody marked a boundary: undefined, not perfect
        matched = match_boundaries(a, b, tol)
        precision = matched / len(a) if a else 0.0
        recall = matched / len(b) if b else 0.0
        return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0

    tolerant, exact = [], []
    coders = sorted(per_coder_sets)
    for ca, cb in combinations(coders, 2):
        for chain_id in chain_lengths:
            a = per_coder_sets[ca].get(chain_id, set())
            b = per_coder_sets[cb].get(chain_id, set())
            t = f1(a, b, BOUNDARY_TOLERANCE)
            e = f1(a, b, 0)
            if t is not None:
                tolerant.append(t)
            if e is not None:
                exact.append(e)

    alpha = krippendorff_alpha_nominal(strict_units)
    return {
        "n_candidate_positions": len(strict_units),
        "n_chains": len(chain_lengths),
        "strict_position_alpha": round(alpha, 4) if alpha is not None else None,
        "strict_position_cluster_bootstrap_ci_95": cluster_bootstrap_ci(clusters),
        "strict_position_raw_agreement": raw_agreement(strict_units),
        "exact_match_f1_mean": round(sum(exact) / len(exact), 4) if exact else None,
        "tolerant_f1_mean": round(sum(tolerant) / len(tolerant), 4) if tolerant else None,
        "tolerance_messages": BOUNDARY_TOLERANCE,
        "confusion": pairwise_confusion(strict_units),
        "estimability_status": estimability(strict_units, alpha),
        "note": ("positions inside a chain are NOT independent: the CI is a cluster "
                 "bootstrap over CHAINS, strict alpha under-states and tolerant F1 "
                 "over-states segmentation agreement, and n_chains is the real "
                 "limit on power, not n_candidate_positions"),
    }


# --- io ----------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def opaque_id(seed: str, item_id: str) -> str:
    return "x" + hashlib.sha256(f"{seed}/{item_id}".encode()).hexdigest()[:12]


# --- materialize -------------------------------------------------------------

RELATION_FILE = "relation-items.jsonl"
SEGMENT_FILE = "segmentation-items.jsonl"


def materialize(corpus_dir: Path) -> int:
    """Deterministic per-annotator projections + seal.

    Each annotator gets their own order and their own opaque ids, so layers
    cannot be aligned by eye before they are frozen, and the facilitator map is
    the only way back to canonical ids.
    """
    relation = load_jsonl(corpus_dir / RELATION_FILE)
    segments = load_jsonl(corpus_dir / SEGMENT_FILE)
    pres_dir = corpus_dir / "presentation"
    map_dir = corpus_dir / "presentation-map"
    pres_dir.mkdir(exist_ok=True)
    map_dir.mkdir(exist_ok=True)

    for annotator in ANNOTATORS:
        seed = f"{PRESENTATION_SEED_PREFIX}/{annotator}"
        rng = random.Random(seed)
        mapping: dict[str, str] = {}

        def project(items: list[dict], keep: tuple[str, ...]) -> list[dict]:
            out = []
            for it in items:
                oid = opaque_id(seed, it["item_id"])
                mapping[oid] = it["item_id"]
                # stratum / anchor_kind / design_note are facilitator-only: knowing
                # what an item was built to test anchors the answer.
                out.append({k: (oid if k == "item_id" else it[k]) for k in keep})
            rng.shuffle(out)
            return out

        rel = project(relation, ("schema_version", "item_id", "language", "messages",
                                 "anchor_message_id", "target_message_id",
                                 "applicable_primitives"))
        seg = project(segments, ("schema_version", "item_id", "language", "messages",
                                 "candidate_boundaries"))

        (pres_dir / f"{annotator}-relation.jsonl").write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in rel) + "\n", encoding="utf-8")
        (pres_dir / f"{annotator}-segmentation.jsonl").write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in seg) + "\n", encoding="utf-8")
        (map_dir / f"{annotator}.json").write_text(
            json.dumps({"schema_version": "rf.primitives-presentation-map.v1",
                        "annotator": annotator, "seed": seed, "map": mapping},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sealed = sorted(
        [RELATION_FILE, SEGMENT_FILE]
        + [f"presentation/{a}-{k}.jsonl" for a in ANNOTATORS for k in ("relation", "segmentation")]
        + [f"presentation-map/{a}.json" for a in ANNOTATORS])
    (corpus_dir / "CHECKSUMS.sha256").write_text(
        "".join(f"{sha256_file(corpus_dir / rel)}  {rel}\n" for rel in sealed), encoding="utf-8")
    print(f"OK: {len(relation)} relation items, {len(segments)} chains, "
          f"{len(ANNOTATORS)} layers, {len(sealed)} files sealed")
    return 0


# --- validation --------------------------------------------------------------

def validate_corpus(corpus_dir: Path) -> list[str]:
    issues: list[str] = []
    relation = load_jsonl(corpus_dir / RELATION_FILE)
    segments = load_jsonl(corpus_dir / SEGMENT_FILE)

    seen: set[str] = set()
    for it in relation:
        iid = it["item_id"]
        if iid in seen:
            issues.append(f"{iid}: duplicate item_id")
        seen.add(iid)
        ids = {m["message_id"] for m in it["messages"]}
        if it["anchor_message_id"] not in ids:
            issues.append(f"{iid}: anchor_message_id not among messages")
        if it["target_message_id"] not in ids:
            issues.append(f"{iid}: target_message_id not among messages")
        for m in it["messages"]:
            if m.get("reply_to") and m["reply_to"] not in ids:
                issues.append(f"{iid}: reply_to points outside the item")
        prims = it["applicable_primitives"]
        if "P1" not in prims or "P2" not in prims:
            issues.append(f"{iid}: P1 and P2 apply to every relation item")
        if ("P3" in prims) != (it["anchor_kind"] == "negative"):
            issues.append(f"{iid}: P3 applicability must follow anchor_kind=negative")
        if ("P4" in prims) != (it["anchor_kind"] == "softening"):
            issues.append(f"{iid}: P4 applicability must follow anchor_kind=softening")

    for it in segments:
        ids = [m["message_id"] for m in it["messages"]]
        expected = [f"{ids[i]}|{ids[i+1]}" for i in range(len(ids) - 1)]
        if it["candidate_boundaries"] != expected:
            issues.append(f"{it['item_id']}: candidate_boundaries must be every consecutive gap")
    return issues


def validate_responses(items: list[dict], responses: list[dict], layer: str) -> list[str]:
    issues: list[str] = []
    by_id = {it["item_id"]: it for it in items}
    seen: Counter = Counter(r["item_id"] for r in responses)
    for iid, n in seen.items():
        if n > 1:
            issues.append(f"{layer}/{iid}: answered {n} times")
        if iid not in by_id:
            issues.append(f"{layer}/{iid}: unknown item")
    for missing in sorted(set(by_id) - set(seen)):
        issues.append(f"{layer}/{missing}: not answered")

    for r in responses:
        iid = r.get("item_id")
        it = by_id.get(iid)
        if it is None:
            continue
        if r.get("schema_version") != "rf.primitives-response.v1":
            issues.append(f"{layer}/{iid}: bad schema_version")
        for prim in ("P1", "P2", "P3", "P4"):
            value = r.get(prim.lower())
            applicable = prim in it["applicable_primitives"]
            if applicable and value not in ANSWERS[prim]:
                issues.append(f"{layer}/{iid}: {prim} must be one of {ANSWERS[prim]}, got {value!r}")
            if not applicable and value is not None:
                issues.append(f"{layer}/{iid}: {prim} answered but not applicable to this item")
        fb = r.get("feedback")
        if fb is not None:
            for flag in fb.get("flags", []):
                if flag not in FEEDBACK_FLAGS:
                    issues.append(f"{layer}/{iid}: unknown feedback flag {flag!r}")
    return issues


def validate_boundary_responses(items: list[dict], responses: list[dict], layer: str) -> list[str]:
    issues: list[str] = []
    by_id = {it["item_id"]: it for it in items}
    for r in responses:
        iid = r.get("item_id")
        it = by_id.get(iid)
        if it is None:
            issues.append(f"{layer}/{iid}: unknown chain")
            continue
        if r.get("schema_version") != "rf.primitives-boundary-response.v1":
            issues.append(f"{layer}/{iid}: bad schema_version")
        answers = r.get("boundaries") or {}
        for key in it["candidate_boundaries"]:
            if answers.get(key) not in BOUNDARY_ANSWERS:
                issues.append(f"{layer}/{iid}: boundary {key} must be one of {BOUNDARY_ANSWERS}")
        for key in answers:
            if key not in it["candidate_boundaries"]:
                issues.append(f"{layer}/{iid}: unknown boundary {key}")
    for missing in sorted(set(by_id) - {r.get("item_id") for r in responses}):
        issues.append(f"{layer}/{missing}: chain not answered")
    return issues


# --- report ------------------------------------------------------------------

def remap(corpus_dir: Path, annotator: str, responses: list[dict]) -> list[dict]:
    path = corpus_dir / "presentation-map" / f"{annotator}.json"
    if not path.exists():
        return responses
    mapping = json.loads(path.read_text(encoding="utf-8"))["map"]
    return [{**r, "item_id": mapping.get(r["item_id"], r["item_id"])} for r in responses]


def report(corpus_dir: Path) -> int:
    relation = load_jsonl(corpus_dir / RELATION_FILE)
    segments = load_jsonl(corpus_dir / SEGMENT_FILE)
    responses_dir = corpus_dir / "responses"

    corpus_issues = validate_corpus(corpus_dir)
    if corpus_issues:
        print("CORPUS VALIDATION FAILED:", file=sys.stderr)
        for i in corpus_issues:
            print(f"- {i}", file=sys.stderr)
        return 1

    rel_layers, seg_layers, present = {}, {}, []
    for annotator in ANNOTATORS:
        rp = responses_dir / f"{annotator}-relation.jsonl"
        sp = responses_dir / f"{annotator}-segmentation.jsonl"
        if not rp.exists():
            continue
        present.append(annotator)
        rel_layers[annotator] = remap(corpus_dir, annotator, load_jsonl(rp))
        seg_layers[annotator] = remap(corpus_dir, annotator, load_jsonl(sp)) if sp.exists() else []

    if len(present) < 2:
        print(f"MISSING LAYERS: {len(present)} of {len(ANNOTATORS)} present — "
              f"agreement needs at least two. No report written.", file=sys.stderr)
        return 2

    issues: list[str] = []
    for annotator in present:
        issues += validate_responses(relation, rel_layers[annotator], annotator)
        issues += validate_boundary_responses(segments, seg_layers[annotator], annotator)
    if issues:
        print("RESPONSE VALIDATION FAILED:", file=sys.stderr)
        for i in issues:
            print(f"- {i}", file=sys.stderr)
        return 1

    by_item = {a: {r["item_id"]: r for r in rel_layers[a]} for a in present}

    def units_for(prim: str, subset: list[dict]) -> list[list[str]]:
        out = []
        for it in subset:
            if prim not in it["applicable_primitives"]:
                continue
            out.append([by_item[a].get(it["item_id"], {}).get(prim.lower()) for a in present])
        return out

    per_primitive = {}
    for prim, categories in ANSWERS.items():
        applicable = [it for it in relation if prim in it["applicable_primitives"]]
        per_primitive[prim] = {
            "construct_name": PRIMITIVE_NAMES[prim],
            "all": primitive_stats(units_for(prim, applicable), categories),
        }
        for name, members in SUPER_STRATA.items():
            subset = [it for it in applicable if it["stratum"] in members]
            per_primitive[prim][f"super_stratum:{name}"] = primitive_stats(
                units_for(prim, subset), categories)
        # DESCRIPTIVE ONLY below: n=5 per stratum, n=12 for en.
        for stratum in sorted({it["stratum"] for it in applicable}):
            subset = [it for it in applicable if it["stratum"] == stratum]
            per_primitive[prim][f"descriptive_stratum:{stratum}"] = primitive_stats(
                units_for(prim, subset), categories)
        for lang in sorted({it["language"] for it in applicable}):
            subset = [it for it in applicable if it["language"] == lang]
            per_primitive[prim][f"descriptive_language:{lang}"] = primitive_stats(
                units_for(prim, subset), categories)

    per_chain: dict[str, dict[str, list[str]]] = {}
    seg_by_item = {a: {r["item_id"]: r for r in seg_layers[a]} for a in present}
    for it in segments:
        per_chain[it["item_id"]] = {
            key: [seg_by_item[a].get(it["item_id"], {}).get("boundaries", {}).get(key)
                  for a in present]
            for key in it["candidate_boundaries"]
        }

    feedback: Counter = Counter()
    for a in present:
        for r in rel_layers[a]:
            for flag in (r.get("feedback") or {}).get("flags", []):
                feedback[flag] += 1

    out = {
        "schema_version": "rf.primitives-report.v1",
        "pilot_id": "interaction-primitives-v0",
        "prereg": "docs/research/interaction-primitives-v0-prereg.md",
        "annotators_present": present,
        "n_relation_items": len(relation),
        "n_segmentation_chains": len(segments),
        "thresholds": {"alpha_fail": ALPHA_FAIL, "alpha_target": ALPHA_TARGET,
                       "min_pairable_units": MIN_PAIRABLE_UNITS,
                       "min_category_union": MIN_CATEGORY_UNION,
                       "boundary_tolerance": BOUNDARY_TOLERANCE},
        "construct_names": PRIMITIVE_NAMES,
        "super_strata": {k: list(v) for k, v in SUPER_STRATA.items()},
        "per_primitive": per_primitive,
        "boundaries": boundary_stats(per_chain),
        "item_feedback": dict(feedback.most_common()),
        "note": ("Analyses not listed in the prereg document are POST_HOC and must "
                 "be reported as such. Keys prefixed `descriptive_` are DESCRIPTIVE "
                 "ONLY and never gate a decision; SUPPORTED_FOR_NEXT_STAGE additionally "
                 "requires the `substantive` layer to be estimable."),
    }
    out_dir = corpus_dir / "report"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "primitives-report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: report written to {out_dir}")
    return 0


def preview(corpus_dir: Path, annotator: str = "annotator-1") -> int:
    """Render one presentation layer the way a human must see it.

    Exists because C1 only tests explicit-reply metadata if the SURFACE actually
    draws the reply relation. A linear list of three messages turns
    `explicit_reply_trap` into a content-only judgement and quietly voids the
    comparison. A JSON file that carries `reply_to` and is very proud of itself is
    not the same thing as a human seeing an arrow.
    """
    path = corpus_dir / "presentation" / f"{annotator}-relation.jsonl"
    rows = load_jsonl(path)
    lines = [f"# {annotator} — relation task preview ({len(rows)} items)", ""]
    with_reply = 0
    for row in rows:
        lines.append(f"## {row['item_id']} [{row['language']}]  "
                     f"вопросы: {', '.join(row['applicable_primitives'])}")
        by_id = {m["message_id"]: m for m in row["messages"]}
        for m in row["messages"]:
            marks = []
            if m["message_id"] == row["anchor_message_id"]:
                marks.append("A")
            if m["message_id"] == row["target_message_id"]:
                marks.append("B")
            tag = f"[{'/'.join(marks)}]" if marks else "[ ]"
            if m.get("reply_to"):
                with_reply += 1
                quoted = by_id[m["reply_to"]]["text"]
                lines.append(f"  {tag} {m['author']}: ↳ в ответ на «{quoted[:40]}»")
                lines.append(f"      {m['text']}")
            else:
                lines.append(f"  {tag} {m['author']}: {m['text']}")
        lines.append("")
    out = corpus_dir / "preview" / f"{annotator}-relation.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK: preview -> {out} ({with_reply} message(s) rendered with an explicit "
          f"reply relation)")
    return 0 if with_reply else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("materialize", "validate", "report", "preview"))
    ap.add_argument("--corpus-dir", type=Path, required=True)
    args = ap.parse_args()
    if args.command == "materialize":
        return materialize(args.corpus_dir)
    if args.command == "preview":
        return preview(args.corpus_dir)
    if args.command == "validate":
        issues = validate_corpus(args.corpus_dir)
        for i in issues:
            print(f"- {i}", file=sys.stderr)
        print("OK: corpus valid" if not issues else f"{len(issues)} issue(s)")
        return 1 if issues else 0
    return report(args.corpus_dir)


if __name__ == "__main__":
    raise SystemExit(main())
