"""Scanner for public Telegram Desktop exports — evidence, not a collection.

NOT AN ADAPTER. It produces no `RawMessage`, feeds nothing downstream, and
lives outside `extractor/` on purpose: the rule "no adapter until the
properties it depends on are qualified" still holds. This answers questions
ABOUT a file.

The point is to settle one question empirically across many public files
without accumulating a second corpus of other people's private conversations —
humanity manages that unaided. So the scan reads message text and keeps none of
it. What survives a scan:

    source label · sha256 · byte size · counts · inversion tuples
    (position, id_before, time_before, id_after, time_after)

What never survives: text, entities, names, `from`/`from_id`, chat id, chat
name, media paths, reactions, reply targets. `ScanResult` has no field that can
hold any of them, which is the same guarantee the extractor's types carry.

The decisive question, after the history-fetch pass established that the export
is ordered by ascending id:

    id[i+1] > id[i]  AND  date_unixtime[i+1] < date_unixtime[i]

ONE such pair proves exported id-order is not chronological order, and ends the
idea of using id as a chronological tie-break. The pair does not have to be
inside one second — hours apart is a stronger counterexample, not a weaker one.
Finding none proves nothing stronger than "not observed in this corpus".

    python -m tools.export_scan <label> <file.json> [...]
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Kept small: this is evidence, not a dataset. The first few pairs settle the
#: question; the count says how common it is.
MAX_COUNTEREXAMPLES = 20


class StrictJson(json.JSONDecoder):
    """Rejects what the standard library tolerates but JSON does not."""

    def __init__(self):
        super().__init__(parse_constant=self._refuse)

    @staticmethod
    def _refuse(name):
        raise ValueError(f"non-standard JSON constant {name!r}")


@dataclass(frozen=True, slots=True)
class Inversion:
    """Two adjacent entries whose id and time disagree about order."""

    position: int
    id_before: int
    time_before: int
    id_after: int
    time_after: int


@dataclass(frozen=True, slots=True)
class ScanResult:
    source: str
    sha256: str
    size_bytes: int
    strict_json_valid: bool
    #: parser message with the content stripped — position only
    parse_error: str | None = None
    entries: int = 0
    messages: int = 0
    service: int = 0
    other_types: int = 0
    missing_date_unixtime: int = 0
    unparsable_ids: int = 0
    duplicate_ids: int = 0
    negative_ids: int = 0
    adjacent_id_inversions: int = 0
    adjacent_time_inversions: int = 0
    equal_timestamp_pairs: int = 0
    chronology_counterexamples: int = 0
    samples: tuple[Inversion, ...] = ()

    @property
    def verdict(self) -> str:
        if not self.strict_json_valid:
            return "REFUSED: not valid JSON"
        if self.chronology_counterexamples:
            return (f"REFUTED: id order is not chronological "
                    f"({self.chronology_counterexamples} pairs)")
        if self.entries == 0:
            return "EMPTY: no entries to look at"
        return f"no inversion observed in {self.entries} entries"


def _collect_message_arrays(node, out: list) -> None:
    """Both shapes: a single-chat export is a chat object; a full export nests
    chats under `chats.list`. Anything with a `messages` array counts."""
    if isinstance(node, dict):
        messages = node.get("messages")
        if isinstance(messages, list):
            out.append(messages)
        for value in node.values():
            _collect_message_arrays(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_message_arrays(item, out)


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def scan_bytes(raw: bytes, source: str) -> ScanResult:
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = json.loads(raw.decode("utf-8"), cls=StrictJson)
    except (UnicodeDecodeError, ValueError) as failure:
        # position only: the message may quote the offending bytes
        text = str(failure)
        marker = text.find(":")
        return ScanResult(
            source=source, sha256=digest, size_bytes=len(raw),
            strict_json_valid=False,
            parse_error=(text[:marker] if marker > 0 else type(failure).__name__),
        )

    arrays: list = []
    _collect_message_arrays(document, arrays)

    counts = dict(entries=0, messages=0, service=0, other_types=0,
                  missing_date_unixtime=0, unparsable_ids=0, negative_ids=0,
                  adjacent_id_inversions=0, adjacent_time_inversions=0,
                  equal_timestamp_pairs=0, chronology_counterexamples=0)
    seen_ids: set[int] = set()
    duplicates = 0
    samples: list[Inversion] = []

    for messages in arrays:
        previous = None
        for position, entry in enumerate(messages):
            if not isinstance(entry, dict):
                continue
            counts["entries"] += 1
            kind = entry.get("type")
            if kind == "message":
                counts["messages"] += 1
            elif kind == "service":
                counts["service"] += 1
            else:
                counts["other_types"] += 1

            identifier = _as_int(entry.get("id"))
            stamp = _as_int(entry.get("date_unixtime"))
            if identifier is None:
                counts["unparsable_ids"] += 1
            else:
                if identifier < 0:
                    counts["negative_ids"] += 1
                if identifier in seen_ids:
                    duplicates += 1
                seen_ids.add(identifier)
            if stamp is None:
                counts["missing_date_unixtime"] += 1

            if identifier is not None and stamp is not None:
                if previous is not None:
                    prev_id, prev_time = previous
                    if identifier <= prev_id:
                        counts["adjacent_id_inversions"] += 1
                    if stamp < prev_time:
                        counts["adjacent_time_inversions"] += 1
                    if stamp == prev_time:
                        counts["equal_timestamp_pairs"] += 1
                    if identifier > prev_id and stamp < prev_time:
                        counts["chronology_counterexamples"] += 1
                        if len(samples) < MAX_COUNTEREXAMPLES:
                            samples.append(Inversion(position, prev_id, prev_time,
                                                     identifier, stamp))
                previous = (identifier, stamp)

    return ScanResult(source=source, sha256=digest, size_bytes=len(raw),
                      strict_json_valid=True, duplicate_ids=duplicates,
                      samples=tuple(samples), **counts)


def scan_file(path: str | Path, source: str | None = None) -> ScanResult:
    path = Path(path)
    return scan_bytes(path.read_bytes(), source or path.name)


def render(result: ScanResult) -> str:
    lines = [
        f"{result.source}  sha256={result.sha256[:16]}…  {result.size_bytes} bytes",
        f"  strict JSON: {'valid' if result.strict_json_valid else 'INVALID'}"
        + (f" ({result.parse_error})" if result.parse_error else ""),
    ]
    if result.strict_json_valid:
        lines += [
            f"  entries {result.entries} (message {result.messages} · "
            f"service {result.service} · other {result.other_types})",
            f"  ids: duplicates {result.duplicate_ids} · negative {result.negative_ids} "
            f"· unparsable {result.unparsable_ids}",
            f"  adjacency: id inversions {result.adjacent_id_inversions} · "
            f"time inversions {result.adjacent_time_inversions} · "
            f"equal timestamps {result.equal_timestamp_pairs}",
        ]
        for sample in result.samples[:5]:
            lines.append(f"    ! pos {sample.position}: id {sample.id_before}→"
                         f"{sample.id_after} but t {sample.time_before}→{sample.time_after}")
    lines.append(f"  → {result.verdict}")
    return "\n".join(lines)


def main(argv) -> int:  # pragma: no cover - reporting only
    if len(argv) < 3:
        print("usage: python -m tools.export_scan <label> <file.json> [...]")
        return 2
    label = argv[1]
    for path in argv[2:]:
        print(render(scan_file(path, f"{label}:{Path(path).name}")))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
