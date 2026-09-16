"""Мутационный набор против самого harness'а.

Смысл теста злой и единственный: каждая мутация обязана быть поймана, иначе мы
честно узнаём, что построили красивую систему ссылок, которая врёт так же
бодро, как предыдущая. Поэтому здесь же живёт meta-проверка: у каждой
объявленной проверки verifier'а обязана быть мутация, доказывающая, что она
кусается.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Callable

from spine.verifier import Finding, verify_spec_dir

from ._harness import build_mirror

Mutation = Callable[[Path, Path], None]

# --- мутации ----------------------------------------------------------------


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"mutation target not found in {path.name}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def rename_label_in_markdown_only(spec: Path, repo: Path) -> None:
    _edit(spec / "B.VALIDATION.md", "# B.VALIDATION\n", "# B.VALIDATION_V2\n")


def delete_a_label(spec: Path, repo: Path) -> None:
    (spec / "B.REPAIR_ATTEMPT.md").unlink()


def break_confusable_with(spec: Path, repo: Path) -> None:
    _edit(spec / "B.REPAIR_ATTEMPT.md", "confusable_with:\n  - B.VALIDATION\n", "confusable_with:\n")


def change_allowed_units(spec: Path, repo: Path) -> None:
    _edit(spec / "B.VALIDATION.md", "allowed_units:\n  - utterance\n  - turn\n", "allowed_units:\n  - turn\n")


def hand_edit_generated_json(spec: Path, repo: Path) -> None:
    path = repo / "experiments/semantic-spine/generated/ontology.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["labels"][0]["canonical_name"] = "Something an agent will now believe"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rewrite_generated_ontology_version(spec: Path, repo: Path) -> None:
    # Если verifier берёт ontology_version из того же файла, который проверяет,
    # эта правка проходит мимо.
    path = repo / "experiments/semantic-spine/generated/ontology.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["ontology_version"] = "behavior-v9.9-invented"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def delete_test_target(spec: Path, repo: Path) -> None:
    (repo / "src/annotation-web/test/PilotSpec.hs").unlink()


def delete_implementation_target(spec: Path, repo: Path) -> None:
    (repo / "src/RelationshipFix.Evaluation/Slice/RuleStubAnnotator.cs").unlink()


def plant_stale_evidence(spec: Path, repo: Path) -> None:
    path = repo / "data/pilot/v0.1/items.jsonl"
    path.write_bytes(path.read_bytes() + b'{"item_id": "smuggled-in"}\n')


def contradictory_invariant(spec: Path, repo: Path) -> None:
    # implements обязан идти code -> label. Явный from разворачивает его назад.
    _edit(
        spec / "B.VALIDATION.md",
        "## Links\n",
        '## Links\n\n```rf-edge\nfrom: "label:B.VALIDATION"\nrelation: implements\n'
        'to: "code:src/annotation-web/src/Domain.hs#labelCode"\n```\n',
    )


def introduce_cycle(spec: Path, repo: Path) -> None:
    _edit(
        spec / "B.VALIDATION.md",
        "## Links\n",
        '## Links\n\n```rf-edge\nfrom: "label:B.VALIDATION"\nrelation: depends_on\n'
        'to: "label:B.VALIDATION"\n```\n',
    )


def duplicate_stable_id(spec: Path, repo: Path) -> None:
    _edit(spec / "B.REPAIR_ATTEMPT.md", "id: repair-attempt-pos-ru-01", "id: validation-pos-ru-01")


def duplicate_edge(spec: Path, repo: Path) -> None:
    block = (
        '```rf-edge\nrelation: tested_by\nto: "test:src/annotation-web/test/PilotSpec.hs#activeLabels"\n```\n'
    )
    _edit(spec / "B.VALIDATION.md", "## Links\n", f"## Links\n\n{block}\n{block}")


def _drop_examples_matching(spec: Path, field_line: str) -> None:
    """Вырезать все rf-example блоки с данной строкой поля."""

    path = spec / "B.VALIDATION.md"
    text = path.read_text(encoding="utf-8")
    while field_line in text:
        marker = text.index(field_line)
        start = text.rindex("```rf-example", 0, marker)
        end = text.index("```", text.index("rationale:", marker)) + 4
        text = text[:start] + text[end:]
    path.write_text(text, encoding="utf-8")


def drop_positive_examples(spec: Path, repo: Path) -> None:
    # Одного positive мало: у label'а есть и ru, и en. Проверка говорит правду,
    # пока хоть один positive жив, поэтому мутация убирает все.
    _drop_examples_matching(spec, "\nverdict: positive\n")


def drop_english_examples(spec: Path, repo: Path) -> None:
    _drop_examples_matching(spec, "\nlanguage: en\n")


def unknown_verdict(spec: Path, repo: Path) -> None:
    _edit(spec / "B.VALIDATION.md", "verdict: positive", "verdict: probably")


def invent_a_status(spec: Path, repo: Path) -> None:
    # Компилятор примет любую непустую строку; закрытое множество держит схема.
    _edit(spec / "B.VALIDATION.md", "status: draft", "status: experimental")


def hand_edit_generated_graph(spec: Path, repo: Path) -> None:
    # Правка внутри graph.json не двигает spec_digest — проверка обязана
    # сравнивать содержимое, а не только дайджест.
    path = repo / "experiments/semantic-spine/generated/graph.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["edges"][0]["to"] = "label:B.SOMETHING_ELSE"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dangling_doc_anchor(spec: Path, repo: Path) -> None:
    _edit(
        spec / "B.VALIDATION.md",
        '"doc:docs/annotation-protocol-v0.md#3. Решения разметчика"',
        '"doc:docs/annotation-protocol-v0.md#3. Решения, которых там нет"',
    )


# Мутация -> проверка, которая ОБЯЗАНА сработать.
MUTATIONS: dict[str, tuple[Mutation, str]] = {
    "rename label only in Markdown": (rename_label_in_markdown_only, "spec_compile"),
    "delete B.REPAIR_ATTEMPT": (delete_a_label, "dangling_reference"),
    "break confusable_with": (break_confusable_with, "asymmetric_relation"),
    "change allowed_units": (change_allowed_units, "example_unit_not_allowed"),
    "hand-edit generated JSON": (hand_edit_generated_json, "generated_stale"),
    "delete a declared test": (delete_test_target, "declared_test_missing"),
    "delete a declared implementation": (delete_implementation_target, "declared_implementation_missing"),
    "plant stale evidence": (plant_stale_evidence, "stale_evidence"),
    "contradictory invariant (reversed implements)": (contradictory_invariant, "illegal_edge_type"),
    "introduce a depends_on cycle": (introduce_cycle, "forbidden_cycle"),
    "duplicate a stable id": (duplicate_stable_id, "duplicate_stable_id"),
    "duplicate an edge": (duplicate_edge, "duplicate_edge"),
    "drop every positive example": (drop_positive_examples, "missing_required_example"),
    "drop all English examples": (drop_english_examples, "language_coverage"),
    "invent a verdict": (unknown_verdict, "unknown_verdict"),
    "point at a heading that does not exist": (dangling_doc_anchor, "dangling_reference"),
    "invent a label status": (invent_a_status, "schema_violation"),
    "hand-edit generated graph.json": (hand_edit_generated_graph, "generated_stale"),
    "rewrite the generated ontology_version": (rewrite_generated_ontology_version, "generated_stale"),
}

# Все check id, которые verifier умеет выдавать. Список закрыт намеренно:
# новая проверка без мутации роняет test_every_check_has_a_mutation.
DECLARED_CHECKS = {
    "spec_compile",
    "duplicate_stable_id",
    "duplicate_edge",
    "dangling_reference",
    "illegal_edge_type",
    "forbidden_cycle",
    "asymmetric_relation",
    "missing_required_example",
    "language_coverage",
    "example_unit_not_allowed",
    "unknown_verdict",
    "generated_stale",
    "declared_test_missing",
    "declared_implementation_missing",
    "stale_evidence",
    "schema_violation",
}


class MutationSuite(unittest.TestCase):
    def _run_mutation(self, mutate: Mutation) -> list[Finding]:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = build_mirror(repo)
            self.assertEqual(verify_spec_dir(repo, spec), [], "mirror must be clean before mutating")
            mutate(spec, repo)
            return verify_spec_dir(repo, spec)

    def test_clean_mirror_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = build_mirror(repo)
            self.assertEqual(verify_spec_dir(repo, spec), [])

    def test_every_mutation_is_caught(self) -> None:
        for name, (mutate, expected) in MUTATIONS.items():
            with self.subTest(mutation=name):
                findings = self._run_mutation(mutate)
                self.assertTrue(findings, f"mutation '{name}' produced no findings at all")
                checks = {finding.check for finding in findings}
                self.assertIn(
                    expected,
                    checks,
                    f"mutation '{name}' was not caught by '{expected}'; got {sorted(checks)}",
                )

    def test_every_check_has_a_mutation(self) -> None:
        """Проверка без мутации — это обещание, а не гарантия."""

        exercised = {expected for _, expected in MUTATIONS.values()}
        self.assertEqual(
            DECLARED_CHECKS - exercised,
            set(),
            "these verifier checks have no mutation proving they fire",
        )


if __name__ == "__main__":
    unittest.main()
