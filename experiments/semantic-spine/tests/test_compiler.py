"""Компиляция и — главное — равенство с production-онтологией.

Пока spec не является source of truth, единственное, что делает эксперимент
осмысленным, — доказуемое равенство compile(spec) подмножеству behavior-v0.1.
Если этот тест покраснел, spec разошёлся с репозиторием, и виноват spec.
"""

import json
import unittest
from pathlib import Path

from spine.compiler import (
    CompileError,
    compile_spec_dir,
    emit_fixtures,
    emit_graph,
    emit_ontology,
)
from spine.parser import parse_spec_text

from ._harness import REPO_ROOT, SPEC_DIR

ONTOLOGY_VERSION = "behavior-v0.1"


class Equivalence(unittest.TestCase):
    def test_compile_equals_production_ontology_subset(self) -> None:
        compilation = compile_spec_dir(SPEC_DIR)
        produced = {
            label["id"]: label for label in emit_ontology(compilation, ONTOLOGY_VERSION)["labels"]
        }
        reference = json.loads(
            (REPO_ROOT / "data/ontology" / f"{ONTOLOGY_VERSION}.json").read_text(encoding="utf-8")
        )
        expected = {
            label["id"]: label for label in reference["labels"] if label["id"] in produced
        }
        self.assertEqual(set(produced), set(expected))
        for label_id in sorted(produced):
            with self.subTest(label=label_id):
                self.assertEqual(produced[label_id], expected[label_id])

    def test_spec_covers_exactly_the_declared_four_labels(self) -> None:
        compilation = compile_spec_dir(SPEC_DIR)
        self.assertEqual(
            compilation.label_ids(),
            ["B.BLAME_CRITICISM", "B.PRESSURE_FOR_CHANGE", "B.REPAIR_ATTEMPT", "B.VALIDATION"],
        )

    def test_emitted_ontology_schema_matches_the_dotnet_loader_contract(self) -> None:
        payload = emit_ontology(compile_spec_dir(SPEC_DIR), ONTOLOGY_VERSION)
        self.assertEqual(payload["schema_version"], "rf.ontology.v1")
        reference = json.loads(
            (REPO_ROOT / "data/ontology" / f"{ONTOLOGY_VERSION}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sorted(payload), sorted(reference))
        self.assertEqual(
            sorted(payload["labels"][0]), sorted(reference["labels"][0])
        )


class Determinism(unittest.TestCase):
    def test_compilation_is_stable_across_runs(self) -> None:
        first = compile_spec_dir(SPEC_DIR)
        second = compile_spec_dir(SPEC_DIR)
        self.assertEqual(first.spec_digest, second.spec_digest)
        self.assertEqual(emit_graph(first), emit_graph(second))
        self.assertEqual(emit_fixtures(first), emit_fixtures(second))

    def test_generated_artifacts_on_disk_are_current(self) -> None:
        compilation = compile_spec_dir(SPEC_DIR)
        generated = SPEC_DIR.parent / "generated"
        self.assertEqual(
            json.loads((generated / "ontology.json").read_text(encoding="utf-8")),
            emit_ontology(compilation, ONTOLOGY_VERSION),
        )
        self.assertEqual(
            json.loads((generated / "graph.json").read_text(encoding="utf-8")),
            emit_graph(compilation),
        )
        self.assertEqual(
            json.loads((generated / "fixtures.json").read_text(encoding="utf-8")),
            emit_fixtures(compilation),
        )


class StructuralRefusals(unittest.TestCase):
    """Компилятор отвечает за «можно ли это считать объявлением», не за правду."""

    def _compile_one(self, text: str):
        from spine.compiler import compile_document

        return compile_document(parse_spec_text(text.split("\n"), "spec/T.md"))

    BASE = (
        "# B.X\n\n```rf-label\nid: B.X\ncanonical_name: \"X\"\n"
        "plain_language_name_en: \"x\"\nplain_language_name_ru: \"х\"\n"
        "allowed_units:\n  - utterance\ndirectionality: other_directed\n"
        "evidence_required: true\nsource_frameworks:\n  - \"none\"\nstatus: draft\n```\n\n"
        "## Operational definition\n\nОпределение.\n\n"
        "## Inclusion\n\n- критерий\n\n## Exclusion\n\n- исключение\n"
    )

    def test_the_base_document_compiles(self) -> None:
        entities, _ = self._compile_one(self.BASE)
        self.assertEqual(entities[0].attributes["id"], "B.X")

    def test_rejects_structural_defects(self) -> None:
        cases = {
            "H1 disagrees with the block id": self.BASE.replace("# B.X\n", "# B.Y\n", 1),
            "unknown field": self.BASE.replace("status: draft", "status: draft\nvibes: good"),
            "missing required field": self.BASE.replace("status: draft\n", ""),
            "two definition paragraphs": self.BASE.replace(
                "Определение.\n", "Определение.\n\nИ ещё одно.\n"
            ),
            "missing inclusion section": self.BASE.replace("## Inclusion\n\n- критерий\n", ""),
            "empty exclusion section": self.BASE.replace("- исключение", ""),
            "non-boolean evidence_required": self.BASE.replace(
                "evidence_required: true", 'evidence_required: "yes"'
            ),
            "unknown relation": self.BASE
            + '\n## Links\n\n```rf-edge\nrelation: vibes_with\nto: "label:B.Y"\n```\n',
            "rf-edge without a resolvable target": self.BASE
            + '\n## Links\n\n```rf-edge\nrelation: specified_by\nto: "nonsense"\n```\n',
            "two rf-label blocks": self.BASE + "\n```rf-label\nid: B.Z\n```\n",
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(CompileError):
                    self._compile_one(text)

    def test_duplicate_ids_across_files_are_refused(self) -> None:
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec"
            shutil.copytree(SPEC_DIR, spec)
            shutil.copy2(spec / "B.VALIDATION.md", spec / "B.VALIDATION-copy.md")
            with self.assertRaises(CompileError) as caught:
                compile_spec_dir(spec)
            self.assertEqual(caught.exception.check, "duplicate_stable_id")


if __name__ == "__main__":
    unittest.main()
