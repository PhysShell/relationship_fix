"""Строгий парсер содержимого typed fenced blocks.

Это НЕ YAML. Это намеренно крошечное подмножество, которое умеет ровно три
вещи: `key: scalar`, `key:` + список из `  - scalar`, и комментарии. Всё
остальное — ошибка с номером строки.

Мягкий парсер в verification harness — это врун: он молча превращает опечатку
в валидные данные. Поэтому здесь fail-closed: непонятная строка роняет разбор,
а не «интерпретируется как строка».
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_TRUE = "true"
_FALSE = "false"


class BlockSyntaxError(ValueError):
    """Синтаксическая ошибка в теле блока, с координатами."""

    def __init__(self, path: str, line_no: int, message: str) -> None:
        super().__init__(f"{path}:{line_no}: {message}")
        self.path = path
        self.line_no = line_no
        self.message = message


@dataclass(frozen=True)
class Block:
    """Разобранный typed block: его тип, поля и место в файле."""

    kind: str
    fields: dict[str, Any]
    path: str
    line_start: int
    line_end: int


def _parse_scalar(raw: str, path: str, line_no: int) -> Any:
    text = raw.strip()
    if not text:
        raise BlockSyntaxError(path, line_no, "empty value; use \"\" for an explicit empty string")

    if text.startswith('"'):
        return _parse_quoted(text, path, line_no)

    if text.startswith("'"):
        raise BlockSyntaxError(path, line_no, "single quotes are not supported; use double quotes")

    if text in (_TRUE, _FALSE):
        return text == _TRUE

    if text == "null":
        return None

    if _looks_like_int(text):
        return int(text)

    # Голый скаляр: запрещаем всё, что в YAML имело бы особый смысл, чтобы
    # никто не написал `text: да: нет` и не получил тихо другое значение.
    for forbidden in ('"', "#", "{", "}", "[", "]"):
        if forbidden in text:
            raise BlockSyntaxError(
                path, line_no, f"bare scalar contains {forbidden!r}; quote the value"
            )
    if ": " in text or text.endswith(":"):
        raise BlockSyntaxError(path, line_no, "bare scalar looks like a mapping; quote the value")
    return text


def _looks_like_int(text: str) -> bool:
    body = text[1:] if text[:1] in "+-" else text
    return bool(body) and body.isdigit()


def _parse_quoted(text: str, path: str, line_no: int) -> str:
    if len(text) < 2 or not text.endswith('"'):
        raise BlockSyntaxError(path, line_no, "unterminated double-quoted string")

    body = text[1:-1]
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            if char == '"':
                raise BlockSyntaxError(path, line_no, "unescaped quote inside quoted string")
            out.append(char)
            index += 1
            continue
        if index + 1 >= len(body):
            raise BlockSyntaxError(path, line_no, "trailing backslash in quoted string")
        escaped = body[index + 1]
        if escaped == "n":
            out.append("\n")
        elif escaped in ('"', "\\"):
            out.append(escaped)
        else:
            raise BlockSyntaxError(path, line_no, f"unsupported escape '\\{escaped}'")
        index += 2
    return "".join(out)


def parse_block_body(kind: str, body_lines: list[tuple[int, str]], path: str, line_start: int, line_end: int) -> Block:
    """Разобрать тело блока. body_lines — пары (номер строки в файле, текст)."""

    fields: dict[str, Any] = {}
    current_list_key: str | None = None

    for line_no, raw_line in body_lines:
        if raw_line.strip() == "" or raw_line.lstrip().startswith("#"):
            continue

        if raw_line.startswith("  - "):
            if current_list_key is None:
                raise BlockSyntaxError(path, line_no, "list item without a preceding 'key:' line")
            fields[current_list_key].append(_parse_scalar(raw_line[4:], path, line_no))
            continue

        if raw_line.startswith(" "):
            raise BlockSyntaxError(
                path, line_no, "unexpected indentation; only '  - item' list entries may be indented"
            )

        if ":" not in raw_line:
            raise BlockSyntaxError(path, line_no, "expected 'key: value' or 'key:'")

        key, _, value = raw_line.partition(":")
        key = key.strip()
        if not key:
            raise BlockSyntaxError(path, line_no, "empty key")
        if not all(ch.isalnum() or ch == "_" for ch in key):
            raise BlockSyntaxError(path, line_no, f"invalid key {key!r}; use snake_case")
        if key in fields:
            raise BlockSyntaxError(path, line_no, f"duplicate key {key!r}")

        if value.strip() == "":
            fields[key] = []
            current_list_key = key
        else:
            fields[key] = _parse_scalar(value, path, line_no)
            current_list_key = None

    return Block(kind=kind, fields=fields, path=path, line_start=line_start, line_end=line_end)
