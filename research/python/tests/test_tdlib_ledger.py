"""TDLIB-0: the contract-only ledger, and what it must not claim yet."""

import unittest

from extractor.adapters import telegram_desktop as desktop
from extractor.adapters import telegram_tdlib as tdlib
from extractor.adapters.acquisition import ClaimScope, Status


class ContractOnlyTests(unittest.TestCase):
    """Steps 2-6 of the spike need a real Telegram account and have not run.
    A vendor's documentation sentence is evidence about intent, not a
    measurement, and the ledger must not pretend otherwise."""

    def test_nothing_is_marked_unavailable_because_nothing_was_measured(self):
        """UNAVAILABLE means "the source demonstrably does not provide it".
        Nothing here has been observed, so nothing may carry that verdict."""
        self.assertEqual(tdlib.LEDGER.by_status(Status.UNAVAILABLE), ())

    def test_no_property_claims_physical_chronology(self):
        for entry in tdlib.LEDGER.properties:
            self.assertIsNot(entry.claim_scope, ClaimScope.PHYSICAL_CHRONOLOGY, entry.key)

    def test_every_open_property_names_the_spike_step_that_closes_it(self):
        for entry in tdlib.LEDGER.properties:
            if entry.effective_status is Status.UNKNOWN:
                self.assertTrue(entry.fixture_needed, entry.key)

    def test_the_terms_of_service_are_not_assumed_to_permit_us(self):
        """api_id is free of charge; that is not the same as "our mode of use
        is allowed". Reading the ToS is step 1 and it is not done."""
        entry = tdlib.LEDGER.property("deployment.api_terms")
        self.assertIs(entry.status, Status.UNKNOWN)
        assumption = next(a for a in tdlib.LEDGER.assumptions if a.key == "use_is_permitted")
        self.assertIn(assumption, tdlib.LEDGER.unresolved_assumptions())


class WhyThisSourceTests(unittest.TestCase):

    def test_the_ordering_contract_is_stronger_than_the_export_path_had(self):
        """messages.getHistory states the ordering outright; the export path had
        only "typically ... descending object ID values"."""
        entry = tdlib.LEDGER.property("ordering.contract")
        self.assertIs(entry.status, Status.QUALIFIED)
        self.assertIn("ordered by date (descending)", " ".join(entry.primary_evidence))

    def test_two_vendor_documents_describe_the_order_differently(self):
        """MTProto says by date; TDLib says by decreasing message_id and calls
        that chronological with an "i.e.". They coincide only if id is monotone
        in time — the very thing we refused to assume."""
        entry = tdlib.LEDGER.property("ordering.tdlib_conflates_id_and_time")
        self.assertIs(entry.status, Status.UNKNOWN)
        limits = " ".join(entry.observed_limitations)
        self.assertIn("РАЗНО", limits)

    def test_the_tie_assumption_stays_eliminated_by_construction(self):
        """The new source does not reintroduce it. TiePolicy.STRICT holds
        whatever the vendor writes in a parenthesis, so the frozen core is not
        touched under any answer."""
        assumption = next(a for a in tdlib.LEDGER.assumptions
                          if a.key == "order_is_chronological")
        self.assertTrue(assumption.eliminated_by)
        self.assertNotIn(assumption, tdlib.LEDGER.unresolved_assumptions())

    def test_the_producer_version_problem_disappears_by_construction(self):
        """The worst line of the export ledger — producer_version UNAVAILABLE —
        is gone because Telegram Desktop leaves the acquisition path entirely."""
        self.assertIs(desktop.LEDGER.property("provenance.producer_version").status,
                      Status.UNAVAILABLE)
        entry = tdlib.LEDGER.property("provenance.producer_under_our_control")
        self.assertIs(entry.status, Status.QUALIFIED)
        self.assertIn("не задаётся человеку", entry.adapter_behavior.replace(
            "к человеку больше не задаётся", "не задаётся человеку"))

    def test_the_library_licence_permits_shipping_unlike_the_gpl_donors(self):
        entry = tdlib.LEDGER.property("deployment.library_license")
        self.assertIs(entry.status, Status.QUALIFIED)
        self.assertIn("Boost Software License", " ".join(entry.primary_evidence))


class CTargetLinkageTests(unittest.TestCase):
    """The whole reason for a second source ledger."""

    def test_zero_routine_actions_depends_on_authorisation_being_one_off(self):
        """If authorisation recurs every period, C_target is unreachable and
        the move to this source loses its entire point."""
        assumption = next(a for a in tdlib.LEDGER.assumptions
                          if a.key == "zero_routine_user_actions")
        self.assertEqual(assumption.supported_by, "deployment.authorization_burden")
        self.assertIn(assumption, tdlib.LEDGER.unresolved_assumptions())

    def test_a_short_page_must_not_be_read_as_the_end_of_history(self):
        entry = tdlib.LEDGER.property("coverage.page_limit")
        self.assertIn("исчерпанию курсора", entry.adapter_behavior)

    def test_local_only_mode_is_refused_rather_than_trusted(self):
        entry = tdlib.LEDGER.property("coverage.only_local_truncation")
        self.assertIn("only_local = false", entry.adapter_behavior)

    def test_no_adapter_exists_yet(self):
        self.assertFalse(hasattr(tdlib, "adapt"))
        self.assertFalse(hasattr(tdlib, "SEMANTICS"))


if __name__ == "__main__":
    unittest.main()
