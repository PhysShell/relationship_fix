"""Anchor-level ground truth: не «нужный файл», а «нужное место в файле».

`file_recall` считает файл найденным, когда стратегия принесла из него хоть
что-нибудь. Это даёт chunk-стратегиям структурное преимущество над
whole-file oracle'ом: spine приносит 60 строк раздела и засчитывает файл, а
oracle приносит те же 14 тысяч токенов целиком и не помещается в бюджет.
Вывод «наш chunking лучше whole-file oracle» — правда, но скучная.

Здесь вводится второй уровень: цель — это конкретная строка-определение
(заголовок, символ, ключ в JSON). Цель покрыта, только если ИМЕННО эта строка
попала в выданный контекст.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class TargetUnresolvable(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    raw: str
    path: str
    anchor: str


@dataclass(frozen=True)
class TargetLocation:
    target: Target
    line_no: int
    line_text: str


def parse_target(raw: str) -> Target:
    text = raw.strip()
    path, sep, anchor = text.partition("#")
    if not sep or not path or not anchor:
        raise TargetUnresolvable(f"target {raw!r} must be '<repo-relative-path>#<anchor>'")
    if path.startswith("/") or ".." in path.split("/"):
        raise TargetUnresolvable(f"target {raw!r} must use a repo-relative path without '..'")
    return Target(raw=text, path=path, anchor=anchor)


def _heading_line(lines: list[str], anchor: str) -> int | None:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") and stripped.lstrip("#").strip() == anchor:
            return index
    return None


def _json_definition_line(lines: list[str], anchor: str) -> int | None:
    # Определяющее вхождение в артефакте — это строка вида `"id": "B.VALIDATION"`,
    # а не упоминание того же значения в confusable_with соседа.
    pattern = re.compile(rf'"(?:id|ontology_version|schema_version)"\s*:\s*"{re.escape(anchor)}"')
    for index, line in enumerate(lines):
        if pattern.search(line):
            return index
    return None


def _symbol_line(lines: list[str], anchor: str) -> int | None:
    leaf = anchor.rsplit(".", 1)[-1]
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(leaf)}(?![A-Za-z0-9_])")
    for index, line in enumerate(lines):
        if pattern.search(line):
            return index
    return None


def locate(subject_root: Path, target: Target) -> TargetLocation:
    """Найти строку-определение цели в исследуемом репозитории."""

    path = subject_root / target.path
    if not path.is_file():
        raise TargetUnresolvable(f"{target.raw}: no such file in the subject repository")
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")

    suffix = path.suffix
    if suffix == ".md":
        index = _heading_line(lines, target.anchor)
    elif suffix in (".json", ".jsonl"):
        index = _json_definition_line(lines, target.anchor)
    else:
        index = _symbol_line(lines, target.anchor)

    if index is None:
        raise TargetUnresolvable(f"{target.raw}: anchor not found in {target.path}")
    return TargetLocation(target=target, line_no=index + 1, line_text=lines[index])


def locate_all(subject_root: Path, raw_targets: list[str]) -> list[TargetLocation]:
    return [locate(subject_root, parse_target(raw)) for raw in raw_targets]


def covers(location: TargetLocation, chunk_path: str | None, chunk_text: str) -> bool:
    """Покрывает ли выданный фрагмент именно строку-определение цели.

    Сравнение по содержимому строки, а не по номеру: чанки режутся по-разному,
    и номер строки внутри excerpt'а стратегии не принадлежит.
    """

    if chunk_path != location.target.path:
        return False
    needle = location.line_text.strip()
    if not needle:
        return False
    return needle in chunk_text
