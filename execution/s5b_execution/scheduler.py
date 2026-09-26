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


def key_slices(groups: int) -> tuple:
    """Ключи, порезанные на `groups` групп. ОДНА функция на весь слой.

    Ею пользуется и планировщик, и калибровка экономии деления. Вторая
    реализация того же разреза означала бы, что калибровка измеряет не то,
    что потом исполняется, — а именно за это расхождение уже был заплачен
    один отменённый прогон.

    Порядок ключей канонический и задан наукой. Срезы СМЕЖНЫЕ, поэтому при
    неоднородной стоимости ключа группы окажутся неравными: это свойство
    раскладки, а не дефект, и калибровка обязана его измерить, а не
    усреднить.
    """
    if groups < 1:
        raise PlanRefused(f"групп должно быть хотя бы одна, дано {groups}")
    if groups > len(KEYS):
        raise PlanRefused(f"групп {groups} больше, чем ключей {len(KEYS)}")
    if groups == 1:
        return (KEYS,)
    size = -(-len(KEYS) // groups)
    return tuple(KEYS[i:i + size] for i in range(0, len(KEYS), size))


def units_for(look: int, ledger: Ledger | None = None,
              skip: set[str] | None = None) -> list:
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
        for keys in key_slices(groups):
            if ledger is not None and not ledger.unit_is_needed(
                    tag, keys, FRACTIONS):
                continue
            unit = S.Unit(arm=tag, look=look, keys=keys,
                          weight=cost.seconds_for(arm["effective_rate"], look)
                          * (len(keys) / len(KEYS)))
            if skip and unit.task_id in skip:
                continue                      # уже посчитан прошлым прогоном
            out.append(S.Unit(arm=tag, look=look, keys=keys,
                              weight=cost.seconds_for(
                                  arm["effective_rate"], look)
                              * (len(keys) / len(KEYS))))
    return out


def makespan(buckets, max_parallel: int) -> float:
    """Предсказанное время ПРОГОНА при `max_parallel` одинаковых слотах.

    Список заданий раскладывается на слоты жадно: очередное задание уходит
    в слот, освобождающийся раньше всех. Это ровно то, что делает GitHub,
    и ровно то, чего не знает «время худшего задания».

    Считать число волн как `ceil(n / parallel) * budget` — грубее: волны
    предполагают, что все задания одинаковы. LPT делает их почти
    одинаковыми, но не точно, и на хвосте разница видна.
    """
    if max_parallel < 1:
        raise PlanRefused("одновременных заданий должно быть хотя бы одно")
    slots = [0.0] * max_parallel
    costs = sorted((sum(u.weight for u in b) + cost.JOB_OVERHEAD_SECONDS
                    for b in buckets), reverse=True)
    for c in costs:
        i = min(range(max_parallel), key=lambda k: slots[k])
        slots[i] += c
    return max(slots)


def shards_needed(units, max_parallel: int = None) -> int:
    """Число заданий, минимизирующее предсказанный MAKESPAN.

    Не «наименьшее, при котором влезает в бюджет». Эти две задачи
    расходятся: мельче дробить — каждое задание безопаснее, но заданий
    больше, и при ограниченном числе слотов прогон идёт ДОЛЬШЕ.

    Ограничения, все обязательные:
        каждое задание <= бюджета шарда;
        заданий <= потолка матрицы;
        одновременность <= объявленного max_parallel (его ставит
            `strategy.max-parallel`, а не наша арифметика).

    Юниты неделимы, поэтому и здесь проверяется НАСТОЯЩАЯ раскладка, а не
    формула: формула уже однажды дала 4.12 ч при бюджете 4.0.
    """
    if not units:
        raise PlanRefused("юнитов нет: считать нечего")
    if max_parallel is None:
        max_parallel = cost.MAX_PARALLEL
    budget = cost.SHARD_BUDGET_HOURS * 3600.0
    heaviest = max(u.weight for u in units)
    if heaviest > budget:
        raise PlanRefused(
            f"юнит весом {heaviest/3600:.2f} ч не влезает в бюджет "
            f"{cost.SHARD_BUDGET_HOURS} ч и неделим")
    best = None
    for count in range(1, min(len(units), S.GITHUB_MATRIX_MAX_JOBS) + 1):
        buckets = S.assign(units, count)
        if any(sum(u.weight for u in b) > budget for b in buckets):
            continue
        span = makespan(buckets, max_parallel)
        # при равном makespan берётся МЕНЬШЕЕ число заданий: лишние
        # задания стоят очередей и чужих слотов, ничего не ускоряя
        if best is None or span < best[0] - 1e-9:
            best = (span, count)
    if best is None:
        raise PlanRefused(
            f"{len(units)} юнитов не раскладываются в "
            f"{S.GITHUB_MATRIX_MAX_JOBS} заданий при бюджете "
            f"{cost.SHARD_BUDGET_HOURS} ч")
    return best[1]


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
