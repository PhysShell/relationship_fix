"""The vertical slice: bytes in, allowed aggregate out.

    Telegram Desktop result.json
            ↓  import           strict parse or REFUSED
            ↓  qualification    is this our target at all
            ↓  adapter          ledger contracts applied
            ↓  FROZEN extractor treated as an external immovable component
            ↓  boundary         allowlist enforced, not hoped for
      outward result

Deliberately not an application and not a UX. It exists so that
instrumentation qualification has a real path to test rather than a diagram.

Two rules shape everything here. The extractor is never used as a validator —
it is not asked questions it would answer by raising, because a frozen engine
doubling as an input checker is how freezes get amended for "quick fixes". And
no failure may return an empty measurement: the type system refuses to build an
`OutwardResult` that is both a refusal and a number.
"""

from __future__ import annotations

from extractor.extract import EXPORT_KEYS, extract, production_export
from extractor.model import HORIZONS_HOURS, Mode, TiePolicy

from .model import Finding, Layer, OutwardResult, ProducerProvenance, ProtocolWindow, Verdict
from .telegram import Refusal, TARGET_CHAT_TYPE, adapt, coverage_findings, load, qualify


def run(
    raw: bytes,
    window: ProtocolWindow,
    producer: ProducerProvenance | None,
    horizons_hours: tuple[float, ...] = HORIZONS_HOURS,
) -> OutwardResult:
    """One acquisition attempt. Never raises for bad input — it returns a
    verdict, because a caller that has to catch exceptions eventually writes
    `except Exception: return []` and the study acquires a population of
    extremely quiet people."""

    def refused(finding: Finding, source_type=None) -> OutwardResult:
        return OutwardResult(verdict=Verdict.REFUSED, window=window, producer=producer,
                             source_type=source_type, findings=(finding,))

    if producer is None:
        return refused(Finding(Layer.IMPORT, "missing_producer_provenance",
                               "the export records no version; it must come from acquisition"))
    if not producer.consent_recorded:
        return refused(Finding(Layer.IMPORT, "consent_not_recorded"))

    try:
        document = load(raw)
        source_type = qualify(document)
    except Refusal as stop:
        return refused(stop.finding)

    if source_type != TARGET_CHAT_TYPE:
        return OutwardResult(
            verdict=Verdict.OUT_OF_SCOPE, window=window, producer=producer,
            source_type=source_type,
            findings=(Finding(Layer.QUALIFICATION, "not_the_target_chat_type", source_type),),
        )

    try:
        messages, findings = adapt(document, window)
    except Refusal as stop:
        return refused(stop.finding, source_type)

    # The frozen extractor is not an input validator, so everything it would
    # object to is decided here, before it is called.
    actors = {m.actor for m in messages}
    if len(actors) > 2:
        return OutwardResult(
            verdict=Verdict.OUT_OF_SCOPE, window=window, producer=producer,
            source_type=source_type,
            findings=findings + (Finding(Layer.QUALIFICATION, "not_a_dyad", str(len(actors))),),
        )
    if window.participant_id not in actors:
        # Otherwise extraction succeeds and reports a period in which this
        # person did nothing — a wrong answer wearing the clothes of a right one.
        return refused(Finding(Layer.QUALIFICATION, "participant_absent_from_export"),
                       source_type)
    if not any(window.start <= m.timestamp < window.end for m in messages):
        return refused(Finding(Layer.QUALIFICATION, "window_outside_export"), source_type)

    result = extract(
        messages, window.participant_id, window.period_id, window.start, window.end,
        mode=Mode.PRODUCTION, horizons_hours=horizons_hours, tie_policy=TiePolicy.STRICT,
    )

    payload = production_export(result.aggregate)
    extra = set(payload) - set(EXPORT_KEYS)
    if extra:
        # The allowlist is enforced on the way out, not assumed from the fact
        # that someone once wrote it down.
        return refused(Finding(Layer.BOUNDARY, "payload_outside_allowlist",
                               " ".join(sorted(extra))), source_type)

    findings = findings + coverage_findings(document, messages, window)
    incomplete = any(f.code in ("suspicious_round_count", "left_edge_unproven")
                     for f in findings)
    return OutwardResult(
        verdict=Verdict.INCOMPLETE if incomplete else Verdict.ACCEPTED,
        window=window, producer=producer, source_type=source_type,
        findings=findings, aggregate=payload,
    )
