"""Ссылки на сущности: `<kind>:<locator>[#<anchor>]`.

Идентификатор сущности — сама ссылка. Это даёт глобально уникальные стабильные
id без отдельного реестра и делает dangling reference обнаружимым: разрешение
внешних целей идёт по настоящему репозиторию, а не по списку в голове.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ir import (
    KIND_CODE,
    KIND_DATA,
    KIND_DOC,
    KIND_EXAMPLE,
    KIND_GENERATED,
    KIND_LABEL,
    KIND_ONTOLOGY,
    KIND_TEST,
    KIND_UNIT,
)

# Префикс ссылки → kind сущности. Закрытое множество: неизвестный префикс не
# «считается документом», а роняет разбор.
REF_KINDS = {
    "label": KIND_LABEL,
    "example": KIND_EXAMPLE,
    "unit": KIND_UNIT,
    "doc": KIND_DOC,
    "code": KIND_CODE,
    "test": KIND_TEST,
    "data": KIND_DATA,
    "ontology": KIND_ONTOLOGY,
    "generated": KIND_GENERATED,
}

# Цели, которые обязаны существовать на диске репозитория.
PATH_KINDS = frozenset({KIND_DOC, KIND_CODE, KIND_TEST, KIND_DATA, KIND_GENERATED})


class RefSyntaxError(ValueError):
    pass


@dataclass(frozen=True)
class Ref:
    raw: str
    prefix: str
    kind: str
    locator: str
    anchor: str | None

    @property
    def is_path(self) -> bool:
        return self.kind in PATH_KINDS


def parse_ref(raw: str) -> Ref:
    text = raw.strip()
    if not text:
        raise RefSyntaxError("empty reference")

    prefix, sep, rest = text.partition(":")
    if not sep:
        raise RefSyntaxError(f"reference {raw!r} has no '<kind>:' prefix")
    if prefix not in REF_KINDS:
        known = ", ".join(sorted(REF_KINDS))
        raise RefSyntaxError(f"reference {raw!r} has unknown kind {prefix!r}; known kinds: {known}")
    if not rest:
        raise RefSyntaxError(f"reference {raw!r} has an empty locator")

    locator, hash_sep, anchor = rest.partition("#")
    if hash_sep and not anchor:
        raise RefSyntaxError(f"reference {raw!r} has an empty anchor after '#'")
    if not locator:
        raise RefSyntaxError(f"reference {raw!r} has an empty locator")

    kind = REF_KINDS[prefix]
    if kind in PATH_KINDS and (locator.startswith("/") or ".." in locator.split("/")):
        raise RefSyntaxError(f"reference {raw!r} must use a repo-relative path without '..'")

    return Ref(raw=text, prefix=prefix, kind=kind, locator=locator, anchor=anchor or None)
