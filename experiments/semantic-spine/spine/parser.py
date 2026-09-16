"""Markdown → structured document. Человек пишет обычный документ.

Проза остаётся прозой, Markdown-списки остаются списками, а typed fenced
blocks несут ровно то, что обязано быть machine-checked. Никакого нового
чудо-языка: файл читается глазами и рендерится любым Markdown-движком.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .blocks import Block, BlockSyntaxError, parse_block_body

FENCE = "```"


class SpecSyntaxError(ValueError):
    def __init__(self, path: str, line_no: int, message: str) -> None:
        super().__init__(f"{path}:{line_no}: {message}")
        self.path = path
        self.line_no = line_no
        self.message = message


@dataclass
class Section:
    """Раздел уровня H2: его проза, пункты списка и вложенные блоки."""

    title: str
    line_start: int
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)


@dataclass
class SpecDocument:
    path: str
    title: str
    title_line: int
    sections: list[Section]

    def section(self, name: str) -> Section | None:
        for section in self.sections:
            if section.title == name:
                return section
        return None

    def blocks_of(self, kind: str) -> list[Block]:
        return [b for section in self.sections for b in section.blocks if b.kind == kind]


def parse_spec_file(path: Path, repo_relative: str | None = None) -> SpecDocument:
    display = repo_relative or str(path)
    lines = path.read_text(encoding="utf-8").split("\n")
    return parse_spec_text(lines, display)


def parse_spec_text(lines: list[str], display: str) -> SpecDocument:
    title: str | None = None
    title_line = 0
    sections: list[Section] = []
    # Всё до первого H2 живёт в этом безымянном разделе (там лежит rf-label).
    current = Section(title="", line_start=1)
    sections.append(current)

    index = 0
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            current.paragraphs.append(" ".join(part.strip() for part in paragraph).strip())
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        line_no = index + 1

        if line.startswith(FENCE):
            flush_paragraph()
            kind = line[len(FENCE) :].strip()
            if not kind:
                raise SpecSyntaxError(display, line_no, "fenced block without an info string")
            body: list[tuple[int, str]] = []
            index += 1
            closed = False
            while index < len(lines):
                inner = lines[index]
                if inner.startswith(FENCE):
                    closed = True
                    break
                body.append((index + 1, inner))
                index += 1
            if not closed:
                raise SpecSyntaxError(display, line_no, f"unterminated '{kind}' block")
            end_line = index + 1
            if kind.startswith("rf-"):
                try:
                    current.blocks.append(parse_block_body(kind, body, display, line_no, end_line))
                except BlockSyntaxError as exc:
                    raise SpecSyntaxError(display, exc.line_no, exc.message) from exc
            index += 1
            continue

        if line.startswith("# "):
            flush_paragraph()
            if title is not None:
                raise SpecSyntaxError(display, line_no, "second H1; a spec file describes one entity")
            title = line[2:].strip()
            title_line = line_no
            index += 1
            continue

        if line.startswith("## "):
            flush_paragraph()
            current = Section(title=line[3:].strip(), line_start=line_no)
            sections.append(current)
            index += 1
            continue

        if line.startswith("#"):
            raise SpecSyntaxError(display, line_no, "only H1 and H2 headings are allowed in a spec file")

        if line.startswith("- "):
            flush_paragraph()
            current.bullets.append(line[2:].strip())
            index += 1
            continue

        if line.strip() == "":
            flush_paragraph()
        else:
            paragraph.append(line)
        index += 1

    flush_paragraph()

    if title is None:
        raise SpecSyntaxError(display, 1, "spec file has no H1 title")

    return SpecDocument(path=display, title=title, title_line=title_line, sections=sections)
