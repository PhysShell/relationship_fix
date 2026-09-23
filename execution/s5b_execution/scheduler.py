"""Какие юниты считать дальше и как разложить их по заданиям.

Замороженные объекты (`Unit`, `production_arms`, `assign`) берутся из
научного дерева и НЕ переопределяются. Меняется только вес юнита, а
`task_id` от веса не зависит — это отдельный гейт науки. Поэтому любая
перераскладка оставляет артефакты побайтово теми же.
"""

from __future__ import annotations

from simulation import s5b_escalation as E
from simulation import s5b_prereg as P
from simulation import s5b_shard as S

from . import cost
from .ledger import Ledger

#: доли горизонта, по одной на конец ключа
FRACTIONS = tuple(P.DELTA_FRACTIONS_OF_HORIZON)

#: все ключи сетки, порядок канонический и задан наукой
KEYS = tuple(E.KEYS)

#: Перераскладка не меняет ни одного научного числа именно потому, что
#: `task_id` считается от `(arm, look, keys)` и не включает вес.
TASK_ID_IS_INDEPENDENT_OF_COST = True


class PlanRefused(Exception):
    """План не построен. Пустой или неполный план не исполняется."""


def arms() -> dict[str, dict]:
    return {a["tag"]: a for a in S.production_arms()}


def units_for(look: int, ledger: Ledger | None = None) -> list:
    """Юниты ступени `look`, отфильтрованные по реестру.

    Без реестра — вся сетка (так считалась первая ступень). С реестром
    остаются только руки, где хоть один конец ещё не закрылся.

    Пересчёт уже закрывшегося конца науку не портит, он лишь стоит
    времени; подмену его значения не пускает `Ledger.absorb`, а не этот
    фильтр. Разделение намеренное: расписание отвечает за стоимость,
    реестр — за смысл.
    """
    out = []
    for tag, arm in arms().items():
        groups = cost.groups_needed(arm["effective_rate"], look, len(KEYS))
        if groups == 1:
            slices = (KEYS,)
        else:
            size = -(-len(KEYS) // groups)
            slices = tuple(KEYS[i:i + size] for i in range(0, len(KEYS), size))
        for keys in slices:
            if ledger is not None and not ledger.unit_is_needed(
                    tag, keys, FRACTIONS):
                continue
            out.append(S.Unit(arm=tag, look=look, keys=keys,
                              weight=cost.seconds_for(
                                  arm["effective_rate"], look)
                              * (len(keys) / len(KEYS))))
    return out


def shards_needed(units) -> int:
    """Наименьшее число заданий, при котором раскладка ВЛЕЗАЕТ в бюджет.

    Выводится проверкой настоящей раскладки, а не формулой: юниты
    неделимы, и формула уже однажды дала 4.12 ч при бюджете 4.0.
    """
    if not units:
        raise PlanRefused("юнитов нет: считать нечего")
    budget = cost.SHARD_BUDGET_HOURS * 3600.0
    heaviest = max(u.weight for u in units)
    if heaviest > budget:
        raise PlanRefused(
            f"юнит весом {heaviest/3600:.2f} ч не влезает в бюджет "
            f"{cost.SHARD_BUDGET_HOURS} ч и неделим")
    for count in range(1, S.GITHUB_MATRIX_MAX_JOBS + 1):
        buckets = S.assign(units, count)
        if all(sum(u.weight for u in b) <= budget for b in buckets):
            return count
    raise PlanRefused(
        f"{len(units)} юнитов не раскладываются в {S.GITHUB_MATRIX_MAX_JOBS} "
        f"заданий при бюджете {cost.SHARD_BUDGET_HOURS} ч")


def check_platform(buckets) -> None:
    """Ни одно задание не смеет превышать платформенный потолок."""
    if len(buckets) > S.GITHUB_MATRIX_MAX_JOBS:
        raise PlanRefused(f"{len(buckets)} заданий против потолка матрицы "
                          f"{S.GITHUB_MATRIX_MAX_JOBS}")
    for index, bucket in enumerate(buckets):
        total = sum(u.weight for u in bucket)
        if not cost.fits_platform(total):
            raise PlanRefused(
                f"задание {index}: {total/3600:.2f} ч против потолка "
                f"{cost.PLATFORM_CAP_HOURS:.2f} ч")
