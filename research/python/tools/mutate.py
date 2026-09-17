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
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where a surviving mutant actually matters. Everything else is out of scope
#: on purpose: whole-repository mutation testing is slower than a sedated sloth
#: and buries the real survivors under noise.
SURFACE = (
    "extractor/model.py",
    "extractor/extract.py",
    "extractor/estimands.py",
)

TESTS = (
    "tests.test_extractor",
    "tests.test_estimands",
    "tests.test_extractor_properties",
    "tests.test_maichat_adapter",
)

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


def mutants_for(path: str) -> list[Mutant]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    collector = _Collect()
    collector.visit(tree)
    # _Collect and _Apply walk in the same order, so index i is the same point
    return [Mutant(path, i, line, text) for i, (line, text) in enumerate(collector.points)]


def _source_with(path: str, index: int) -> str:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    mutated = _Apply(index).visit(copy.deepcopy(tree))
    ast.fix_missing_locations(mutated)
    return ast.unparse(mutated)


def _clear_bytecode() -> None:
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _run_tests() -> bool:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "-q", *TESTS],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False        # a mutant that hangs the suite is caught, not survived
    return proc.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--files", nargs="*", default=list(SURFACE))
    args = parser.parse_args()

    all_mutants = [m for path in args.files for m in mutants_for(path)]
    print(f"surface: {', '.join(args.files)}")
    print(f"mutants: {len(all_mutants)}")
    if args.list:
        return 0

    _clear_bytecode()
    if not _run_tests():
        print("BASELINE IS RED — fix the suite before asking it to catch anything")
        return 2

    survivors, started = [], time.time()
    originals = {path: (ROOT / path).read_text(encoding="utf-8") for path in args.files}

    def restore():
        for path, text in originals.items():
            (ROOT / path).write_text(text, encoding="utf-8")
        _clear_bytecode()

    atexit.register(restore)
    try:
        for n, mutant in enumerate(all_mutants, 1):
            target = ROOT / mutant.path
            try:
                target.write_text(_source_with(mutant.path, mutant.index), encoding="utf-8")
                _clear_bytecode()
                if _run_tests():
                    survivors.append(mutant)
                    print(f"  SURVIVED  {mutant.path}:{mutant.line}  {mutant.description}")
            finally:
                target.write_text(originals[mutant.path], encoding="utf-8")
            if n % 25 == 0:
                print(f"  ... {n}/{len(all_mutants)}  survivors so far: {len(survivors)}")
    finally:
        restore()

    killed = len(all_mutants) - len(survivors)
    print(f"\nkilled {killed}/{len(all_mutants)} "
          f"({killed / len(all_mutants):.1%}) in {time.time() - started:.0f}s")
    for mutant in survivors:
        print(f"  survivor: {mutant.path}:{mutant.line}  {mutant.description}")
    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
