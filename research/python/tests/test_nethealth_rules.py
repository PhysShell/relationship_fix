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
        base = dict(pairs_examined=5000, d0_exact=0, d1_near=10,
                    d2_expected_by_chance=8.0)
        return DuplicateEvidence(**{**base, **over})

    def test_any_exact_mirror_settles_it_immediately(self):
        self.assertIs(classify_duplicates(self.evidence(d0_exact=1)),
                      DuplicateVerdict.PRESENT)

    def test_a_large_near_mirror_excess_also_settles_it(self):
        self.assertIs(
            classify_duplicates(self.evidence(d1_near=100, d2_expected_by_chance=5.0)),
            DuplicateVerdict.PRESENT)

    def test_a_near_mirror_count_close_to_chance_is_not_evidence(self):
        self.assertIs(
            classify_duplicates(self.evidence(d1_near=10, d2_expected_by_chance=8.0)),
            DuplicateVerdict.NO_SIGNATURE_OBSERVED)

    def test_too_few_pairs_means_the_question_was_not_asked(self):
        self.assertIs(classify_duplicates(self.evidence(pairs_examined=10)),
                      DuplicateVerdict.INSUFFICIENT)

    def test_the_clean_outcome_is_named_narrowly(self):
        """«Сигнатуры не наблюдается» — не «двойное логирование невозможно».
        Второе из первого не следует и выводом не станет."""
        self.assertEqual(DuplicateVerdict.NO_SIGNATURE_OBSERVED.value,
                         "no_signature_observed")

    def test_the_excess_is_reported_as_a_number_not_only_a_verdict(self):
        self.assertAlmostEqual(self.evidence(d1_near=30).d2_excess, 22.0)

    def test_the_window_is_fixed_in_advance_and_justified(self):
        """Пять секунд выбраны из разрешения, а не из будущего пика."""
        import inspect
        self.assertEqual(rules.DEDUP_NEAR_WINDOW_SECONDS, 5.0)
        self.assertIn("94.3", inspect.getsource(rules))


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
