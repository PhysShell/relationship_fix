"""Self-tests for the mutation harness, which is now trusted test infrastructure.

It already shipped one silent defect — the collector walked the AST pre-order
and the transformer post-order, so index `i` mutated a different point from the
one the report named, and every survivor line was fiction. It was caught by
luck: a survivor that could not possibly have survived. Luck is not a control.

Two classes of check live here. First, that the mutator mutates the point it
claims. Second, that a mutant which merely BREAKS the run is never counted as a
mutant the tests caught — otherwise a perfect score can be earned by snapping
the import graph, which looks magnificent and certifies the state of the
electricity supply.
"""

import ast
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools import mutate
from tools.mutate import Verdict

SAMPLE = textwrap.dedent('''
    def outer(a, b, c):
        return a + (b - c)

    def guard(x, cap):
        return x <= cap and x == 0

    def pick(a, b):
        return min(a, b) if True else max(a, b)
''')


class LocationFidelityTests(unittest.TestCase):
    """Index i must mutate the point index i describes."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / "sample.py").write_text(SAMPLE, encoding="utf-8")
        self.addCleanup(self.dir.cleanup)
        self.mutants = mutate.mutants_for("sample.py", self.root)

    def describe(self, source: str):
        collector = mutate._Collect()
        collector.visit(ast.parse(source))
        return collector.points

    def test_every_mutant_changes_exactly_the_point_it_names(self):
        """Not just "something changed" and not just the count: the mutated
        source, re-collected, must show the inverse operator AT THAT INDEX and
        every other point untouched."""
        before = self.describe(SAMPLE)
        for mutant in self.mutants:
            after = self.describe(mutate._source_with("sample.py", mutant.index, self.root))
            self.assertEqual(len(after), len(before), f"point count moved at {mutant}")
            for i, (was, now) in enumerate(zip(before, after)):
                if i == mutant.index:
                    self.assertNotEqual(was[1], now[1], f"{mutant} did not change its own point")
                    self.assertEqual(now[1], _inverse(was[1]), f"{mutant} changed the wrong way")
                else:
                    self.assertEqual(was[1], now[1], f"{mutant} also changed point {i}")

    def test_the_collector_and_the_applier_agree_on_order(self):
        """The regression for the pre-order/post-order defect. In `a + (b - c)`
        the outer Add is point 0; an applier that recursed first would give it
        to the inner Sub."""
        first = self.mutants[0]
        self.assertEqual(first.description, "Add -> Sub")
        mutated = mutate._source_with("sample.py", 0, self.root)
        self.assertIn("a - (b - c)", mutated)

    def test_no_mutant_is_a_no_op(self):
        original = ast.unparse(ast.parse(SAMPLE))
        for mutant in self.mutants:
            self.assertNotEqual(mutate._source_with("sample.py", mutant.index, self.root),
                                original, f"{mutant} produced identical source")

    def test_every_mutant_is_still_parseable_python(self):
        for mutant in self.mutants:
            ast.parse(mutate._source_with("sample.py", mutant.index, self.root))

    def test_reported_lines_point_at_real_lines(self):
        lines = SAMPLE.splitlines()
        for mutant in self.mutants:
            self.assertTrue(1 <= mutant.line <= len(lines) + 1, f"{mutant} line out of range")


def _inverse(description: str) -> str:
    left, right = description.split(" -> ")
    return f"{right} -> {left}"


class VerdictClassificationTests(unittest.TestCase):
    """Three verdicts are NOT "the tests caught it"."""

    GREEN = "..........\n----\nRan 10 tests in 0.1s\n\nOK\n"
    RED = "..F.......\n----\nRan 10 tests in 0.1s\n\nFAILED (failures=1)\n"
    BROKEN_IMPORT = ("E\n----\nRan 1 test in 0.0s\n\nERROR: "
                     "Failed to import test module: test_thing\nImportError: boom\n")

    def test_a_full_green_run_is_a_survivor(self):
        self.assertIs(mutate.classify(0, self.GREEN, baseline_tests=10), Verdict.SURVIVED)

    def test_a_full_red_run_is_a_kill(self):
        self.assertIs(mutate.classify(1, self.RED, baseline_tests=10), Verdict.KILLED)

    def test_a_broken_import_is_not_a_kill(self):
        self.assertIs(mutate.classify(1, self.BROKEN_IMPORT, baseline_tests=10),
                      Verdict.NOT_VIABLE)

    def test_a_short_run_is_not_a_kill_even_without_an_import_message(self):
        """Fewer tests than the baseline means something was not collected."""
        short = "....\n----\nRan 4 tests in 0.1s\n\nFAILED (failures=1)\n"
        self.assertIs(mutate.classify(1, short, baseline_tests=10), Verdict.NOT_VIABLE)

    def test_a_timeout_is_not_a_kill(self):
        self.assertIs(mutate.classify(1, self.RED, baseline_tests=10, timed_out=True),
                      Verdict.TIMED_OUT)

    def test_a_runner_that_never_reported_is_not_a_kill(self):
        self.assertIs(mutate.classify(None, "", baseline_tests=10), Verdict.CRASHED)
        self.assertIs(mutate.classify(1, "segmentation fault", baseline_tests=10),
                      Verdict.CRASHED)

    def test_the_score_divides_by_conclusive_mutants_not_by_all_of_them(self):
        report = mutate.Report(verdicts={
            Verdict.KILLED: [object()] * 3,
            Verdict.SURVIVED: [object()],
            Verdict.NOT_VIABLE: [object()] * 6,
        }, seconds=0.0)
        self.assertEqual(report.total, 10)
        self.assertEqual(report.conclusive, 4)
        self.assertEqual(report.score, 0.75)   # not 3/10, and not 9/10


# ---------------------------------------------------------------------------
# end-to-end calibration against golden expectations
# ---------------------------------------------------------------------------

TARGET = textwrap.dedent('''
    def at_least(x, threshold):
        return "high" if x >= threshold else "low"

    def half(x):
        return x / 2

    def gap(a, b):
        return a - b

    def lower(a, b):
        return min(a, b)

    def both(a, b):
        return a and b

    def same(a, b):
        return a == b

    def enabled():
        return True

    def untested(x):
        return x + 1
''')

TARGET_TESTS = textwrap.dedent('''
    import unittest
    import calib_target as t

    class Tests(unittest.TestCase):
        def test_boundary(self):
            self.assertEqual(t.at_least(5, 5), "high")
        def test_half(self):
            self.assertEqual(t.half(10), 5)
        def test_gap(self):
            self.assertEqual(t.gap(10, 4), 6)
        def test_lower(self):
            self.assertEqual(t.lower(2, 7), 2)
        def test_both(self):
            self.assertIs(t.both(True, False), False)
        def test_same(self):
            self.assertIs(t.same(1, 2), False)
        def test_enabled(self):
            self.assertIs(t.enabled(), True)
''')


class CalibrationTests(unittest.TestCase):
    """Proof that the whole pipeline — locate, mutate, execute, classify,
    report — works, on a module whose answers are known in advance.

    Seven operators each have exactly one test that must catch them, and
    `untested` has none. If the harness cannot reproduce that, its verdict on
    real code is worth nothing.
    """

    def test_a_module_with_known_mutants_produces_the_known_report(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "calib_target.py").write_text(TARGET, encoding="utf-8")
            (root / "test_calib.py").write_text(TARGET_TESTS, encoding="utf-8")

            report = mutate.evaluate(["calib_target.py"], ["test_calib"], root=root)

            self.assertEqual(report.total, 8)
            self.assertEqual(len(report.of(Verdict.KILLED)), 7)
            self.assertEqual(len(report.of(Verdict.NOT_VIABLE)), 0)
            self.assertEqual(len(report.of(Verdict.TIMED_OUT)), 0)
            self.assertEqual(len(report.of(Verdict.CRASHED)), 0)

            survivors = report.of(Verdict.SURVIVED)
            self.assertEqual(len(survivors), 1)
            self.assertEqual(survivors[0].description, "Add -> Sub")
            self.assertIn("untested", TARGET.splitlines()[survivors[0].line - 2])

            # and the sources are back exactly as written
            self.assertEqual((root / "calib_target.py").read_text(encoding="utf-8"), TARGET)

    def test_a_red_baseline_is_refused_rather_than_scored(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "calib_target.py").write_text(TARGET, encoding="utf-8")
            (root / "test_calib.py").write_text(
                TARGET_TESTS + "\n    def test_broken(self):\n        self.fail('red')\n",
                encoding="utf-8")
            with self.assertRaises(RuntimeError):
                mutate.evaluate(["calib_target.py"], ["test_calib"], root=root)


if __name__ == "__main__":
    unittest.main()
