"""Раскладка этапа 1 по шардам. ВЫЧИСЛИТЕЛЬНЫЙ слой, научного в нём нет.

ЧТО ЗДЕСЬ РАЗРЕШЕНО МЕНЯТЬ И ЧТО ЗАПРЕЩЕНО. Разрешено — КТО и В КАКОМ
ПОРЯДКЕ считает. Запрещено — ЧТО получается. Эстиманд, сетка, пороги,
семантика сидов, правила классификации и критерии сюда не входят, и это
проверяется эквивалентностью юнита монолиту, а не обещается.

ОСЬ РАЗРЕЗА — КЛЮЧИ, А НЕ ДИАПАЗОНЫ ПЕРИОДОВ, и выбрана она замером, а не
вкусом. Первая редакция резала периоды: юнит считал `start..stop` и отдавал
частичный склад, который потом сливался. Два числа её отменили.

    склад весит 1640 байт на период на все 72 ключа
      -> между ступенями пришлось бы возить 1.0 + 3.1 + 12.3 = 16.4 ГБ

    генерация диад   5% стоимости периода
    работа по ключам 95%

Шестнадцать гигабайт не запрещены физически — включённое хранилище
артефактов идёт от 500 МБ до 50 ГБ по планам, а превышение в части планов
переходит в оплачиваемое. Но возить их ради экономии CPU, который
детерминирован и дёшево пересчитывается, попросту нелепо.

Поэтому юнит есть `(рука, ступень, ГРУППА КЛЮЧЕЙ)`. Он считает ПРЕФИКС
`0..look` целиком сам и отдаёт только концы своих ключей. Промежуточное
состояние не передаётся вовсе, сливать нечего — части конкатенируются.

ВЛОЖЕННОСТЬ СОХРАНЯЕТСЯ ТОЧНО. Период `i` определяется сидом `f"{tag}:{i}"`,
поэтому ступень 3, пересчитав `0..64000`, получает для `0..4000` ПОБИТОВО
те же наблюдения, что видела ступень 1. Пересчёт не создаёт новой выборки;
он повторяет вычисление, а не эксперимент.

ЦЕНА ЧЕСТНАЯ: около +39% CPU (373.8 ч против 284.8 ч, если эскалируют все
руки) — каждая ступень пересчитывает префикс, и каждая лишняя группа
ключей добавляет 5% на регенерацию диад.

`task_id` — ФУНКЦИЯ ТОЛЬКО НАУЧНЫХ КООРДИНАТ: рука, ступень, ключи. Ни
номер шарда, ни их число, ни порядок в него не входят, поэтому при любой
раскладке имя задания одно и то же, и повторный запуск его узнаёт.

ЖАДНАЯ РАСКЛАДКА, А НЕ РАЗРЕЗАНИЕ ПОПОЛАМ: рука с высокой ставкой дороже
руки с низкой в десятки раз, и шард, которому достались только дорогие,
задержит всех. LPT на это и отвечает.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from simulation import s5b_escalation as E
from simulation import s5b_precision as PR
from simulation import s5b_prereg as P

# ЦЕНА ПЕРИОДА — ЗАМЕР НА ТОМ ЖЕЛЕЗЕ, ГДЕ БУДЕТ СЧИТАТЬСЯ.
#
# Первое значение (1.16 с на 60 периодов при rate = 6, то есть 0.0193333)
# снято на машине разработчика: 4 x Intel Xeon @ 2.10GHz, 15 ГБ, Python
# 3.11.15. Сравнивать его с шестичасовым потолком GitHub было бы выдачей
# бенчмарка одной машины за время другой, поэтому самый дорогой юнит сетки
# прогнан на настоящем ubuntu-latest (run 35769710129):
#
#     эффективная ставка 120, look 64000, 36 ключей из 72
#     факт      16035.7 с = 4.454 ч
#     прогноз              3.610 ч
#     коэффициент          1.2343
#
# Значение ниже выведено ИЗ ЭТОГО ЗАМЕРА, а не домножением старого числа:
#
#     X = 16035.7 / (64000 * (120/6) * (0.05 + 0.95*0.5)) = 0.0238626
#
# ЧТО ЭТО ЗА ЧИСЛО И ЧТО ОНО НЕ ЗНАЧИТ. Это ОДНА точка: один юнит, один
# раннер, один момент. Производительность публичных раннеров плавает, и
# считать `0.0238626` точным было бы той же ошибкой в новой обёртке.
# Запас держит НЕ точность этого числа, а `SHARD_BUDGET_HOURS = 4.0` при
# потолке 6.0: полтора часа сверху на то, что раннер окажется медленнее
# ещё в полтора раза.
SECONDS_PER_PERIOD_AT_REFERENCE = 0.0238626
SECONDS_PER_PERIOD_MEASURED_ON = "ubuntu-latest, run 35769710129, 2026-09-22"
SECONDS_PER_PERIOD_BEFORE_SMOKE = 1.16 / 60.0
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
    """Минимум шардов, при котором РЕАЛЬНАЯ раскладка укладывается в бюджет.

    Формула «сумма делить на бюджет» ошибается, и ошибается в опасную
    сторону: юнит неделим, поэтому идеальной упаковки не бывает, и на
    второй ступени она давала 4.12 ч при бюджете 4.0 ч. Число выводится
    ПРОВЕРКОЙ раскладки, а не оценкой средней нагрузки: считать нужно то,
    что будет исполнено, а не то, что получилось бы при равномерности.
    """
    units = list(units)
    if not units:
        return 1
    total = sum(u.weight for u in units)
    budget = SHARD_BUDGET_HOURS * 3600.0
    start = max(1, -(-int(total) // int(budget)))
    for count in range(start, GITHUB_MATRIX_MAX_JOBS + 1):
        try:
            check_platform_limits(assign(units, count))
        except PlanRefused:
            continue
        return count
    raise PlanRefused(
        f"даже {GITHUB_MATRIX_MAX_JOBS} шардов не укладываются в бюджет "
        f"{SHARD_BUDGET_HOURS} ч: самый дорогой юнит "
        f"{max(u.weight for u in units) / 3600:.2f} ч")


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


#: ДОЛЯ ГЕНЕРАЦИИ ДИАД В СТОИМОСТИ ПЕРИОДА — ЗАМЕР, а не прикидка:
#: 60 периодов дали 0.06 с на генерацию и 1.06 с на работу по 72 ключам.
#: Именно это число и решило ось разреза: регенерировать диады в каждой
#: группе ключей стоит 5%, а тащить между ступенями промежуточный склад —
#: 16.4 ГБ.
GENERATION_SHARE = 0.05


@dataclass(frozen=True, slots=True)
class Unit:
    """Рука x ступень x ГРУППА КЛЮЧЕЙ. Префикс `0..look` считается целиком."""

    arm: str
    look: int
    keys: tuple
    weight: float

    @property
    def task_id(self) -> str:
        """Стабильное имя. Только научные координаты: рука, ступень, ключи."""
        raw = f"{self.arm}|{self.look}|" + ";".join(repr(k) for k in self.keys)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cost_of(rate: float, look: int, share: float = 1.0) -> float:
    """Оценка секунд. Генерация диад не делится, работа по ключам делится.

    Оценка влияет ТОЛЬКО на балансировку: ошибиться в ней значит считать
    дольше, а не посчитать другое.
    """
    full = (look * SECONDS_PER_PERIOD_AT_REFERENCE
            * max(rate, 1e-9) / REFERENCE_RATE)
    return full * (GENERATION_SHARE + (1.0 - GENERATION_SHARE) * share)


def groups_needed(rate: float, look: int) -> int:
    """Сколько групп ключей нужно, чтобы уложиться в бюджет задания.

    Для `rate = 96` на третьей ступени одна группа даёт 5.5 ч при потолке
    задания 6 ч — запаса нет, и упереться в потолок значит потерять ВСЮ
    работу задания. Две группы дают 2.9 ч.
    """
    for groups in range(1, len(E.KEYS) + 1):
        if cost_of(rate, look, 1.0 / groups) <= SHARD_BUDGET_HOURS * 3600.0:
            return groups
    return len(E.KEYS)


def key_groups(groups: int) -> tuple[tuple, ...]:
    """Смежные группы канонического порядка. `delta` снаружи, поэтому
    группа покрывает целые разрешения и чужой `to_bins` не считается."""
    total = len(E.KEYS)
    size = -(-total // groups)
    return tuple(E.KEYS[i:i + size] for i in range(0, total, size))


def production_arms():
    """Все руки сетки с ЭФФЕКТИВНОЙ ставкой для оценки стоимости.

    Нагрузка идёт не по ставке сетки, а по `rate * ratio * c_rate`: у
    режимов без канала incidence (`ratio = 1`) и при сильной
    c-реактивности она до 1.25 раза выше. Считать по ставке сетки значило
    бы недооценить ровно самые тяжёлые руки — то есть те, которые и
    упираются в потолок задания.
    """
    from simulation import s5b_stage1 as legacy
    out = []
    for rate in P.OPPORTUNITY_RATE_GRID:
        for c_rate, c_shift in P.C_REACTIVITY_POINTS:
            for regime, magnitude in legacy.REGIMES:
                _, ratio = E.regime_effect("cost", 0, regime, magnitude)
                if regime == "R4":
                    ratio = 1.0            # канала incidence у R4 нет
                out.append({
                    "tag": legacy.arm_tag(rate, c_rate, regime, magnitude),
                    "rate": rate, "c_rate": c_rate, "c_shift": c_shift,
                    "regime": regime, "magnitude": magnitude,
                    "effective_rate": rate * ratio * c_rate})
    return tuple(out)


def plan(arms, ladder=PR.LOOKS) -> tuple[Unit, ...]:
    """Детерминированный манифест. Состав и порядок — функция только входа.

    `arms` — последовательность `(arm_tag, rate)`. Юнит считает ПРЕФИКС
    `0..look` целиком: период `i` определяется сидом `f"{tag}:{i}"`, поэтому
    пересчёт даёт побитово тот же период, и научная вложенность сохраняется
    ТОЧНО, а не приблизительно. Промежуточное состояние между ступенями не
    передаётся вовсе.
    """
    units: list[Unit] = []
    for arm, rate in arms:
        for look in ladder:
            groups = key_groups(groups_needed(rate, look))
            for keys in groups:
                units.append(Unit(arm=arm, look=look, keys=keys,
                                  weight=cost_of(rate, look,
                                                 len(keys) / len(E.KEYS))))
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
    """Слияние отказано. Частичный результат молча не собирается."""


def result_digest(results) -> str:
    """Стабильный дайджест выхода юнита. Не зависит от порядка ключей."""
    parts = []
    for name in sorted(results, key=repr):
        endpoint = results[name]
        parts.append(f"{name!r}={endpoint.point!r},{endpoint.low!r},"
                     f"{endpoint.high!r},{endpoint.status.value},{endpoint.look!r}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def merge(arm: str, look: int, parts, *, expected) -> dict:
    """Концы руки на ступени `look` из частей. ЛЮБОЙ изъян — отказ.

    Сливать здесь нечего: ключи разделимы ВЫЧИСЛИТЕЛЬНО, поэтому части
    конкатенируются. Отказ, а не предупреждение: неполный набор концов
    внешне неотличим от полного, он просто короче.
    """
    wanted = tuple(u for u in expected if u.arm == arm and u.look == look)
    if not wanted:
        raise MergeRefused(f"манифест не объявлял {arm} на ступени {look}")
    got = {}
    for unit, results in parts:
        if unit.arm != arm or unit.look != look:
            continue
        if unit.task_id in got:
            raise MergeRefused(f"юнит {unit.task_id} прислан дважды")
        got[unit.task_id] = (unit, results)

    missing = [u.task_id for u in wanted if u.task_id not in got]
    if missing:
        raise MergeRefused(f"не хватает юнитов: {missing}")
    extra = [t for t in got if t not in {u.task_id for u in wanted}]
    if extra:
        raise MergeRefused(f"лишние юниты: {extra}")

    seen, merged = set(), {}
    for unit in wanted:
        _, results = got[unit.task_id]
        overlap = seen & set(unit.keys)
        if overlap:
            raise MergeRefused(f"ключи пересекаются: {sorted(overlap, key=repr)}")
        seen.update(unit.keys)
        for name, endpoint in results.items():
            if name[0] not in unit.keys:
                raise MergeRefused(f"юнит прислал чужой ключ: {name[0]!r}")
            merged[name] = endpoint
    if seen != set(E.KEYS):
        raise MergeRefused(
            f"покрыто {len(seen)} ключей из {len(E.KEYS)}")
    return merged


def run_unit(unit: Unit, *, z: float = PR.Z_PER_COMPARISON, **arm) -> dict:
    """Исполнение одного задания: префикс `0..look` по СВОИМ ключам.

    Параметры руки прокидываются как есть, включая `regime`/`magnitude`:
    розыгрыш эффекта идёт из потока, зависящего только от `(tag, i)`, а не
    от того, какой группе ключей достался расчёт.
    """
    store = E.accumulate(unit.arm, 0, unit.look, wanted=unit.keys, **arm)
    return E.endpoints_from(store, look=unit.look, z=z)
