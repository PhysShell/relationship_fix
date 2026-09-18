"""The certificate and the boundary injections, on artifacts a test can build.

The 25 000-message run happens through `tools/certify.py` against a path: the
fixture is not vendored, the same rule every corpus in this project follows.
What is pinned here is the machinery, so that the big run means something.
"""

import json
import unittest

from acquisition.certificate import FIELD_ARTIFACT, SYNTHETIC_FIXTURE, certify
from acquisition.injection import INJECTIONS, PLANTED
from acquisition.model import ProducerProvenance, ProtocolWindow, Verdict
from acquisition.pipeline import run

HOUR = 3600.0
A, B = "user111", "user222"
WINDOW = ProtocolWindow(participant_id=A, period_id="w1", start=0.0, end=30 * 24 * HOUR)
PRODUCER = ProducerProvenance("Telegram Desktop", "6.7.8", "linux", True)
MARKER = "CERT_MARKER_44921"


def artifact(pairs=40) -> bytes:
    messages = []
    for i in range(pairs):
        base = 2.0 + i * 3.0
        messages.append({"id": 100 + 2 * i, "type": "message",
                         "date": "2026-03-19T07:28:54",
                         "date_unixtime": str(int(base * HOUR)),
                         "from": MARKER, "from_id": B, "text": MARKER})
        messages.append({"id": 101 + 2 * i, "type": "message",
                         "date": "2026-03-19T08:28:54",
                         "date_unixtime": str(int((base + 1.0) * HOUR)),
                         "from": MARKER, "from_id": A, "text": MARKER})
    return json.dumps({"name": MARKER, "type": "personal_chat", "id": 7,
                       "messages": messages}).encode("utf-8")


class CertificateTests(unittest.TestCase):

    def setUp(self):
        self.cert = certify(artifact(), WINDOW, PRODUCER,
                            artifact_kind=SYNTHETIC_FIXTURE,
                            generator_provenance="test", markers=(MARKER,))

    def test_it_passes_and_reports_every_section(self):
        self.assertEqual(self.cert.verdict, "PASS")
        self.assertEqual([s.name for s in self.cert.sections],
                         ["INPUT", "ACQUISITION", "ADAPTER", "EXTRACTOR",
                          "EXPORT BOUNDARY", "DETERMINISM"])

    def test_the_artifact_is_identified_by_hash_and_kind_not_by_filename(self):
        """A synthetic fixture whose upstream regenerates keeps its name and
        loses its meaning. The hash and the generator provenance are what make
        the certificate re-checkable."""
        self.assertEqual(len(self.cert.artifact_sha256), 64)
        self.assertEqual(self.cert.artifact_kind, SYNTHETIC_FIXTURE)
        self.assertNotEqual(SYNTHETIC_FIXTURE, FIELD_ARTIFACT)
        self.assertTrue(self.cert.generator_provenance)

    def test_planted_markers_are_hunted_and_absent(self):
        boundary = self.cert.section("EXPORT BOUNDARY")
        self.assertEqual(boundary.facts["markers_leaked"], "none")
        self.assertEqual(boundary.facts["outside_allowlist"], "none")
        self.assertTrue(boundary.passed)

    def test_determinism_is_measured_rather_than_assumed(self):
        self.assertTrue(self.cert.section("DETERMINISM").facts["identical"])

    def test_the_leak_hunter_can_actually_find_something(self):
        """«Markers leaked: none» означает что-то, только если охотник вообще
        умеет ловить. Маркер, который в результате ЕСТЬ по праву, обязан быть
        найден — иначе privacy-секция проверяет собственную слепоту."""
        cert = certify(artifact(), WINDOW, PRODUCER, artifact_kind=SYNTHETIC_FIXTURE,
                       generator_provenance="test", markers=(A,))
        boundary = cert.section("EXPORT BOUNDARY")
        self.assertEqual(boundary.facts["markers_leaked"], A)
        self.assertFalse(boundary.passed)
        self.assertEqual(cert.verdict, "FAILED")

    def test_an_artifact_declaring_no_messages_fails_the_input_section(self):
        empty = json.dumps({"type": "personal_chat", "messages": []}).encode()
        cert = certify(empty, WINDOW, PRODUCER, artifact_kind=SYNTHETIC_FIXTURE,
                       generator_provenance="test")
        self.assertFalse(cert.section("INPUT").passed)
        self.assertEqual(cert.section("INPUT").facts["declared_message_count"], 0)

    def test_an_out_of_scope_artifact_fails_at_the_extractor_section(self):
        """Acquisition succeeded — the file is fine, it is simply not a dyad —
        so this section is the one that has to say there is nothing to certify."""
        other = json.loads(artifact())
        other["type"] = "private_group"
        cert = certify(json.dumps(other).encode(), WINDOW, PRODUCER,
                       artifact_kind=SYNTHETIC_FIXTURE, generator_provenance="test")
        self.assertTrue(cert.section("ACQUISITION").passed)
        self.assertFalse(cert.section("EXTRACTOR").passed)
        self.assertEqual(cert.verdict, "FAILED")

    def test_a_participant_silent_inside_the_window_fails_the_adapter_section(self):
        """Their messages exist in the file and none fall inside the period.
        Opportunities can still be counted; a certificate that called that a
        healthy adapter would be certifying a person's absence."""
        narrow = ProtocolWindow(participant_id=A, period_id="w9",
                                start=0.0, end=3 * HOUR)
        messages = [
            {"id": 1, "type": "message", "date_unixtime": str(int(1 * HOUR)),
             "from_id": B, "text": "x"},
            {"id": 2, "type": "message", "date_unixtime": str(int(10 * HOUR)),
             "from_id": A, "text": "x"},
        ]
        raw = json.dumps({"type": "personal_chat", "messages": messages}).encode()
        cert = certify(raw, narrow, PRODUCER, artifact_kind=SYNTHETIC_FIXTURE,
                       generator_provenance="test")
        self.assertEqual(cert.section("ADAPTER").facts["own_messages"], 0)
        self.assertFalse(cert.section("ADAPTER").passed)

    def test_certificate_types_are_frozen_and_slotted(self):
        """A certificate that can be edited after the fact certifies nothing."""
        import dataclasses as dc
        for obj, field in ((self.cert.sections[0], "name"),
                           (self.cert, "artifact_sha256")):
            self.assertFalse(hasattr(obj, "__dict__"), type(obj).__name__)
            with self.assertRaises(dc.FrozenInstanceError):
                setattr(obj, field, "edited")
            with self.assertRaises((AttributeError, TypeError)):
                setattr(obj, "smuggled", "x")

    def test_findings_always_reach_the_acquisition_section(self):
        """Every path that gets this far carries at least one finding, so the
        section reports them rather than a placeholder."""
        self.assertIn("deletions_unobservable",
                      self.cert.section("ACQUISITION").facts["findings"])

    def test_a_refused_artifact_produces_a_failed_certificate_not_a_crash(self):
        cert = certify(b"{", WINDOW, PRODUCER, artifact_kind=SYNTHETIC_FIXTURE,
                       generator_provenance="test")
        self.assertEqual(cert.verdict, "FAILED")
        self.assertIn("агрегата нет", cert.section("EXTRACTOR").note)


class InjectionTests(unittest.TestCase):
    """Corruptions of one plausible artifact, each with the outcome it must
    produce. A suite where every answer is "refused" would pass on a pipeline
    that refuses everything, so two of the eight must succeed."""

    def setUp(self):
        self.raw = artifact()
        self.baseline = run(self.raw, WINDOW, PRODUCER)
        self.assertTrue(self.baseline.verdict.carries_measurements)

    def result_for(self, injection):
        corrupted = self.raw if injection.corrupt is None else injection.corrupt(self.raw)
        return run(corrupted, WINDOW,
                   None if injection.corrupt is None else PRODUCER)

    def test_every_injection_produces_its_expected_outcome(self):
        for injection in INJECTIONS:
            with self.subTest(injection.key):
                result = self.result_for(injection)
                if injection.expected_verdict is not None:
                    self.assertIs(result.verdict, injection.expected_verdict)
                    if injection.expected_code:
                        self.assertIn(injection.expected_code, result.codes())
                else:
                    self.assertTrue(result.verdict.carries_measurements)

    def test_a_rejected_injection_never_carries_numbers(self):
        for injection in INJECTIONS:
            result = self.result_for(injection)
            if not result.verdict.carries_measurements:
                self.assertIsNone(result.aggregate, injection.key)

    def test_the_tie_injection_raises_the_counter_rather_than_vanishing(self):
        injection = next(i for i in INJECTIONS if i.raises_counter)
        before = self.baseline.aggregate["cross_actor_tie_groups"]
        after = self.result_for(injection).aggregate["cross_actor_tie_groups"]
        self.assertGreater(after, before)

    def test_an_unknown_schema_key_carrying_content_does_not_escape(self):
        """Tomorrow's Telegram version adds a field nobody has read yet."""
        import dataclasses
        injection = next(i for i in INJECTIONS if i.planted_secret)
        result = self.result_for(injection)
        self.assertTrue(result.verdict.carries_measurements)
        self.assertNotIn(PLANTED, json.dumps(dataclasses.asdict(result), default=str))

    def test_two_of_the_eight_must_succeed_by_design(self):
        succeed = [i for i in INJECTIONS if i.expected_verdict is None]
        self.assertEqual(len(succeed), 2)
        self.assertEqual({i.key for i in succeed},
                         {"cross_actor_same_second_tie", "extra_sensitive_fields"})


if __name__ == "__main__":
    unittest.main()
