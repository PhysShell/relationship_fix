"""Версия экспериментального протокола и машинная проверка заморозки.

Обещание «мы ничего не трогали» без проверки — это обещание, а не гарантия;
тот же принцип, что и в мутационном наборе. Поэтому заморожённая поверхность
протокола сведена в дайджест, который пересчитывается тестом.

Разделение ответственности:

  * ДАННЫЕ протокола (задачи, oracle-файлы, якоря, spec-граф, порядок связей)
    закрыты `surface_digest` — правка любого из них двигает дайджест;
  * ПОВЕДЕНИЕ (рендеринг узлов, упаковка бюджета, формулы стратегий) закрыто
    побайтным равенством снимков в eval/results/ — любое изменение двигает
    числа.

Зачем версия. Отрицательный результат v1 («spine проигрывает whole-file
oracle'у по якорям») зафиксирован и в снимках, и здесь. Когда в Phase 3
легально починят рендеринг `materialized_in`, живой тест на эту инверсию
должен быть НЕ «починен до зелёного», а архивирован как свойство v1: иначе CI
начнёт требовать сохранять известный retrieval-баг на том основании, что
когда-то мы честно доказали его существование.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SPINE_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_FILE = SPINE_ROOT / "eval" / "protocol.json"


def surface_digest() -> str:
    """Дайджест данных протокола: задачи + spec + порядок связей."""

    import sys

    sys.path.insert(0, str(SPINE_ROOT))
    from spine.selector import SPINE_RELATION_ORDER

    digest = hashlib.sha256()
    for directory, pattern in ((SPINE_ROOT / "eval" / "tasks", "*.json"), (SPINE_ROOT / "spec", "*.md")):
        for path in sorted(directory.glob(pattern), key=lambda p: p.name):
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    digest.update("|".join(SPINE_RELATION_ORDER).encode("utf-8"))
    return digest.hexdigest()


def load() -> dict:
    return json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))


def version() -> int:
    return int(load()["protocol_version"])


def is_frozen() -> bool:
    return load()["status"] == "immutable"
