"""Run the instrumentation certificate over an artifact on disk.

The fixture is not vendored — same rule as every corpus in this project: the
harness takes a path.

    python -m tools.certify <path.json> [participant_id]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from acquisition.certificate import SYNTHETIC_FIXTURE, certify
from acquisition.injection import INJECTIONS
from acquisition.model import ProducerProvenance, ProtocolWindow
from acquisition.pipeline import run


def main(argv) -> int:  # pragma: no cover - reporting only
    if len(argv) < 2:
        print("usage: python -m tools.certify <path.json> [participant_id]")
        return 2
    raw = Path(argv[1]).read_bytes()
    document = json.loads(raw)
    stamps = [int(m["date_unixtime"]) for m in document["messages"] if "date_unixtime" in m]
    participant = argv[2] if len(argv) > 2 else document["messages"][0]["from_id"]
    # HARNESS-DERIVED WINDOW. A real acquisition takes it from the protocol —
    # deriving it from the file is exactly what coverage.window_provenance
    # forbids. Here it is deliberate and labelled: it also makes the artifact
    # trip its own `starts_at_window_edge` heuristic, which is worth seeing fire
    # at scale.
    window = ProtocolWindow(participant_id=participant, period_id="certify",
                            start=float(min(stamps)), end=float(max(stamps)) + 1.0)
    producer = ProducerProvenance("Telegram Desktop (synthetic)", "n/a",
                                  "n/a", consent_recorded=True)

    print(certify(raw, window, producer, artifact_kind=SYNTHETIC_FIXTURE,
                  generator_provenance=argv[3] if len(argv) > 3 else "unrecorded",
                  markers=("You", document.get("name", ""))).render())

    baseline = run(raw, window, producer)
    print(f"\nfailure injections over this artifact "
          f"(baseline verdict: {baseline.verdict.value}):")
    for injection in INJECTIONS:
        corrupted = raw if injection.corrupt is None else injection.corrupt(raw)
        result = run(corrupted, window, None if injection.corrupt is None else producer)
        detail = ""
        if injection.expected_verdict is not None:
            ok = result.verdict is injection.expected_verdict
        else:
            ok = result.verdict.carries_measurements
        if injection.expected_code:
            ok = ok and injection.expected_code in result.codes()
        if injection.raises_counter:
            before = (baseline.aggregate or {}).get(injection.raises_counter, 0)
            after = (result.aggregate or {}).get(injection.raises_counter, -1)
            ok = ok and after > before
            detail = f"  {injection.raises_counter}: {before} -> {after}"
        if injection.planted_secret:
            import dataclasses
            leaked = injection.planted_secret in json.dumps(
                dataclasses.asdict(result), default=str)
            ok = ok and not leaked
            detail = f"  planted secret leaked: {leaked}"
        print(f"  {'ok ' if ok else '!! '}{injection.key:<30} "
              f"{result.verdict.value:<13}{detail}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
