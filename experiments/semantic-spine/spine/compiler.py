"""spec/*.md → DocumentIr → generated/*.json.

Компилятор отвечает только за структуру: он не решает, правда ли написанное,
он решает, можно ли это вообще считать объявлением. Все смысловые инварианты —
в verifier.py, чтобы «оно скомпилировалось» никогда не означало «оно верно».
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .ir import Edge, Entity, SourceSpan
from .ir import (
    KIND_EXAMPLE,
    KIND_GENERATED,
    KIND_LABEL,
    RELATIONS,
)
from .parser import SpecDocument, SpecSyntaxError, parse_spec_file
from .refs import RefSyntaxError, parse_ref

SCHEMA_VERSION = "rf.ontology.v1"
# Версия онтологии, которую воспроизводит spec. Живёт здесь, а не в cli, чтобы
# verifier не брал её из того самого файла, который проверяет.
ONTOLOGY_VERSION = "behavior-v0.1"
GRAPH_SCHEMA_VERSION = "rf.semantic-spine-graph.v1"
FIXTURES_SCHEMA_VERSION = "rf.semantic-spine-fixtures.v1"

LABEL_REQUIRED_FIELDS = (
    "id",
    "canonical_name",
    "plain_language_name_en",
    "plain_language_name_ru",
    "allowed_units",
    "directionality",
    "evidence_required",
    "source_frameworks",
    "status",
)
LABEL_OPTIONAL_FIELDS = ("confusable_with",)

EXAMPLE_REQUIRED_FIELDS = ("id", "language", "unit", "verdict", "text", "rationale")

EDGE_REQUIRED_FIELDS = ("relation", "to")
EDGE_OPTIONAL_FIELDS = ("sha256", "note", "from")

SECTION_DEFINITION = "Operational definition"
SECTION_INCLUSION = "Inclusion"
SECTION_EXCLUSION = "Exclusion"
SECTION_EXAMPLES = "Examples"
SECTION_LINKS = "Links"

GENERATED_ONTOLOGY_REF = "generated:experiments/semantic-spine/generated/ontology.json"


class CompileError(ValueError):
    """Ошибка разбора с именем проверки: verifier превращает её в Finding с тем же check id."""

    def __init__(self, message: str, check: str = "spec_compile") -> None:
        super().__init__(message)
        self.check = check


@dataclass
class Compilation:
    entities: dict[str, Entity]
    edges: list[Edge]
    labels: list[Entity]
    spec_digest: str
    spec_files: list[str]

    def label_ids(self) -> list[str]:
        return [entity.attributes["id"] for entity in self.labels]


def _require(block_fields: dict[str, Any], required: Iterable[str], allowed: Iterable[str], where: str) -> None:
    allowed_set = set(required) | set(allowed)
    for name in required:
        if name not in block_fields:
            raise CompileError(f"{where}: missing required field '{name}'")
    for name in block_fields:
        if name not in allowed_set:
            raise CompileError(f"{where}: unknown field '{name}'")


def _as_list_of_str(value: Any, where: str, field: str) -> list[str]:
    if not isinstance(value, list):
        raise CompileError(f"{where}: field '{field}' must be a list")
    for item in value:
        if not isinstance(item, str):
            raise CompileError(f"{where}: field '{field}' must contain only strings")
    return list(value)


def _as_str(value: Any, where: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompileError(f"{where}: field '{field}' must be a non-empty string")
    return value


def compile_document(doc: SpecDocument) -> tuple[list[Entity], list[Edge]]:
    label_blocks = doc.blocks_of("rf-label")
    if len(label_blocks) != 1:
        raise CompileError(f"{doc.path}: expected exactly one rf-label block, found {len(label_blocks)}")
    block = label_blocks[0]
    where = f"{doc.path}:{block.line_start}"
    _require(block.fields, LABEL_REQUIRED_FIELDS, LABEL_OPTIONAL_FIELDS, where)

    label_id = _as_str(block.fields["id"], where, "id")
    if label_id != doc.title:
        raise CompileError(f"{doc.path}: H1 title {doc.title!r} does not match rf-label id {label_id!r}")

    definition = doc.section(SECTION_DEFINITION)
    if definition is None or len(definition.paragraphs) != 1:
        raise CompileError(
            f"{doc.path}: section '{SECTION_DEFINITION}' must exist and hold exactly one paragraph"
        )

    inclusion = doc.section(SECTION_INCLUSION)
    exclusion = doc.section(SECTION_EXCLUSION)
    if inclusion is None or not inclusion.bullets:
        raise CompileError(f"{doc.path}: section '{SECTION_INCLUSION}' must exist and be a non-empty list")
    if exclusion is None or not exclusion.bullets:
        raise CompileError(f"{doc.path}: section '{SECTION_EXCLUSION}' must exist and be a non-empty list")

    evidence_required = block.fields["evidence_required"]
    if not isinstance(evidence_required, bool):
        raise CompileError(f"{where}: field 'evidence_required' must be true or false")

    label_ref = f"label:{label_id}"
    attributes: dict[str, Any] = {
        "id": label_id,
        "canonical_name": _as_str(block.fields["canonical_name"], where, "canonical_name"),
        "plain_language_name_en": _as_str(block.fields["plain_language_name_en"], where, "plain_language_name_en"),
        "plain_language_name_ru": _as_str(block.fields["plain_language_name_ru"], where, "plain_language_name_ru"),
        "operational_definition": definition.paragraphs[0],
        "allowed_units": _as_list_of_str(block.fields["allowed_units"], where, "allowed_units"),
        "directionality": _as_str(block.fields["directionality"], where, "directionality"),
        "inclusion_criteria": list(inclusion.bullets),
        "exclusion_criteria": list(exclusion.bullets),
        "confusable_with": _as_list_of_str(block.fields.get("confusable_with", []), where, "confusable_with"),
        "evidence_required": evidence_required,
        "source_frameworks": _as_list_of_str(block.fields["source_frameworks"], where, "source_frameworks"),
        "status": _as_str(block.fields["status"], where, "status"),
    }

    span = SourceSpan(doc.path, block.line_start, block.line_end)
    entities: list[Entity] = [
        Entity(
            id=label_ref,
            kind=KIND_LABEL,
            prose={
                SECTION_DEFINITION: attributes["operational_definition"],
                SECTION_INCLUSION: "\n".join(inclusion.bullets),
                SECTION_EXCLUSION: "\n".join(exclusion.bullets),
            },
            attributes=attributes,
            source=span,
        )
    ]
    edges: list[Edge] = []

    for target in attributes["confusable_with"]:
        edges.append(
            Edge(label_ref, "confusable_with", f"label:{target}", source=span)
        )
    for unit in attributes["allowed_units"]:
        edges.append(Edge(label_ref, "depends_on", f"unit:{unit}", source=span))

    examples_section = doc.section(SECTION_EXAMPLES)
    example_blocks = examples_section.blocks if examples_section else []
    for example in example_blocks:
        if example.kind != "rf-example":
            raise CompileError(
                f"{doc.path}:{example.line_start}: section '{SECTION_EXAMPLES}' may only hold rf-example blocks"
            )
        ex_where = f"{doc.path}:{example.line_start}"
        _require(example.fields, EXAMPLE_REQUIRED_FIELDS, (), ex_where)
        example_id = _as_str(example.fields["id"], ex_where, "id")
        ex_attributes = {
            "id": example_id,
            "language": _as_str(example.fields["language"], ex_where, "language"),
            "text": _as_str(example.fields["text"], ex_where, "text"),
            "unit": _as_str(example.fields["unit"], ex_where, "unit"),
            "verdict": _as_str(example.fields["verdict"], ex_where, "verdict"),
            "rationale": _as_str(example.fields["rationale"], ex_where, "rationale"),
        }
        ex_span = SourceSpan(doc.path, example.line_start, example.line_end)
        entities.append(
            Entity(
                id=f"example:{example_id}",
                kind=KIND_EXAMPLE,
                prose={"rationale": ex_attributes["rationale"], "text": ex_attributes["text"]},
                attributes=ex_attributes,
                source=ex_span,
            )
        )
        edges.append(Edge(f"example:{example_id}", "exemplifies", label_ref, source=ex_span))

    links_section = doc.section(SECTION_LINKS)
    for edge_block in links_section.blocks if links_section else []:
        edges.append(_compile_edge_block(doc, edge_block, implicit_from=label_ref))

    return entities, edges


def _compile_edge_block(doc: SpecDocument, edge_block, implicit_from: str | None):
    """rf-edge → Edge. В label-файле сторона 'from' подразумевается, в links-файле обязательна."""

    if edge_block.kind != "rf-edge":
        raise CompileError(
            f"{doc.path}:{edge_block.line_start}: section '{SECTION_LINKS}' may only hold rf-edge blocks"
        )
    edge_where = f"{doc.path}:{edge_block.line_start}"
    _require(edge_block.fields, EDGE_REQUIRED_FIELDS, EDGE_OPTIONAL_FIELDS, edge_where)
    relation = _as_str(edge_block.fields["relation"], edge_where, "relation")
    if relation not in RELATIONS:
        known = ", ".join(sorted(RELATIONS))
        raise CompileError(f"{edge_where}: unknown relation {relation!r}; known relations: {known}")
    target_raw = _as_str(edge_block.fields["to"], edge_where, "to")
    try:
        target_ref = parse_ref(target_raw)
    except RefSyntaxError as exc:
        raise CompileError(f"{edge_where}: {exc}") from exc

    edge_attributes: dict[str, Any] = {}
    if "sha256" in edge_block.fields:
        edge_attributes["sha256"] = _as_str(edge_block.fields["sha256"], edge_where, "sha256")
    if "note" in edge_block.fields:
        edge_attributes["note"] = _as_str(edge_block.fields["note"], edge_where, "note")

    edge_span = SourceSpan(doc.path, edge_block.line_start, edge_block.line_end)

    if "from" in edge_block.fields:
        source_raw = _as_str(edge_block.fields["from"], edge_where, "from")
        try:
            parse_ref(source_raw)
        except RefSyntaxError as exc:
            raise CompileError(f"{edge_where}: {exc}") from exc
        return Edge(source_raw, relation, target_raw, attributes=edge_attributes, source=edge_span)

    if implicit_from is None:
        raise CompileError(f"{edge_where}: rf-edge outside a label file must declare 'from'")

    # Направление ребра задаёт таблица RELATIONS: implements идёт от кода к
    # label'у, поэтому объявленный в label-файле implements разворачивается.
    pairs = RELATIONS[relation]
    if any(src == target_ref.kind and dst == KIND_LABEL for src, dst in pairs):
        return Edge(target_raw, relation, implicit_from, attributes=edge_attributes, source=edge_span)
    return Edge(implicit_from, relation, target_raw, attributes=edge_attributes, source=edge_span)


def compile_links_document(doc: SpecDocument) -> tuple[list[Entity], list[Edge]]:
    """Файл без rf-label: только графовые рёбра между внешними сущностями."""

    stray = [b for section in doc.sections for b in section.blocks if b.kind != "rf-edge"]
    if stray:
        raise CompileError(
            f"{doc.path}:{stray[0].line_start}: a links file may only hold rf-edge blocks, found '{stray[0].kind}'"
        )
    edge_blocks = [b for section in doc.sections for b in section.blocks]
    if not edge_blocks:
        raise CompileError(f"{doc.path}: links file declares no rf-edge blocks")
    return [], [_compile_edge_block(doc, block, implicit_from=None) for block in edge_blocks]


def compute_spec_digest(spec_files: list[Path]) -> str:
    """Дайджест всех spec-исходников: единственный вход staleness-проверки."""

    digest = hashlib.sha256()
    for path in sorted(spec_files, key=lambda p: p.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def compile_spec_dir(spec_dir: Path) -> Compilation:
    spec_files = sorted(spec_dir.glob("*.md"))
    if not spec_files:
        raise CompileError(f"{spec_dir}: no spec files found")

    entities: dict[str, Entity] = {}
    edges: list[Edge] = []
    labels: list[Entity] = []

    for path in spec_files:
        try:
            doc = parse_spec_file(path, repo_relative=f"spec/{path.name}")
        except SpecSyntaxError as exc:
            raise CompileError(str(exc)) from exc
        has_label = bool(doc.blocks_of("rf-label"))
        doc_entities, doc_edges = (
            compile_document(doc) if has_label else compile_links_document(doc)
        )
        for entity in doc_entities:
            if entity.id in entities:
                previous = entities[entity.id].source
                raise CompileError(
                    f"{entity.source}: duplicate stable id {entity.id!r} (already declared at {previous})",
                    check="duplicate_stable_id",
                )
            entities[entity.id] = entity
            if entity.kind == KIND_LABEL:
                labels.append(entity)
        edges.extend(doc_edges)

    digest = compute_spec_digest(spec_files)
    generated = Entity(
        id=GENERATED_ONTOLOGY_REF,
        kind=KIND_GENERATED,
        attributes={"spec_digest": digest},
        source=SourceSpan("spine/compiler.py", 0, 0),
    )
    entities[generated.id] = generated
    for label in labels:
        edges.append(Edge(generated.id, "generated_from", label.id, source=generated.source))

    labels.sort(key=lambda e: e.attributes["id"])
    return Compilation(
        entities=entities,
        edges=edges,
        labels=labels,
        spec_digest=digest,
        spec_files=[f"spec/{p.name}" for p in spec_files],
    )


ONTOLOGY_LABEL_FIELD_ORDER = (
    "id",
    "canonical_name",
    "plain_language_name_en",
    "plain_language_name_ru",
    "operational_definition",
    "allowed_units",
    "directionality",
    "inclusion_criteria",
    "exclusion_criteria",
    "examples",
    "confusable_with",
    "evidence_required",
    "source_frameworks",
    "status",
)
EXAMPLE_FIELD_ORDER = ("language", "text", "unit", "verdict", "rationale")


def emit_ontology(compilation: Compilation, ontology_version: str) -> dict[str, Any]:
    """Сборка rf.ontology.v1 — того же формата, что читает .NET OntologyLoader."""

    labels: list[dict[str, Any]] = []
    for label in compilation.labels:
        examples = [
            entity
            for entity in compilation.entities.values()
            if entity.kind == KIND_EXAMPLE
            and any(
                e.source_id == entity.id and e.relation == "exemplifies" and e.target_id == label.id
                for e in compilation.edges
            )
        ]
        examples.sort(key=lambda e: (e.source.file, e.source.line_start) if e.source else (e.id, 0))
        payload = dict(label.attributes)
        payload["examples"] = [
            {field: example.attributes[field] for field in EXAMPLE_FIELD_ORDER} for example in examples
        ]
        labels.append({field: payload[field] for field in ONTOLOGY_LABEL_FIELD_ORDER})

    return {"schema_version": SCHEMA_VERSION, "ontology_version": ontology_version, "labels": labels}


def emit_graph(compilation: Compilation) -> dict[str, Any]:
    entities = [
        {
            "id": entity.id,
            "kind": entity.kind,
            "source": None
            if entity.source is None
            else {
                "file": entity.source.file,
                "line_start": entity.source.line_start,
                "line_end": entity.source.line_end,
            },
            "attributes": dict(entity.attributes),
        }
        for entity in sorted(compilation.entities.values(), key=lambda e: e.id)
    ]
    edges = [
        {
            "from": edge.source_id,
            "relation": edge.relation,
            "to": edge.target_id,
            "attributes": dict(edge.attributes),
            "source": None
            if edge.source is None
            else {
                "file": edge.source.file,
                "line_start": edge.source.line_start,
                "line_end": edge.source.line_end,
            },
        }
        for edge in sorted(compilation.edges, key=lambda e: e.key())
    ]
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "spec_digest": compilation.spec_digest,
        "spec_files": compilation.spec_files,
        "entities": entities,
        "edges": edges,
    }


def emit_fixtures(compilation: Compilation) -> dict[str, Any]:
    """Плоский список примеров: тот же материал, но удобный для eval-скриптов."""

    rows: list[dict[str, Any]] = []
    for edge in sorted(compilation.edges, key=lambda e: e.key()):
        if edge.relation != "exemplifies":
            continue
        example = compilation.entities[edge.source_id]
        rows.append(
            {
                "example_id": example.attributes["id"],
                "label_id": compilation.entities[edge.target_id].attributes["id"],
                "language": example.attributes["language"],
                "unit": example.attributes["unit"],
                "verdict": example.attributes["verdict"],
                "text": example.attributes["text"],
                "rationale": example.attributes["rationale"],
            }
        )
    rows.sort(key=lambda r: r["example_id"])
    return {
        "schema_version": FIXTURES_SCHEMA_VERSION,
        "spec_digest": compilation.spec_digest,
        "examples": rows,
    }


def dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
