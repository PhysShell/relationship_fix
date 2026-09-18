"""Симулятор проверяется тем же, чем проверяется экстрактор: попыткой его сломать.

Генератор ground truth — сам по себе измерительный прибор, и непроверенный
прибор хуже отсутствующего: он выдаёт числа с той же уверенностью, что и
верный. Здесь пиннится ровно то, на что потом будут ссылаться выводы PHASE S:
детерминизм при seed, спаривание рук, отсутствие текста, разрешение часов как
источник неоднозначности — и таблица истинности вердиктов, отдельно от всякой
симуляции.
"""

import dataclasses
import math
import random
import unittest

from extractor.model import RawMessage
from simulation import interval, recovery as rec
from simulation.process import (
    DAY, HOUR, PARTICIPANT, PARTNER, DyadParameters, Population, TrueEffect,
    _is_night, generate_arm, generate_dyad,
)

H = 24.0


def params(**over) -> DyadParameters:
    return dataclasses.replace(DyadParameters(), **over)


def population(**over) -> Population:
    """Популяция без разброса: для пиннинга механики гетерогенность — шум."""
    return Population(base=params(**over), rate_log_sd=0.0,
                      latency_log_sd_between=0.0, nonresponse_sd=0.0)


class DeterminismTests(unittest.TestCase):
    """Один seed — одна трасса, всегда и на любой машине."""

    def test_same_seed_and_label_reproduce_the_arm_exactly(self):
        a = generate_arm(4, Population(), TrueEffect(), dyads=5, days=7)
        b = generate_arm(4, Population(), TrueEffect(), dyads=5, days=7)
        self.assertEqual(a, b)

    def test_different_label_is_a_different_sample(self):
        a = generate_arm(4, Population(), TrueEffect(), dyads=5, days=7, label="T")
        b = generate_arm(4, Population(), TrueEffect(), dyads=5, days=7, label="C")
        self.assertNotEqual(a, b)

    def test_seeding_survives_a_hostile_hash_seed(self):
        """Строковый seed идёт через sha512, а не через `hash()`.

        Если кто-то заменит его на `hash((seed, index))`, воспроизводимость
        тихо станет зависеть от PYTHONHASHSEED — и симуляция начнёт давать
        разные «истины» в разных запусках CI.
        """
        one = random.Random("4::0:stream").random()
        self.assertEqual(one, random.Random("4::0:stream").random())
        self.assertNotEqual(one, random.Random("4::1:stream").random())

    def test_the_drawn_parameters_are_pinned_to_recorded_values(self):
        """Золотые значения. Меняется порядок вытягивания — меняется ВСЯ истина.

        Любая прежде посчитанная ground truth относилась к прежнему процессу.
        Поэтому порядок и знаки вытягиваний в `draw` пинуются числами, а не
        описанием: этот тест обязан упасть, если процесс переопределили, даже
        когда распределение формально осталось прежним.
        """
        drawn = Population().draw(random.Random("0::0:params"))
        self.assertAlmostEqual(drawn.opportunity_rate_per_day, 12.51779765849134)
        self.assertAlmostEqual(drawn.latency_log_mean, 6.13374850180814)
        self.assertAlmostEqual(drawn.nonresponse_p, 0.035117455578258724)

    def test_a_dyad_index_keeps_its_parameters_across_arms(self):
        drawn = [Population().draw(random.Random(f"4::{i}:params")) for i in range(3)]
        again = [Population().draw(random.Random(f"4::{i}:params")) for i in range(3)]
        self.assertEqual(drawn, again)
        self.assertNotEqual(drawn[0], drawn[1])


class ImmutabilityTests(unittest.TestCase):
    """Параметры — значения, а не состояние, и это должно быть невозможно нарушить.

    `Population.base` разделяется всеми парами обеих рук. Будь он изменяемым,
    `TrueEffect.apply`, написанный однажды через присваивание вместо `replace`,
    протёк бы в контрольную руку — и контраст обнулился бы молча, без единого
    падения. Мутационный прогон показал, что `frozen=True` тут не проверял
    никто.
    """

    def test_the_parameter_objects_refuse_assignment(self):
        # имя поля берётся у самого класса: под `slots=True` присваивание
        # НЕСУЩЕСТВУЮЩЕГО имени в 3.11 даёт TypeError вместо FrozenInstanceError,
        # и тест на выдуманном имени проверял бы этот курьёз, а не заморозку
        for value in (DyadParameters(), Population(), TrueEffect()):
            name = dataclasses.fields(value)[0].name
            with self.assertRaises(dataclasses.FrozenInstanceError,
                                   msg=type(value).__name__):
                setattr(value, name, 1.0)

    def test_applying_an_effect_leaves_the_shared_base_untouched(self):
        base = DyadParameters()
        before = dataclasses.asdict(base)
        TrueEffect(opportunity_rate_ratio=0.5, latency_log_shift=1.0).apply(base)
        self.assertEqual(dataclasses.asdict(base), before)

    def test_drawing_a_dyad_leaves_the_population_untouched(self):
        pop = Population()
        before = dataclasses.asdict(pop)
        pop.draw(random.Random("x"))
        self.assertEqual(dataclasses.asdict(pop), before)


class NightWindowTests(unittest.TestCase):
    """Границы ночи и окно через полночь — то, чего по умолчанию не бывает.

    Значения по умолчанию (1..8) никогда не заходят за полночь, поэтому ветка
    переноса не исполнялась ни одним тестом. Реалистичное окно — как раз
    переносное, и молчащая ветка тут была бы молчащей и в поле.
    """

    DAY_PARAMS = DyadParameters(night_start_hour=1, night_end_hour=8)
    WRAPPED = DyadParameters(night_start_hour=23, night_end_hour=7)

    def test_the_night_includes_its_start_and_excludes_its_end(self):
        self.assertTrue(_is_night(1 * HOUR, self.DAY_PARAMS))
        self.assertTrue(_is_night(8 * HOUR - 1.0, self.DAY_PARAMS))
        self.assertFalse(_is_night(8 * HOUR, self.DAY_PARAMS))
        self.assertFalse(_is_night(1 * HOUR - 1.0, self.DAY_PARAMS))

    def test_a_window_crossing_midnight_covers_both_sides_of_it(self):
        self.assertTrue(_is_night(23 * HOUR, self.WRAPPED))
        self.assertTrue(_is_night(23.5 * HOUR, self.WRAPPED))
        self.assertTrue(_is_night(0.0, self.WRAPPED))
        self.assertTrue(_is_night(7 * HOUR - 1.0, self.WRAPPED))

    def test_a_window_crossing_midnight_still_has_a_daytime(self):
        self.assertFalse(_is_night(7 * HOUR, self.WRAPPED))
        self.assertFalse(_is_night(12 * HOUR, self.WRAPPED))
        self.assertFalse(_is_night(23 * HOUR - 1.0, self.WRAPPED))

    def test_the_hour_is_read_from_the_day_and_not_from_the_epoch(self):
        self.assertTrue(_is_night(97 * DAY + 3 * HOUR, self.DAY_PARAMS))
        self.assertFalse(_is_night(97 * DAY + 15 * HOUR, self.DAY_PARAMS))


class NoTextTests(unittest.TestCase):
    """Приватная граница начинается с того, что текста не существует."""

    def test_the_message_type_has_no_text_bearing_field(self):
        fields = {f.name for f in dataclasses.fields(RawMessage)}
        self.assertEqual(fields & {"text", "body", "content", "message", "raw"}, set())

    def test_generated_length_is_a_number_and_never_a_string(self):
        for message in generate_dyad(random.Random(1), params(), days=3):
            self.assertIsInstance(message.char_count, int)
            self.assertGreaterEqual(message.char_count, 1)


class ProcessShapeTests(unittest.TestCase):
    """Процесс должен производить ту топологию, которую экстрактор и описывает."""

    def test_only_the_two_actors_of_a_dyad_appear(self):
        stream = generate_dyad(random.Random(2), params(), days=10)
        self.assertEqual({m.actor for m in stream}, {PARTNER, PARTICIPANT})

    def test_every_run_is_opened_by_the_partner(self):
        stream = generate_dyad(random.Random(3), params(), days=10)
        self.assertEqual(stream[0].actor, PARTNER)
        for before, after in zip(stream, stream[1:]):
            if after.actor == PARTICIPANT:
                self.assertEqual(before.actor, PARTNER)

    def test_total_suppression_empties_the_night(self):
        stream = generate_dyad(random.Random(5), params(night_suppression=1.0), days=30)
        opens = [m for m in stream if m.actor == PARTNER]
        night = [m for m in opens if 1 <= (m.timestamp % DAY) / 3600.0 < 8]
        # серия, начатая в 00:5x, и ответ дотягиваются в ночь; открыться в ней
        # не может ничто, поэтому сравнение идёт с долей, а не с нулём
        self.assertLess(len(night) / len(opens), 0.08)

    def test_nonresponse_one_produces_no_participant_message_at_all(self):
        stream = generate_dyad(random.Random(6), params(nonresponse_p=1.0), days=20)
        self.assertEqual([m for m in stream if m.actor == PARTICIPANT], [])

    def test_timestamps_are_quantised_to_the_source_clock(self):
        stream = generate_dyad(random.Random(7), params(), days=10)
        for message in stream:
            self.assertEqual(message.timestamp, math.floor(message.timestamp))

    def test_continuous_time_would_hide_the_ambiguity_the_clock_creates(self):
        """Разрешение часов — источник ties, и без него симуляция себе льстит.

        Непрерывное время не производит cross-actor ties почти никогда, и тогда
        цена `TiePolicy.STRICT` в симуляции выходит нулевой — а в поле нет.
        """
        pop = population(timestamp_resolution_seconds=1.0)
        coarse = rec.run_arm(7, pop, TrueEffect(), dyads=60, days=14)
        fine = rec.run_arm(7, population(timestamp_resolution_seconds=0.0),
                           TrueEffect(), dyads=60, days=14)
        self.assertEqual(sum(a.cross_actor_tie_groups for a in fine), 0)
        self.assertGreater(sum(a.cross_actor_tie_groups for a in coarse), 0)

    def test_forced_ties_are_dropped_rather_than_ordered(self):
        pop = population(tie_p=1.0)
        aggregates = rec.run_arm(11, pop, TrueEffect(), dyads=20, days=14)
        self.assertGreater(sum(a.ambiguous_opportunities for a in aggregates), 0)


class TrueEffectTests(unittest.TestCase):

    def test_the_null_effect_is_the_identity(self):
        base = params()
        self.assertTrue(TrueEffect().is_null)
        self.assertEqual(TrueEffect().apply(base), base)

    def test_any_single_channel_makes_it_non_null(self):
        self.assertFalse(TrueEffect(opportunity_rate_ratio=0.99).is_null)
        self.assertFalse(TrueEffect(latency_log_shift=0.01).is_null)
        self.assertFalse(TrueEffect(nonresponse_shift=0.01).is_null)

    def test_channels_move_the_parameter_they_name(self):
        got = TrueEffect(opportunity_rate_ratio=0.5, latency_log_shift=0.2,
                         nonresponse_shift=0.1).apply(params())
        self.assertAlmostEqual(got.opportunity_rate_per_day, 3.0)
        self.assertAlmostEqual(got.latency_log_mean, math.log(600.0) + 0.2)
        self.assertAlmostEqual(got.nonresponse_p, 0.18)

    def test_nonresponse_stays_a_probability(self):
        self.assertEqual(TrueEffect(nonresponse_shift=-5.0).apply(params()).nonresponse_p, 0.0)
        self.assertEqual(TrueEffect(nonresponse_shift=5.0).apply(params()).nonresponse_p, 0.95)


class ClassifyTests(unittest.TestCase):
    """Таблица истинности вердикта. Ни одной симуляции — только пять чисел."""

    def verdict(self, **over):
        base = dict(observed=10.0, planted=10.0, half_width=1.0,
                    agreement_half_width=2.0, delta=5.0)
        return rec.classify(**{**base, **over})

    def test_interval_excluding_zero_and_covering_truth_is_recovery(self):
        self.assertIs(self.verdict(), rec.Verdict.RECOVERED)

    def test_interval_inside_delta_is_absence(self):
        self.assertIs(self.verdict(observed=0.5, planted=0.0), rec.Verdict.ABSENT)

    def test_interval_touching_zero_and_wider_than_delta_is_inconclusive(self):
        self.assertIs(self.verdict(observed=1.0, planted=0.0, half_width=7.0,
                                   agreement_half_width=9.0), rec.Verdict.INCONCLUSIVE)

    def test_missing_truth_is_not_estimated(self):
        self.assertIs(self.verdict(planted=None), rec.Verdict.NOT_ESTIMATED)
        self.assertIs(self.verdict(observed=None), rec.Verdict.NOT_ESTIMATED)

    def test_found_the_wrong_number_is_mismatch_not_recovery(self):
        """Знак совпал, размер — нет. В поле это выглядело бы как успех."""
        got = self.verdict(observed=40.0, planted=10.0)
        self.assertIs(got, rec.Verdict.MISMATCH)

    def test_mismatch_outranks_absence_too(self):
        self.assertIs(self.verdict(observed=0.0, planted=9.0, half_width=1.0,
                                   agreement_half_width=2.0), rec.Verdict.MISMATCH)

    def test_agreement_width_is_the_one_that_decides_mismatch(self):
        """Ошибка эталона расширяет только проверку истины, не проверку нуля."""
        self.assertIs(self.verdict(observed=13.0, agreement_half_width=4.0),
                      rec.Verdict.RECOVERED)
        self.assertIs(self.verdict(observed=13.0, agreement_half_width=2.0),
                      rec.Verdict.MISMATCH)

    def test_absence_needs_the_whole_interval_inside_delta(self):
        # точка внутри delta, но интервал вылезает — это не «практически ноль»
        self.assertIs(self.verdict(observed=4.0, planted=4.0, half_width=3.0,
                                   agreement_half_width=4.0, delta=5.0),
                      rec.Verdict.RECOVERED)
        self.assertIs(self.verdict(observed=1.0, planted=1.0, half_width=5.0,
                                   agreement_half_width=6.0, delta=5.0),
                      rec.Verdict.INCONCLUSIVE)


class ReplicatesTests(unittest.TestCase):

    def test_undefined_replicates_are_counted_and_not_read_as_zero(self):
        r = rec.Replicates("x", H, values=(10.0, 20.0), undefined=3)
        self.assertEqual(r.n, 2)
        self.assertEqual(r.mean, 15.0)
        self.assertEqual(r.undefined, 3)

    def test_a_single_replicate_has_no_spread(self):
        r = rec.Replicates("x", H, values=(10.0,), undefined=0)
        self.assertIsNone(r.sd)
        self.assertIsNone(r.se)

    def test_standard_error_shrinks_with_the_root_of_n(self):
        four = rec.Replicates("x", H, values=(1.0, 3.0, 1.0, 3.0), undefined=0)
        self.assertAlmostEqual(four.se, four.sd / 2.0)


class ArmTests(unittest.TestCase):

    def test_one_person_period_per_dyad_over_the_declared_window(self):
        aggregates = rec.run_arm(3, Population(), TrueEffect(), dyads=6, days=14)
        self.assertEqual(len(aggregates), 6)
        for aggregate in aggregates:
            self.assertEqual(aggregate.observation_window_seconds, 14 * DAY)
        self.assertEqual(len({a.period_id for a in aggregates}), 6)

    def test_the_production_path_is_the_one_being_simulated(self):
        """Под PRODUCTION трасса не строится; восстановление не должно её ждать."""
        aggregates = rec.run_arm(3, Population(), TrueEffect(), dyads=2, days=7)
        self.assertTrue(all(a.horizons for a in aggregates))


class PairingTests(unittest.TestCase):

    def test_a_paired_null_contrast_is_exactly_zero(self):
        """Не «около нуля». Побитово те же руки — значит тождественно нуль."""
        got = rec.contrast(Population(), TrueEffect(), dyads=8, days=14,
                           replicates=3, base_seed=21, horizon_hours=H, paired=True)
        for name, c in got.items():
            self.assertEqual(set(c.differences), {0.0}, name)
            self.assertEqual(c.undefined, 0, name)

    def test_an_unpaired_null_contrast_is_noise_and_must_not_be_zero(self):
        """Спаренная дисперсия для мощности — ложь; здесь она и берётся честной."""
        got = rec.contrast(Population(), TrueEffect(), dyads=8, days=14,
                           replicates=4, base_seed=21, horizon_hours=H, paired=False)
        self.assertGreater(got["mean_burden"].sd, 0.0)
        self.assertNotEqual(got["mean_burden"].mean, 0.0)


class RecoveryTests(unittest.TestCase):
    """Сквозной прогон: положили сдвиг латентности — нашли ли его именно тем.

    Ни одно утверждение здесь не опирается на удачу конкретного seed: та же
    конфигурация была проверена на base_seed 31, 77, 404 и 1009, и RECOVERED
    выходит на всех четырёх по всем четырём величинам. Один зафиксирован в
    тесте ради скорости, а не ради результата.
    """

    @classmethod
    def setUpClass(cls):
        pop = Population()
        effect = TrueEffect(latency_log_shift=0.4)
        truth = rec.planted_truth(pop, effect, dyads=150, days=14, replicates=5,
                                  base_seed=9000, horizon_hours=H)
        observed = rec.contrast(pop, effect, dyads=80, days=14, replicates=8,
                                base_seed=31, horizon_hours=H, paired=True)
        cls.truth = truth
        cls.checks = {
            name: rec.check_recovery(observed[name], truth[name], delta=60.0)
            for name in rec.ESTIMANDS
        }

    def test_every_estimand_recovers_what_was_planted(self):
        for name, check in self.checks.items():
            self.assertIs(check.verdict, rec.Verdict.RECOVERED,
                          f"{name}: observed {check.observed} vs planted {check.planted}")

    def test_a_longer_latency_lengthens_the_duration_estimands(self):
        for name in ("opportunity_rmtr", "person_period_rmtr", "mean_burden"):
            self.assertGreater(self.checks[name].planted, 0.0, name)
            self.assertGreater(self.checks[name].observed, 0.0, name)

    def test_the_channels_are_not_separable_and_that_is_a_finding(self):
        """Сдвиг ТОЛЬКО латентности двигает и частоту возможностей, вниз.

        Процесс последовательный: следующая возможность не открывается, пока
        участник не вернулся. Значит incidence — НЕ свободный от воздействия
        канал, и обе половины `mean_burden = N x R` зависят от одного и того же
        сдвига. Это ровно то, из-за чего `Cov(N, R)` не ноль, и ровно то, чего
        не видно на кросс-секции.
        """
        self.assertLess(self.checks["mean_incidence"].planted, 0.0)
        self.assertLess(self.checks["mean_incidence"].observed, 0.0)

    def test_the_four_verdicts_are_not_four_independent_checks(self):
        """Одна выборка на все четыре величины, и корреляция между ними высокая.

        Неудачно вытянутый набор пар сдвигает все четыре в одну сторону разом,
        поэтому «три MISMATCH из четырёх» — это одно событие, а не три.
        Считать их независимыми уликами значит утраивать одну и ту же.
        """
        observed = [self.checks[n].observed for n in
                    ("mean_burden", "opportunity_rmtr", "person_period_rmtr")]
        planted = [self.checks[n].planted for n in
                   ("mean_burden", "opportunity_rmtr", "person_period_rmtr")]
        signs = {math.copysign(1.0, o - p) for o, p in zip(observed, planted)}
        self.assertEqual(len(signs), 1)

    def test_the_interval_is_reported_next_to_the_verdict(self):
        check = self.checks["person_period_rmtr"]
        low, high = check.ci
        self.assertLess(low, check.observed)
        self.assertGreater(high, check.observed)
        self.assertGreater(check.agreement_df, 1.0)

    def test_a_verdict_cannot_be_built_from_one_replicate(self):
        thin = rec.Contrast("mean_burden", H, differences=(1.0,), undefined=0, paired=True)
        fat = rec.Contrast("mean_burden", H, differences=(1.0, 2.0), undefined=0, paired=True)
        with self.assertRaises(ValueError):
            rec.check_recovery(thin, fat, delta=1.0)
        with self.assertRaises(ValueError):
            rec.check_recovery(fat, thin, delta=1.0)

    def test_comparing_two_different_things_is_refused(self):
        a = rec.Contrast("mean_burden", H, differences=(1.0, 2.0), undefined=0, paired=True)
        b = rec.Contrast("mean_incidence", H, differences=(1.0, 2.0), undefined=0, paired=True)
        with self.assertRaises(ValueError):
            rec.check_recovery(a, b, delta=1.0)


class IntervalTests(unittest.TestCase):
    """Квантиль Стьюдента сверяется с ПЕЧАТНОЙ таблицей, а не сам с собой."""

    TABLE = {1: 12.706, 2: 4.303, 3: 3.182, 5: 2.571, 10: 2.228,
             20: 2.086, 30: 2.042, 100: 1.984}

    def test_two_sided_95_percent_matches_the_published_table(self):
        for df, want in self.TABLE.items():
            self.assertAlmostEqual(interval.student_t_quantile(0.975, df), want, places=3)

    def test_one_sided_95_percent_matches_the_published_table(self):
        self.assertAlmostEqual(interval.student_t_quantile(0.95, 10), 1.812, places=3)

    def test_it_is_symmetric_about_zero(self):
        self.assertAlmostEqual(interval.student_t_quantile(0.025, 7),
                               -interval.student_t_quantile(0.975, 7))
        self.assertEqual(interval.student_t_quantile(0.5, 7), 0.0)

    def test_it_narrows_towards_the_normal_as_df_grows(self):
        quantiles = [interval.student_t_quantile(0.975, df) for df in (2, 5, 20, 200, 5000)]
        self.assertEqual(quantiles, sorted(quantiles, reverse=True))
        self.assertAlmostEqual(quantiles[-1], 1.96, places=3)

    def test_it_is_never_narrower_than_the_normal_quantile(self):
        """Это и есть та поправка, ради которой модуль существует."""
        for df in range(1, 60):
            self.assertGreater(interval.student_t_quantile(0.975, df), 1.959963)

    def test_the_cdf_agrees_with_the_quantile_it_inverts(self):
        for df in (1, 4, 17, 90):
            t = interval.student_t_quantile(0.975, df)
            self.assertAlmostEqual(interval.student_t_cdf(t, df), 0.975, places=8)

    def test_impossible_inputs_are_refused_rather_than_extrapolated(self):
        with self.assertRaises(ValueError):
            interval.student_t_quantile(0.0, 5)
        with self.assertRaises(ValueError):
            interval.student_t_quantile(1.0, 5)
        with self.assertRaises(ValueError):
            interval.student_t_cdf(0.0, 0)
        with self.assertRaises(ValueError):
            interval.half_width(1.0, 1)

    def test_the_incomplete_beta_hits_its_closed_form_cases(self):
        # I_x(1, 1) = x
        for x in (0.1, 0.5, 0.9):
            self.assertAlmostEqual(interval.regularized_incomplete_beta(1.0, 1.0, x), x)
        # I_x(a, b) + I_{1-x}(b, a) = 1
        self.assertAlmostEqual(
            interval.regularized_incomplete_beta(2.5, 3.5, 0.3)
            + interval.regularized_incomplete_beta(3.5, 2.5, 0.7), 1.0)
        self.assertEqual(interval.regularized_incomplete_beta(2.0, 3.0, 0.0), 0.0)
        self.assertEqual(interval.regularized_incomplete_beta(2.0, 3.0, 1.0), 1.0)


class CoverageTests(unittest.TestCase):
    """Частота ошибок инструмента МЕРЯЕТСЯ. Чистая часть — отдельно от прогона."""

    def test_the_nominal_rate_is_accepted(self):
        self.assertTrue(rec.Coverage("x", trials=20, mismatches=1, nominal=0.05).within_nominal)
        self.assertTrue(rec.Coverage("x", trials=20, mismatches=0, nominal=0.05).within_nominal)
        self.assertTrue(rec.Coverage("x", trials=20, mismatches=3, nominal=0.05).within_nominal)

    def test_a_grossly_undercovering_interval_is_rejected(self):
        self.assertFalse(rec.Coverage("x", trials=20, mismatches=6, nominal=0.05).within_nominal)
        self.assertFalse(rec.Coverage("x", trials=80, mismatches=15, nominal=0.05).within_nominal)

    def test_the_rate_is_a_share_and_not_a_count(self):
        self.assertEqual(rec.Coverage("x", trials=20, mismatches=5, nominal=0.05).rate, 0.25)

    def test_a_probe_with_no_trials_does_not_divide_by_zero(self):
        self.assertEqual(rec.Coverage("x", trials=0, mismatches=0, nominal=0.05).rate, 0.0)

    def test_the_probe_runs_end_to_end_and_reports_per_estimand(self):
        """Маленький прогон: здесь проверяется проводка, калибровка — в docs."""
        pop = Population()
        effect = TrueEffect(latency_log_shift=0.4)
        truth = rec.planted_truth(pop, effect, dyads=60, days=7, replicates=4,
                                  base_seed=9000, horizon_hours=H)
        probe = rec.coverage_probe(pop, effect, truth, dyads=20, days=7, replicates=4,
                                   trials=3, base_seed=70000, horizon_hours=H, delta=60.0)
        self.assertEqual(set(probe), set(rec.ESTIMANDS))
        for name, coverage in probe.items():
            self.assertEqual(coverage.trials, 3, name)
            self.assertLessEqual(coverage.mismatches, 3, name)


if __name__ == "__main__":
    unittest.main()
