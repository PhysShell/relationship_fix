"""TDLIB-0: the contract-only ledger, and what it must not claim yet."""

import unittest

from extractor.adapters import telegram_desktop as desktop
from extractor.adapters import telegram_tdlib as tdlib
from extractor.adapters.acquisition import ClaimScope, Status


class ContractOnlyTests(unittest.TestCase):
    """Steps 2-6 of the spike need a real Telegram account and have not run.
    A vendor's documentation sentence is evidence about intent, not a
    measurement, and the ledger must not pretend otherwise."""

    def test_no_BEHAVIOURAL_property_is_unavailable_without_a_measurement(self):
        """UNAVAILABLE means "demonstrably not provided". No runtime behaviour
        has been observed yet, so no behavioural property may carry it.

        Legal properties are the exception, and a principled one: there the
        primary source IS a document, so reading it is the measurement. That is
        why `legal.ai_use` is allowed to be UNAVAILABLE while nothing about
        pagination or ordering may be."""
        for entry in tdlib.LEDGER.by_status(Status.UNAVAILABLE):
            self.assertTrue(entry.key.startswith("legal."), entry.key)

    def test_no_property_claims_physical_chronology(self):
        for entry in tdlib.LEDGER.properties:
            self.assertIsNot(entry.claim_scope, ClaimScope.PHYSICAL_CHRONOLOGY, entry.key)

    def test_every_open_property_names_the_spike_step_that_closes_it(self):
        for entry in tdlib.LEDGER.properties:
            if entry.effective_status is Status.UNKNOWN:
                self.assertTrue(entry.fixture_needed, entry.key)

    def test_the_terms_are_read_and_still_do_not_permit_us(self):
        """Both documents are now quoted verbatim, and both scope questions
        remain open — with the text reading against us rather than merely being
        silent. That is a legal determination, not one a test can close."""
        for key in ("legal.api_terms_app_scope", "legal.content_access_purpose"):
            entry = tdlib.LEDGER.property(key)
            self.assertIs(entry.status, Status.UNKNOWN, key)
            self.assertTrue(entry.primary_evidence, key)
            self.assertIn("Блокирует", entry.fixture_needed, key)
        open_keys = {a.key for a in tdlib.LEDGER.unresolved_assumptions()}
        self.assertIn("app_is_in_scope_of_the_terms", open_keys)
        self.assertIn("measurement_purpose_is_licensed", open_keys)


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
        entry = tdlib.LEDGER.property("legal.library_license")
        self.assertIs(entry.status, Status.QUALIFIED)
        self.assertIn("Boost Software License", " ".join(entry.primary_evidence))


class AiFirewallTests(unittest.TestCase):
    """The one property that is settled and settled against us."""

    def test_telegram_derived_data_may_not_enter_an_ai_path(self):
        entry = tdlib.LEDGER.property("legal.ai_use")
        self.assertIs(entry.status, Status.UNAVAILABLE)
        self.assertIn("train, fine-tune", entry.claim)
        self.assertIn("§1.5", " ".join(entry.primary_evidence))
        self.assertIn("firewall", entry.downstream_consequence)

    def test_the_firewall_binds_the_spike_too(self):
        """A feasibility run must not become the first AI processing path by
        accident — that is how a prohibition gets crossed by nobody in
        particular."""
        entry = tdlib.LEDGER.property("legal.ai_use")
        self.assertIn("спайк", entry.downstream_consequence)

    def test_the_consent_exception_needs_BOTH_members_of_the_dyad(self):
        """"All relevant users" is not "our participant". It is the same
        second-person consent problem prereg §3.1 already had open."""
        limits = " ".join(tdlib.LEDGER.property("legal.ai_use").observed_limitations)
        self.assertIn("all relevant users", limits)
        self.assertIn("ОБОИХ", limits)

    def test_the_prohibition_resolves_the_assumption_rather_than_leaving_a_hole(self):
        """UNAVAILABLE with a written refusal is an answer: the AI layer does
        not eat Telegram data, and that is now a design constraint."""
        assumption = next(a for a in tdlib.LEDGER.assumptions
                          if a.key == "ai_layer_may_use_telegram_data")
        self.assertNotIn(assumption, tdlib.LEDGER.unresolved_assumptions())


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
