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

# Состояния протокола. Переход v1 -> v2 обязан быть ступенчатым: иначе можно
# одним коммитом поднять версию, починить рендеринг и раскрыть held-out задачи,
# и формально «порядок соблюдён концептуально», а Git видит одну кашу.
PHASES = (
    "v1_closed",
    "v2_implementation_frozen",
    "v2_tasks_revealed",
    "v2_experiment_complete",
)

# Treatment — всё, что превращает (spec + репозиторий) в ContextBundle.
# Именно это в Phase 3 становится частью воздействия, а не измерения, поэтому
# хешируется отдельно от surface_digest и преригистрируется ДО раскрытия задач.
# Измерение (targets, verifier, schema_check) сюда намеренно не входит.
TREATMENT_FILES = (
    "spine/blocks.py",
    "spine/parser.py",
    "spine/compiler.py",
    "spine/ir.py",
    "spine/refs.py",
    "spine/graph.py",
    "spine/budget.py",
    "spine/selector.py",
    "spine/subject.py",
)


def surface_digest(root: Path | None = None) -> str:
    """Дайджест данных протокола: задачи + spec + порядок связей."""

    import sys

    root = root or SPINE_ROOT
    sys.path.insert(0, str(SPINE_ROOT))
    from spine.selector import SPINE_RELATION_ORDER

    digest = hashlib.sha256()
    for directory, pattern in ((root / "eval" / "tasks", "*.json"), (root / "spec", "*.md")):
        for path in sorted(directory.glob(pattern), key=lambda p: p.name):
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    digest.update("|".join(SPINE_RELATION_ORDER).encode("utf-8"))
    return digest.hexdigest()


def treatment_digest(root: Path | None = None) -> str:
    """Дайджест кода воздействия.

    В v1 байт-равенство снимков прекрасно фиксирует НАБЛЮДАВШЕЕСЯ поведение.
    В v2 этого мало: измеряется поведение агента, и семантика реализации
    становится частью treatment. Поэтому после раскрытия held-out задач ни
    selector, ни рендеринг, ни packing, ни token accounting не имеют права
    измениться без новой версии протокола — включая «безобидный рефакторинг»,
    который внезапно меняет условие D.
    """

    root = root or SPINE_ROOT
    digest = hashlib.sha256()
    for relative in TREATMENT_FILES:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def phase(root: Path | None = None) -> str:
    return load(root).get("phase", "v1_closed")


def load(root: Path | None = None) -> dict:
    path = (root or SPINE_ROOT) / "eval" / "protocol.json"
    return json.loads(path.read_text(encoding="utf-8"))


def version(root: Path | None = None) -> int:
    return int(load(root)["protocol_version"])


def is_frozen(root: Path | None = None) -> bool:
    return load(root)["status"] == "immutable"


def _git(root: Path, *args: str) -> str:
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def transition_problems(root: Path | None = None) -> list[str]:
    """Проверки ступенчатого перехода v1 -> v2. Пустой список — всё законно.

    Одна функция на всех: её зовут и тесты, и симуляция легального пути. Так
    нельзя случайно проверять в симуляции не то, что проверяет CI.
    """

    root = root or SPINE_ROOT
    protocol = load(root)
    current = protocol.get("phase", "v1_closed")
    problems: list[str] = []

    if current not in PHASES:
        return [f"unknown phase {current!r}; known: {', '.join(PHASES)}"]

    tasks_on_disk = len(list((root / "eval" / "tasks").glob("*.json")))
    v1_tasks = protocol.get("v1_record", {}).get("tasks")
    if v1_tasks is None:
        problems.append("v1_record.tasks is missing; the historical record must survive v2")

    if current == "v1_closed":
        if int(protocol["protocol_version"]) != 1:
            problems.append("phase is v1_closed but protocol_version is not 1")
        if v1_tasks is not None and tasks_on_disk != v1_tasks:
            problems.append(f"v1 task set changed: {tasks_on_disk} on disk, {v1_tasks} recorded")
        return problems

    if current == "v2_implementation_frozen":
        if v1_tasks is not None and tasks_on_disk != v1_tasks:
            problems.append(
                "held-out tasks appeared before the treatment was preregistered "
                f"({tasks_on_disk} on disk, {v1_tasks} at v1)"
            )
        recorded = protocol.get("preregistered_treatment_digest")
        if recorded is not None and recorded != treatment_digest(root):
            problems.append("preregistered_treatment_digest does not match the treatment code")
        return problems

    if current == "v2_tasks_revealed":
        recorded = protocol.get("preregistered_treatment_digest")
        if recorded is None:
            problems.append("tasks revealed without a preregistered treatment")
        elif recorded != treatment_digest(root):
            problems.append(
                "the treatment code changed after the held-out tasks were revealed; "
                "that includes an 'innocent refactor' that silently moves condition D"
            )

        commit = protocol.get("preregistered_at_commit")
        if commit is None:
            problems.append("preregistration must name the commit that froze the treatment")
        else:
            head = _git(root, "rev-parse", "HEAD")
            resolved = _git(root, "rev-parse", f"{commit}^{{commit}}")
            if not resolved:
                problems.append(f"preregistration commit {commit} is not in this clone")
            elif resolved == head:
                problems.append(
                    "preregistration cannot be the same commit that reveals the tasks: "
                    "a digest written by that commit matches by construction"
                )
            else:
                # Путь к каталогу задач вычисляется от корня репозитория, а не
                # хардкодится: `git -C <подкаталог>` разрешает <rev>:<path>
                # иначе, чем от корня, и хардкод молча давал пустой листинг.
                toplevel = _git(root, "rev-parse", "--show-toplevel")
                relative = (root / "eval" / "tasks").resolve().relative_to(Path(toplevel).resolve())
                listing = _git(Path(toplevel), "ls-tree", "--name-only", f"{resolved}:{relative}")
                at_prereg = len([line for line in listing.split("\n") if line.endswith(".json")])
                if v1_tasks is not None and at_prereg != v1_tasks:
                    problems.append(
                        "the held-out tasks already existed at the preregistration commit; "
                        "the treatment was frozen after seeing them"
                    )
        return problems

    return problems
