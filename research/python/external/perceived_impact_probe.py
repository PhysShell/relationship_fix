"""Probe: is recipient-perceived impact the same measurement as observer coding?

External Measurement & Calibration Audit, TRACK 4. The architectural claim under
test is narrow and falsifiable:

    an observer rating of a message and the recipient's own report of how that
    message landed are two different observations, and neither is a version of
    the other.

If the claim is wrong -- if observers reliably recover what recipients report --
then `PerceivedImpact` needs no separate representation and an observer-coded
pipeline can carry it. So we look for a public dataset where the SAME six named
constructs were rated twice, once by the person who received the message and
once by people who only read it, on the same 1-7 scale, keyed to the same
conversation.

Reference data (both files, MIT-licensed, in the replication repository of
Kumar et al., "When Large Language Models are Reliable for Judging Empathic
Communication", arXiv:2506.10150 / Nature Machine Intelligence 2026):

  original_data/perceived_empathy_self_ratings.csv
      one row per discloser from Yin, Jia & Wakslak, "AI can help people feel
      heard, but an AI label diminishes this impact", PNAS 2024. Carries the
      RECIPIENT's own 1-7 ratings, plus the two randomised experimental factors
      `responseR` (who actually wrote the reply) and `labelR` (who the recipient
      was TOLD wrote it).

  annotations/combined_annotations_across_methods_and_datasets.csv
      observer ratings of the same conversations by three experts, their median,
      crowdworkers, and three LLMs, on the same six names.

Neither file is vendored here: this module takes paths. The conversation TEXT of
the Perceived Empathy corpus is not public (available on request to Yin et al.),
so this probe reports ids and numbers and never an example utterance.

This module imports nothing from `dyadic` and changes nothing: like the TRACK 1
probe it measures an external corpus against a proposed representation, and a
probe that repaired the thing it probes would be worthless.
"""

from __future__ import annotations

import csv
import itertools
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_RATINGS = "Yin, Jia & Wakslak 2024, PNAS (doi:10.1073/pnas.2319112121)"
SOURCE_OBSERVERS = "Kumar et al. 2026, Nat Mach Intell (arXiv:2506.10150)"

#: The six constructs rated by BOTH sides. Same word, same 1-7 scale, two
#: different questions -- see `QUESTION_ASYMMETRY`.
SHARED_DIMENSIONS = ("understood", "validated", "affirmed", "seen", "accepted", "caredfor")

#: Verbatim from the two instruments. The observer is not asked to describe the
#: message; the observer is asked to PREDICT the recipient. That is what makes
#: the comparison in this probe meaningful -- and what makes agreement between
#: them a testable claim rather than a definitional truth.
QUESTION_ASYMMETRY = {
    "observer": "To what extent do you think reading the response would make the discloser feel {dimension}?",
    "recipient": "the discloser's own 1-7 rating of feeling {dimension}, collected after reading the response",
}

#: Observer groups present in the reference file, in the order we report them.
OBSERVER_GROUPS = ("experts", "expert1", "expert2", "expert3", "crowd", "llm", "gpt", "claude")

BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_SEED = 42
PERMUTATION_ITERATIONS = 20000

#: A composite gap at or above this many scale points is reported as a
#: disagreement case. Chosen to match the threshold the reference paper used
#: when it looked for expert/LLM disagreements (3 or more points).
DISAGREEMENT_POINTS = 3.0


@dataclass(frozen=True, slots=True)
class SelfReport:
    """What the person who received the message said about receiving it.

    `stated_label` is the randomised claim about authorship the recipient was
    shown. It is part of the recipient's evidence and no part of the message,
    which is the whole point: an observer reading the message cannot see it.
    """

    discloser_id: str
    ratings: dict[str, float]
    actual_source: str | None = None   # 'human response' | 'ai response'
    stated_label: str | None = None    # 'human label'   | 'ai label'

    @property
    def composite(self) -> float:
        return statistics.fmean(self.ratings[d] for d in SHARED_DIMENSIONS)


@dataclass(frozen=True, slots=True)
class ObserverRating:
    """What someone who only read the exchange estimated about the recipient."""

    conversation_id: str
    group: str
    ratings: dict[str, float]

    @property
    def composite(self) -> float:
        return statistics.fmean(self.ratings[d] for d in SHARED_DIMENSIONS)


@dataclass
class PairingReport:
    """What could be paired and what could not.

    Shaped as lists rather than a coverage percentage, for the same reason as
    the TRACK 1 losslessness report: a percentage lets a pairing that silently
    drops one arm of a randomised design look fine.
    """

    matched: list[str] = field(default_factory=list)
    self_only: list[str] = field(default_factory=list)
    observer_only: list[str] = field(default_factory=list)
    #: Ids present on both sides but missing at least one shared dimension.
    incomplete: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.observer_only and not self.incomplete


@dataclass(frozen=True, slots=True)
class Association:
    """One ordinal association with its interval. No p-value, no verdict.

    `n` travels with it because an interval this wide is a statement about the
    sample size as much as about the world.
    """

    label: str
    n: int
    tau_b: float
    ci_low: float
    ci_high: float

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.label}: tau_b={self.tau_b:+.2f} CI=[{self.ci_low:+.2f},{self.ci_high:+.2f}] (n={self.n})"


@dataclass(frozen=True, slots=True)
class GroupContrast:
    """A difference in means between two arms, with a permutation p-value."""

    label: str
    n_a: int
    n_b: int
    mean_a: float
    mean_b: float
    p_value: float

    @property
    def difference(self) -> float:
        return self.mean_a - self.mean_b


@dataclass(frozen=True, slots=True)
class DisagreementCase:
    """A conversation where the two sides diverge by DISAGREEMENT_POINTS or more.

    Carries ids and numbers only. The conversation text of this corpus is not
    public, and a probe that invented a plausible message to illustrate its own
    finding would be manufacturing the evidence it claims to have found.
    """

    conversation_id: str
    recipient: float
    observer: float
    observer_group: str
    stated_label: str | None

    @property
    def gap(self) -> float:
        return self.observer - self.recipient

    @property
    def direction(self) -> str:
        return "observer_high_recipient_low" if self.gap > 0 else "observer_low_recipient_high"


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def load_self_reports(path: str | Path) -> dict[str, SelfReport]:
    """Read the recipient side. Rows missing any shared dimension are skipped."""
    out: dict[str, SelfReport] = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            try:
                ratings = {d: float(row[d]) for d in SHARED_DIMENSIONS}
            except (KeyError, ValueError):
                continue
            out[row["id"]] = SelfReport(
                discloser_id=row["id"],
                ratings=ratings,
                actual_source=row.get("responseR") or None,
                stated_label=row.get("labelR") or None,
            )
    return out


def load_observer_ratings(path: str | Path) -> dict[str, dict[str, ObserverRating]]:
    """Read the observer side, keyed group -> conversation_id.

    The reference file is several differently-keyed blocks concatenated
    side by side with repeated column names, so we locate the Perceived Empathy
    block by its id column and read the fixed-width run that follows it rather
    than trusting a dict reader to resolve duplicate headers.
    """
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    start = header.index("perceived_conversation_id")
    columns = header[start : start + 11]
    if "annotation_method" not in columns:
        raise ValueError("perceived-empathy block does not carry an annotation_method column")
    method_at = start + columns.index("annotation_method")

    out: dict[str, dict[str, ObserverRating]] = {}
    for row in rows[1:]:
        if len(row) <= method_at or not row[start]:
            continue
        try:
            ratings = {d: float(row[start + 1 + i]) for i, d in enumerate(SHARED_DIMENSIONS)}
        except ValueError:
            continue
        group = row[method_at]
        out.setdefault(group, {})[row[start]] = ObserverRating(row[start], group, ratings)
    return out


def pair(
    self_reports: dict[str, SelfReport],
    observers: dict[str, ObserverRating],
) -> tuple[list[str], PairingReport]:
    """Match one observer group to the recipient side on conversation id."""
    report = PairingReport()
    for cid in sorted(observers):
        if cid not in self_reports:
            report.observer_only.append(cid)
        else:
            report.matched.append(cid)
    report.self_only = sorted(set(self_reports) - set(observers))
    return report.matched, report


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def kendall_tau_b(xs: list[float], ys: list[float]) -> float:
    """Tie-corrected ordinal association.

    tau_b rather than a Pearson correlation or a kappa on purpose: both sides
    use the scale differently (see `scale_use`), so a statistic that rewards
    matching absolute values would report calibration, not ordering.
    """
    if len(xs) != len(ys):
        raise ValueError("kendall_tau_b needs equal-length inputs")
    concordant = discordant = tied_x = tied_y = 0
    for i, j in itertools.combinations(range(len(xs)), 2):
        dx, dy = xs[i] - xs[j], ys[i] - ys[j]
        if dx == 0 and dy == 0:
            tied_x += 1
            tied_y += 1
        elif dx == 0:
            tied_x += 1
        elif dy == 0:
            tied_y += 1
        elif (dx > 0) == (dy > 0):
            concordant += 1
        else:
            discordant += 1
    pairs = len(xs) * (len(xs) - 1) / 2
    denominator = ((pairs - tied_x) * (pairs - tied_y)) ** 0.5
    if denominator == 0:
        raise ValueError("tau_b is undefined when one side is constant")
    return (concordant - discordant) / denominator


def associate(
    label: str,
    xs: list[float],
    ys: list[float],
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> Association:
    """tau_b with a bootstrap interval over conversations."""
    point = kendall_tau_b(xs, ys)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(iterations):
        idx = [rng.randrange(len(xs)) for _ in range(len(xs))]
        try:
            draws.append(kendall_tau_b([xs[i] for i in idx], [ys[i] for i in idx]))
        except ValueError:
            continue  # a resample with one side constant carries no ordering
    draws.sort()
    return Association(label, len(xs), point, draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws))])


def association_difference(
    label: str,
    xs: list[float],
    ys_a: list[float],
    ys_b: list[float],
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> Association:
    """tau_b(xs, ys_a) - tau_b(xs, ys_b), resampling conversations jointly.

    Comparing two intervals by eye is not a test. Resampling the same
    conversations for both sides is, because the two associations move together
    under the resample.
    """
    point = kendall_tau_b(xs, ys_a) - kendall_tau_b(xs, ys_b)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(iterations):
        idx = [rng.randrange(len(xs)) for _ in range(len(xs))]
        sub = [xs[i] for i in idx]
        try:
            draws.append(kendall_tau_b(sub, [ys_a[i] for i in idx]) - kendall_tau_b(sub, [ys_b[i] for i in idx]))
        except ValueError:
            continue
    draws.sort()
    return Association(label, len(xs), point, draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws))])


def permutation_contrast(
    label: str,
    arm_a: list[float],
    arm_b: list[float],
    iterations: int = PERMUTATION_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> GroupContrast:
    """Two-sided permutation test on a difference in means."""
    observed = abs(statistics.fmean(arm_a) - statistics.fmean(arm_b))
    pooled = list(arm_a) + list(arm_b)
    rng = random.Random(seed)
    hits = 0
    for _ in range(iterations):
        rng.shuffle(pooled)
        if abs(statistics.fmean(pooled[: len(arm_a)]) - statistics.fmean(pooled[len(arm_a) :])) >= observed:
            hits += 1
    return GroupContrast(
        label=label,
        n_a=len(arm_a),
        n_b=len(arm_b),
        mean_a=statistics.fmean(arm_a),
        mean_b=statistics.fmean(arm_b),
        p_value=(hits + 1) / (iterations + 1),
    )


def scale_use(values: list[float], high_from: float = 5.0) -> dict[str, float]:
    """Where on the scale a rater group actually lives."""
    return {
        "n": float(len(values)),
        "mean": statistics.fmean(values),
        "sd": statistics.pstdev(values),
        "min": min(values),
        "max": max(values),
        "share_at_or_above": sum(1 for v in values if v >= high_from) / len(values),
    }


def disagreements(
    ids: list[str],
    self_reports: dict[str, SelfReport],
    observers: dict[str, ObserverRating],
    threshold: float = DISAGREEMENT_POINTS,
    centered: bool = False,
) -> list[DisagreementCase]:
    """Conversations the two sides read differently, both directions, sorted.

    On raw scores the two sides sit ~2 scale points apart (see `scale_use`), so
    an uncentered list is mostly a restatement of that offset and will come back
    one-directional. `centered=True` subtracts each side's own mean first, which
    asks the different and more useful question: which conversations does one
    side rank unusually high RELATIVE TO ITS OWN SPREAD and the other not.
    """
    cases = []
    offset_recipient = statistics.fmean(self_reports[c].composite for c in ids) if centered else 0.0
    offset_observer = statistics.fmean(observers[c].composite for c in ids) if centered else 0.0
    for cid in ids:
        recipient = self_reports[cid].composite - offset_recipient
        observer = observers[cid].composite - offset_observer
        if abs(observer - recipient) >= threshold:
            cases.append(
                DisagreementCase(
                    conversation_id=cid,
                    recipient=recipient,
                    observer=observer,
                    observer_group=observers[cid].group,
                    stated_label=self_reports[cid].stated_label,
                )
            )
    return sorted(cases, key=lambda c: c.gap)


def label_effect(
    self_reports: dict[str, SelfReport],
    actual_source: str = "human response",
) -> GroupContrast:
    """The manipulation that no observer can see.

    Within one actual authorship condition, recipients were randomly told the
    reply came from a human or from an AI. Randomisation makes the distribution
    of response text independent of the label, so any difference here is a
    component of perceived impact that is NOT IDENTIFIABLE FROM THE RESPONSE
    TEXT ALONE: it moves under contextual information the text does not carry.

    Note the limit of the design: the two arms were not shown the same literal
    text twice, so this is a randomised contrast, not a paired same-text
    counterfactual. It establishes a causal contextual effect; it does not
    establish what an ideal reader of one fixed message could or could not do.
    """
    arm = [s for s in self_reports.values() if s.actual_source == actual_source]
    human_label = [s.composite for s in arm if s.stated_label == "human label"]
    ai_label = [s.composite for s in arm if s.stated_label == "ai label"]
    if not human_label or not ai_label:
        raise ValueError(f"no randomised label arms under actual_source={actual_source!r}")
    return permutation_contrast(f"stated label, {actual_source} only", human_label, ai_label)


def label_blindness_control(
    ids: list[str],
    self_reports: dict[str, SelfReport],
    observers: dict[str, ObserverRating],
) -> GroupContrast:
    """Negative control: observer ratings split by the recipient's label arm.

    This is NOT a finding. Observers were never shown the label and the label
    was randomised, so a null here is guaranteed by the design. It is a data
    integrity check: a difference would mean the id join is wrong.
    """
    human_label = [observers[c].composite for c in ids if self_reports[c].stated_label == "human label"]
    ai_label = [observers[c].composite for c in ids if self_reports[c].stated_label == "ai label"]
    return permutation_contrast("observer ratings by recipient's label arm (control)", human_label, ai_label)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def report(self_ratings_csv: str | Path, annotations_csv: str | Path, lengths_csv: str | Path | None = None) -> None:
    """Print the full probe. Reproduces the numbers recorded in
    docs/research/perceived-impact-audit.md."""
    selves = load_self_reports(self_ratings_csv)
    groups = load_observer_ratings(annotations_csv)

    print(f"recipient side : {len(selves)} disclosers   [{SOURCE_RATINGS}]")
    print(f"observer side  : {sorted(groups)}   [{SOURCE_OBSERVERS}]")

    print("\n== the manipulation observers cannot see ==")
    for source in ("human response", "ai response"):
        try:
            effect = label_effect(selves, source)
        except ValueError:
            continue
        print(
            f"  {source:15s}: told-human {effect.mean_a:.2f} (n={effect.n_a}) vs "
            f"told-AI {effect.mean_b:.2f} (n={effect.n_b})  diff={effect.difference:+.2f}  perm p={_p(effect.p_value)}"
        )

    ids, pairing = pair(selves, groups["experts"])
    print(f"\n== pairing == matched {len(pairing.matched)}, observer-only {len(pairing.observer_only)}, "
          f"self-only {len(pairing.self_only)}, incomplete {len(pairing.incomplete)}")

    recipient = [selves[c].composite for c in ids]
    print("\n== scale use (composite of six shared dimensions, 1-7) ==")
    for name, vals in [("recipient", recipient)] + [(g, [groups[g][c].composite for c in ids]) for g in OBSERVER_GROUPS if g in groups]:
        u = scale_use(vals)
        print(f"  {name:9s} mean={u['mean']:.2f} sd={u['sd']:.2f} range=[{u['min']:.2f},{u['max']:.2f}] share>=5: {u['share_at_or_above']:.0%}")

    print("\n== does an observer recover the recipient's ordering? ==")
    for group in OBSERVER_GROUPS:
        if group not in groups:
            continue
        observed = [groups[group][c].composite for c in ids]
        print("  " + str(associate(f"{group} -> recipient", observed, recipient)))

    print("\n== per dimension (experts / crowd / llm) ==")
    for group in ("experts", "crowd", "llm"):
        if group not in groups:
            continue
        for dimension in SHARED_DIMENSIONS:
            observed = [groups[group][c].ratings[dimension] for c in ids]
            target = [selves[c].ratings[dimension] for c in ids]
            print(f"  {group:8s} " + str(associate(dimension, observed, target)))

    if lengths_csv is not None:
        lengths = _load_lengths(lengths_csv)
        if all(c in lengths for c in ids):
            xs = [lengths[c] for c in ids]
            print("\n== what each side tracks: response length ==")
            print("  " + str(associate("length -> recipient", xs, recipient)))
            for group in ("experts", "crowd", "llm"):
                if group not in groups:
                    continue
                observed = [groups[group][c].composite for c in ids]
                print("  " + str(associate(f"length -> {group}", xs, observed)))
                print("    " + str(association_difference(f"length tracked by {group} minus by recipient", xs, observed, recipient)))

    print("\n== negative control (design-guaranteed null; a hit means a bad join) ==")
    for group in ("experts", "crowd", "llm"):
        if group not in groups:
            continue
        control = label_blindness_control(ids, selves, groups[group])
        print(f"  {group:8s} diff={control.difference:+.3f} perm p={_p(control.p_value)}")

    raw = disagreements(ids, selves, groups["experts"])
    print(f"\n== disagreement cases vs median expert, RAW (gap >= {DISAGREEMENT_POINTS} points) ==")
    print(f"  {len(raw)} of {len(ids)}; "
          f"{sum(1 for c in raw if c.gap < 0)} observer-low/recipient-high, "
          f"{sum(1 for c in raw if c.gap > 0)} observer-high/recipient-low")
    print("  one-directional by construction: the two sides sit ~2 points apart on the same scale")
    print("\n== the four widest disagreements in each direction, MEAN-CENTERED ==")
    centered = disagreements(ids, selves, groups["experts"], threshold=0.0, centered=True)
    print("  observer ranks it far ABOVE where the recipient did:")
    for case in reversed(centered[-4:]):
        print(f"    {case.conversation_id}  recipient={case.recipient:+.2f} expert={case.observer:+.2f} "
              f"gap={case.gap:+.2f} told: {case.stated_label}")
    print("  observer ranks it far BELOW where the recipient did:")
    for case in centered[:4]:
        print(f"    {case.conversation_id}  recipient={case.recipient:+.2f} expert={case.observer:+.2f} "
              f"gap={case.gap:+.2f} told: {case.stated_label}")
    print("  (conversation text is not public for this corpus; ids and numbers only)")


def _p(value: float) -> str:
    """Never print a permutation p as 0.0000; it is bounded below by 1/(N+1)."""
    floor = 1 / (PERMUTATION_ITERATIONS + 1)
    return f"<{floor:.5f}" if value <= floor else f"{value:.4f}"


def _load_lengths(path: str | Path) -> dict[str, float]:
    out: dict[str, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            try:
                out[row["OriginalDiscloserID"]] = float(row["response_length"])
            except (KeyError, ValueError):
                continue
    return out


if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) < 3:
        raise SystemExit(
            "usage: perceived_impact_probe.py <perceived_empathy_self_ratings.csv> "
            "<combined_annotations_across_methods_and_datasets.csv> [sample_perceived_empathy_annotations.csv]"
        )
    report(*sys.argv[1:4])
