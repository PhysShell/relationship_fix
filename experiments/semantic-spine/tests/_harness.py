"""Зеркало репозитория для мутационных тестов.

Мутации должны уметь удалять тест или портить evidence, не трогая настоящий
репозиторий. Зеркало собирается из самих ссылок графа: если spec начнёт
ссылаться на новый файл, зеркало подхватит его само, а не устареет молча.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from spine.compiler import compile_spec_dir
from spine.refs import parse_ref
from spine.verifier import DIRECTIONALITY_ENUM_FILE, UNIT_ENUM_FILE

SPINE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SPINE_ROOT.parent.parent
SPEC_DIR = SPINE_ROOT / "spec"
GENERATED_DIR = SPINE_ROOT / "generated"

ALWAYS_MIRRORED = (
    UNIT_ENUM_FILE,
    DIRECTIONALITY_ENUM_FILE,
    "data/ontology/behavior-v0.1.json",
    "data/ontology/behavior-v0.2-candidate.json",
)


def referenced_paths() -> list[str]:
    compilation = compile_spec_dir(SPEC_DIR)
    paths: set[str] = set(ALWAYS_MIRRORED)
    for edge in compilation.edges:
        for node in (edge.source_id, edge.target_id):
            try:
                ref = parse_ref(node)
            except ValueError:
                continue
            if ref.is_path and not ref.locator.startswith("experiments/semantic-spine/"):
                paths.add(ref.locator)
    return sorted(paths)


def build_mirror(destination: Path) -> Path:
    """Собрать минимальный репозиторий: только то, на что ссылается spec."""

    for relative in referenced_paths():
        source = REPO_ROOT / relative
        if not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    spec_copy = destination / "experiments/semantic-spine/spec"
    shutil.copytree(SPEC_DIR, spec_copy)
    shutil.copytree(GENERATED_DIR, destination / "experiments/semantic-spine/generated")
    shutil.copytree(SPINE_ROOT / "schema", destination / "experiments/semantic-spine/schema")
    return spec_copy
