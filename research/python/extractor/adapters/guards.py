"""Checks that belong at the import boundary, not in the core extractor.

The core asks only that a stream be dyadic (`len(actors) <= 2`). That is NOT the
same question as "are these the two people the source says were talking". Two
actors, one of whom is not a declared participant, passes the core check and is
still an import bug — a mis-joined file, a group thread flattened to two
speakers, a system account counted as a person.

Kept shared rather than per-adapter so the messy adapters that come next inherit
a tested rule instead of each inventing one under deadline.
"""

from __future__ import annotations


class DyadMembershipError(ValueError):
    """A message's actor is not one of the two participants the source declared."""


def verify_dyad_membership(actors, declared: tuple[str, str], source: str) -> None:
    """Every observed actor must be one the source named. Fails closed.

    `declared` comes from the source's own conversation record, so this catches
    the case the core cannot: a stream that is dyadic but about the wrong dyad.
    """
    if len(set(declared)) != 2:
        raise DyadMembershipError(
            f"{source}: the source declared {len(set(declared))} distinct participants, not 2")
    strangers = sorted(set(actors) - set(declared))
    if strangers:
        raise DyadMembershipError(
            f"{source}: message actors not among the declared pair: {strangers}")
