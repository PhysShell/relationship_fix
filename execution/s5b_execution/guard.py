"""Границы, которые ДОКАЗЫВАЮТСЯ, а не объявляются.

Два инварианта, каждый закрывает дыру в том, что выглядело закрытым.
"""

from __future__ import annotations

import importlib
import pathlib
import subprocess


class BoundaryViolated(Exception):
    """Архитектурная граница нарушена. Прогон не начинается."""


#: Точки входа: их импорт втягивает остальной научный граф
SCIENCE_ENTRY_POINTS = ("simulation.s5b_shard", "simulation.s5b_escalation",
                        "simulation.s5b_precision", "simulation.s5b_prereg",
                        "simulation.s5b_stage1")

#: Пространства имён, КАЖДЫЙ загруженный модуль которых обязан прийти из
#: science-checkout. Проверять две вершины мало: `s5b_escalation` из
#: SCIENCE_SHA и `coarsening.bounded` из execution-checkout собрались бы
#: в одного Франкенштейна, и Python не стал бы извиняться.
SCIENCE_NAMESPACES = ("simulation", "coarsening")

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
    import sys
    root = pathlib.Path(checkout).resolve()
    for name in SCIENCE_ENTRY_POINTS:
        importlib.import_module(name)
    seen: dict[str, str] = {}
    for name, module in sorted(sys.modules.items()):
        head = name.split(".")[0]
        if head not in SCIENCE_NAMESPACES:
            continue
        where = getattr(module, "__file__", None)
        if where is None:            # пакет без файла проверять нечего
            continue
        where = pathlib.Path(where).resolve()
        # resolve + is_relative_to, а НЕ startswith: `/tmp/science-evil`
        # начинается с `/tmp/science` и строковый префикс это пропустит
        if not where.is_relative_to(root):
            raise BoundaryViolated(
                f"{name} импортирован из {where}, а не из science-checkout "
                f"{root}: граница науки и исполнения не держится")
        seen[name] = str(where)
    if not seen:
        raise BoundaryViolated("научных модулей не загружено вовсе")
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


def assert_object_exists(repo, sha: str) -> None:
    """Коммит обязан БЫТЬ в checkout'е.

    Мелкий checkout молча не находит якорь, и `git diff` тогда падает не
    тем отказом либо, хуже, сравнивает не то. Проверка отдельная, чтобы
    «объекта нет» никогда не выглядело как «различий нет».
    """
    done = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise BoundaryViolated(
            f"коммита {sha} нет в checkout'е: история обрезана, "
            f"сравнивать не с чем")


def assert_is_ancestor(repo, pin: str, head: str) -> None:
    """Якорь обязан быть ПРЕДКОМ заявки.

    Иначе diff считался бы между ветками, разошедшимися где угодно, и
    «ничего постороннего не менялось» перестало бы значить то, что
    написано.
    """
    done = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", pin, head],
        capture_output=True, text=True)
    if done.returncode != 0:
        raise BoundaryViolated(
            f"якорь {pin} не является предком заявки {head}")


def assert_request_is_only_a_signal(paths) -> None:
    """Между пином исполнения и заявкой меняется ТОЛЬКО файл заявки.

    Закрепить `EXECUTION_SHA` — мало. Сам YAML воркфлоу GitHub берёт из
    triggering ref, а НЕ из пина. Значит между пин-коммитом и заявкой
    можно переписать оркестрацию целиком, и все три SHA напечатаются
    честно при подменённом воркфлоу. Тройка врала бы ровно на полшага.
    """
    paths = sorted(paths)
    if paths != [REQUEST_PATH]:
        raise BoundaryViolated(
            f"между якорем и заявкой должен меняться РОВНО один путь "
            f"{REQUEST_PATH}, а изменены {paths or 'ничего'}. Пустой список "
            f"тоже отказ: значит запуск случился не тем механизмом, "
            f"которым мы думаем")


def sha256_of(path) -> str:
    """Отпечаток файла. Для воркфлоу — единственное, что его закрепляет."""
    import hashlib
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def assert_workflow_matches(path, expected: str) -> str:
    """Исполняемый воркфлоу обязан совпадать с объявленным в заявке.

    Почему отпечаток, а не поле в самом воркфлоу: коммит, закрепляющий
    пин, ПО ОПРЕДЕЛЕНИЮ меняет воркфлоу. Хранить якорь внутри того, что
    он закрепляет, — самореференция: между объявленным пином и заявкой
    всегда оказывался бы лишний путь. Отпечаток файла X, лежащий в файле
    Y, этой петли не образует.
    """
    got = sha256_of(path)
    if got != expected:
        raise BoundaryViolated(
            f"воркфлоу {path}: отпечаток {got}, заявлен {expected} — "
            f"исполняется не то, что объявлено в заявке")
    return got


def assert_pin_descends_from(repo, execution_sha: str, pin: str) -> None:
    """Якорь заявки обязан быть потомком закреплённого слоя исполнения.

    Без этого заявка могла бы объявить якорем произвольный коммит и
    сделать diff пустым «по построению».
    """
    done = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor",
         execution_sha, pin], capture_output=True, text=True)
    if done.returncode != 0:
        raise BoundaryViolated(
            f"якорь заявки {pin} не является потомком EXECUTION_SHA "
            f"{execution_sha}")


#: Что эти проверки ловят, а что нет. Формулировка честная: они закрывают
#: СНОС ПО НЕВНИМАТЕЛЬНОСТИ — правку воркфлоу между закреплением и
#: заявкой. Сознательный сдвиг якоря вперёд вместе с переобъявлением
#: отпечатка они не запрещают, но делают его ВИДИМЫМ: и якорь, и
#: отпечаток лежат в заявке и уходят в provenance прогона.
CATCHES_DRIFT_MAKES_DELIBERATE_CHANGE_VISIBLE = True
