"""Document IR: сущности, типизированные рёбра и их происхождение в исходнике.

Инвариант слоя: любая сущность и любое ребро знают файл и строки, из которых
пришли. Без source_span verifier умеет только сказать «что-то не так», а нам
нужно «строка 31 файла spec/B.VALIDATION.md врёт».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# --- kinds ------------------------------------------------------------------

KIND_LABEL = "label"
KIND_EXAMPLE = "example"
KIND_UNIT = "unit"
KIND_DOC = "doc"
KIND_CODE = "code"
KIND_TEST = "test"
KIND_DATA = "data"
KIND_ONTOLOGY = "ontology"
KIND_GENERATED = "generated"

ENTITY_KINDS = frozenset(
    {
        KIND_LABEL,
        KIND_EXAMPLE,
        KIND_UNIT,
        KIND_DOC,
        KIND_CODE,
        KIND_TEST,
        KIND_DATA,
        KIND_ONTOLOGY,
        KIND_GENERATED,
    }
)

# --- relations --------------------------------------------------------------

# Типизированность рёбер — это и есть отличие harness от «папки с ссылками».
# Пара (kind источника, kind цели) закрыта: ребро вне таблицы = illegal_edge_type.
RELATIONS: Mapping[str, frozenset[tuple[str, str]]] = {
    "confusable_with": frozenset({(KIND_LABEL, KIND_LABEL)}),
    "implements": frozenset({(KIND_CODE, KIND_LABEL), (KIND_CODE, KIND_UNIT)}),
    "specified_by": frozenset({(KIND_LABEL, KIND_DOC), (KIND_UNIT, KIND_DOC)}),
    "tested_by": frozenset({(KIND_LABEL, KIND_TEST), (KIND_CODE, KIND_TEST)}),
    "evidenced_by": frozenset({(KIND_LABEL, KIND_DATA)}),
    "depends_on": frozenset({(KIND_LABEL, KIND_UNIT), (KIND_LABEL, KIND_LABEL)}),
    "supersedes": frozenset({(KIND_ONTOLOGY, KIND_ONTOLOGY)}),
    "materialized_in": frozenset({(KIND_LABEL, KIND_ONTOLOGY)}),
    "generated_from": frozenset({(KIND_GENERATED, KIND_LABEL), (KIND_GENERATED, KIND_DOC)}),
    "exemplifies": frozenset({(KIND_EXAMPLE, KIND_LABEL)}),
}

# Рёбра, по которым цикл — дефект, а не факт. confusable_with симметрично
# по определению, поэтому в список не входит.
ACYCLIC_RELATIONS = frozenset({"depends_on", "supersedes", "generated_from", "implements"})

# Рёбра, которые обязаны быть симметричными.
SYMMETRIC_RELATIONS = frozenset({"confusable_with"})


@dataclass(frozen=True, order=True)
class SourceSpan:
    """Где именно в исходнике это объявлено. 1-based, конец включительно."""

    file: str
    line_start: int
    line_end: int

    def __str__(self) -> str:  # pragma: no cover - формат сообщений
        return f"{self.file}:{self.line_start}-{self.line_end}"


@dataclass(frozen=True)
class Entity:
    id: str
    kind: str
    prose: Mapping[str, str] = field(default_factory=dict)
    attributes: Mapping[str, Any] = field(default_factory=dict)
    source: SourceSpan | None = None

    def __post_init__(self) -> None:
        if self.kind not in ENTITY_KINDS:
            raise ValueError(f"unknown entity kind {self.kind!r}")


@dataclass(frozen=True)
class Edge:
    source_id: str
    relation: str
    target_id: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    source: SourceSpan | None = None

    def __post_init__(self) -> None:
        if self.relation not in RELATIONS:
            raise ValueError(f"unknown relation {self.relation!r}")

    def key(self) -> tuple[str, str, str]:
        return (self.source_id, self.relation, self.target_id)


@dataclass(frozen=True)
class DocumentIr:
    """Результат разбора одного spec-файла."""

    path: str
    entities: Sequence[Entity]
    edges: Sequence[Edge]
