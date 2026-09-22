"""Раскладка этапа 1 по шардам. ВЫЧИСЛИТЕЛЬНЫЙ слой, научного в нём нет.

ЧТО ЗДЕСЬ РАЗРЕШЕНО МЕНЯТЬ И ЧТО ЗАПРЕЩЕНО. Разрешено — КТО и В КАКОМ
ПОРЯДКЕ считает. Запрещено — ЧТО получается. Эстиманд, сетка, пороги,
семантика сидов, правила классификации и критерии не входят в этот модуль
вообще, и это проверяется эквивалентностью: `serial == sharded ==
reordered`.

ЕДИНИЦА РАБОТЫ — ДИАПАЗОН ПЕРИОДОВ ОДНОЙ РУКИ, а не «просмотр целиком»:

    unit = (arm_tag, start, stop)

потому что лестница ВЛОЖЕНА. Отдельные задания на 4000, 16000 и 64000
пересчитывали бы одно и то же трижды. Диапазоны же дают ровно то, что
нужно: склад просмотра `L` есть объединение юнитов с `stop <= L`.

ГРАНИЦЫ ЮНИТОВ ВЫРОВНЕНЫ ПО ЛЕСТНИЦЕ. Ни один юнит не пересекает
`4000`, `16000` или `64000`, иначе просмотр нельзя было бы собрать из
завершённых юнитов, не заглядывая в недосчитанный. Внутри ступени юнит
дробится дальше — ради балансировки, не ради науки.

`task_id` — ФУНКЦИЯ ТОЛЬКО НАУЧНЫХ КООРДИНАТ. Ни номер шарда, ни их число,
ни порядок в него не входят. Поэтому одно и то же задание при любой
раскладке имеет одно и то же имя, и повторный запуск его узнаёт.

ЖАДНАЯ РАСКЛАДКА, А НЕ РАЗРЕЗАНИЕ ПОПОЛАМ. Непрерывные равные куски дают
перекос: рука с высокой ставкой возможностей дороже руки с низкой в
несколько раз, и шард, которому достались только дорогие, задержит всех.
LPT (longest processing time first) на это и отвечает.

РАННИЙ СЧЁТ РАЗРЕШЁН, РАННИЙ ВЗГЛЯД — НЕТ. Физически посчитать
`i = 16000..63999` заранее можно; научная процедура обязана не смотреть на
них до соответствующего просмотра. Это два разных запрета, и путать их не
нужно: компьютеры могут знать будущее, статистика — нет. Гейт называется
`store_for_look` и ничего, кроме завершённых юнитов своей ступени, в склад
не пускает.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from simulation import s5b_escalation as E
from simulation import s5b_precision as PR

#: Цена одного периода в секундах при опорной ставке. Замер, а не догадка:
#: 60 периодов полной руки (все 72 ключа) заняли 1.16 с при rate = 6.
SECONDS_PER_PERIOD_AT_REFERENCE = 1.16 / 60.0
REFERENCE_RATE = 6.0

#: Целевая длительность юнита. Мельче числа воркеров — иначе хвост одного
#: длинного задания определяет весь прогон.
TARGET_UNIT_SECONDS = 600.0
MIN_UNIT_PERIODS = 250

# ---------------------------------------------------------------------------
# ПЛАТФОРМЕННЫЕ ПРЕДЕЛЫ — СВЕРЕНЫ С ДОКУМЕНТАЦИЕЙ, А НЕ ВЗЯТЫ ПО ПАМЯТИ
# ---------------------------------------------------------------------------
#
#   «A job matrix can generate a maximum of 256 jobs per workflow run. This
#    limit applies to both GitHub-hosted and self-hosted runners.»
#   «GitHub-hosted runners: up to 6 hours per job.»
#
# Оба предела меняют КОНСТРУКЦИЮ, а не оформление. При 1365 юнитах третьей
# ступени «один юнит — одно задание» невозможно в принципе: это в пять раз
# больше потолка матрицы. Поэтому юниты группируются в шарды, и шард — это
# задание, а не юнит.
GITHUB_MATRIX_MAX_JOBS = 256
GITHUB_JOB_MAX_HOURS = 6.0

#: Бюджет шарда с запасом на checkout, установку и выгрузку артефакта.
#: Упереться в шестичасовой потолок значит потерять ВСЮ работу задания.
SHARD_BUDGET_HOURS = 4.0


class PlanRefused(Exception):
    """План нарушает платформенный предел. Лучше отказ, чем потеря работы."""


def shards_needed(units) -> int:
    """Минимум шардов, при котором ни один не упрётся в потолок задания."""
    total = sum(u.weight for u in units)
    if total <= 0.0:
        return 1
    return max(1, -(-int(total) // int(SHARD_BUDGET_HOURS * 3600)))


def check_platform_limits(buckets) -> None:
    """Отказ, если матрица или длительность задания вне документированных
    пределов. Проверяется ПЕРЕД запуском, а не по факту отмены."""
    if len(buckets) > GITHUB_MATRIX_MAX_JOBS:
        raise PlanRefused(
            f"{len(buckets)} шардов против потолка матрицы "
            f"{GITHUB_MATRIX_MAX_JOBS}")
    for index, bucket in enumerate(buckets):
        hours = sum(u.weight for u in bucket) / 3600.0
        if hours > SHARD_BUDGET_HOURS:
            raise PlanRefused(
                f"шард {index}: {hours:.2f} ч против бюджета "
                f"{SHARD_BUDGET_HOURS} ч (потолок задания "
                f"{GITHUB_JOB_MAX_HOURS} ч)")


@dataclass(frozen=True, slots=True)
class Unit:
    """Диапазон периодов одной руки. Имя стабильно, вес — оценка."""

    arm: str
    start: int
    stop: int
    look: int          # ступень лестницы, которую этот юнит достраивает
    weight: float

    @property
    def periods(self) -> int:
        return self.stop - self.start

    @property
    def task_id(self) -> str:
        """Стабильное имя. Ни shard, ни worker, ни порядок в него не входят."""
        raw = f"{self.arm}|{self.start}|{self.stop}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cost_of(rate: float, periods: int) -> float:
    """Оценка секунд. Линейна по периодам и по ставке возможностей.

    Оценка влияет ТОЛЬКО на балансировку. Ошибиться в ней значит считать
    дольше, а не посчитать другое.
    """
    return (periods * SECONDS_PER_PERIOD_AT_REFERENCE
            * max(rate, 1e-9) / REFERENCE_RATE)


def _split(start: int, stop: int, rate: float) -> list[tuple[int, int]]:
    """Дробление ступени на юниты целевой длительности."""
    total = stop - start
    if total <= 0:
        return []
    per_unit = cost_of(rate, 1)
    want = max(MIN_UNIT_PERIODS, int(TARGET_UNIT_SECONDS / max(per_unit, 1e-12)))
    parts = max(1, -(-total // want))            # ceil
    size = -(-total // parts)
    out, cursor = [], start
    while cursor < stop:
        end = min(stop, cursor + size)
        out.append((cursor, end))
        cursor = end
    return out


def plan(arms, ladder=PR.LOOKS) -> tuple[Unit, ...]:
    """Детерминированный манифест. Порядок и состав — функция только входа.

    `arms` — последовательность `(arm_tag, rate)`. Ступени лестницы режутся
    по границам: юнит НИКОГДА не пересекает `4000`, `16000`, `64000`.
    """
    units: list[Unit] = []
    for arm, rate in arms:
        previous = 0
        for look in ladder:
            for start, stop in _split(previous, look, rate):
                units.append(Unit(arm=arm, start=start, stop=stop, look=look,
                                  weight=cost_of(rate, stop - start)))
            previous = look
    return tuple(units)


def assign(units, shards: int) -> tuple[tuple[Unit, ...], ...]:
    """LPT: самые дорогие первыми, каждый — в наименее загруженный шард.

    Раскладка МЕНЯЕТ порядок исполнения и ничего больше. `task_id` юнита от
    неё не зависит, поэтому при другом числе шардов имена заданий те же.
    """
    if shards < 1:
        raise ValueError("шардов должно быть хотя бы один")
    buckets: list[list[Unit]] = [[] for _ in range(shards)]
    load = [0.0] * shards
    ordered = sorted(units, key=lambda u: (-u.weight, u.task_id))
    for unit in ordered:
        target = min(range(shards), key=lambda i: (load[i], i))
        buckets[target].append(unit)
        load[target] += unit.weight
    return tuple(tuple(bucket) for bucket in buckets)


# ---------------------------------------------------------------------------
# слияние: ОТКАЗ ПО УМОЛЧАНИЮ
# ---------------------------------------------------------------------------

class MergeRefused(Exception):
    """Слияние отказано. Частичный склад молча не собирается."""


def store_digest(store) -> str:
    """Стабильный дайджест склада. Не зависит от порядка ключей."""
    parts = []
    for key in sorted(store, key=repr):
        pieces = store[key]
        parts.append(repr(key))
        for period in pieces:
            parts.append(";".join(f"{p.n!r},{p.b!r}" for p in period))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def merge(arm: str, parts, *, look: int, expected) -> dict:
    """Склад руки на просмотре `look` из частей. ЛЮБОЙ изъян — отказ.

    `parts` — последовательность `(Unit, store)`. `expected` — юниты,
    которые манифест объявил для этой руки и этой ступени. Отказ, а не
    предупреждение, потому что недосчитанный склад внешне неотличим от
    досчитанного: он просто короче.
    """
    wanted = tuple(u for u in expected if u.arm == arm and u.stop <= look)
    got = {}
    for unit, store in parts:
        if unit.arm != arm or unit.stop > look:
            continue
        if unit.task_id in got:
            raise MergeRefused(f"юнит {unit.task_id} прислан дважды")
        got[unit.task_id] = (unit, store)

    missing = [u.task_id for u in wanted if u.task_id not in got]
    if missing:
        raise MergeRefused(f"не хватает юнитов: {missing}")
    extra = [t for t in got if t not in {u.task_id for u in wanted}]
    if extra:
        raise MergeRefused(f"лишние юниты: {extra}")

    ordered = sorted((got[u.task_id] for u in wanted),
                     key=lambda pair: pair[0].start)
    cursor = 0
    for unit, _ in ordered:
        if unit.start != cursor:
            raise MergeRefused(
                f"разрыв или перехлёст: ждали {cursor}, пришёл {unit.start}")
        cursor = unit.stop
    if cursor != look:
        raise MergeRefused(f"покрытие обрывается на {cursor}, а нужно {look}")

    merged: dict = {}
    for _, store in ordered:
        for key, pieces in store.items():
            merged.setdefault(key, []).extend(pieces)
    return merged


def store_for_look(arm: str, parts, *, look: int, expected) -> dict:
    """Склад ровно этой ступени. Юниты следующих ступеней НЕ видны.

    Ранний счёт разрешён, ранний взгляд запрещён: части с `stop > look`
    отбрасываются, даже если они уже посчитаны и лежат рядом.
    """
    return merge(arm, parts, look=look, expected=expected)


def run_unit(unit: Unit, **arm) -> dict:
    """Исполнение одного задания. Ничего, кроме своего диапазона.

    Параметры руки прокидываются как есть, включая `regime`/`magnitude`:
    розыгрыш эффекта идёт из потока, зависящего только от `(tag, i)`, а не
    от того, какому шарду достался диапазон.
    """
    return E.accumulate(unit.arm, unit.start, unit.stop, **arm)
