"""The acquisition ledger's rules, and the current Telegram verdict pinned.

The point of making the ledger data rather than prose: a status cannot drift,
`PARTIAL` cannot quietly mean "seems fine", and adding an extractor assumption
without naming the observable property behind it fails the build rather than
the pilot.
"""

import unittest

from extractor.adapters import telegram_desktop as tg
from extractor.adapters.acquisition import (
    Assumption,
    ClaimScope,
    Ledger,
    LedgerError,
    Property,
    Status,
)


def prop(**kw) -> Property:
    base = dict(
        key="x", question="?", claim="c", status=Status.QUALIFIED,
        claim_scope=ClaimScope.ARTIFACT, primary_evidence=("doc:1",),
        observed_limitations=(), downstream_consequence="d",
        adapter_behavior="a", fixture_needed="f",
    )
    return Property(**{**base, **kw})


class ClaimDisciplineTests(unittest.TestCase):

    def test_qualified_without_primary_evidence_is_refused(self):
        with self.assertRaises(LedgerError):
            prop(primary_evidence=())

    def test_a_claim_about_physical_chronology_needs_qualified_evidence(self):
        """The EXPORTED_POSITION lesson as a constructor check: "the source
        gives an order" must not grow into "we know what actually happened"."""
        with self.assertRaises(LedgerError):
            prop(status=Status.UNKNOWN, claim_scope=ClaimScope.PHYSICAL_CHRONOLOGY)
        prop(status=Status.QUALIFIED, claim_scope=ClaimScope.PHYSICAL_CHRONOLOGY)

    def test_unavailable_must_say_what_refuses(self):
        with self.assertRaises(LedgerError):
            prop(status=Status.UNAVAILABLE, adapter_behavior="")
        self.assertTrue(prop(status=Status.UNAVAILABLE).usable is False)


class PartialNeedsAContractTests(unittest.TestCase):

    def test_partial_without_a_consequence_decays_to_unknown(self):
        weak = prop(status=Status.PARTIAL, downstream_consequence="")
        self.assertIs(weak.status, Status.PARTIAL)          # what was written
        self.assertIs(weak.effective_status, Status.UNKNOWN)  # what it is worth
        self.assertTrue(weak.demoted)
        self.assertFalse(weak.usable)

    def test_partial_without_an_adapter_behaviour_decays_too(self):
        self.assertIs(prop(status=Status.PARTIAL, adapter_behavior="").effective_status,
                      Status.UNKNOWN)

    def test_partial_with_both_stands(self):
        strong = prop(status=Status.PARTIAL)
        self.assertIs(strong.effective_status, Status.PARTIAL)
        self.assertFalse(strong.demoted)
        self.assertTrue(strong.usable)


class LedgerStructureTests(unittest.TestCase):

    def ledger(self, properties, assumptions=()):
        return Ledger(target="t", acquisition_path="p",
                      properties=properties, assumptions=assumptions)

    def test_duplicate_property_keys_are_refused(self):
        with self.assertRaises(LedgerError):
            self.ledger((prop(key="a"), prop(key="a")))

    def test_an_assumption_must_name_a_property_that_exists(self):
        with self.assertRaises(LedgerError):
            self.ledger((prop(key="a"),),
                        (Assumption("guess", "somewhere", "b", "breaks"),))

    def test_unavailable_resolves_an_assumption_and_unknown_does_not(self):
        """"The source does not provide it, and here is what stops working" is
        an answer. "Nobody checked" is the state the TRACK exists to empty."""
        known_gap = self.ledger(
            (prop(key="a", status=Status.UNAVAILABLE),),
            (Assumption("x", "extractor", "a", "feature refuses"),))
        self.assertEqual(known_gap.unresolved_assumptions(), ())

        unchecked = self.ledger(
            (prop(key="a", status=Status.UNKNOWN),),
            (Assumption("x", "extractor", "a", "keeps assuming"),))
        self.assertEqual(len(unchecked.unresolved_assumptions()), 1)


class TelegramVerdictTests(unittest.TestCase):
    """The current state, pinned. These numbers are expected to move; they are
    expected to move because someone opened a real export, not by themselves."""

    def test_every_qualified_property_cites_a_primary_source(self):
        for entry in tg.LEDGER.by_status(Status.QUALIFIED):
            self.assertTrue(entry.primary_evidence, entry.key)

    def test_no_property_claims_physical_chronology(self):
        for entry in tg.LEDGER.properties:
            self.assertIsNot(entry.claim_scope, ClaimScope.PHYSICAL_CHRONOLOGY, entry.key)

    def test_no_partial_survived_without_a_contract(self):
        for entry in tg.LEDGER.properties:
            self.assertFalse(entry.demoted, f"{entry.key} was written PARTIAL without a contract")

    def test_the_unavailable_properties_are_the_expected_ones(self):
        keys = {p.key for p in tg.LEDGER.by_status(Status.UNAVAILABLE)}
        self.assertEqual(keys, {
            "coverage.window_provenance", "coverage.completeness",
            "coverage.requested_range_honored", "provenance.producer_version",
            "events.deleted", "format.strict_json",
        })

    def test_edited_is_not_an_edit_flag(self):
        """Regression against re-promotion. tdesktop#30647: a reaction creates
        `edited` on an unedited message and overwrites a real edit time, so the
        field means "touched after sending" and nothing narrower."""
        entry = tg.LEDGER.property("events.edited")
        self.assertIs(entry.status, Status.PARTIAL)
        self.assertIn("30647", " ".join(entry.primary_evidence))
        self.assertIn("не попадает во временную шкалу", entry.adapter_behavior)

    def test_the_requested_date_range_is_not_a_coverage_statement(self):
        entry = tg.LEDGER.property("coverage.requested_range_honored")
        self.assertIs(entry.status, Status.UNAVAILABLE)
        for issue in ("5854", "27183"):
            self.assertIn(issue, " ".join(entry.primary_evidence))

    def test_completeness_has_a_counterexample_not_merely_an_absence(self):
        """One verified counterexample beats a hundred pages of "usually fine":
        tdesktop#31328 truncates at exactly 10000 messages in JSON and HTML."""
        entry = tg.LEDGER.property("coverage.completeness")
        self.assertIs(entry.status, Status.UNAVAILABLE)
        self.assertIn("31328", " ".join(entry.primary_evidence))
        self.assertIn("10000", entry.adapter_behavior)

    def test_json_validity_is_refuted_not_merely_unproved(self):
        """Two independent classes of syntactically invalid output exist, so
        this is knowledge rather than a gap. The assumption stays eliminated by
        fail-closed parsing either way."""
        entry = tg.LEDGER.property("format.strict_json")
        self.assertIs(entry.status, Status.UNAVAILABLE)
        joined = " ".join(entry.primary_evidence)
        for issue in ("24961", "27571"):
            self.assertIn(issue, joined)
        assumption = next(a for a in tg.LEDGER.assumptions if a.key == "input_is_valid_json")
        self.assertTrue(assumption.eliminated_by_refusal)

    def test_a_live_client_ordering_bug_is_marked_as_not_evidence(self):
        entry = tg.LEDGER.property("ordering.tie_semantics")
        limits = " ".join(entry.observed_limitations)
        self.assertIn("30421", limits)
        self.assertIn("НЕ evidence", limits)

    def test_the_producer_version_is_required_and_absent(self):
        """Semantics change between versions, and the file does not say which
        version wrote it. So the source is not "Telegram Desktop JSON"."""
        entry = tg.LEDGER.property("provenance.producer_version")
        self.assertIs(entry.status, Status.UNAVAILABLE)
        self.assertIn("ВНЕ файла", entry.adapter_behavior)

    def test_the_window_cannot_be_taken_from_the_file(self):
        entry = tg.LEDGER.property("coverage.window_provenance")
        self.assertIs(entry.status, Status.UNAVAILABLE)
        self.assertIn("Отказ выводить period_start", entry.adapter_behavior)

    def test_deletion_is_unobservable_so_zero_must_not_read_as_none_happened(self):
        entry = tg.LEDGER.property("events.deleted")
        self.assertIs(entry.status, Status.UNAVAILABLE)
        self.assertIn("не сообщает об удалениях", entry.adapter_behavior)

    def test_only_one_assumption_is_still_open(self):
        """The history-fetch pass closed three. What is left is a single
        empirical question, not a research programme."""
        self.assertEqual({a.key for a in tg.LEDGER.unresolved_assumptions()},
                         {"ties_resolvable"})

    def test_the_export_order_is_ascending_id_not_chronology(self):
        """Traced through the source: the server returns descending id,
        ParseMessagesSlice walks the vector backwards, the cursor advances by
        the largest id. So position means id order — and calling that
        chronology is the claim that is NOT established."""
        entry = tg.LEDGER.property("ordering.exported_position")
        self.assertIs(entry.status, Status.QUALIFIED)
        self.assertIn("Возрастающий `id`", entry.claim)
        self.assertIs(entry.claim_scope, ClaimScope.ARTIFACT)

    def test_the_tie_question_reduced_to_one_root_question(self):
        entry = tg.LEDGER.property("ordering.tie_semantics")
        self.assertIs(entry.status, Status.UNKNOWN)
        self.assertIn("монотонен ли `id` по времени", entry.claim)

    def test_the_export_path_cannot_emit_duplicate_ids(self):
        entry = tg.LEDGER.property("ordering.multi_device")
        self.assertIs(entry.status, Status.QUALIFIED)
        self.assertIn("НОЛЬ раз", entry.adapter_behavior)

    def test_a_numeric_id_must_not_be_passed_as_a_bare_decimal_string(self):
        """`sort_key = (timestamp, message_id)` compares strings, where
        "10" < "9". With numeric Telegram ids that turns tie resolution into
        lexicographic noise."""
        entry = tg.LEDGER.property("identity.message_id")
        self.assertIn("«10» < «9»", entry.adapter_behavior)

    def test_the_range_bugs_have_a_mechanism_not_just_reports(self):
        entry = tg.LEDGER.property("coverage.requested_range_honored")
        joined = " ".join(entry.primary_evidence)
        for issue in ("5854", "27183", "30412", "31082"):
            self.assertIn(issue, joined)
        self.assertIn("Диапазон в запрос НЕ входит", joined)

    def test_every_open_question_names_the_observation_that_would_close_it(self):
        for entry in tg.LEDGER.properties:
            if entry.effective_status is Status.UNKNOWN:
                self.assertTrue(entry.fixture_needed, entry.key)

    def test_no_adapter_exists_yet(self):
        """The corpus rule, applied to targets: not one line of adapter until
        the properties it depends on are qualified or their refusal written."""
        self.assertFalse(hasattr(tg, "adapt_file"))
        self.assertFalse(hasattr(tg, "SEMANTICS"))


if __name__ == "__main__":
    unittest.main()
