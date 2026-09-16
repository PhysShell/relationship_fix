"""Phase 3: agent runner. Граница проведена, адаптер не подключён.

Здесь намеренно НЕТ ни одного адаптера, который бы «как будто» гонял агента.
Пустой прогон обязан падать, а не возвращать правдоподобные числа: единственное,
что хуже отсутствующего эксперимента, — эксперимент, который отчитался, не
состоявшись.

Чего не хватает, чтобы это поехало (и это работа Phase 3, не забытый TODO):
  1. скрытые acceptance-тесты по каждой задаче (сейчас acceptance.status =
     "not_authored");
  2. адаптер к конкретному агенту за интерфейсом AgentAdapter;
  3. изолированный workdir на base_commit каждой задачи.

Метрики считаются от записанной траектории, поэтому их можно и нужно тестировать
без агента — чем test_runner.py и занимается.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from spine.selector import ContextBundle, TaskSpec


class AgentNotConfigured(RuntimeError):
    """Поднимается вместо возврата нулей, когда адаптер не подключён."""


@dataclass
class Trajectory:
    """Всё, что прогон обязан записать о поведении агента."""

    files_touched: tuple[str, ...] = ()
    tests_passed: bool = False
    tests_ran: bool = False
    total_tokens: int = 0
    tool_calls: int = 0
    wall_time_ms: int = 0
    notes: str = ""


@dataclass
class RunMetrics:
    task_id: str
    strategy: str
    resolved: bool
    tests_ran: bool
    tests_passed: bool
    files_touched: int
    unexpected_files_touched: int
    localization_recall: float
    edit_precision: float
    context_tokens: int
    total_tokens: int
    tool_calls: int
    wall_time_ms: int


def compute_metrics(
    task: TaskSpec, bundle: ContextBundle, trajectory: Trajectory
) -> RunMetrics:
    """Метрики от задачи, выданного контекста и записанной траектории.

    `resolved` намеренно требует, чтобы тесты ДЕЙСТВИТЕЛЬНО прогонялись:
    `tests_passed=True` при `tests_ran=False` — это не успех, это пустой прогон.
    """

    oracle = set(task.oracle_files)
    touched = list(dict.fromkeys(trajectory.files_touched))
    hit = [path for path in touched if path in oracle]
    unexpected = [path for path in touched if path not in oracle]

    retrieved = set(bundle.files())
    localization_recall = len(oracle & retrieved) / len(oracle) if oracle else 0.0
    edit_precision = len(hit) / len(touched) if touched else 0.0

    return RunMetrics(
        task_id=task.id,
        strategy=bundle.strategy,
        resolved=bool(trajectory.tests_ran and trajectory.tests_passed),
        tests_ran=trajectory.tests_ran,
        tests_passed=trajectory.tests_passed,
        files_touched=len(touched),
        unexpected_files_touched=len(unexpected),
        localization_recall=round(localization_recall, 4),
        edit_precision=round(edit_precision, 4),
        context_tokens=bundle.tokens,
        total_tokens=trajectory.total_tokens,
        tool_calls=trajectory.tool_calls,
        wall_time_ms=trajectory.wall_time_ms,
    )


class AgentAdapter(Protocol):
    """Единственная точка, в которую подключается настоящий агент."""

    name: str

    def run(self, task: TaskSpec, bundle: ContextBundle, workdir: Path) -> Trajectory: ...


class UnconfiguredAdapter:
    """Адаптер по умолчанию: падает громко вместо тихого нуля."""

    name = "unconfigured"

    def run(self, task: TaskSpec, bundle: ContextBundle, workdir: Path) -> Trajectory:
        raise AgentNotConfigured(
            f"no agent adapter is wired for task '{task.id}'. Phase 3 needs: hidden "
            f"acceptance tests, an AgentAdapter implementation, and an isolated "
            f"workdir at {task.__class__.__name__}.base_commit. Refusing to emit metrics "
            f"for a run that did not happen."
        )


@dataclass
class PairedResult:
    """Одна задача × набор стратегий. Сравнение всегда парное по задаче."""

    task_id: str
    metrics: list[RunMetrics] = field(default_factory=list)

    def by_strategy(self) -> dict[str, RunMetrics]:
        return {metric.strategy: metric for metric in self.metrics}


def run_paired(
    tasks: Sequence[TaskSpec],
    bundles: dict[tuple[str, str], ContextBundle],
    adapter: AgentAdapter,
    workdir: Path,
) -> list[PairedResult]:
    results: list[PairedResult] = []
    for task in tasks:
        paired = PairedResult(task_id=task.id)
        for (task_id, strategy), bundle in sorted(bundles.items()):
            if task_id != task.id:
                continue
            trajectory = adapter.run(task, bundle, workdir)
            paired.metrics.append(compute_metrics(task, bundle, trajectory))
        results.append(paired)
    return results


def dump_results(results: Sequence[PairedResult], adapter_name: str, destination: Path) -> None:
    payload = {
        "schema_version": "rf.spine-run-result.v1",
        "adapter": adapter_name,
        "results": [
            {"task_id": result.task_id, "metrics": [asdict(m) for m in result.metrics]}
            for result in results
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
