"""Гейт приёма: непроверенное и проваленное здесь равны.

Соблазн, ради которого он и написан: файл наконец приехал, его хочется
посмотреть, а проверки «сделаем потом». Гарантия отличается от политики тем,
что её нельзя забыть исполнить.
"""

import unittest

from acquisition.admission import (
    CORPORA, MESSAGING_MATTERS, Access, Admission, AdmissionCheck, AdmissionError,
    CheckVerdict, corpus_admission, require_admission,
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


class CorpusAdmissionTests(unittest.TestCase):
    """Гейты корпусов, ради которых всё и написано."""

    def test_no_corpus_is_admitted_before_its_file_is_inspected(self):
        for name, (_, _, admission) in CORPORA.items():
            self.assertFalse(admission.admitted, name)
            for entry in admission.checks:
                self.assertIs(entry.verdict, CheckVerdict.UNKNOWN, f"{name}.{entry.key}")

    def test_access_and_licence_are_separate_fields(self):
        """«Скачивается» не значит «разрешено» — самая дорогая из наших привычных
        ошибок. CollegeMsg публичен и лицензии не имеет вовсе."""
        access, licence, _ = CORPORA["CollegeMsg"]
        self.assertIs(access, Access.PUBLIC)
        self.assertIn("NEEDS_VERIFICATION", licence)
        access, licence, _ = CORPORA["SMS-A"]
        self.assertIs(access, Access.PUBLIC)
        self.assertIn("NEEDS_VERIFICATION", licence)

    def test_only_the_verified_licence_is_stated_as_known(self):
        _, licence, _ = CORPORA["CNS"]
        self.assertIn("MIT", licence)
        self.assertNotIn("NEEDS_VERIFICATION", licence)

    def test_the_deferred_corpus_is_kept_rather_than_deleted(self):
        access, _, admission = CORPORA["MessagingMatters"]
        self.assertIs(access, Access.RESTRICTED)
        self.assertIs(admission, MESSAGING_MATTERS)

    def test_every_corpus_gets_the_same_questions(self):
        """Вопрос «что на самом деле в файле» не зависит от того, насколько
        симпатична аннотация."""
        key_sets = {name: tuple(c.key for c in admission.checks)
                    for name, (_, _, admission) in CORPORA.items()}
        self.assertEqual(len(set(key_sets.values())), 1, key_sets)

    def test_direction_is_a_blocking_check(self):
        """Перепутанные sender/receiver не роняют ничего — они молча меняют
        каждую возможность местами."""
        self.assertTrue(corpus_admission("x").check("direction.sender_receiver").blocking)

    def test_the_text_promise_blocks(self):
        admission = corpus_admission("x")
        for key in ("schema.text_present", "schema.text_discarded"):
            self.assertTrue(admission.check(key).blocking, key)

    def test_every_check_names_what_is_at_stake(self):
        for entry in corpus_admission("x").checks:
            self.assertTrue(entry.at_stake, entry.key)

    def test_the_gate_refuses_every_corpus_today(self):
        for name, (_, _, admission) in CORPORA.items():
            with self.assertRaises(AdmissionError, msg=name):
                require_admission(admission)

    def test_a_gate_can_be_opened_or_it_is_a_wall(self):
        admission = corpus_admission("x")
        for entry in tuple(admission.checks):
            if entry.blocking:
                admission = admission.resolve(entry.key, CheckVerdict.PASSED,
                                              "verified on the delivered file")
        self.assertTrue(admission.admitted)
        self.assertIsNone(require_admission(admission))


if __name__ == "__main__":
    unittest.main()


class CopenhagenAdmissionTests(unittest.TestCase):
    """Осмотр CNS: гейт остановил корпус, и это его работа, а не сбой."""

    @classmethod
    def setUpClass(cls):
        from acquisition import cns_admission
        cls.module = cns_admission
        cls.admission = cns_admission.admission()

    def test_the_corpus_is_not_admitted(self):
        self.assertFalse(self.admission.admitted)

    def test_exactly_one_blocking_check_failed_and_it_is_coverage(self):
        open_keys = [c.key for c in self.admission.blocking_open]
        self.assertEqual(open_keys, ["coverage.semantics"])
        self.assertIs(self.admission.check("coverage.semantics").verdict,
                      CheckVerdict.FAILED)

    def test_every_check_carries_an_observation(self):
        """Вердикт без записанного наблюдения — это мнение."""
        for entry in self.admission.checks:
            self.assertIsNot(entry.verdict, CheckVerdict.UNKNOWN, entry.key)
            self.assertTrue(entry.finding, entry.key)

    def test_the_count_discrepancy_is_recorded_rather_than_smoothed(self):
        """24 333 совпало точно, 568 против «577 total users» — нет."""
        finding = self.admission.check("scale.counts").finding
        self.assertIn("24 333", finding)
        self.assertIn("568", finding)
        self.assertIn("577", finding)

    def test_the_licence_is_recorded_with_its_evidence(self):
        finding = self.admission.check("licence.terms").finding
        self.assertIn("MIT", finding)
        self.assertIn(self.module.FIGSHARE_DOI, finding)

    def test_the_unresolved_clock_side_is_named_as_a_limit_not_hidden(self):
        finding = self.admission.check("time.semantics").finding
        self.assertIn("НЕИЗВЕСТНЫМ", finding)
        self.assertIn("Q3", finding)

    def test_the_inspected_file_is_pinned_by_hash(self):
        self.assertEqual(len(self.module.SMS_CSV_SHA256), 64)
        self.assertEqual(self.module.SMS_CSV_BYTES, 368_659)

    def test_what_would_admit_it_is_named_in_advance(self):
        """Иначе «разблокируем как-нибудь» становится планом."""
        self.assertIn("bt_symmetric", self.module.WHAT_WOULD_ADMIT)

    def test_reading_the_corpus_is_refused_today(self):
        with self.assertRaises(AdmissionError):
            require_admission(self.admission)
