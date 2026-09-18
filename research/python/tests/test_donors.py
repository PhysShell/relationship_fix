"""The donor ledger's rules. Licences decide ADOPT versus ORACLE, so they are
read from the repository rather than taken from a badge."""

import unittest

from acquisition.donors import DONORS, Disposition, Donor, LicenseError, adoptable, foreign_shape_donors


def donor(**kw) -> Donor:
    base = dict(
        name="x", url="https://example.invalid", license_spdx="MIT",
        license_evidence="LICENSE read", disposition=(Disposition.ADOPT,),
        input_formats="f", provenance_lost="p", semantics_assumed="s",
        emits_foreign_shape=False, note="n",
    )
    return Donor(**{**base, **kw})


class LicenceDisciplineTests(unittest.TestCase):

    def test_copyleft_cannot_be_adopted_or_wrapped(self):
        for disposition in (Disposition.ADOPT, Disposition.WRAP):
            with self.assertRaises(LicenseError):
                donor(license_spdx="GPL-3.0", disposition=(disposition,))

    def test_a_missing_licence_is_all_rights_reserved_not_probably_fine(self):
        with self.assertRaises(LicenseError):
            donor(license_spdx="NONE", disposition=(Disposition.ADOPT,))

    def test_copyleft_and_unlicensed_work_survive_as_oracle_or_ux(self):
        """Running a separate process over a fixture is not a derivative work,
        and an interface idea is not copyrightable."""
        donor(license_spdx="GPL-3.0", disposition=(Disposition.ORACLE,))
        donor(license_spdx="NONE", disposition=(Disposition.UX,),
              provenance_lost="not applicable", semantics_assumed="competing metric only")

    def test_a_licence_claim_needs_evidence(self):
        with self.assertRaises(LicenseError):
            donor(license_evidence="")

    def test_a_donor_must_answer_the_two_questions_that_matter(self):
        """What does it lose, and what does it assert for us. A donor review
        that skips those is a shopping list."""
        with self.assertRaises(LicenseError):
            donor(provenance_lost="")
        with self.assertRaises(LicenseError):
            donor(semantics_assumed="")


class VerdictTests(unittest.TestCase):

    def test_only_permissively_licensed_donors_enter_our_code(self):
        for candidate in adoptable():
            self.assertEqual(candidate.license_spdx, "MIT", candidate.name)

    def test_the_unlicensed_donor_is_ux_only(self):
        radhium = next(d for d in DONORS if d.name.startswith("Radhium"))
        self.assertEqual(radhium.license_spdx, "NONE")
        self.assertEqual(radhium.disposition, (Disposition.UX,))

    def test_the_copyleft_donor_is_oracle_only(self):
        whatstk = next(d for d in DONORS if "whatstk" in d.name)
        self.assertEqual(whatstk.license_spdx, "GPL-3.0")
        self.assertEqual(whatstk.disposition, (Disposition.ORACLE,))

    def test_a_telegram_shaped_output_is_not_a_telegram_source(self):
        """The trap somebody will spring in six months: identical JSON keys,
        therefore one adapter. Shape is not provenance."""
        foreign = foreign_shape_donors()
        self.assertEqual([d.name for d in foreign], ["KnugiHK/WhatsApp-Chat-Exporter"])
        self.assertIn("WHATSAPP_DB_VIA_WHATSAPP_CHAT_EXPORTER",
                      foreign_shape_donors.__doc__)

    def test_the_synthetic_fixture_donor_is_not_evidence_about_telegram(self):
        tel = next(d for d in DONORS if "TelAnalysis" in d.name)
        self.assertIn(Disposition.FIXTURE, tel.disposition)
        self.assertIn("НЕ evidence", tel.semantics_assumed)

    def test_every_donor_names_what_it_silently_asserts(self):
        for candidate in DONORS:
            self.assertTrue(candidate.semantics_assumed, candidate.name)
            self.assertTrue(candidate.license_evidence.startswith(("LICENSE", "LICENSE отсутствует")),
                            candidate.name)


if __name__ == "__main__":
    unittest.main()
