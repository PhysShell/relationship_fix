"""Phase 2: измерение ОТБОРА КОНТЕКСТА, без агента и без LLM.

Что этот скрипт умеет ответить честно: находит ли стратегия нужные файлы
репозитория в пределах фиксированного бюджета, и сколько бюджета она тратит
не на них. Чего он НЕ умеет: сказать, решил ли агент задачу — для этого нужен
runner из Phase 3 и скрытые acceptance-тесты, которых пока нет.

Правило бенчмарка: ни один oracle-файл не принадлежит harness'у. Иначе spine
выигрывает по построению, а мы получаем красивую таблицу ни о чём.
"""

from __future__ import annotations

import argparse
import json
import subprocess
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

DEFAULT_BUDGET = 8000


@dataclass
class Row:
    task_id: str
    strategy: str
    budget_tokens: int
    context_tokens: int
    chunks: int
    files: int
    oracle_total: int
    oracle_found: int
    localization_recall: float
    context_precision: float
    truncated: bool
    missed: list[str]


def head_commit() -> str:
    """Числа baseline'ов зависят от содержимого репозитория, поэтому снимок
    без коммита нечитаем: непонятно, против чего мерили."""

    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def load_tasks() -> list[TaskSpec]:
    return [TaskSpec.load(path) for path in sorted((HERE / "tasks").glob("*.json"))]


def score(budget_tokens: int, fill: str = FILL_PREFIX) -> list[Row]:
    compilation = compile_spec_dir(SPINE_ROOT / "spec")
    budget = ContextBudget(max_tokens=budget_tokens)
    rows: list[Row] = []

    for task in load_tasks():
        for name, strategy_cls in STRATEGIES.items():
            bundle = strategy_cls(REPO, compilation, fill).select(task, budget)
            selected = set(bundle.files())
            found = [path for path in task.oracle_files if path in selected]
            tokens = bundle.tokens
            rows.append(
                Row(
                    task_id=task.id,
                    strategy=name,
                    budget_tokens=budget_tokens,
                    context_tokens=tokens,
                    chunks=len(bundle.chunks),
                    files=len(selected),
                    oracle_total=len(task.oracle_files),
                    oracle_found=len(found),
                    localization_recall=round(len(found) / len(task.oracle_files), 4),
                    context_precision=round(bundle.tokens_on(task.oracle_files) / tokens, 4) if tokens else 0.0,
                    truncated=bundle.truncated,
                    missed=[path for path in task.oracle_files if path not in selected],
                )
            )
    return rows


def aggregate(rows: list[Row]) -> list[dict]:
    by_strategy: dict[str, list[Row]] = {}
    for row in rows:
        by_strategy.setdefault(row.strategy, []).append(row)
    out = []
    for strategy, group in by_strategy.items():
        out.append(
            {
                "strategy": strategy,
                "tasks": len(group),
                "mean_localization_recall": round(sum(r.localization_recall for r in group) / len(group), 4),
                "mean_context_precision": round(sum(r.context_precision for r in group) / len(group), 4),
                "mean_context_tokens": round(sum(r.context_tokens for r in group) / len(group), 1),
                "tasks_with_full_recall": sum(1 for r in group if r.localization_recall == 1.0),
            }
        )
    out.sort(key=lambda item: (-item["mean_localization_recall"], -item["mean_context_precision"], item["strategy"]))
    return out


def markdown_table(summary: list[dict]) -> str:
    header = "| strategy | recall | precision | tokens | full-recall tasks |"
    sep = "|---|---:|---:|---:|---:|"
    lines = [header, sep]
    for item in summary:
        lines.append(
            f"| {item['strategy']} | {item['mean_localization_recall']:.2f} | "
            f"{item['mean_context_precision']:.2f} | {item['mean_context_tokens']:.0f} | "
            f"{item['tasks_with_full_recall']}/{item['tasks']} |"
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

    rows = score(args.budget, args.fill)
    summary = aggregate(rows)
    payload = {
        "schema_version": "rf.spine-selection-result.v1",
        "budget_tokens": args.budget,
        "fill_policy": args.fill,
        "repo_commit": head_commit(),
        "token_counter": "spine.budget.approx_tokens (deterministic proxy, not a BPE tokenizer)",
        "note": "Selection only. No agent was run; resolved/tests_passed are not measured here.",
        "summary": summary,
        "rows": [asdict(row) for row in rows],
    }

    suffix = "" if args.fill == FILL_PREFIX else f"-{args.fill}"
    destination = args.out or (HERE / "results" / f"selection-{args.budget}{suffix}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(markdown_table(summary))
    print(f"\nwritten: {destination.relative_to(SPINE_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
