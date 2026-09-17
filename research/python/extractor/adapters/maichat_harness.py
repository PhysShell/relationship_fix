"""Run the reference extractor over the whole MaiChat corpus and check invariants.

External qualification: the first time the extractor meets real dyadic message
streams it did not invent. Nothing here is a statistic about people — it checks
that the algorithm behaves lawfully on natural data and reports where the
product's own parameters do not fit the corpus.

The corpus is not vendored (CC BY-SA 4.0 share-alike); pass a path:

    python -m extractor.adapters.maichat_harness /path/to/maichat_dataset/conversations
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from ..extract import extract, production_export
from ..model import HORIZONS_HOURS, Mode
from .maichat import AdapterProvenance, adapt_file

#: The product's grid, from reactivity-power-design §6.2.
PRODUCT_HORIZONS = HORIZONS_HOURS
#: A session-scale grid, used ONLY to exercise topology on a corpus whose
#: conversations last minutes. Not a product parameter and never reported as one.
SESSION_HORIZONS = (1 / 60, 5 / 60, 30 / 60)


@dataclass
class Violations:
    entries: list[str] = field(default_factory=list)

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            self.entries.append(message)

    def __len__(self) -> int:
        return len(self.entries)


def span(messages) -> tuple[float, float]:
    """The conversation's own period: [first, last + 1s)."""
    times = [m.timestamp for m in messages]
    return min(times), max(times) + 1.0


def check_conversation(path: Path, horizons: tuple[float, ...], violations: Violations) -> dict:
    messages, provenance = adapt_file(path)
    if not messages:
        return {"path": path.name, "skipped": "no messages"}
    start, end = span(messages)
    row = {"path": path.name, "messages": len(messages),
           "span_minutes": (end - start) / 60.0, "provenance": provenance,
           "per_participant": {}}

    for participant in provenance.participants:
        result = extract(messages, participant, path.stem, start, end,
                         mode=Mode.QUALIFICATION, consent_to_share_trace=True,
                         horizons_hours=horizons)
        trace = result.export_trace()
        tag = f"{path.name}/{participant[:6]}"

        # 1. no negative latency, and the hand-over always runs partner -> participant
        by_id = {m.message_id: m for m in messages}
        for opportunity in trace:
            latency = opportunity.latency_seconds
            violations.check(latency is None or latency >= 0, f"{tag}: negative latency")
            violations.check(by_id[opportunity.opener_id].actor != participant,
                             f"{tag}: opportunity opened by the participant")
            if opportunity.reply_id is not None:
                violations.check(by_id[opportunity.reply_id].actor == participant,
                                 f"{tag}: reply attributed to the partner")

        # 2. eligibility is non-increasing in H (a longer window needs more room)
        eligible = [h.opportunities_eligible for h in result.aggregate.horizons]
        violations.check(all(a >= b for a, b in zip(eligible, eligible[1:])),
                         f"{tag}: eligibility not monotone in H: {eligible}")

        # 3. bounded statistics
        for aggregate in result.aggregate.horizons:
            rmtr = aggregate.rmtr_seconds
            violations.check(rmtr is None or 0 <= rmtr <= aggregate.horizon_hours * 3600.0,
                             f"{tag}: RMTR outside [0,H] at H={aggregate.horizon_hours}")
            rate = aggregate.reply_rate
            violations.check(rate is None or 0.0 <= rate <= 1.0,
                             f"{tag}: reply rate outside [0,1]")

        # 4. input order cannot matter, and the run reproduces
        payload = production_export(result.aggregate)
        shuffled = list(messages)
        random.Random(1234).shuffle(shuffled)
        again = extract(shuffled, participant, path.stem, start, end,
                        horizons_hours=horizons)
        violations.check(production_export(again.aggregate) == payload,
                         f"{tag}: export changed under input permutation")
        repeat = extract(messages, participant, path.stem, start, end,
                         horizons_hours=horizons)
        violations.check(production_export(repeat.aggregate) == payload,
                         f"{tag}: export not reproducible")

        row["per_participant"][participant] = {
            "opportunities_all": len(trace),
            "eligible": eligible,
            "export": payload,
        }
    return row


def report(directory: str | Path) -> None:  # pragma: no cover - reporting only
    paths = sorted(Path(directory).glob("*.json"))
    print(f"MaiChat external qualification — {len(paths)} conversation files\n")

    for name, horizons in (("PRODUCT grid 6/12/24h", PRODUCT_HORIZONS),
                           ("SESSION grid 1/5/30min", SESSION_HORIZONS)):
        violations = Violations()
        rows = [check_conversation(p, horizons, violations) for p in paths]
        rows = [r for r in rows if "skipped" not in r]
        messages = sum(r["messages"] for r in rows)
        failed = sum(r["provenance"].failed_excluded for r in rows)
        in_file = sum(r["provenance"].messages_in_file for r in rows)
        spans = sorted(r["span_minutes"] for r in rows)
        opportunities = sum(sum(p["opportunities_all"] for p in r["per_participant"].values())
                            for r in rows)
        eligible_totals = [
            sum(sum(p["eligible"][i] for p in r["per_participant"].values()) for r in rows)
            for i in range(len(horizons))
        ]
        print(f"== {name} ==")
        print(f"   conversations {len(rows)} · messages in file {in_file} · adapted {messages} "
              f"· failed excluded {failed}")
        print(f"   conversation span minutes: min {spans[0]:.1f} / median "
              f"{spans[len(spans)//2]:.1f} / max {spans[-1]:.1f}")
        print(f"   hand-overs found (both participants): {opportunities}")
        print(f"   eligible after calendar censoring, per horizon {horizons}: {eligible_totals}")
        print(f"   invariant violations: {len(violations)}")
        for entry in violations.entries[:10]:
            print(f"      ! {entry}")
        print()

    print(rows[0]["provenance"].claim_prefix())


if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("usage: maichat_harness.py <maichat_dataset/conversations>")
    report(sys.argv[1])
