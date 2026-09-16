"""Phase 2: измерение ОТБОРА КОНТЕКСТА, без агента и без LLM.

Исследуемый репозиторий берётся из worktree на `base_commit` задачи, а не из
текущего рабочего дерева. Поэтому прогон воспроизводим: числа не зависят от
того, что завтра появится в основном репозитории.

Два уровня ground truth:
  * file-level   — принесла ли стратегия нужный ФАЙЛ (старая метрика);
  * target-level — попала ли в контекст именно строка-определение (заголовок,
    символ, ключ артефакта). Без второго уровня chunk-стратегии получают
    структурное преимущество над whole-file oracle'ом, и вывод вырождается в
    «наш chunking лучше, чем читать файл целиком».

Чего он НЕ умеет: сказать, решил ли агент задачу. Это Phase 3.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPINE_ROOT = HERE.parent
REPO = SPINE_ROOT.parent.parent
sys.path.insert(0, str(SPINE_ROOT))

from spine.budget import ContextBudget  # noqa: E402
from spine.compiler import compile_spec_dir  # noqa: E402
from spine.selector import FILL_POLICIES, FILL_PREFIX, STRATEGIES, TaskSpec  # noqa: E402
from spine.subject import subject_worktree  # noqa: E402
from spine.targets import covers, locate_all  # noqa: E402

DEFAULT_BUDGET = 8000


@dataclass
class Row:
    task_id: str
    strategy: str
    budget_tokens: int
    context_tokens: int
    chunks: int
    files: int
    oracle_files_total: int
    oracle_files_found: int
    file_recall: float
    file_precision: float
    oracle_targets_total: int
    oracle_targets_covered: int
    target_recall: float
    target_precision: float
    truncated: bool
    missed_files: list[str]
    missed_targets: list[str]


def load_tasks() -> list[TaskSpec]:
    return [TaskSpec.load(path) for path in sorted((HERE / "tasks").glob("*.json"))]


def score(budget_tokens: int, fill: str = FILL_PREFIX) -> tuple[list[Row], dict[str, str]]:
    compilation = compile_spec_dir(SPINE_ROOT / "spec")
    budget = ContextBudget(max_tokens=budget_tokens)
    rows: list[Row] = []
    subjects: dict[str, str] = {}

    for task in load_tasks():
        subject = subject_worktree(REPO, task.base_commit)
        subjects[task.id] = task.base_commit
        locations = locate_all(subject, list(task.oracle_targets))

        for name, strategy_cls in STRATEGIES.items():
            bundle = strategy_cls(subject, compilation, fill).select(task, budget)
            selected = set(bundle.files())
            found = [path for path in task.oracle_files if path in selected]

            covered = [
                location
                for location in locations
                if any(covers(location, chunk.path, chunk.text) for chunk in bundle.chunks)
            ]
            on_target_tokens = sum(
                chunk.tokens
                for chunk in bundle.chunks
                if any(covers(location, chunk.path, chunk.text) for location in locations)
            )

            tokens = bundle.tokens
            rows.append(
                Row(
                    task_id=task.id,
                    strategy=name,
                    budget_tokens=budget_tokens,
                    context_tokens=tokens,
                    chunks=len(bundle.chunks),
                    files=len(selected),
                    oracle_files_total=len(task.oracle_files),
                    oracle_files_found=len(found),
                    file_recall=round(len(found) / len(task.oracle_files), 4),
                    file_precision=round(bundle.tokens_on(task.oracle_files) / tokens, 4) if tokens else 0.0,
                    oracle_targets_total=len(locations),
                    oracle_targets_covered=len(covered),
                    target_recall=round(len(covered) / len(locations), 4) if locations else 0.0,
                    target_precision=round(on_target_tokens / tokens, 4) if tokens else 0.0,
                    truncated=bundle.truncated,
                    missed_files=[p for p in task.oracle_files if p not in selected],
                    missed_targets=[
                        location.target.raw for location in locations if location not in covered
                    ],
                )
            )
    return rows, subjects


def aggregate(rows: list[Row]) -> list[dict]:
    by_strategy: dict[str, list[Row]] = {}
    for row in rows:
        by_strategy.setdefault(row.strategy, []).append(row)

    def mean(group: list[Row], attribute: str) -> float:
        return round(sum(getattr(r, attribute) for r in group) / len(group), 4)

    out = []
    for strategy, group in by_strategy.items():
        out.append(
            {
                "strategy": strategy,
                "tasks": len(group),
                "mean_file_recall": mean(group, "file_recall"),
                "mean_file_precision": mean(group, "file_precision"),
                "mean_target_recall": mean(group, "target_recall"),
                "mean_target_precision": mean(group, "target_precision"),
                "mean_context_tokens": round(sum(r.context_tokens for r in group) / len(group), 1),
                "tasks_with_full_target_recall": sum(1 for r in group if r.target_recall == 1.0),
            }
        )
    out.sort(key=lambda i: (-i["mean_target_recall"], -i["mean_file_recall"], i["strategy"]))
    return out


def markdown_table(summary: list[dict]) -> str:
    lines = [
        "| strategy | target recall | file recall | target prec | tokens | full target recall |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in summary:
        lines.append(
            f"| {item['strategy']} | {item['mean_target_recall']:.2f} | "
            f"{item['mean_file_recall']:.2f} | {item['mean_target_precision']:.2f} | "
            f"{item['mean_context_tokens']:.0f} | "
            f"{item['tasks_with_full_target_recall']}/{item['tasks']} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="score context selection strategies")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="token budget per strategy")
    parser.add_argument("--out", type=Path, default=None, help="write the full result JSON here")
    parser.add_argument(
        "--fill",
        choices=FILL_POLICIES,
        default=FILL_PREFIX,
        help="budget packing policy; 'prefix' puts the strategy's ranking under test",
    )
    args = parser.parse_args(argv)

    rows, subjects = score(args.budget, args.fill)
    payload = {
        "schema_version": "rf.spine-selection-result.v2",
        "budget_tokens": args.budget,
        "fill_policy": args.fill,
        "token_counter": "spine.budget.approx_tokens (deterministic proxy, not a BPE tokenizer)",
        "subject_commits": subjects,
        "note": (
            "Selection only, against a pinned subject worktree per task. No agent was run; "
            "resolved/tests_passed are not measured here."
        ),
        "summary": aggregate(rows),
        "rows": [asdict(row) for row in rows],
    }

    suffix = "" if args.fill == FILL_PREFIX else f"-{args.fill}"
    destination = args.out or (HERE / "results" / f"selection-{args.budget}{suffix}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(markdown_table(payload["summary"]))
    # --out принимает любой путь, в том числе вне каталога harness'а (так его
    # зовёт CI), поэтому относительный путь только когда он вообще существует.
    try:
        shown = destination.resolve().relative_to(SPINE_ROOT)
    except ValueError:
        shown = destination
    print(f"\nwritten: {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
