"""The instrumentation certificate: one artifact, the whole path, section by section.

Not «не упало на 25 тысячах». A certificate states what went in, what each seam
did with it, what came out, and whether a second run agreed — and it carries the
artifact's hash and the generator's provenance, because a synthetic fixture whose
upstream regenerates keeps its filename and loses its meaning. That is the classic
way a test becomes decoration.

CLAIM SCOPE, narrow on purpose:

    this certificate demonstrates that the instrumentation path can process a
    large Telegram-SHAPED personal_chat artifact under known synthetic conditions

It demonstrates NOTHING about Telegram semantics. Those were qualified
separately, from the exporter's source and a verified defect corpus. Keeping the
two boxes apart is what stops «проверено на 25 000 Telegram messages» from
appearing in a month, about messages a generator invented.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from extractor.extract import EXPORT_KEYS

from .model import OutwardResult, ProducerProvenance, ProtocolWindow, Verdict
from .pipeline import run

#: What the artifact IS, so that a synthetic stress test is never read as evidence.
SYNTHETIC_FIXTURE = "synthetic_fixture"
FIELD_ARTIFACT = "field_artifact"


@dataclass(frozen=True, slots=True)
class Section:
    name: str
    facts: dict
    passed: bool
    note: str = ""


@dataclass(frozen=True, slots=True)
class Certificate:
    artifact_sha256: str
    artifact_bytes: int
    artifact_kind: str
    generator_provenance: str
    sections: tuple[Section, ...] = ()

    @property
    def verdict(self) -> str:
        return "PASS" if all(s.passed for s in self.sections) else "FAILED"

    def section(self, name: str) -> Section:
        return next(s for s in self.sections if s.name == name)

    def render(self) -> str:
        lines = [
            f"artifact  sha256={self.artifact_sha256[:16]}…  {self.artifact_bytes} bytes",
            f"          kind={self.artifact_kind}  provenance={self.generator_provenance}",
        ]
        for section in self.sections:
            mark = "ok " if section.passed else "!! "
            lines.append(f"  {mark}{section.name}")
            for key, value in section.facts.items():
                lines.append(f"       {key}: {value}")
            if section.note:
                lines.append(f"       note: {section.note}")
        lines.append(f"  => {self.verdict}")
        return "\n".join(lines)


#: Markers a caller may plant in the artifact before certifying.
def leaks(result: OutwardResult, markers: tuple[str, ...]) -> tuple[str, ...]:
    import dataclasses
    haystack = json.dumps(dataclasses.asdict(result), default=str)
    return tuple(m for m in markers if m in haystack)


def certify(
    raw: bytes,
    window: ProtocolWindow,
    producer: ProducerProvenance,
    *,
    artifact_kind: str,
    generator_provenance: str,
    markers: tuple[str, ...] = (),
) -> Certificate:
    digest = hashlib.sha256(raw).hexdigest()
    try:
        # The certificate reads the artifact only to report what it DECLARES
        # about itself, and must never raise on a bad one: a harness that
        # crashes instead of returning a verdict is the same defect class this
        # stage exists to find, one layer further out.
        document = json.loads(raw.decode("utf-8"))
        if not isinstance(document, dict):
            document = {}
    except (UnicodeDecodeError, ValueError):
        document = {}
    declared_type = document.get("type")
    declared_count = len(document.get("messages", []))
    if not isinstance(declared_count, int):
        declared_count = 0

    first = run(raw, window, producer)
    second = run(raw, window, producer)

    sections = [
        Section("INPUT", {
            "declared_chat_type": declared_type,
            "declared_message_count": declared_count,
        }, passed=declared_count > 0),
        Section("ACQUISITION", {
            "verdict": first.verdict.value,
            "source_type": first.source_type,
            "producer_version": producer.version,
            "window_from_protocol": f"[{window.start}, {window.end})",
            # never empty on any path that reaches here: the adapter always
            # reports `deletions_unobservable`, and an out-of-scope artifact
            # reports its type. A fallback would be unreachable code.
            "findings": " ".join(first.codes()),
        }, passed=first.verdict is not Verdict.REFUSED,
            note="окно подано снаружи и из содержимого не выводится"),
    ]

    aggregate = first.aggregate
    if aggregate is None:
        sections.append(Section("EXTRACTOR", {}, passed=False,
                                note="агрегата нет — дальше сертифицировать нечего"))
        return Certificate(digest, len(raw), artifact_kind, generator_provenance,
                           tuple(sections))

    horizons = {h["horizon_hours"]: h for h in aggregate["horizons"]}
    sections.append(Section("ADAPTER", {
        "own_messages": aggregate["own_message_count"],
        "own_total_chars": aggregate["own_total_chars"],
        "episode_returns": aggregate["own_episode_returns"],
        "cross_actor_tie_groups": aggregate["cross_actor_tie_groups"],
        "ambiguous_opportunities": aggregate["ambiguous_opportunities"],
        "deleted_dropped": aggregate["deleted_dropped"],
    }, passed=aggregate["own_message_count"] > 0,
        note="deleted_dropped=0 сопровождается findings-кодом deletions_unobservable"))

    sections.append(Section("EXTRACTOR", {
        f"H={hours}": (f"N={cell['opportunities_eligible']} "
                       f"replied={cell['replied_within']} "
                       f"burden={cell['sum_min_latency_seconds']:.0f}s")
        for hours, cell in sorted(horizons.items())
    }, passed=all(c["opportunities_eligible"] >= c["replied_within"]
                  for c in horizons.values()),
        note="все настроенные H присутствуют; replied <= eligible на каждом"))

    outside = set(aggregate) - set(EXPORT_KEYS)
    escaped = leaks(first, markers)
    sections.append(Section("EXPORT BOUNDARY", {
        "keys": len(aggregate),
        "outside_allowlist": " ".join(sorted(outside)) or "none",
        "markers_checked": len(markers),
        "markers_leaked": " ".join(escaped) or "none",
    }, passed=not outside and not escaped))

    payloads = json.dumps(first.aggregate, sort_keys=True), json.dumps(second.aggregate, sort_keys=True)
    sections.append(Section("DETERMINISM", {
        "runs": 2,
        "identical": payloads[0] == payloads[1],
    }, passed=payloads[0] == payloads[1]))

    return Certificate(digest, len(raw), artifact_kind, generator_provenance,
                       tuple(sections))
