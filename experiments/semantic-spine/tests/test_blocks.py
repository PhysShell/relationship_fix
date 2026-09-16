"""Парсер блоков обязан ронять всё, чего не понимает."""

import unittest

from spine.blocks import BlockSyntaxError, parse_block_body


def parse(text: str, kind: str = "rf-label"):
    lines = [(index + 1, line) for index, line in enumerate(text.split("\n"))]
    return parse_block_body(kind, lines, "spec/T.md", 1, len(lines))


class BlockParsing(unittest.TestCase):
    def test_scalars_lists_and_escapes(self) -> None:
        block = parse(
            'id: B.X\n'
            'flag: true\n'
            'off: false\n'
            'count: 12\n'
            'nothing: null\n'
            'units:\n'
            '  - utterance\n'
            '  - turn\n'
            'text: "a \\"quoted\\" and a \\\\ backslash"\n'
            '# a comment\n'
        )
        self.assertEqual(block.fields["id"], "B.X")
        self.assertIs(block.fields["flag"], True)
        self.assertIs(block.fields["off"], False)
        self.assertEqual(block.fields["count"], 12)
        self.assertIsNone(block.fields["nothing"])
        self.assertEqual(block.fields["units"], ["utterance", "turn"])
        self.assertEqual(block.fields["text"], 'a "quoted" and a \\ backslash')

    def test_empty_list_is_an_empty_list_not_none(self) -> None:
        self.assertEqual(parse("confusable_with:\n").fields["confusable_with"], [])

    def test_rejects_what_it_cannot_represent(self) -> None:
        cases = {
            "duplicate key": "id: a\nid: b\n",
            "single quotes": "text: 'a'\n",
            "inline mapping": "x: {a: 1}\n",
            "inline list": "x: [1]\n",
            "stray indentation": "  x: 1\n",
            "orphan list item": "  - lonely\n",
            "unterminated quote": 'text: "open\n',
            "unsupported escape": 'text: "a \\t b"\n',
            "trailing backslash": 'text: "a \\\\\\"\n',
            "missing colon": "just words\n",
            "empty key": ": value\n",
            "non snake_case key": "Some-Key: 1\n",
            "empty value": "key:  \n  not-a-list\n",
            "mapping-looking bare scalar": "key: a: b\n",
            "comment char in bare scalar": "key: a # b\n",
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(BlockSyntaxError):
                    parse(text)

    def test_errors_carry_the_line_number(self) -> None:
        with self.assertRaises(BlockSyntaxError) as caught:
            parse("id: ok\nbroken\n")
        self.assertEqual(caught.exception.line_no, 2)


if __name__ == "__main__":
    unittest.main()
