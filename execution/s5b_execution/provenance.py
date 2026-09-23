"""Происхождение прогона. Без него калибровка и результат — фольклор.

Пишется в манифест и в каждый сводный артефакт. Пять полей, и ни одно не
выводится из остальных:

    SCIENCE_SHA     чем считали
    EXECUTION_SHA   чем распоряжались
    REQUEST_SHA     что послужило сигналом к запуску
    inputs          отпечатки артефактов прошлых ступеней
    manifest        отпечаток самого плана
"""

from __future__ import annotations

import hashlib
import json
import os


class ProvenanceIncomplete(Exception):
    """Поле происхождения пустое. Прогон без происхождения не начинается."""


REQUIRED = ("science_sha", "execution_sha", "request_sha")

#: имена переменных окружения, из которых берутся поля выше
REQUIRED_ENV = ("SCIENCE_SHA", "EXECUTION_SHA", "REQUEST_SHA")


def collect(*, inputs: dict[str, str], manifest_digest: str) -> dict:
    """Собрать запись из окружения. Пустое поле — отказ, а не прочерк."""
    record = {
        "science_sha": os.environ.get("SCIENCE_SHA", ""),
        "execution_sha": os.environ.get("EXECUTION_SHA", ""),
        "request_sha": os.environ.get("REQUEST_SHA", ""),
        "inputs": dict(sorted(inputs.items())),
        "manifest_digest": manifest_digest,
    }
    missing = [f for f in REQUIRED if not record[f]]
    if missing:
        raise ProvenanceIncomplete(f"не заданы: {', '.join(missing)}")
    for field in REQUIRED:
        value = record[field]
        if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
            raise ProvenanceIncomplete(
                f"{field} = {value!r}: нужен полный шестнадцатеричный SHA")
    return record


def digest_of(payloads) -> str:
    """Отпечаток набора part-файлов. От порядка чтения не зависит."""
    return hashlib.sha256(json.dumps(
        sorted(p["digest"] for p in payloads), sort_keys=True
    ).encode()).hexdigest()[:16]
