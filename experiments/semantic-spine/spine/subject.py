"""Исследуемый репозиторий на зафиксированном коммите.

До Phase 2.5 `base_commit` был декоративным: он лежал в манифесте задачи,
никем не читался, а стратегии ходили по рабочему дереву. Поэтому числа ездили
от любого файла, который завтра появится в основном репозитории, и назвать
такой прогон воспроизводимым было нельзя.

Теперь subject — это отдельный `git worktree --detach` на объявленном коммите.
Harness и spec/ остаются на экспериментальной ветке; исследуемый репозиторий
читается строго из worktree. Повторный прогон через полгода обязан вернуть те
же байты.

Fail-closed и здесь: если коммит недоступен (например, shallow clone в CI),
мы падаем с внятным сообщением, а НЕ откатываемся молча на рабочее дерево.
Тихий откат вернул бы ровно тот дефект, ради которого написан этот модуль.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ENV_CACHE_DIR = "SPINE_WORKTREE_DIR"


class SubjectUnavailable(RuntimeError):
    """Коммит нельзя получить — прогон не состоится, а не «состоится иначе»."""


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SubjectUnavailable(
            f"git {' '.join(args)} failed in {repo}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def cache_root() -> Path:
    override = os.environ.get(ENV_CACHE_DIR)
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "rf-spine-worktrees"


def resolve_commit(repo_root: Path, commit: str) -> str:
    """Развернуть ссылку в полный sha и убедиться, что объект на месте."""

    try:
        full = _git(repo_root, "rev-parse", f"{commit}^{{commit}}")
    except SubjectUnavailable as exc:
        raise SubjectUnavailable(
            f"base_commit {commit!r} is not in this clone. In CI this usually means a "
            f"shallow checkout: set 'fetch-depth: 0'. Refusing to fall back to the "
            f"working tree, because that is the defect this module exists to fix.\n{exc}"
        ) from exc
    return full


def subject_worktree(repo_root: Path, commit: str, cache_dir: Path | None = None) -> Path:
    """Путь к рабочему дереву репозитория на указанном коммите.

    Идемпотентно: существующее дерево на том же коммите переиспользуется.
    """

    full = resolve_commit(repo_root, commit)
    root = (cache_dir or cache_root()).resolve()
    destination = root / full

    if destination.is_dir():
        try:
            head = _git(destination, "rev-parse", "HEAD")
        except SubjectUnavailable:
            head = ""
        if head == full:
            return destination
        raise SubjectUnavailable(
            f"{destination} exists but is at {head or 'an unreadable HEAD'}, not {full}; "
            f"remove it or point {ENV_CACHE_DIR} elsewhere"
        )

    root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "worktree", "add", "--detach", "--quiet", str(destination), full)
    return destination


def prune(repo_root: Path) -> None:
    """Убрать записи об удалённых worktree'ях. Для локальной уборки."""

    _git(repo_root, "worktree", "prune")
