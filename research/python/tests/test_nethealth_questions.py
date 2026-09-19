"""Допуск по вопросам выводится из проверок, а не объявляется руками.

Если завтра `coverage.capture_window` закроется, Q1 поднимется сам. Пока он
закрыт — не поднимется никаким энтузиазмом.
"""

import unittest

from acquisition.admission import (
    Admissibility, AdmissionError, Question, admissibility,
)
from acquisition import incidence_corpus_spec as spec
from acquisition.nethealth_admission import admission
from acquisition.nethealth_questions import QUESTIONS, verdicts


class QuestionTypeTests(unittest.TestCase):

    def test_a_softened_question_must_name_its_damage(self):
        """«Ухудшается, но не отменяется» без названного ущерба — это надежда."""
        with self.assertRaises(AdmissionError):
            Question("q", "asks?", requires=(), degraded_by=("x",))

    def test_a_hard_failure_refuses_regardless_of_the_rest(self):
        state = admission()
        q = Question("q", "asks?", requires=("coverage.capture_window",))
        self.assertIs(admissibility(q, state), Admissibility.REFUSED)

    def test_a_soft_failure_only_degrades(self):
        state = admission()
        q = Question("q", "asks?", requires=("schema.fields",),
                     degraded_by=("coverage.capture_window",),
                     degradation="правый хвост")
        self.assertIs(admissibility(q, state), Admissibility.PARTIAL)

    def test_everything_clearing_qualifies(self):
        state = admission()
        q = Question("q", "asks?", requires=("schema.fields", "time.resolution"))
        self.assertIs(admissibility(q, state), Admissibility.QUALIFIED)


class NetHealthSplitTests(unittest.TestCase):
    """Тот самый split, и он ВЫВЕДЕН, а не записан."""

    @classmethod
    def setUpClass(cls):
        cls.v = verdicts()

    def test_tie_pressure_on_sm_is_qualified(self):
        """Ему нужен наблюдаемый поток и родная секундная шкала, а не
        доказанное число часов наблюдения."""
        self.assertIs(self.v["tie_pressure_SM"], Admissibility.QUALIFIED)

    def test_duplicate_mechanics_and_channel_structure_are_qualified(self):
        self.assertIs(self.v["duplicate_mechanics"], Admissibility.QUALIFIED)
        self.assertIs(self.v["channel_platform_structure"], Admissibility.QUALIFIED)

    def test_topology_and_latency_are_partial_not_qualified(self):
        """Неизвестная terminal acquisition режет правый хвост: последняя серия
        и последний ответ могут не попасть в выгрузку."""
        self.assertIs(self.v["run_topology"], Admissibility.PARTIAL)
        self.assertIs(self.v["completed_reply_latency"], Admissibility.PARTIAL)

    def test_everything_incidence_shaped_is_refused(self):
        for key in ("incidence_per_day", "nonresponse_fraction",
                    "fixed_window_burden"):
            self.assertIs(self.v[key], Admissibility.REFUSED, key)

    def test_the_degradation_is_directional_and_says_so(self):
        """Смещение в одну сторону — к более коротким наблюдённым латентностям."""
        q = next(q for q in QUESTIONS if q.key == "completed_reply_latency")
        self.assertIn("более коротких", q.degradation)


class IncidenceHuntTests(unittest.TestCase):
    """Новый класс искомого источника, а не ещё один smartphone dataset."""

    def test_the_must_list_demands_operator_side_capture(self):
        self.assertIn("server/operator-side acquisition", spec.MUST)
        self.assertIn("no participant-device observability ambiguity", spec.MUST)

    def test_a_clean_licence_does_not_rescue_a_wrong_population(self):
        """CC BY 4.0 и операторский захват — и всё равно не годится: трафик
        обогащён спамом, потому что это набор для детекции аномалий."""
        c = next(c for c in spec.CANDIDATES if "Anomaly" in c.name)
        self.assertIs(c.fit, spec.Fit.POPULATION_UNSUITABLE)
        self.assertIn("cc-by-4.0", c.evidence)
        self.assertIn("ЧЁРНЫЙ СПИСОК", c.note)

    def test_a_clean_licence_does_not_rescue_wrong_granularity(self):
        c = next(c for c in spec.CANDIDATES if "life course" in c.name)
        self.assertIs(c.fit, spec.Fit.WRONG_GRANULARITY)
        self.assertIn("АГРЕГИРОВАННЫЕ", c.note)

    def test_a_downstream_cc_by_collection_does_not_relicense_the_source(self):
        c = next(c for c in spec.CANDIDATES if "CollegeMsg" in c.name)
        self.assertIs(c.fit, spec.Fit.LICENSE_PROVENANCE_OPEN)
        self.assertIn("не даёт автоматического права", c.note)

    def test_no_candidate_is_yet_a_clean_candidate(self):
        self.assertEqual(spec.by_fit(spec.Fit.CANDIDATE), ())


if __name__ == "__main__":
    unittest.main()
