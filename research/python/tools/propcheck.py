"""A property harness in the standard library, because ADR-0001 §Python says
`dependencies = []` and one documented exception, and this is not it.

What a real property library gives you and this gives you too: many generated
cases, boundary-biased generation, automatic shrinking to a minimal falsifying
case, and a seed that reproduces the run. What it does not give you: clever
integrated shrinking, a generator combinator algebra, or coverage guidance. The
generators here are domain-specific on purpose — this file stays small enough
to read, so it cannot become a second thing to trust.

Lives in `tools/` rather than `tests/` so that it imports the same way
under `unittest discover -s tests` and under `python -m unittest tests.<module>`
— the mutation runner uses the second form.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")

#: Nothing is drawn uniformly. Uniform sampling finds `opened_at + H ==
#: period_end` shortly after the Sun runs out of hydrogen.
BOUNDARY_WEIGHT = 0.55


class Falsified(AssertionError):
    """Carries the shrunk case and the seed that produced it."""

    def __init__(self, name: str, case, seed: int, tried: int, reason: str | None):
        self.case, self.seed, self.tried, self.reason = case, seed, tried, reason
        detail = f"\n  reason: {reason}" if reason else ""
        super().__init__(
            f"property {name!r} falsified after {tried} case(s)"
            f"\n  seed:   {seed}   (rerun with seed={seed})"
            f"\n  case:   {case}{detail}"
        )


@dataclass(frozen=True, slots=True)
class Outcome:
    """A property returns this, so `vacuous` never silently reads as a pass."""

    held: bool | None          # None = the case did not exercise the property
    reason: str | None = None

    @staticmethod
    def ok() -> "Outcome":
        return Outcome(held=True)

    @staticmethod
    def fail(reason: str) -> "Outcome":
        return Outcome(held=False, reason=reason)

    @staticmethod
    def vacuous() -> "Outcome":
        return Outcome(held=None)


def check(
    name: str,
    generate: Callable[[random.Random], T],
    holds: Callable[[T], Outcome],
    shrink: Callable[[T], Iterable[T]],
    *,
    cases: int = 400,
    seed: int | None = None,
    min_effective: int = 1,
) -> int:
    """Run `holds` over generated cases; shrink and raise on the first failure.

    Returns the number of cases that actually exercised the property. A property
    whose every case came back vacuous is a failure, not a pass — that is the
    classic way a green suite proves nothing at all.
    """
    seed = random.randrange(2 ** 31) if seed is None else seed
    rng = random.Random(seed)
    effective = 0
    for attempt in range(1, cases + 1):
        case = generate(rng)
        outcome = holds(case)
        if outcome.held is None:
            continue
        effective += 1
        if not outcome.held:
            minimal, reason = _shrink(case, holds, shrink, outcome.reason)
            raise Falsified(name, minimal, seed, attempt, reason)
    if effective < min_effective:
        raise AssertionError(
            f"property {name!r} was vacuous in {cases} cases (seed={seed}): "
            f"{effective} effective < {min_effective} required — the generator, "
            f"not the code, is what passed"
        )
    return effective


def _shrink(case: T, holds, shrink, reason: str | None, *, rounds: int = 200):
    """Greedy delta debugging: keep any simpler case that still falsifies."""
    for _ in range(rounds):
        for candidate in shrink(case):
            outcome = holds(candidate)
            if outcome.held is False:
                case, reason = candidate, outcome.reason
                break
        else:
            break
    return case, reason


# ---------------------------------------------------------------------------
# biased primitives
# ---------------------------------------------------------------------------

def biased_float(rng: random.Random, boundaries: tuple[float, ...],
                 low: float, high: float) -> float:
    """A boundary value most of the time; a uniform draw the rest of the time."""
    if boundaries and rng.random() < BOUNDARY_WEIGHT:
        return rng.choice(boundaries)
    return rng.uniform(low, high)


def shrink_float(value: float, targets: tuple[float, ...]) -> Iterable[float]:
    """Toward the interesting values first, then halfway toward zero."""
    for target in targets:
        if target != value:
            yield target
    if value not in (0.0,):
        yield value / 2.0
        yield float(int(value))


def shrink_sequence(items: tuple) -> Iterable[tuple]:
    """Drop a half, then drop single elements — the usual ddmin opening moves."""
    n = len(items)
    if n > 2:
        yield items[: n // 2]
        yield items[n // 2:]
    for i in range(n):
        yield items[:i] + items[i + 1:]


def shrink_field(case, field: str, values: Iterable) -> Iterable:
    for value in values:
        if value != getattr(case, field):
            yield replace(case, **{field: value})
