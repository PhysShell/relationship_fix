"""Fail-closed проверки графа против настоящего репозитория.

Правило слоя: verifier не имеет права «предположить». Любая ссылка, которую он
не смог разрешить по диску, — провал, а не предупреждение. Если он перестанет
ронять сборку, он превратится в ещё один documentation-слой, который врёт
ровно так же бодро, как предыдущий, только с JSON-схемой.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .compiler import (
    ONTOLOGY_VERSION,
    Compilation,
    CompileError,
    compile_spec_dir,
    emit_fixtures,
    emit_graph,
    emit_ontology,
)
from .parser import SpecSyntaxError, parse_spec_file
from .schema_check import SchemaError, validate
from .graph import Graph
from .ir import (
    ACYCLIC_RELATIONS,
    KIND_CODE,
    KIND_DATA,
    KIND_DOC,
    KIND_EXAMPLE,
    KIND_GENERATED,
    KIND_LABEL,
    KIND_ONTOLOGY,
    KIND_TEST,
    KIND_UNIT,
    RELATIONS,
    SYMMETRIC_RELATIONS,
)
from .refs import Ref, RefSyntaxError, parse_ref

WORKING_LANGUAGES = ("ru", "en")

UNIT_ENUM_FILE = "src/RelationshipFix.Domain/Ontology/UnitOfAnalysis.cs"
DIRECTIONALITY_ENUM_FILE = "src/RelationshipFix.Domain/Ontology/Directionality.cs"
SMART_ENUM_MEMBER = re.compile(r'new\("([a-z_]+)"\)')

GENERATED_ONTOLOGY = "experiments/semantic-spine/generated/ontology.json"
GENERATED_GRAPH = "experiments/semantic-spine/generated/graph.json"
GENERATED_FIXTURES = "experiments/semantic-spine/generated/fixtures.json"

# Какая проверка отвечает за неразрешённую цель — зависит от типа ребра.
# «Тест объявлен, но его нет» и «просто битая ссылка» диагностируют разное.
MISSING_TARGET_CHECK = {
    "tested_by": "declared_test_missing",
    "implements": "declared_implementation_missing",
}


@dataclass(frozen=True, order=True)
class Finding:
    check: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.where}: {self.message}"


def _read_enum_members(repo: Path, relative: str) -> set[str]:
    path = repo / relative
    if not path.is_file():
        return set()
    return set(SMART_ENUM_MEMBER.findall(path.read_text(encoding="utf-8")))


def _heading_exists(text: str, anchor: str) -> bool:
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") and stripped.lstrip("#").strip() == anchor:
            return True
    return False


def _symbol_exists(text: str, symbol: str) -> bool:
    # Символ может быть объявлен как `Foo.Bar`; проверяем последний сегмент как
    # целое слово — этого достаточно, чтобы поймать удалённый/переименованный.
    leaf = symbol.rsplit(".", 1)[-1]
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(leaf)}(?![A-Za-z0-9_])", text) is not None


class Verifier:
    def __init__(self, repo_root: Path, spec_dir: Path) -> None:
        self.repo = repo_root
        self.spec_dir = spec_dir
        self.units = _read_enum_members(repo_root, UNIT_ENUM_FILE)
        self.directionalities = _read_enum_members(repo_root, DIRECTIONALITY_ENUM_FILE)

    # --- разрешение ссылок -------------------------------------------------

    def resolve(self, ref: Ref) -> str | None:
        """None — цель существует. Иначе — причина, по которой не существует."""

        if ref.kind == KIND_UNIT:
            if not self.units:
                return f"cannot read the unit enum at {UNIT_ENUM_FILE}"
            if ref.locator not in self.units:
                return f"unit '{ref.locator}' is not a member of {UNIT_ENUM_FILE}"
            return None

        if ref.kind == KIND_ONTOLOGY:
            path = self.repo / "data/ontology" / f"{ref.locator}.json"
            if not path.is_file():
                return f"no ontology artifact at data/ontology/{ref.locator}.json"
            declared = json.loads(path.read_text(encoding="utf-8")).get("ontology_version")
            if declared != ref.locator:
                return f"ontology artifact declares ontology_version '{declared}'"
            return None

        if not ref.is_path:
            return f"reference kind '{ref.kind}' is not resolvable against the repository"

        path = self.repo / ref.locator
        if not path.is_file():
            return f"no such file: {ref.locator}"
        if ref.anchor is None:
            return None

        text = path.read_text(encoding="utf-8", errors="replace")
        if ref.kind == KIND_DOC:
            if not _heading_exists(text, ref.anchor):
                return f"no heading '{ref.anchor}' in {ref.locator}"
            return None
        if not _symbol_exists(text, ref.anchor):
            return f"no symbol '{ref.anchor}' in {ref.locator}"
        return None

    # --- проверки ----------------------------------------------------------

    def verify(self, compilation: Compilation, spec_dir: Path | None = None) -> list[Finding]:
        findings: list[Finding] = []
        graph = Graph(compilation.entities, compilation.edges)

        findings += self._check_edges(compilation, graph)
        findings += self._check_symmetry(graph)
        findings += self._check_cycles(graph)
        findings += self._check_labels(compilation, graph)
        findings += self._check_generated(compilation)
        findings += self._check_block_schema(spec_dir or self.spec_dir)
        return sorted(set(findings))

    def _kind_of(self, node: str, compilation: Compilation) -> tuple[str | None, str | None]:
        entity = compilation.entities.get(node)
        if entity is not None:
            return entity.kind, None
        try:
            return parse_ref(node).kind, None
        except RefSyntaxError as exc:
            return None, str(exc)

    def _check_edges(self, compilation: Compilation, graph: Graph) -> list[Finding]:
        findings: list[Finding] = []
        seen: set[tuple[str, str, str]] = set()

        for edge in compilation.edges:
            where = str(edge.source) if edge.source else "<unknown>"

            if edge.key() in seen:
                findings.append(
                    Finding("duplicate_edge", where, f"edge {edge.source_id} -{edge.relation}-> {edge.target_id} declared twice")
                )
                continue
            seen.add(edge.key())

            source_kind, source_error = self._kind_of(edge.source_id, compilation)
            target_kind, target_error = self._kind_of(edge.target_id, compilation)
            for side, error in (("from", source_error), ("to", target_error)):
                if error:
                    findings.append(Finding("dangling_reference", where, f"{side}: {error}"))
            if source_kind is None or target_kind is None:
                continue

            if (source_kind, target_kind) not in RELATIONS[edge.relation]:
                allowed = ", ".join(sorted(f"{a}->{b}" for a, b in RELATIONS[edge.relation]))
                findings.append(
                    Finding(
                        "illegal_edge_type",
                        where,
                        f"'{edge.relation}' cannot go {source_kind}->{target_kind}; allowed: {allowed}",
                    )
                )

            for node in (edge.source_id, edge.target_id):
                findings += self._check_endpoint(node, edge, compilation, where)

            expected = edge.attributes.get("sha256")
            if expected:
                findings += self._check_digest(edge, expected, where)

        return findings

    def _check_endpoint(self, node: str, edge, compilation: Compilation, where: str) -> list[Finding]:
        if node in compilation.entities and compilation.entities[node].kind in (KIND_LABEL, KIND_EXAMPLE, KIND_GENERATED):
            return []
        try:
            ref = parse_ref(node)
        except RefSyntaxError as exc:
            return [Finding("dangling_reference", where, str(exc))]

        if ref.kind in (KIND_LABEL, KIND_EXAMPLE):
            if node not in compilation.entities:
                check = MISSING_TARGET_CHECK.get(edge.relation, "dangling_reference")
                return [Finding(check, where, f"no spec declares {node}")]
            return []

        problem = self.resolve(ref)
        if problem is None:
            return []
        check = MISSING_TARGET_CHECK.get(edge.relation, "dangling_reference")
        return [Finding(check, where, problem)]

    def _check_digest(self, edge, expected: str, where: str) -> list[Finding]:
        try:
            ref = parse_ref(edge.target_id)
        except RefSyntaxError as exc:
            return [Finding("dangling_reference", where, str(exc))]
        if not ref.is_path:
            return [Finding("stale_evidence", where, f"sha256 declared for a non-file target {edge.target_id}")]
        path = self.repo / ref.locator
        if not path.is_file():
            return [Finding("stale_evidence", where, f"no such file: {ref.locator}")]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            return [
                Finding(
                    "stale_evidence",
                    where,
                    f"{ref.locator} has sha256 {actual}, the spec pins {expected}",
                )
            ]
        return []

    def _check_symmetry(self, graph: Graph) -> list[Finding]:
        findings: list[Finding] = []
        present = {edge.key() for edge in graph.edges}
        for edge in graph.edges:
            if edge.relation not in SYMMETRIC_RELATIONS:
                continue
            mirror = (edge.target_id, edge.relation, edge.source_id)
            if mirror not in present:
                findings.append(
                    Finding(
                        "asymmetric_relation",
                        str(edge.source) if edge.source else "<unknown>",
                        f"'{edge.relation}' is symmetric but {edge.target_id} does not declare it back to {edge.source_id}",
                    )
                )
        return findings

    def _check_cycles(self, graph: Graph) -> list[Finding]:
        findings: list[Finding] = []
        for cycle in graph.find_cycles(ACYCLIC_RELATIONS):
            findings.append(
                Finding(
                    "forbidden_cycle",
                    "<graph>",
                    "cycle over acyclic relations: " + " -> ".join(cycle),
                )
            )
        return findings

    def _check_labels(self, compilation: Compilation, graph: Graph) -> list[Finding]:
        findings: list[Finding] = []
        for label in compilation.labels:
            where = str(label.source) if label.source else "<unknown>"
            label_id = label.attributes["id"]
            allowed_units = set(label.attributes["allowed_units"])

            for unit in label.attributes["allowed_units"]:
                if self.units and unit not in self.units:
                    findings.append(
                        Finding("dangling_reference", where, f"allowed_units has unknown unit '{unit}'")
                    )
            directionality = label.attributes["directionality"]
            if self.directionalities and directionality not in self.directionalities:
                findings.append(
                    Finding(
                        "dangling_reference",
                        where,
                        f"directionality '{directionality}' is not a member of {DIRECTIONALITY_ENUM_FILE}",
                    )
                )

            examples = [
                compilation.entities[edge.source_id]
                for edge in graph.in_edges(label.id, ["exemplifies"])
                if edge.source_id in compilation.entities
            ]

            verdicts = {example.attributes["verdict"] for example in examples}
            for needed in ("positive", "negative"):
                if needed not in verdicts:
                    findings.append(
                        Finding("missing_required_example", where, f"{label_id} has no {needed} example")
                    )

            languages = {example.attributes["language"] for example in examples}
            for language in WORKING_LANGUAGES:
                if language not in languages:
                    findings.append(
                        Finding("language_coverage", where, f"{label_id} has no '{language}' example")
                    )
            for example in examples:
                ex_where = str(example.source) if example.source else where
                if example.attributes["language"] not in WORKING_LANGUAGES:
                    findings.append(
                        Finding(
                            "language_coverage",
                            ex_where,
                            f"example language '{example.attributes['language']}' is not a working language",
                        )
                    )
                if example.attributes["unit"] not in allowed_units:
                    findings.append(
                        Finding(
                            "example_unit_not_allowed",
                            ex_where,
                            f"example unit '{example.attributes['unit']}' is not in allowed_units of {label_id}",
                        )
                    )
                if example.attributes["verdict"] not in ("positive", "negative", "ambiguous"):
                    findings.append(
                        Finding(
                            "unknown_verdict",
                            ex_where,
                            f"example verdict '{example.attributes['verdict']}' is not positive/negative/ambiguous",
                        )
                    )
        return findings

    def _check_generated(self, compilation: Compilation) -> list[Finding]:
        findings: list[Finding] = []
        for relative in (GENERATED_ONTOLOGY, GENERATED_GRAPH, GENERATED_FIXTURES):
            path = self.repo / relative
            if not path.is_file():
                findings.append(
                    Finding("generated_stale", relative, "generated artifact is missing; run `spine compile`")
                )
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                findings.append(Finding("generated_stale", relative, f"not valid JSON: {exc}"))
                continue

            # Сравниваем ПОЛНОЕ содержимое, а не только spec_digest: дайджест
            # считается по spec/*.md, поэтому правка руками внутри самого
            # generated-файла его не двигает и прошла бы мимо проверки.
            if relative == GENERATED_ONTOLOGY:
                expected = emit_ontology(compilation, ONTOLOGY_VERSION)
            elif relative == GENERATED_GRAPH:
                expected = emit_graph(compilation)
            else:
                expected = emit_fixtures(compilation)

            if payload != expected:
                digest = payload.get("spec_digest")
                detail = (
                    f"spec_digest {digest} != {compilation.spec_digest}"
                    if digest is not None and digest != compilation.spec_digest
                    else "content does not match the spec; it was edited by hand"
                )
                findings.append(Finding("generated_stale", relative, f"{detail}; run `spine compile`"))
        return findings

    def _check_block_schema(self, spec_dir: Path) -> list[Finding]:
        """Блоки обязаны проходить schema/block.schema.json.

        Компилятор проверяет форму объявления, схема — закрытые множества
        значений (status, verdict, unit). Без этого `status: experimental`
        спокойно доезжает до сгенерированной онтологии.
        """

        schema_path = self.repo / "experiments/semantic-spine/schema/block.schema.json"
        if not schema_path.is_file():
            return [Finding("schema_violation", "schema/block.schema.json", "block schema is missing")]
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        definitions = schema.get("definitions", {})

        findings: list[Finding] = []
        for path in sorted(spec_dir.glob("*.md")):
            display = f"spec/{path.name}"
            try:
                doc = parse_spec_file(path, repo_relative=display)
            except SpecSyntaxError as exc:
                findings.append(Finding("spec_compile", display, exc.message))
                continue
            for section in doc.sections:
                for block in section.blocks:
                    where = f"{display}:{block.line_start}"
                    if block.kind not in definitions:
                        findings.append(
                            Finding("schema_violation", where, f"no schema for block '{block.kind}'")
                        )
                        continue
                    try:
                        errors = validate(block.fields, definitions[block.kind], schema)
                    except SchemaError as exc:
                        findings.append(Finding("schema_violation", where, str(exc)))
                        continue
                    findings += [Finding("schema_violation", where, error) for error in errors]
        return findings


def verify_spec_dir(repo_root: Path, spec_dir: Path) -> list[Finding]:
    """Единая точка входа: компиляция + проверки, обе fail-closed."""

    verifier = Verifier(repo_root, spec_dir)
    try:
        compilation = compile_spec_dir(spec_dir)
    except CompileError as exc:
        return [Finding(exc.check, str(spec_dir), str(exc))]
    return verifier.verify(compilation, spec_dir)
