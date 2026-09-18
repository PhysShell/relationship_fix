"""Mutation testing for the estimand-critical surface, in the standard library.

The question the normal suite cannot answer: if someone broke the
implementation, would any of these tests notice? A mutant that survives is a
line of code with no test behind it, however many green ticks surround it.

Operators are the ones that match this project's actual defect history:
comparison boundaries (`<=` vs `<`), arithmetic (`+`/`-`, `*`/`/`), boolean
connectives, literal truth, and `min`/`max` — the last because clipping at the
horizon is one call away from being clipping at the wrong end.

Runs each mutant with bytecode writing OFF and `__pycache__` cleared. That is
not hygiene theatre: an earlier manual run of this exercise produced a FALSE
PASS when a mutated line happened to match the original's length and land in
the same mtime second, so CPython reused the mutant's `.pyc` for the restored
source.

    python -m tools.mutate                     # default surface, extractor tests
    python -m tools.mutate --list              # count mutants, run nothing
"""

from __future__ import annotations

import argparse
import ast
import atexit
import copy
import os
import shutil
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where a surviving mutant actually matters. Everything else is out of scope
#: on purpose: whole-repository mutation testing is slower than a sedated sloth
#: and buries the real survivors under noise.
#: The engine set. Everything here is downstream of the extractor, so a mutant
#: in it gets the whole set rather than a guessed subset.
TESTS = (
    "tests.test_acquisition_pipeline",
    "tests.test_certificate",
    "tests.test_extractor",
    "tests.test_estimands",
    "tests.test_extractor_properties",
    "tests.test_maichat_adapter",
)

#: The simulation harness is not imported by any of the above, so running them
#: against its mutants could only ever produce survivors — and a survivor that
#: no test COULD have killed is not a finding, it is padding. Narrowing the set
#: per file can only turn KILLED into SURVIVED, never the reverse, so it is the
#: conservative direction.
SIMULATION_TESTS = ("tests.test_simulation",)

SURFACE = {
    "extractor/model.py": TESTS,
    "extractor/extract.py": TESTS,
    "extractor/estimands.py": TESTS,
    "acquisition/model.py": TESTS,
    "acquisition/telegram.py": TESTS,
    "acquisition/pipeline.py": TESTS,
    "acquisition/certificate.py": TESTS,
    "simulation/process.py": SIMULATION_TESTS,
    "simulation/recovery.py": SIMULATION_TESTS,
    "simulation/interval.py": SIMULATION_TESTS,
}

_SWAPS = {
    ast.Add: ast.Sub, ast.Sub: ast.Add,
    ast.Mult: ast.Div, ast.Div: ast.Mult,
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.And: ast.Or, ast.Or: ast.And,
}
_FUNCS = {"min": "max", "max": "min"}


@dataclass(frozen=True)
class Mutant:
    path: str
    index: int
    line: int
    description: str


class _Collect(ast.NodeVisitor):
    def __init__(self):
        self.points: list[tuple[int, str]] = []

    def _note(self, node, description):
        self.points.append((getattr(node, "lineno", 0), description))

    def visit_BinOp(self, node):
        if type(node.op) in _SWAPS:
            self._note(node, f"{type(node.op).__name__} -> {_SWAPS[type(node.op)].__name__}")
        self.generic_visit(node)

    def visit_Compare(self, node):
        for op in node.ops:
            if type(op) in _SWAPS:
                self._note(node, f"{type(op).__name__} -> {_SWAPS[type(op)].__name__}")
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        if type(node.op) in _SWAPS:
            self._note(node, f"{type(node.op).__name__} -> {_SWAPS[type(node.op)].__name__}")
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, bool):
            self._note(node, f"{node.value} -> {not node.value}")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            self._note(node, f"{node.func.id}() -> {_FUNCS[node.func.id]}()")
        self.generic_visit(node)


class _Apply(ast.NodeTransformer):
    """Applies exactly the mutation at `target`.

    Counts in the SAME order as `_Collect`: note first, recurse second. Getting
    this wrong is silent and total — the collector walks pre-order, so an
    applier that recursed first would mutate a different point from the one it
    reported, and every survivor line in the report would be fiction. Found by
    a survivor whose mutation could not possibly have survived.
    """

    def __init__(self, target: int):
        self.target, self.seen = target, 0

    def _hit(self):
        self.seen += 1
        return self.seen - 1 == self.target

    def visit_BinOp(self, node):
        if type(node.op) in _SWAPS and self._hit():
            node.op = _SWAPS[type(node.op)]()
        self.generic_visit(node)
        return node

    def visit_Compare(self, node):
        for i, op in enumerate(node.ops):
            if type(op) in _SWAPS and self._hit():
                node.ops[i] = _SWAPS[type(op)]()
        self.generic_visit(node)
        return node

    def visit_BoolOp(self, node):
        if type(node.op) in _SWAPS and self._hit():
            node.op = _SWAPS[type(node.op)]()
        self.generic_visit(node)
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, bool) and self._hit():
            return ast.copy_location(ast.Constant(value=not node.value), node)
        return node

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in _FUNCS and self._hit():
            node.func = ast.copy_location(ast.Name(id=_FUNCS[node.func.id], ctx=node.func.ctx), node.func)
        self.generic_visit(node)
        return node


def mutants_for(path: str, root: Path = None) -> list[Mutant]:
    tree = ast.parse(((root or ROOT) / path).read_text(encoding="utf-8"))
    collector = _Collect()
    collector.visit(tree)
    # _Collect and _Apply walk in the same order, so index i is the same point
    return [Mutant(path, i, line, text) for i, (line, text) in enumerate(collector.points)]


def _source_with(path: str, index: int, root: Path = None) -> str:
    tree = ast.parse(((root or ROOT) / path).read_text(encoding="utf-8"))
    mutated = _Apply(index).visit(copy.deepcopy(tree))
    ast.fix_missing_locations(mutated)
    return ast.unparse(mutated)


def _clear_bytecode(root: Path = None) -> None:
    for cache in (root or ROOT).rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


class Verdict(Enum):
    """What happened to a mutant. Three of these are NOT "killed".

    A score that counts crashes, timeouts and collection failures as kills
    looks magnificent and certifies the state of the electricity supply. The
    whole point of the harness is to distinguish "a test noticed the change"
    from "the change stopped the tests from running".
    """

    KILLED = "killed"          # the suite ran in full and something failed
    SURVIVED = "survived"      # the suite ran in full and passed
    NOT_VIABLE = "not_viable"  # the mutant broke import/collection: no evidence
    TIMED_OUT = "timed_out"    # the suite hung: no evidence either
    CRASHED = "crashed"        # the runner itself died: no evidence at all


_RAN = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)
_IMPORT_FAILURE = re.compile(r"Failed to import test module|ImportError|SyntaxError")


def classify(returncode: int | None, output: str, *, baseline_tests: int,
             timed_out: bool = False) -> Verdict:
    """Pure, so it can be tested without running anything.

    `returncode is None` means the runner never produced one.
    """
    if timed_out:
        return Verdict.TIMED_OUT
    if returncode is None:
        return Verdict.CRASHED
    ran = _RAN.search(output)
    if ran is None:
        return Verdict.CRASHED
    if int(ran.group(1)) != baseline_tests or _IMPORT_FAILURE.search(output):
        # fewer tests than the baseline means something did not get collected,
        # which is not the same as a test objecting to the mutation
        return Verdict.NOT_VIABLE
    return Verdict.SURVIVED if returncode == 0 else Verdict.KILLED


def _run_tests(tests, root: Path, baseline_tests: int | None) -> tuple[Verdict | None, int]:
    """Returns (verdict, tests_run). `baseline_tests=None` means: measure it."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "-q", *tests],
            cwd=root, env=env, capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return Verdict.TIMED_OUT, 0
    except OSError:
        return Verdict.CRASHED, 0
    output = proc.stdout + proc.stderr
    ran = _RAN.search(output)
    count = int(ran.group(1)) if ran else 0
    if baseline_tests is None:
        return (None if proc.returncode == 0 else Verdict.KILLED), count
    return classify(proc.returncode, output, baseline_tests=baseline_tests), count


@dataclass
class Report:
    """Every mutant lands in exactly one bucket, and three of them are not
    evidence about the test suite at all."""

    verdicts: dict[Verdict, list[Mutant]]
    seconds: float

    def of(self, verdict: Verdict) -> list[Mutant]:
        return self.verdicts.get(verdict, [])

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.verdicts.values())

    @property
    def conclusive(self) -> int:
        """Killed + survived. The denominator of any honest score."""
        return len(self.of(Verdict.KILLED)) + len(self.of(Verdict.SURVIVED))

    @property
    def score(self) -> float | None:
        """killed / conclusive — NOT killed / total.

        Reads as: every mutant THIS operator set produces is detected by the
        current suite. It does not read as: the implementation is correct. A
        mutator does not invent algorithmic mistakes, a wrong estimand, or a new
        class of source semantics; it measures the suite's sensitivity to one
        space of perturbations.
        """
        return None if self.conclusive == 0 else len(self.of(Verdict.KILLED)) / self.conclusive

    def summary(self) -> str:
        parts = [f"{len(self.of(v))} {v.value}" for v in Verdict if self.of(v)]
        score = "n/a" if self.score is None else f"{self.score:.1%}"
        return (f"{len(self.of(Verdict.KILLED))}/{self.conclusive} conclusive mutants killed "
                f"({score}); {' · '.join(parts)}; {self.seconds:.0f}s")


def _test_sets(files, tests) -> dict[str, tuple[str, ...]]:
    """`tests` is either one set for every file, or a per-file mapping."""
    if isinstance(tests, dict):
        missing = [path for path in files if path not in tests]
        if missing:
            raise RuntimeError(f"no test set declared for: {', '.join(missing)}")
        return {path: tuple(tests[path]) for path in files}
    return {path: tuple(tests) for path in files}


def evaluate(files, tests, *, root: Path = None, progress: bool = False) -> Report:
    """Run every mutant of `files` against its tests. Restores sources always."""
    root = root or ROOT
    per_file = _test_sets(files, tests)
    all_mutants = [m for path in files for m in mutants_for(path, root)]
    _clear_bytecode(root)
    baselines: dict[tuple[str, ...], int] = {}
    for test_set in dict.fromkeys(per_file.values()):
        baseline_verdict, baseline_tests = _run_tests(test_set, root, None)
        if baseline_verdict is not None or baseline_tests == 0:
            raise RuntimeError(
                f"baseline is not green for {', '.join(test_set)} "
                f"({baseline_tests} tests) — fix the suite before asking it to "
                f"catch anything"
            )
        baselines[test_set] = baseline_tests

    originals = {path: (root / path).read_text(encoding="utf-8") for path in files}

    def restore():
        for path, text in originals.items():
            target = root / path
            if target.parent.is_dir():      # a temporary root may already be gone
                target.write_text(text, encoding="utf-8")
        _clear_bytecode(root)

    # last-resort guard for a SIGINT between write and restore; unregistered on
    # the way out so repeated calls do not stack closures that fire at exit
    # against directories that no longer exist
    atexit.register(restore)
    verdicts: dict[Verdict, list[Mutant]] = {}
    started = time.time()
    try:
        for n, mutant in enumerate(all_mutants, 1):
            target = root / mutant.path
            try:
                target.write_text(_source_with(mutant.path, mutant.index, root), encoding="utf-8")
                _clear_bytecode(root)
                test_set = per_file[mutant.path]
                verdict, _ = _run_tests(test_set, root, baselines[test_set])
            finally:
                target.write_text(originals[mutant.path], encoding="utf-8")
            verdicts.setdefault(verdict, []).append(mutant)
            if progress and verdict is not Verdict.KILLED:
                print(f"  {verdict.value.upper():<11} {mutant.path}:{mutant.line}  {mutant.description}")
            if progress and n % 25 == 0:
                print(f"  ... {n}/{len(all_mutants)}")
    finally:
        restore()
        atexit.unregister(restore)
    return Report(verdicts=verdicts, seconds=time.time() - started)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--files", nargs="*", default=list(SURFACE))
    args = parser.parse_args()

    if args.list:
        mutants = [m for path in args.files for m in mutants_for(path)]
        print(f"surface: {', '.join(args.files)}")
        print(f"mutants: {len(mutants)}")
        return 0

    print(f"surface: {', '.join(args.files)}")
    try:
        report = evaluate(args.files, SURFACE, progress=True)
    except RuntimeError as failure:
        print(failure)
        return 2
    print(f"\n{report.summary()}")
    for verdict in (Verdict.SURVIVED, Verdict.NOT_VIABLE, Verdict.TIMED_OUT, Verdict.CRASHED):
        for mutant in report.of(verdict):
            print(f"  {verdict.value}: {mutant.path}:{mutant.line}  {mutant.description}")
    return 1 if report.of(Verdict.SURVIVED) else 0


if __name__ == "__main__":
    raise SystemExit(main())
