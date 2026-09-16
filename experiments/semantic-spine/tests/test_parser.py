"""Spec-файл остаётся обычным Markdown: проза прозой, списки списками."""

import unittest

from spine.parser import SpecSyntaxError, parse_spec_text

DOC = """# B.X

```rf-label
id: B.X
```

## Operational definition

Первая строка определения
и её продолжение на второй строке.

## Inclusion

- первый критерий
- второй критерий

## Examples

```rf-example
id: x-pos-ru-01
verdict: positive
```
"""


class SpecParsing(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = parse_spec_text(DOC.split("\n"), "spec/B.X.md")

    def test_title_and_sections(self) -> None:
        self.assertEqual(self.doc.title, "B.X")
        self.assertEqual(
            [s.title for s in self.doc.sections],
            ["", "Operational definition", "Inclusion", "Examples"],
        )

    def test_wrapped_paragraph_becomes_one_line(self) -> None:
        section = self.doc.section("Operational definition")
        self.assertEqual(
            section.paragraphs,
            ["Первая строка определения и её продолжение на второй строке."],
        )

    def test_bullets_stay_bullets(self) -> None:
        self.assertEqual(
            self.doc.section("Inclusion").bullets, ["первый критерий", "второй критерий"]
        )

    def test_blocks_are_attached_to_their_section(self) -> None:
        self.assertEqual([b.kind for b in self.doc.blocks_of("rf-label")], ["rf-label"])
        self.assertEqual(len(self.doc.section("Examples").blocks), 1)

    def test_block_spans_point_back_at_the_file(self) -> None:
        block = self.doc.blocks_of("rf-label")[0]
        self.assertEqual(block.path, "spec/B.X.md")
        self.assertEqual(block.line_start, 3)
        self.assertEqual(block.line_end, 5)

    def test_rejects_malformed_documents(self) -> None:
        cases = {
            "no title": "some prose\n",
            "two H1": "# A\n\n# B\n",
            "H3 heading": "# A\n\n### too deep\n",
            "unterminated fence": "# A\n\n```rf-label\nid: x\n",
            "fence without info string": "# A\n\n```\nbody\n```\n",
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(SpecSyntaxError):
                    parse_spec_text(text.split("\n"), "spec/T.md")


if __name__ == "__main__":
    unittest.main()
