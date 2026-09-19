"""Правила, объявленные до данных, проверяются без данных.

Смысл модуля — в том, что его нельзя подправить после просмотра, не оставив
следа в истории. Тесты пинуют именно те значения, которые соблазнительно
подкрутить: окно D1, ступени уверенности, роли каналов и единственность
источника времени.
"""

import unittest

from acquisition import nethealth_rules as rules
from acquisition.nethealth_rules import (
    DuplicateEvidence, DuplicateVerdict, TemporalSourceError,
    classify_duplicates, primary_identity_regime, temporal_field,
)


class TemporalSourceTests(unittest.TestCase):
    """Один источник истины. Второй заводится ровно тогда, когда первый работает."""

    def test_only_epochtime_is_a_time_axis(self):
        self.assertEqual(temporal_field("epochtime"), "epochtime")

    def test_the_local_wall_clock_fields_are_refused(self):
        for field in ("date", "time", "dayofweek"):
            with self.assertRaises(TemporalSourceError, msg=field):
                temporal_field(field)

    def test_an_unrelated_field_is_refused_too(self):
        with self.assertRaises(TemporalSourceError):
            temporal_field("studyday")

    def test_the_refusal_says_why_rather_than_just_no(self):
        with self.assertRaises(TemporalSourceError) as caught:
            temporal_field("time")
        self.assertIn("epochtime", str(caught.exception))


class DuplicateLadderTests(unittest.TestCase):
    """D0 доказывает наличие. Его отсутствие не доказывает ничего."""

    def evidence(self, **over):
        #: нулевая полоса и ненулевые полосы фона, те же потоки
        base = dict(pairs_examined=5000, d0_exact=0,
                    band_counts=(100, 95, 92, 90, 88))
        return DuplicateEvidence(**{**base, **over})

    def test_any_exact_mirror_settles_it_immediately(self):
        self.assertIs(classify_duplicates(self.evidence(d0_exact=1)),
                      DuplicateVerdict.PRESENT)

    def test_a_zero_lag_band_far_above_its_neighbours_settles_it(self):
        self.assertIs(
            classify_duplicates(self.evidence(band_counts=(900, 100, 95, 90))),
            DuplicateVerdict.PRESENT)

    def test_a_zero_lag_band_level_with_its_neighbours_is_not_evidence(self):
        """Плотный трафик сам по себе набивает нулевую полосу. D1 в одиночку
        вердикта не даёт никогда."""
        self.assertIs(classify_duplicates(self.evidence()),
                      DuplicateVerdict.NO_SIGNATURE_OBSERVED)

    def test_the_background_preserves_burstiness_by_construction(self):
        """Фон взят из ТЕХ ЖЕ потоков на ненулевых задержках, а не из
        постоянной интенсивности. Пуассоновский нуль занижал случайные
        совпадения и раздувал превышение примерно в сорок раз."""
        e = self.evidence(band_counts=(1_913_647, 400_794, 296_217, 242_020,
                                       212_472, 199_697, 190_656, 178_792))
        self.assertAlmostEqual(e.background, 245_806.9, places=1)
        self.assertAlmostEqual(e.d2_ratio, 7.79, places=2)

    def test_too_few_pairs_means_the_question_was_not_asked(self):
        self.assertIs(classify_duplicates(self.evidence(pairs_examined=10)),
                      DuplicateVerdict.INSUFFICIENT)

    def test_the_clean_outcome_is_named_narrowly(self):
        """«Сигнатуры не наблюдается» — не «двойное логирование невозможно».
        Второе из первого не следует и выводом не станет."""
        self.assertEqual(DuplicateVerdict.NO_SIGNATURE_OBSERVED.value,
                         "no_signature_observed")

    def test_the_ratio_is_reported_as_a_number_not_only_a_verdict(self):
        e = self.evidence(band_counts=(200, 100, 100, 100))
        self.assertEqual(e.d1_near, 200)
        self.assertAlmostEqual(e.d2_ratio, 2.0)

    def test_no_background_gives_no_ratio_rather_than_infinity(self):
        self.assertIsNone(self.evidence(band_counts=(5,)).d2_ratio)

    def test_the_window_is_fixed_in_advance_and_justified_correctly(self):
        """Пять секунд объявлены заранее. Обоснование ПОПРАВЛЕНО: секундное
        квантование само даёт максимум около секунды, остальное — расхождение
        часов и момента журналирования двух аппаратов."""
        import inspect
        source = inspect.getsource(rules)
        self.assertEqual(rules.DEDUP_NEAR_WINDOW_SECONDS, 5.0)
        self.assertIn("расхождение часов", source)

    def test_detection_and_repair_are_separated(self):
        """Если алгоритм ремонта влияет на доказательство существования
        проблемы, доказательства больше нет."""
        self.assertFalse(rules.DEDUP_POLICY_IN_FORCE)
        self.assertEqual(rules.DEDUP_MATCHING, "one_to_one_minimum_distance")

    def test_the_greedy_repair_hazard_is_written_down(self):
        import inspect
        self.assertIn("msg2", inspect.getsource(rules))


class IdentityRegimeTests(unittest.TestCase):

    def test_the_regimes_are_nested_and_ordered_strictest_first(self):
        thresholds = [t for _, t in rules.IDENTITY_REGIMES]
        self.assertEqual(thresholds, sorted(thresholds, reverse=True))
        self.assertEqual(thresholds, [0.95, 0.70, 0.60])

    def test_the_strictest_surviving_regime_is_primary(self):
        self.assertEqual(primary_identity_regime({"I0": 500, "I1": 900, "I2": 1200}), "I0")
        self.assertEqual(primary_identity_regime({"I0": 10, "I1": 900, "I2": 1200}), "I1")
        self.assertEqual(primary_identity_regime({"I0": 10, "I1": 20, "I2": 1200}), "I2")

    def test_no_regime_survives_is_an_answer_not_a_fallback(self):
        self.assertIsNone(primary_identity_regime({"I0": 1, "I1": 2, "I2": 3}))

    def test_the_survival_threshold_is_declared_before_sample_sizes_are_seen(self):
        self.assertEqual(rules.IDENTITY_MINIMUM_DYADS, 200)

    def test_the_threshold_applies_after_every_other_narrowing(self):
        """Иначе «I0 выжил на 230 диадах», а после coverage-гейта их 87."""
        self.assertEqual(rules.IDENTITY_THRESHOLD_APPLIED_AFTER,
                         ("channel_filter", "dedup_policy", "coverage_restriction"))

    def test_the_population_consequence_is_written_into_the_estimand_phrase(self):
        """Правило отбора — определение популяции, пусть и объявленное заранее."""
        self.assertIn("preregistered identity-confidence admission rule",
                      rules.IDENTITY_POPULATION_PHRASE)


class ChannelPolicyTests(unittest.TestCase):

    def test_plain_sms_is_the_only_primary_channel(self):
        self.assertEqual(rules.channel_role("SMS", "SM"), "primary")

    def test_imessage_is_sensitivity_because_it_is_iphone_only(self):
        self.assertEqual(rules.channel_role("SMS", "iM"), "sensitivity")
        self.assertEqual(rules.channel_role("WhatsApp", "DM"), "sensitivity")

    def test_group_chat_is_excluded_as_a_different_topology(self):
        self.assertEqual(rules.channel_role("WhatsApp", "GC"), "excluded")

    def test_anything_unlisted_is_unassigned_rather_than_quietly_included(self):
        self.assertEqual(rules.channel_role("Call", "V"), "unassigned")
        self.assertEqual(rules.channel_role("MMS", "I"), "unassigned")

    def test_the_roles_do_not_overlap(self):
        groups = (rules.CHANNEL_PRIMARY, rules.CHANNEL_SENSITIVITY, rules.CHANNEL_EXCLUDED)
        seen = [k for g in groups for k in g]
        self.assertEqual(len(seen), len(set(seen)))


class ResolutionStratificationTests(unittest.TestCase):

    def test_resolution_is_stratified_before_any_verdict(self):
        """«Смешанное разрешение, Q3 закрыт» было бы преждевременным, пока не
        разрезано по каналу и платформе."""
        for field in ("eventtypedetail", "iphone", "outgoing"):
            self.assertIn(field, rules.RESOLUTION_STRATA)


if __name__ == "__main__":
    unittest.main()


class CoverageConceptTests(unittest.TestCase):
    """Три понятия покрытия разведены, чтобы не притворялись друг другом."""

    def test_all_three_concepts_are_named(self):
        self.assertEqual(rules.COVERAGE_CONCEPTS,
                         ("participation_window", "device_activity",
                          "acquisition_coverage"))

    def test_incidence_needs_the_third_and_not_the_other_two(self):
        """Первый и второй не доказывают третий ни по отдельности, ни вместе.
        Складывать два PARTIAL и получать PASS запрещено."""
        self.assertEqual(rules.COVERAGE_REQUIRED_FOR_INCIDENCE,
                         "acquisition_coverage")
        self.assertNotIn(rules.COVERAGE_REQUIRED_FOR_INCIDENCE,
                         ("participation_window", "device_activity"))

    def test_post_window_activity_may_not_select_the_cohort(self):
        """Оставив только тех, у кого есть событие после окна, мы определим
        популяцию через активность и «починим» missingness, выбрав более
        активных. Очень изящный способ получить красивую плотность."""
        self.assertEqual(rules.POST_WINDOW_EVENT_AS_COHORT_FILTER, "FORBIDDEN")

    def test_the_cns_style_proxy_error_is_named_in_the_source(self):
        import inspect
        self.assertIn("Bluetooth", inspect.getsource(rules))


class MatchFieldTests(unittest.TestCase):

    def test_messagetype_is_dropped_because_the_authors_say_to_ignore_it(self):
        self.assertNotIn("messagetype", rules.DEDUP_MATCH_FIELDS_CANDIDATE)

    def test_length_is_kept_because_the_project_itself_keyed_on_it(self):
        """Серверный первичный ключ iOS-SMS: (phone_number, time_stamp,
        destination, text_length, is_from_me)."""
        self.assertIn("length", rules.DEDUP_MATCH_FIELDS_CANDIDATE)

    def test_the_server_key_is_recorded_as_per_device(self):
        """Оно и объясняет, почему межустройственные зеркала пережили чужую
        дедупликацию: номер аппарата входит в ключ."""
        self.assertTrue(rules.SERVER_DEDUP_KEY_IS_PER_DEVICE)
