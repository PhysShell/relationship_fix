"""Схемы обязаны быть load-bearing: по ним валидируются реальные артефакты."""

import json
import unittest
from pathlib import Path

from spine.compiler import compile_spec_dir
from spine.parser import parse_spec_file
from spine.schema_check import SchemaError, validate

from ._harness import SPEC_DIR, SPINE_ROOT

SCHEMA_DIR = SPINE_ROOT / "schema"
GENERATED = SPINE_ROOT / "generated"


def load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


class GraphSchema(unittest.TestCase):
    def test_generated_graph_validates(self) -> None:
        errors = validate(
            json.loads((GENERATED / "graph.json").read_text(encoding="utf-8")),
            load("graph.schema.json"),
        )
        self.assertEqual(errors, [])

    def test_schema_actually_rejects_a_broken_graph(self) -> None:
        schema = load("graph.schema.json")
        payload = json.loads((GENERATED / "graph.json").read_text(encoding="utf-8"))
        payload["edges"][0]["relation"] = "vibes_with"
        self.assertTrue(validate(payload, schema))

        payload = json.loads((GENERATED / "graph.json").read_text(encoding="utf-8"))
        payload["spec_digest"] = "not-a-digest"
        self.assertTrue(validate(payload, schema))

        payload = json.loads((GENERATED / "graph.json").read_text(encoding="utf-8"))
        payload["entities"][0]["surprise"] = 1
        self.assertTrue(validate(payload, schema))


class BlockSchema(unittest.TestCase):
    def test_every_block_in_every_spec_file_validates(self) -> None:
        schema = load("block.schema.json")
        definitions = schema["definitions"]
        checked = 0
        for path in sorted(SPEC_DIR.glob("*.md")):
            doc = parse_spec_file(path, repo_relative=f"spec/{path.name}")
            for section in doc.sections:
                for block in section.blocks:
                    with self.subTest(file=path.name, line=block.line_start, kind=block.kind):
                        self.assertIn(block.kind, definitions)
                        self.assertEqual(
                            validate(block.fields, definitions[block.kind], schema), []
                        )
                        checked += 1
        self.assertGreater(checked, 40)

    def test_schema_rejects_an_invented_verdict(self) -> None:
        schema = load("block.schema.json")
        errors = validate(
            {
                "id": "x-01",
                "language": "ru",
                "unit": "utterance",
                "verdict": "probably",
                "text": "t",
                "rationale": "r",
            },
            schema["definitions"]["rf-example"],
            schema,
        )
        self.assertTrue(errors)


class ValidatorItself(unittest.TestCase):
    """Валидатор обязан отказываться от схем, которые он не умеет проверять."""

    def test_refuses_unsupported_keywords(self) -> None:
        with self.assertRaises(SchemaError):
            validate({}, {"type": "object", "oneOf": []})

    def test_boolean_is_not_an_integer(self) -> None:
        self.assertTrue(validate(True, {"type": "integer"}))
        self.assertEqual(validate(True, {"type": "boolean"}), [])
        self.assertTrue(validate(1, {"type": "boolean"}))

    def test_required_and_additional_properties(self) -> None:
        schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}, "additionalProperties": False}
        self.assertEqual(validate({"a": "x"}, schema), [])
        self.assertTrue(validate({}, schema))
        self.assertTrue(validate({"a": "x", "b": 1}, schema))


if __name__ == "__main__":
    unittest.main()
