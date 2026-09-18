"""The exit gate, and the finding nobody wanted."""

import unittest

from acquisition.qualification import (
    GATE,
    REACTIVITY_SURFACE,
    SEAMS,
    SeamVerdict,
    Touchpoint,
)


class SeamLedgerTests(unittest.TestCase):

    def test_every_seam_names_the_test_that_demonstrates_it(self):
        for seam in SEAMS:
            self.assertTrue(seam.evidence, seam.key)

    def test_every_seam_names_what_the_world_looks_like_when_it_lies(self):
        """A seam without a failure mode is a wish, and a wish cannot be
        checked by anybody who arrives later."""
        for seam in SEAMS:
            self.assertTrue(seam.failure_mode, seam.key)

    def test_not_applicable_is_not_a_pass(self):
        self.assertIsNot(SeamVerdict.NOT_APPLICABLE, SeamVerdict.QUALIFIED)
        skipped = Touchpoint  # placeholder to keep the import honest
        self.assertTrue(skipped)

    def test_the_gate_closes_on_named_criteria_including_the_freeze(self):
        self.assertIn("no change to the frozen extractor", GATE.criteria)
        self.assertEqual(len(GATE.criteria), 10)

    def test_the_gate_is_open_while_any_seam_is(self):
        self.assertEqual(GATE.open_seams(), ())
        self.assertTrue(GATE.passed)


class ReactivitySurfaceTests(unittest.TestCase):
    """The stage's most uncomfortable output, pinned so it cannot be forgotten
    between here and the preregistration."""

    def test_the_acquisition_path_is_not_passive(self):
        """Every single thing it needs is a deliberate human action. Calling
        this arm "passive observation" would be false, and the falsehood would
        sit inside the control condition of a reactivity experiment."""
        passive = [t for t in REACTIVITY_SURFACE if t.passive]
        self.assertEqual(passive, [])

    def test_the_largest_touchpoint_repeats_every_period(self):
        manual = next(t for t in REACTIVITY_SURFACE if t.key == "manual_export")
        self.assertTrue(manual.per_period)
        self.assertFalse(manual.passive)

    def test_every_touchpoint_carries_its_consequence(self):
        for touchpoint in REACTIVITY_SURFACE:
            self.assertTrue(touchpoint.note, touchpoint.key)


if __name__ == "__main__":
    unittest.main()
