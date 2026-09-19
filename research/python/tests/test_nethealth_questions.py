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
        self.assertIn("не выдают прав, которых нет у источника", c.note)

    def test_no_candidate_is_yet_a_clean_candidate(self):
        self.assertEqual(spec.by_fit(spec.Fit.CANDIDATE), ())

    def test_a_licence_on_a_derived_collection_is_not_a_licence_on_the_source(self):
        """Figshare-коллекция под CC BY 4.0, а сырые CDR под NDA. Лицензию
        проверять у того артефакта, который будешь читать."""
        c = next(c for c in spec.CANDIDATES if "Multiplexity" in c.name)
        self.assertIs(c.fit, spec.Fit.ARTIFACT_MISMATCH)
        self.assertIn("non-disclosure agreement", c.evidence)
        self.assertTrue(spec.LICENCE_APPLIES_TO_THE_ARTIFACT_YOU_READ)

    def test_an_unverified_licence_is_recorded_as_unverified(self):
        """Republic of Letters: вторичные упоминания CC BY 4.0 есть, первичного
        подтверждения я не получил. Значит так и записано."""
        c = next(c for c in spec.CANDIDATES if "Republic" in c.name)
        self.assertIn("НЕ ПОДТВЕРЖДЕНА", c.evidence)

    def test_the_historical_corpus_is_an_anchor_and_not_a_target(self):
        c = next(c for c in spec.CANDIDATES if "Republic" in c.name)
        self.assertIs(c.fit, spec.Fit.STRESS_ANCHOR_ONLY)
        self.assertIn("43 секунды", c.note)

    def test_q1_is_split_so_one_corpus_need_not_answer_everything(self):
        self.assertEqual(set(spec.SUBQUESTIONS), {
            "Q1a_absolute_incidence_scale",
            "Q1b_incidence_shape_heterogeneity",
            "Q1c_density_and_run_merging"})

    def test_only_the_absolute_scale_demands_complete_coverage(self):
        self.assertIn("coverage-полный",
                      spec.SUBQUESTIONS["Q1a_absolute_incidence_scale"][1])
        self.assertIn("терпит",
                      spec.SUBQUESTIONS["Q1b_incidence_shape_heterogeneity"][1])

    def test_a_stop_rule_exists_and_is_a_number(self):
        """Поиск датасета не превращается в новый исследовательский проект."""
        self.assertIsInstance(spec.STOP_AFTER_SERIOUS_CANDIDATES, int)
        self.assertGreater(spec.STOP_AFTER_SERIOUS_CANDIDATES,
                           spec.serious_candidates_checked() - 1)

    def test_the_wall_is_recorded_as_structural_not_as_bad_luck(self):
        self.assertTrue(spec.WALL_IS_STRUCTURAL)

    def test_the_search_classes_replace_the_general_zoo(self):
        self.assertEqual(len(spec.SEARCH_CLASSES), 3)
        self.assertTrue(any("Dataverse" in c for c in spec.SEARCH_CLASSES))


if __name__ == "__main__":
    unittest.main()
