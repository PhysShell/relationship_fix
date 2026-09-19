"""Гейт приёма: непроверенное и проваленное здесь равны.

Соблазн, ради которого он и написан: файл наконец приехал, его хочется
посмотреть, а проверки «сделаем потом». Гарантия отличается от политики тем,
что её нельзя забыть исполнить.
"""

import unittest

from acquisition.admission import (
    MESSAGING_MATTERS, Admission, AdmissionCheck, AdmissionError, CheckVerdict,
    require_admission,
)


def check(key="k", *, blocking=True, verdict=CheckVerdict.UNKNOWN, finding=""):
    return AdmissionCheck(key, "question?", "something breaks", blocking,
                          verdict, finding)


class CheckTests(unittest.TestCase):

    def test_a_verdict_without_an_observation_is_refused(self):
        """Вердикт без записанного наблюдения — это мнение."""
        for verdict in (CheckVerdict.PASSED, CheckVerdict.FAILED):
            with self.assertRaises(AdmissionError):
                check(verdict=verdict)

    def test_an_observation_without_a_verdict_is_refused(self):
        with self.assertRaises(AdmissionError):
            check(finding="saw something")

    def test_a_check_must_name_what_breaks_without_it(self):
        """Проверка без названной цены отказа — ритуал, а не проверка."""
        with self.assertRaises(AdmissionError):
            AdmissionCheck("k", "question?", "", True)

    def test_only_passed_clears(self):
        self.assertTrue(check(verdict=CheckVerdict.PASSED, finding="ok").clears)
        self.assertFalse(check(verdict=CheckVerdict.FAILED, finding="no").clears)
        self.assertFalse(check().clears)

    def test_resolving_returns_a_new_check_and_keeps_the_question(self):
        original = check()
        resolved = original.resolved(CheckVerdict.PASSED, "observed X")
        self.assertIs(original.verdict, CheckVerdict.UNKNOWN)
        self.assertIs(resolved.verdict, CheckVerdict.PASSED)
        self.assertEqual(resolved.question, original.question)
        self.assertEqual(resolved.at_stake, original.at_stake)


class AdmissionTests(unittest.TestCase):

    def test_unknown_is_not_a_pass(self):
        """Центральное правило. Непроверенная проверка не отличается от
        проваленной, и отсутствие не становится свидетельством."""
        admission = Admission("c", (check("a"),))
        self.assertFalse(admission.admitted)
        self.assertEqual(len(admission.blocking_open), 1)

    def test_all_blocking_checks_must_pass(self):
        admission = Admission("c", (
            check("a", verdict=CheckVerdict.PASSED, finding="ok"),
            check("b")))
        self.assertFalse(admission.admitted)
        admission = admission.resolve("b", CheckVerdict.PASSED, "ok too")
        self.assertTrue(admission.admitted)

    def test_a_failed_blocking_check_keeps_the_corpus_out(self):
        admission = Admission("c", (check("a"),)).resolve(
            "a", CheckVerdict.FAILED, "licence forbids it")
        self.assertFalse(admission.admitted)

    def test_a_non_blocking_check_does_not_hold_the_gate(self):
        admission = Admission("c", (
            check("a", verdict=CheckVerdict.PASSED, finding="ok"),
            check("b", blocking=False)))
        self.assertTrue(admission.admitted)

    def test_duplicate_keys_are_refused(self):
        with self.assertRaises(AdmissionError):
            Admission("c", (check("a"), check("a")))

    def test_resolving_does_not_mutate_the_earlier_state(self):
        before = Admission("c", (check("a"),))
        after = before.resolve("a", CheckVerdict.PASSED, "ok")
        self.assertFalse(before.admitted)
        self.assertTrue(after.admitted)

    def test_an_unknown_key_is_an_error_rather_than_a_silent_no_op(self):
        with self.assertRaises(KeyError):
            Admission("c", (check("a"),)).check("b")


class GuardTests(unittest.TestCase):

    def test_reading_an_unadmitted_corpus_raises(self):
        with self.assertRaises(AdmissionError) as caught:
            require_admission(Admission("c", (check("a"),)))
        self.assertIn("a", str(caught.exception))

    def test_an_admitted_corpus_passes_silently(self):
        admission = Admission("c", (check("a", verdict=CheckVerdict.PASSED,
                                           finding="ok"),))
        self.assertIsNone(require_admission(admission))


class MessagingMattersTests(unittest.TestCase):
    """Тот самый корпус, ради которого гейт и написан."""

    def test_nothing_is_admitted_before_the_file_exists(self):
        self.assertFalse(MESSAGING_MATTERS.admitted)
        for entry in MESSAGING_MATTERS.checks:
            self.assertIs(entry.verdict, CheckVerdict.UNKNOWN, entry.key)

    def test_the_questions_the_reconnaissance_got_wrong_are_all_here(self):
        """S4 prereg §0.3: «133 чата» против N = 142 в самой статье. Эти
        величины входят как ИЗМЕРЯЕМЫЕ, а не как основание."""
        keys = {entry.key for entry in MESSAGING_MATTERS.checks}
        for required in ("scale.counts", "schema.fields", "time.resolution",
                         "time.semantics", "coverage.semantics"):
            self.assertIn(required, keys)

    def test_the_text_promise_from_the_letter_is_a_blocking_check(self):
        """В письме обещано отрезать текст на входе. Обещание исполняется
        здесь или не исполняется вовсе."""
        for key in ("schema.text_present", "schema.text_discarded"):
            self.assertTrue(MESSAGING_MATTERS.check(key).blocking, key)

    def test_licence_and_redistribution_both_gate(self):
        """MaiChat уже не вендорится из-за share-alike."""
        self.assertTrue(MESSAGING_MATTERS.check("licence.terms").blocking)
        self.assertTrue(MESSAGING_MATTERS.check("licence.redistribution").blocking)

    def test_every_check_names_what_is_at_stake(self):
        for entry in MESSAGING_MATTERS.checks:
            self.assertTrue(entry.at_stake, entry.key)

    def test_the_gate_refuses_the_corpus_today(self):
        with self.assertRaises(AdmissionError):
            require_admission(MESSAGING_MATTERS)

    def test_resolving_everything_blocking_would_admit_it(self):
        """Гейт должен уметь открыться — иначе это не гейт, а стена."""
        admission = MESSAGING_MATTERS
        for entry in MESSAGING_MATTERS.checks:
            if entry.blocking:
                admission = admission.resolve(entry.key, CheckVerdict.PASSED,
                                              "verified on the delivered file")
        self.assertTrue(admission.admitted)
        self.assertIsNone(require_admission(admission))


if __name__ == "__main__":
    unittest.main()
