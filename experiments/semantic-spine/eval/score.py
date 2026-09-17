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
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
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
QUANTUM = Decimal("0.0001")


def ratio(numerator: int, denominator: int) -> Fraction:
    return Fraction(0) if denominator == 0 else Fraction(numerator, denominator)


def quantize(value: Fraction) -> float:
    """Точная дробь -> 4 знака, одним детерминированным правилом.

    Раньше здесь было round() поверх уже округлённых float'ов, и это молча
    зависело от версии Python: CPython 3.12 добавил компенсированное
    суммирование в sum() для float'ов, поэтому 3.11 и 3.13 расходились в
    четвёртом знаке на значениях, попадающих на десятичную границу (5/6 ->
    0.83335). Сложение float'ов вдобавок не ассоциативно, так что результат
    зависел и от порядка задач.

    Байт-равенство, которое держится на том, с какой стороны от границы легло
    двоичное представление, — это не воспроизводимость, а везение.
    """

    exact = Decimal(value.numerator) / Decimal(value.denominator)
    return float(exact.quantize(QUANTUM, rounding=ROUND_HALF_UP))


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
    # Целые числители: агрегаты считаются от них, а не от округлённых долей.
    oracle_file_tokens: int = 0
    on_target_tokens: int = 0


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
                    file_recall=quantize(ratio(len(found), len(task.oracle_files))),
                    file_precision=quantize(ratio(bundle.tokens_on(task.oracle_files), tokens)),
                    oracle_targets_total=len(locations),
                    oracle_targets_covered=len(covered),
                    target_recall=quantize(ratio(len(covered), len(locations))),
                    target_precision=quantize(ratio(on_target_tokens, tokens)),
                    truncated=bundle.truncated,
                    missed_files=[p for p in task.oracle_files if p not in selected],
                    missed_targets=[
                        location.target.raw for location in locations if location not in covered
                    ],
                    oracle_file_tokens=bundle.tokens_on(task.oracle_files),
                    on_target_tokens=on_target_tokens,
                )
            )
    return rows, subjects


def aggregate(rows: list[Row]) -> list[dict]:
    by_strategy: dict[str, list[Row]] = {}
    for row in rows:
        by_strategy.setdefault(row.strategy, []).append(row)

    def macro(group: list[Row], numerator: str, denominator: str) -> float:
        """Macro-среднее по точным дробям: ни порядок, ни платформа не влияют."""

        total = sum(
            (ratio(getattr(r, numerator), getattr(r, denominator)) for r in group),
            Fraction(0),
        )
        return quantize(total / len(group))

    out = []
    for strategy, group in by_strategy.items():
        token_total = sum(r.context_tokens for r in group)
        out.append(
            {
                "strategy": strategy,
                "tasks": len(group),
                "mean_file_recall": macro(group, "oracle_files_found", "oracle_files_total"),
                "mean_file_precision": macro(group, "oracle_file_tokens", "context_tokens"),
                "mean_target_recall": macro(group, "oracle_targets_covered", "oracle_targets_total"),
                "mean_target_precision": macro(group, "on_target_tokens", "context_tokens"),
                "mean_context_tokens": float(
                    (Decimal(token_total) / Decimal(len(group))).quantize(
                        Decimal("0.1"), rounding=ROUND_HALF_UP
                    )
                ),
                "tasks_with_full_target_recall": sum(
                    1 for r in group if r.oracle_targets_covered == r.oracle_targets_total
                ),
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
