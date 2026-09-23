"""Границы, которые ДОКАЗЫВАЮТСЯ, а не объявляются.

Два инварианта, каждый закрывает дыру в том, что выглядело закрытым.
"""

from __future__ import annotations

import importlib
import pathlib
import subprocess


class BoundaryViolated(Exception):
    """Архитектурная граница нарушена. Прогон не начинается."""


#: Научные модули, чьё происхождение проверяется поимённо
SCIENCE_MODULES = ("simulation.s5b_shard", "simulation.s5b_escalation",
                   "simulation.s5b_precision", "simulation.s5b_prereg",
                   "simulation.s5b_stage1")

#: Единственный путь, которому разрешено меняться между пином и заявкой
REQUEST_PATH = ".github/s5b-stage1-request.txt"


def assert_science_comes_from(checkout) -> dict[str, str]:
    """Научные модули обязаны приходить из science-checkout.

    Execution-checkout — ПОЛНЫЙ репозиторий, и в нём лежит свой
    `research/python`. Сегодня коллизии нет лишь потому, что в
    `PYTHONPATH` попадает `exec/execution`, а не `exec`. Это свойство
    одной строки, а не гарантия: стоит добавить туда корень, и
    `SCIENCE_SHA` станет табличкой на двери, за которой никто не живёт.

    Возвращает карту «модуль -> файл»: она идёт в provenance, чтобы
    граница была не только проверена, но и записана.
    """
    root = pathlib.Path(checkout).resolve()
    seen: dict[str, str] = {}
    for name in SCIENCE_MODULES:
        module = importlib.import_module(name)
        where = pathlib.Path(module.__file__).resolve()
        if not where.is_relative_to(root):
            raise BoundaryViolated(
                f"{name} импортирован из {where}, а не из science-checkout "
                f"{root}: граница науки и исполнения не держится")
        seen[name] = str(where)
    return seen


def changed_paths(repo, pin: str, head: str) -> list[str]:
    """Пути, изменённые между пином исполнения и коммитом-заявкой."""
    done = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", f"{pin}..{head}"],
        capture_output=True, text=True)
    if done.returncode != 0:
        raise BoundaryViolated(
            f"git diff {pin}..{head} не удался: {done.stderr.strip()}")
    return [line for line in done.stdout.splitlines() if line.strip()]


def assert_request_is_only_a_signal(paths) -> None:
    """Между пином исполнения и заявкой меняется ТОЛЬКО файл заявки.

    Закрепить `EXECUTION_SHA` — мало. Сам YAML воркфлоу GitHub берёт из
    triggering ref, а НЕ из пина. Значит между пин-коммитом и заявкой
    можно переписать оркестрацию целиком, и все три SHA напечатаются
    честно при подменённом воркфлоу. Тройка врала бы ровно на полшага.
    """
    stray = sorted(p for p in paths if p != REQUEST_PATH)
    if stray:
        raise BoundaryViolated(
            f"после пина исполнения изменён не только {REQUEST_PATH}: {stray}")
