"""S4-closure: решение записано так, чтобы его нельзя было пересказать шире.

Опасность конкретна: через месяц S5b сошлётся на S4 как на «мы наконец
откалибровали incidence». Тесты здесь следят не за кодом, а за тем, чтобы
сила утверждений не выросла сама собой.
"""

import unittest

from coarsening import q1c_result, s4_closure
from coarsening.s4_closure import Status


class EpistemicAsymmetryTests(unittest.TestCase):
    """У двух выводов S4 РАЗНЫЕ цепочки, и это структура, а не оговорка."""

    def test_the_n_claim_rests_on_measurement_plus_a_theorem(self):
        claim = next(c for c in s4_closure.CLAIMS
                     if c.key == "strict_n_incompatible")
        self.assertIn(Status.PROVED_IN_LEAN, claim.chain)
        self.assertIn(Status.EMPIRICAL, claim.chain)
        self.assertEqual(claim.weakest, Status.EMPIRICAL)

    def test_the_rmtr_claim_is_weaker_and_says_so(self):
        claim = next(c for c in s4_closure.CLAIMS
                     if c.key == "strict_rmtr_outside_envelope")
        self.assertNotIn(Status.PROVED_IN_LEAN, claim.chain)
        self.assertIn(Status.ASSUMPTION, claim.chain)
        self.assertEqual(claim.weakest, Status.ASSUMPTION)

    def test_the_two_are_not_interchangeable(self):
        """Произнести их одним предложением — ровно то, что здесь ловится."""
        n = next(c for c in s4_closure.CLAIMS if c.key == "strict_n_incompatible")
        r = next(c for c in s4_closure.CLAIMS
                 if c.key == "strict_rmtr_outside_envelope")
        self.assertNotEqual(n.chain, r.chain)
        self.assertNotEqual(n.weakest, r.weakest)


class WhatS4DidNotDoTests(unittest.TestCase):

    def test_absolute_incidence_is_still_not_measured(self):
        self.assertIn("DOCUMENTED_LIMITATION",
                      s4_closure.DECISIONS["Q1a_absolute_incidence"])
        self.assertIn("абсолютные opportunities в сутки",
                      s4_closure.NOT_CALIBRATABLE)

    def test_the_rate_stays_an_axis_not_an_input(self):
        self.assertTrue(s4_closure.OPPORTUNITY_RATE_IS_A_SENSITIVITY_AXIS)
        self.assertIn("абсолютная incidence как вход дизайна",
                      s4_closure.S5B_STILL_BLOCKED)

    def test_the_forbidden_sentences_are_recorded_verbatim(self):
        """Чтобы узнавались, а не пересказывались своими словами."""
        self.assertIn("S4 откалибровал incidence", s4_closure.FORBIDDEN_IN_S5B)
        self.assertIn("STRICT даёт консервативную оценку",
                      s4_closure.FORBIDDEN_IN_S5B)

    def test_strict_is_not_called_conservative_anywhere(self):
        """Он не консервативен: он считает ДРУГОЙ функционал."""
        self.assertIn("другой функционал",
                      s4_closure.DECISIONS["strict_on_coarse_timestamps"])


class DecisionsTests(unittest.TestCase):

    def test_bounded_is_the_policy_and_ambiguity_is_a_normal_outcome(self):
        policy = s4_closure.DECISIONS["tie_policy_for_coarse_data"]
        self.assertTrue(policy.startswith("BOUNDED"))
        self.assertIn("НОРМАЛЬНЫЙ ИСХОД", policy)

    def test_the_closure_agrees_with_the_result_artifact(self):
        """Решение и числа должны сходиться, иначе одно из них устарело."""
        self.assertEqual(s4_closure.DECISIONS["S4_Q1c"], q1c_result.STATUS)
        self.assertIn("NOT_WORTH_BUILDING",
                      s4_closure.DECISIONS["sharper_time_layer"])
        self.assertEqual(q1c_result.SHARP_TIME_LAYER, "NOT_WORTH_BUILDING")

    def test_the_boundary_question_is_deferred_not_solved(self):
        self.assertTrue(
            s4_closure.DECISIONS["n_eligible_boundary_semantics"].startswith("DEFERRED"))

    def test_s5b_is_only_partially_unblocked(self):
        self.assertEqual(s4_closure.S5B_STATUS, "PARTIALLY_UNBLOCKED")
        self.assertTrue(s4_closure.S5B_UNBLOCKED)
        self.assertTrue(s4_closure.S5B_STILL_BLOCKED)

    def test_every_freezer_item_carries_its_reason(self):
        """Морозилка без причин через месяц выглядит как список упущений."""
        for key, reason in s4_closure.FREEZER.items():
            self.assertGreater(len(reason), 20, key)
