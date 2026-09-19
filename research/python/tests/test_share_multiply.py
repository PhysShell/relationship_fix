"""Гейт Share and Multiply: допуск выводится, Q1a закрыт, pickle не читается.

Три разные вещи проверяются здесь, и ни одна не проверяет «мы так решили»:

  классификатор разрешения устроен НЕСИММЕТРИЧНО и должен таким остаться;
  допуск по вопросам ВЫВОДИТСЯ из вердиктов — уроните проверку, и вопрос
  упадёт сам;
  обещание «мы не запускаем чужой pickle» исполняется здесь или нигде.
"""

import ast
import pathlib
import unittest

from acquisition.admission import Admissibility, CheckVerdict, admissibility
from acquisition import incidence_corpus_spec as spec
from acquisition import share_multiply_rules as rules
from acquisition.share_multiply_admission import (
    FINDINGS, QUESTIONS, Q1C_SUBSET_AGREEMENT, Q1C_SUBSET_BY_DECLARED,
    Q1C_SUBSET_CHATS, admission, verdicts,
)


class ResolutionClassifierTests(unittest.TestCase):
    """Доказательства «секунды» и «минуты» неравноправны, и это намеренно."""

    def test_one_nonzero_second_settles_it(self):
        """SECONDS — контрпример. Одной метки достаточно, длина не важна."""
        self.assertIs(rules.classify_resolution([60_000, 61_000]),
                      rules.Resolution.SECONDS)

    def test_minutes_needs_enough_messages_to_not_be_luck(self):
        """MINUTES — отсутствие контрпримеров, а отсутствие надо заслужить."""
        few = [60_000 * k for k in range(rules.MINUTES_VERDICT_MIN_MESSAGES - 1)]
        self.assertIs(rules.classify_resolution(few), rules.Resolution.UNDETERMINED)
        enough = [60_000 * k for k in range(rules.MINUTES_VERDICT_MIN_MESSAGES)]
        self.assertIs(rules.classify_resolution(enough), rules.Resolution.MINUTES)

    def test_subsecond_outranks_seconds(self):
        self.assertIs(rules.classify_resolution([60_000, 61_001]),
                      rules.Resolution.MILLISECONDS)

    def test_a_short_chat_is_never_quietly_folded_into_the_majority(self):
        """UNDETERMINED обязан остаться отдельным ответом, а не округлиться."""
        self.assertIsNot(rules.classify_resolution([60_000]),
                         rules.Resolution.MINUTES)


class GateTests(unittest.TestCase):

    def test_no_check_is_left_unanswered(self):
        """UNKNOWN не проходит. Незакрытая проверка равна проваленной."""
        open_checks = [c.key for c in admission().checks
                       if c.verdict is CheckVerdict.UNKNOWN]
        self.assertEqual(open_checks, [])

    def test_the_corpus_is_not_globally_admitted(self):
        """Допуск по вопросам — не способ объявить корпус чистым целиком."""
        state = admission()
        self.assertFalse(state.admitted)
        self.assertEqual(
            sorted(c.key for c in state.blocking_open),
            ["coverage.capture_window", "selection.donation_mechanism",
             "time.absolute_offset"])

    def test_q1a_is_refused(self):
        self.assertIs(verdicts()["q1a_absolute_incidence"], Admissibility.REFUSED)

    def test_diurnal_is_refused_even_though_time_semantics_passed(self):
        """Ровно та причина, по которой проверку пришлось расщепить надвое."""
        state = admission()
        self.assertTrue(state.check("time.semantics").clears)
        self.assertFalse(state.check("time.absolute_offset").clears)
        self.assertIs(verdicts()["diurnal_profile"], Admissibility.REFUSED)

    def test_q1c_is_partial_not_qualified(self):
        """«Почти идеален» — это PARTIAL с названным ущербом, а не PASS."""
        self.assertIs(verdicts()["q1c_density_and_run_merging"],
                      Admissibility.PARTIAL)
        self.assertIs(verdicts()["q1c_coarsening_operator"], Admissibility.PARTIAL)

    def test_the_refusal_is_derived_and_not_written_down(self):
        """Уроните обе проверки обратно в PASSED — и Q1a поднимется сам.

        Тест существует затем, чтобы отказ нельзя было «запомнить»: если
        завтра появится корпус с известным окном, машинерия обязана это
        заметить, а не хранить наш сегодняшний вердикт как убеждение.
        """
        state = admission()
        q1a = next(q for q in QUESTIONS if q.key == "q1a_absolute_incidence")
        self.assertIs(admissibility(q1a, state), Admissibility.REFUSED)
        repaired = state
        for key in ("selection.donation_mechanism", "coverage.capture_window"):
            repaired = repaired.resolve(key, CheckVerdict.PASSED, "гипотетически")
        self.assertIs(admissibility(q1a, repaired), Admissibility.QUALIFIED)

    def test_one_repaired_check_is_not_enough(self):
        """Два PARTIAL не складываются в PASS — здесь буквально."""
        state = admission().resolve(
            "selection.donation_mechanism", CheckVerdict.PASSED, "гипотетически")
        q1a = next(q for q in QUESTIONS if q.key == "q1a_absolute_incidence")
        self.assertIs(admissibility(q1a, state), Admissibility.REFUSED)

    def test_every_recorded_finding_belongs_to_a_real_check(self):
        keys = {c.key for c in admission().checks}
        self.assertEqual([k for k, _, _ in FINDINGS if k not in keys], [])


class SubsetTests(unittest.TestCase):

    def test_the_subset_clears_a_threshold_declared_before_counting(self):
        self.assertGreaterEqual(Q1C_SUBSET_CHATS, rules.Q1C_MINIMUM_DYADS)

    def test_the_seconds_claim_was_settled_by_counting_not_by_one_example(self):
        self.assertTrue(rules.SECONDS_SUBSET_CLAIM_VERIFIED)
        self.assertEqual(rules.SECONDS_CHATS_MEASURED, 1_598)
        self.assertEqual(rules.CHATS_MEASURED, 5_956)

    def test_equal_sizes_do_not_mean_the_same_chats(self):
        """Оба определения диадичности дали 520. Это совпадение, не согласие.

        Совпадение размеров опасно тем, что снимает желание сверить состав:
        три чата с каждой стороны разные, и выбор определения — решение, а не
        формальность.
        """
        self.assertEqual(Q1C_SUBSET_CHATS, Q1C_SUBSET_BY_DECLARED)
        self.assertLess(Q1C_SUBSET_AGREEMENT, Q1C_SUBSET_CHATS)

    def test_dyadic_seconds_is_smaller_than_seconds(self):
        """1 598 секундных — это ВСЕ чаты; диад среди них меньше. Не путать."""
        self.assertLess(Q1C_SUBSET_CHATS, rules.SECONDS_CHATS_MEASURED)


class StopRuleTests(unittest.TestCase):

    def test_the_stop_rule_fired(self):
        self.assertTrue(spec.stop_rule_fired())
        self.assertEqual(spec.Q1A_STATUS, "DOCUMENTED_LIMITATION")

    def test_the_limitation_says_what_it_does_not_say(self):
        """Отсутствие корпуса не становится свидетельством о величине."""
        self.assertIn("ЧЕГО ЭТО НЕ ЗНАЧИТ", spec.Q1A_LIMITATION)
        self.assertIn("UNCALIBRATED", spec.MOSAIC["Q1a absolute incidence"])

    def test_the_rediscovery_is_recorded_as_a_process_finding(self):
        """Шестой кандидат лежал в собственном ledger'е проекта всё это время."""
        again = spec.rediscovered()
        self.assertEqual(len(again), 1)
        self.assertIn("reactivity-power-design.md", again[0].previously_assessed)


class PickleIsNotExecutedTests(unittest.TestCase):
    """Обещание не запускать чужой код исполняется проверкой, а не абзацем."""

    def test_no_module_deserialises_the_pickle(self):
        forbidden = {"read_pickle", "load", "loads"}
        offenders = []
        for path in pathlib.Path("acquisition").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                if name not in forbidden:
                    continue
                owner = getattr(getattr(func, "value", None), "id", "")
                if name == "read_pickle" or owner in {"pickle", "cPickle", "pd"}:
                    offenders.append(f"{path}:{node.lineno} {owner}.{name}")
        self.assertEqual(offenders, [], "pickle читается — это исполнение кода")

    def test_the_rule_is_stated_where_the_reader_will_look(self):
        self.assertTrue(rules.PICKLE_IS_NOT_READ)
        self.assertEqual(rules.DIURNAL_ANALYSIS, "FORBIDDEN")
