"""Личность конца и чтение артефактов прошлых просмотров.

Конец опознаётся тройкой `(рука, ключ, доля δ)`. Просмотр в личность НЕ
входит — в этом весь смысл: один и тот же конец считается на нескольких
ступенях, и задача слоя — не перепутать его копии между собой.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

#: значения, которые вправе стоять в поле `status` артефакта
ACHIEVED = "MC_PRECISION_ACHIEVED"
INSUFFICIENT = "MC_PRECISION_INSUFFICIENT"
KNOWN_STATUSES = (ACHIEVED, INSUFFICIENT)

#: `look` в личность не входит НАМЕРЕННО
LOOK_IS_NOT_PART_OF_IDENTITY = True

#: Файлы каталога ступени, которые part-файлами НЕ являются. Список
#: именно перечислен, а не заменён на «пропускать незнакомое»: иначе
#: чужой или битый файл тихо выпал бы из проверки полноты.
NOT_PART_FILES = ("manifest.json", "reduced.json")


#: Поля, из которых part-файл ИСХОДНО считал свой digest. `seconds` и
#: `peak_rss_mb` дописываются ПОСЛЕ и в отпечаток не входят: они зависят
#: от раннера, а не от науки.
CANONICAL_DIGEST_FIELDS = ("task_id", "arm", "look", "keys", "endpoints")


def recompute_digest(payload: dict) -> str:
    """Отпечаток части, пересчитанный ИЗ СОДЕРЖИМОГО.

    Без этого `prior_digest` якорил бы не байты, а чужое слово о байтах:
    и старый CLI, и первая версия `digest_of` складывали сохранённые
    строки `payload["digest"]`. Файл с подменёнными `endpoints` и старым
    правильным `digest` прошёл бы оба.
    """
    import hashlib
    canon = {k: payload[k] for k in CANONICAL_DIGEST_FIELDS}
    return hashlib.sha256(
        json.dumps(canon, sort_keys=True).encode()).hexdigest()[:16]


class ArtifactRefused(Exception):
    """Артефакт не принят. Частичный или странный вход не чинится молча."""


@dataclass(frozen=True, slots=True)
class EndpointId:
    """Рука, ключ, доля горизонта. Просмотра здесь нет."""

    arm: str
    key: tuple
    fraction: float

    def as_json(self) -> list:
        return [self.arm, list(self.key), self.fraction]


def endpoint_ids(payload: dict):
    """Личности всех концов одного part-файла, в порядке файла."""
    for record in payload["endpoints"]:
        yield EndpointId(payload["arm"], tuple(record["key"]),
                         record["fraction"]), record


def load_unit_payloads(directory) -> list[dict]:
    """Все part-файлы каталога. `manifest.json` не part-файл.

    Отказ, а не предупреждение: файл без обязательных полей означает, что
    артефакт приехал не оттуда, откуда думает вызывающий.
    """
    directory = pathlib.Path(directory)
    out = []
    for path in sorted(directory.glob("*.json")):
        if path.name in NOT_PART_FILES:
            continue
        payload = json.loads(path.read_text())
        for field in ("task_id", "arm", "look", "keys", "endpoints", "digest"):
            if field not in payload:
                raise ArtifactRefused(f"{path.name}: нет поля {field!r}")
        if path.stem != payload["task_id"]:
            raise ArtifactRefused(
                f"{path.name}: имя файла не совпадает с task_id "
                f"{payload['task_id']!r}")
        got = recompute_digest(payload)
        if got != payload["digest"]:
            raise ArtifactRefused(
                f"{path.name}: отпечаток содержимого {got}, в файле "
                f"{payload['digest']} — содержимое не то, что заявлено")
        out.append(payload)
    if not out:
        raise ArtifactRefused(f"{directory}: part-файлов нет вовсе")
    return out
