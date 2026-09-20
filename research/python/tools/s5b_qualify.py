"""Квалификация ПРОЦЕДУРЫ точности на ПРОИЗВОДСТВЕННОЙ лестнице.

ЧТО ЗДЕСЬ КВАЛИФИЦИРУЕТСЯ. Не оценщик на одном `M`, а вся вложенная
процедура `4000 -> 16000 -> 64000` с остановкой по ширине: именно
последовательная остановка и создаёт риск, которого у одного просмотра нет.

ЧЕТЫРЕ ТРЕБОВАНИЯ, КОТОРЫЕ ПРЕДЫДУЩАЯ РЕДАКЦИЯ НАРУШАЛА.

1. **Лестница производственная.** Прошлая проверка шла по `400 -> 1600 ->
   6400` и объясняла это тем, что «логика последовательной остановки от
   абсолютных `M` не зависит». Теоремы под этим нет, а зависимости есть:
   нормальность стьюдентизованной статистики, частота вырожденных выборок,
   геометрия Филлера (связность множества зависит от `M` ЯВНО — см.
   `fieller`). Масштабированная лестница квалифицирует масштабированную
   процедуру, а исполняется другая.

2. **Множественность двумерна.** Сертификат точности ЯЧЕЙКИ — это
   4 конца x 3 просмотра = 12 утверждений, значит `z` считается от `α/12`.

3. **Истина аналитически точна.** Покрытие меряется относительно `λ0`,
   известного в замкнутой форме, а не относительно оценки при большом `M`:
   у такой оценки своя монте-карловская ошибка, и она уже однажды съела
   результат (см. `contaminated-first-attempt`).

4. **Набор B-7 исполняется целиком**, а не тремя удобными сценариями.

ЧТО ЭТА ПРОВЕРКА МЕРЯЕТ, А ЧТО НЕТ. Меряется покрытие ОДНОГО конца
одновременно по всем просмотрам, которые процедура успела сделать.
Номинал такого утверждения — `1 − 3α/12 = 1 − α/4 = 0.9875` по союзной
границе. Переход от конца к ЯЧЕЙКЕ (`>= 1 − α`) — это арифметика союзной
границы по четырём концам, и она здесь НЕ измеряется: измеримо только то,
что каждое отдельное утверждение держит свой уровень.

ПРИЁМКА ОБЪЯВЛЕНА ДО ПРОГОНА и берётся из уже существующего правила
проекта: нижний предел Уилсона `>= COVERAGE_ACCEPTANCE_FLOOR` (0.93) в
КАЖДОМ сценарии, худший решает. Единственное ужесточение — семейный `z`
считается по числу сценариев ЭТОЙ суиты, а не по семи сценариям суиты
S5b: одалживать чужую поправку на меньшее семейство значит брать более
слабый порог. Требуются ОБА: и по объявленному `z`, и по семейному.

ОТРИЦАТЕЛЬНЫЕ КОНТРОЛИ ОБЪЯВЛЕНЫ ПОИМЁННО, вместе с тем, какие сценарии
они НЕ МОГУТ уронить, и почему — вывод аналитический, сделан до прогона:

    degenerate_variance   множество задаётся соглашением о вырожденной
                          дисперсии, которое от `z` не зависит вообще
    boundary_zero         при `b ≡ 0` квадратичная форма вырождается в
                          `a·λ² <= 0` с `a > 0`, то есть множество равно
                          ровно `{0} = {λ0}` при ЛЮБОМ `z`

Для них содержание контроля другое: вырожденная дисперсия обязана НИКОГДА
не выдавать «точность достигнута», а граничный случай обязан давать точку
РОВНО в истине. Объявлено полем `narrow_control_must_fail`.

БЫСТРЫЙ ПУТЬ И ПОЧЕМУ ЕМУ МОЖНО ВЕРИТЬ. Производственный `acceptance_set`
на каждом сегменте проходит по ВСЕМ периодам; при `M = 64000` и 4000
репликах это часы. Здесь агрегаты сегмента считаются инкрементально
(Уэлфорд) или по счётчикам типов, а дальше вызывается ТОТ ЖЕ самый
`_solve` из `coarsening.inversion` — численно тонкая часть не дублируется.
Совпадение с производственной функцией проверяется в
`tests/test_s5b_qualify.py` на всех сценариях и на РАБОЧИХ `M`
(4000/16000/64000), а не только на игрушечных.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Callable

from coarsening.inversion import (Piece, ZERO_VARIANCE_IS_ACCEPTED, _solve,
                                  acceptance_set)
from simulation import s5b_precision as PR
from simulation.s5b_prereg import (COVERAGE_ACCEPTANCE_FLOOR, SIMULTANEOUS_ALPHA,
                                   coverage_is_accepted, wilson_lower)

LO = 0.0
HI = 3600.0
#: САМАЯ ТЕСНАЯ δ объявленной сетки для H = 3600 (0.01 * H). Берётся худший
#: случай, а не удобный: цель по точности от δ пропорциональна.
DELTA = 36.0
REPLICATES = 4_000


# --------------------------------------------------------------------------
# агрегаты сегмента: то, чем на самом деле определяется множество принятия
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Segment:
    """Отрезок, на котором активный кусок каждого периода фиксирован.

    `count` — размер ВСЕЙ выборки (как в производственной функции), а не
    число периодов, попавших на отрезок.
    """

    left: float
    right: float
    count: int
    mean_b: float
    mean_n: float
    s_bb: float
    s_bn: float
    s_nn: float


def accept_from_segments(segments, *, z: float, lo: float = LO, hi: float = HI,
                         tolerance: float = 1e-9) -> list[tuple[float, float]]:
    """Точная копия тела `acceptance_set`, но от агрегатов, а не от периодов.

    Совпадает по построению: те же коэффициенты, тот же `_solve`, то же
    соглашение о вырожденной дисперсии, тот же пропуск коротких отрезков и
    то же слияние. Проверяется тестом, а не обещанием.
    """
    if not segments:
        return [(lo, hi)]
    count = segments[0].count
    if count < 2:
        return [(lo, hi)]

    found: list[tuple[float, float]] = []
    scale = z * z / (count - 1)
    for seg in segments:
        if seg.right - seg.left < tolerance:
            continue
        a = count * seg.mean_n * seg.mean_n - scale * seg.s_nn
        b = -2 * count * seg.mean_b * seg.mean_n + 2 * scale * seg.s_bn
        c = count * seg.mean_b * seg.mean_b - scale * seg.s_bb
        if seg.s_nn == 0.0 and seg.s_bb == 0.0 and ZERO_VARIANCE_IS_ACCEPTED:
            found.append((seg.left, seg.right))
            continue
        found.extend(_solve((a, b, c), seg.left, seg.right))

    found.sort()
    merged: list[tuple[float, float]] = []
    for piece in found:
        if merged and piece[0] - merged[-1][1] <= tolerance:
            merged[-1] = (merged[-1][0], max(merged[-1][1], piece[1]))
        else:
            merged.append(piece)
    return merged


def root_from_segments(segments, lo: float = LO, hi: float = HI) -> float:
    """`inf{λ : g(λ) <= 0}`, обрезанный на домен. Точно, без дихотомии.

    `g` кусочно-линейна и убывает, поэтому первый отрезок, на правом конце
    которого `g <= 0`, содержит корень, и он берётся решением линейного
    уравнения, а не шестьюдесятью делениями пополам.
    """
    for seg in segments:
        if seg.mean_b - seg.left * seg.mean_n <= 0.0:
            return seg.left
        if seg.mean_b - seg.right * seg.mean_n <= 0.0:
            return seg.mean_b / seg.mean_n
    return hi


class MomentSample:
    """Однокусочные периоды: двумерный Уэлфорд, ровно один отрезок.

    Инкрементально — потому что вложенность требует, чтобы `M = 16000`
    ПРОДОЛЖАЛ выборку `M = 4000`, а не строил новую.
    """

    __slots__ = ("count", "mean_b", "mean_n", "m_bb", "m_bn", "m_nn")

    def __init__(self) -> None:
        self.count = 0
        self.mean_b = self.mean_n = 0.0
        self.m_bb = self.m_bn = self.m_nn = 0.0

    def add(self, n: float, b: float) -> None:
        self.count += 1
        d_b = b - self.mean_b
        d_n = n - self.mean_n
        self.mean_b += d_b / self.count
        self.mean_n += d_n / self.count
        self.m_bb += d_b * (b - self.mean_b)
        self.m_bn += d_b * (n - self.mean_n)
        self.m_nn += d_n * (n - self.mean_n)

    def periods(self):                      # только для тестов эквивалентности
        raise NotImplementedError("моментный накопитель периодов не хранит")

    def segments(self, lo: float = LO, hi: float = HI):
        return (Segment(lo, hi, self.count, self.mean_b, self.mean_n,
                        self.m_bb, self.m_bn, self.m_nn),)


class CatalogueSample:
    """Конечный каталог типов периодов: счётчики вместо списка.

    Изломы берутся ТОЛЬКО у присутствующих типов — производственная
    `_breakpoints` тоже видит лишь то, что попало в выборку.
    """

    __slots__ = ("catalogue", "counts", "count")

    def __init__(self, catalogue) -> None:
        self.catalogue = catalogue
        self.counts = [0] * len(catalogue)
        self.count = 0

    def add_type(self, index: int) -> None:
        self.counts[index] += 1
        self.count += 1

    def segments(self, lo: float = LO, hi: float = HI):
        present = [i for i, c in enumerate(self.counts) if c]
        edges = {lo, hi}
        for i in present:
            pieces = self.catalogue[i]
            for j, first in enumerate(pieces):
                for second in pieces[j + 1:]:
                    if first.n != second.n:
                        lam = (first.b - second.b) / (first.n - second.n)
                        if lo < lam < hi:
                            edges.add(lam)
        out = []
        total = self.count
        for left, right in zip(sorted(edges), sorted(edges)[1:]):
            middle = (left + right) / 2.0
            active = [(self.counts[i],
                       min(self.catalogue[i], key=lambda p: p.b - middle * p.n))
                      for i in present]
            mean_b = sum(c * p.b for c, p in active) / total
            mean_n = sum(c * p.n for c, p in active) / total
            s_bb = sum(c * (p.b - mean_b) ** 2 for c, p in active)
            s_bn = sum(c * (p.b - mean_b) * (p.n - mean_n) for c, p in active)
            s_nn = sum(c * (p.n - mean_n) ** 2 for c, p in active)
            out.append(Segment(left, right, total, mean_b, mean_n,
                               s_bb, s_bn, s_nn))
        return out


# --------------------------------------------------------------------------
# сценарии: у каждого λ0 известен АНАЛИТИЧЕСКИ
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    truth: float
    new_sample: Callable[[], object]
    draw: Callable[[random.Random, object], None]
    #: объявлено ДО прогона: обязан ли контроль `z = 0.5` уронить сценарий
    narrow_control_must_fail: bool
    why: str


def _regular(rng, s):
    n = rng.randint(1, 9)
    s.add(n, 1200.0 * n + rng.gauss(0.0, 400.0))


def _heavy_tail(rng, s):
    n = 100 if rng.random() < 0.04 else 1
    s.add(n, 1200.0 * n + rng.gauss(0.0, 200.0))


def _zero_heavy(rng, s):
    n = 0 if rng.random() < 0.5 else rng.randint(1, 4)
    s.add(n, 1200.0 * n + (rng.gauss(0.0, 300.0) if n else 0.0))


def _heavy_zero_90(rng, s):
    n = 0 if rng.random() < 0.9 else rng.randint(1, 4)
    s.add(n, 1200.0 * n + (rng.gauss(0.0, 300.0) if n else 0.0))


def _boundary_zero(rng, s):
    """`B ≡ 0`, `N` разбросан: λ0 = 0 РОВНО на границе домена.

    Физически допустимый способ получить нулевой корень при `B >= 0`.
    Здесь `mean_b = s_bb = s_bn = 0`, значит форма вырождается в
    `a·λ² <= 0` с `a > 0` — ДВОЙНОЙ корень ровно в истине, то есть прямая
    проверка `DISCRIMINANT_TOLERANCE`.
    """
    s.add(rng.randint(0, 4), 0.0)


#: СОБСТВЕННЫЙ GOLDEN ПРОЕКТА, ПЕРЕСЧИТАННЫЙ НА РАБОЧЕЕ `M`. Golden на
#: 25 периодах даёт несвязное множество, но несвязность там — эффект малой
#: выборки: множество не-вальдово (ветви принятия уходят на бесконечность)
#: ровно когда
#:
#:     CV(N)² > M / z²
#:
#: то есть при `M = 25`, `z = 1.96` достаточно `CV² > 6.5`, а у golden 15.3.
#: При `M = 4000`, `z = 2.8653` нужно уже `CV² > 487`. Поэтому тот же
#: ПОРЯДОК ВЕЛИЧИН (одна тяжёлая рука на много лёгких, разные отношения
#: B/N) пересчитан так, чтобы патология дожила до производственной лестницы:
#:
#:     тяжёлый   N = 10 000,  B = 12 479 520   (B/N = 1247.952)  p = 1/1000
#:     лёгкий    N = 1,       B = 720          (B/N = 720)       p = 999/1000
#:
#: Оба куска физически допустимы: `B <= N·H` при `H = 3600`. Корень точен,
#: и это проверяется целыми числами:
#:
#:     E[N] = 10999/1000,  E[B] = 13198800/1000,  10999 · 1200 = 13198800
#:
#: Первая редакция сценария добавляла к `B` гауссов шум — и несвязность
#: ИСЧЕЗАЛА (5 случаев из 40): шум поднимает пол дисперсии и сглаживает
#: стьюдентизованную статистику ровно там, где дырка и возникает. Записано
#: как отрицательный результат: «филлеровский по замыслу» не значит
#: «филлеровский по факту», и проверять это надо вычислением.
FIELLER_CATALOGUE = ((Piece(10_000.0, 12_479_520.0),), (Piece(1.0, 720.0),))
FIELLER_WEIGHTS = (0.001, 1.0)

#: Каталоги. Веса нормированы, корни считаются в закрытой форме ниже.
KINK_CATALOGUE = (
    (Piece(1.0, 1200.0), Piece(3.0, 3600.0)),   # излом РОВНО в λ = 1200
    (Piece(1.0, 1350.0),),
    (Piece(1.0, 1050.0),),
)
KINK_WEIGHTS = (0.5, 0.75, 1.0)                  # кумулятивно: 0.5 / 0.25 / 0.25

BOUNDARY_SIGNED_CATALOGUE = ((Piece(1.0, 80.0),), (Piece(1.0, -80.0),))
BOUNDARY_SIGNED_WEIGHTS = (0.5, 1.0)

DEGENERATE_CATALOGUE = (
    (Piece(1.0, 1200.0),),
    (Piece(1.0, 1200.0), Piece(2.0, 3000.0)),    # излом в λ = 1800, правее λ0
)
DEGENERATE_WEIGHTS = (0.5, 1.0)


def _catalogue_draw(weights):
    def draw(rng, s):
        u = rng.random()
        for index, edge in enumerate(weights):
            if u < edge:
                s.add_type(index)
                return
        s.add_type(len(weights) - 1)
    return draw


SCENARIOS = (
    Scenario("regular", 1200.0, MomentSample, _regular, True,
             "мягкий случай: N ~ U{1..9}, B = 1200N + N(0,400)"),
    Scenario("heavy_tail", 1200.0, MomentSample, _heavy_tail, True,
             "перекос: N = 100 с вероятностью 0.04"),
    Scenario("zero_heavy", 1200.0, MomentSample, _zero_heavy, True,
             "половина периодов с N = 0"),
    Scenario("heavy_zero_90", 1200.0, MomentSample, _heavy_zero_90, True,
             "девять десятых периодов с N = 0"),
    Scenario("fieller", 1200.0,
             lambda: CatalogueSample(FIELLER_CATALOGUE),
             _catalogue_draw(FIELLER_WEIGHTS), True,
             "golden проекта, пересчитанный так, что множество НЕСВЯЗНО "
             "при M = 4000"),
    Scenario("kink_at_root", 1200.0,
             lambda: CatalogueSample(KINK_CATALOGUE),
             _catalogue_draw(KINK_WEIGHTS), True,
             "излом ψ РОВНО в λ0, то есть корень на границе сегментов"),
    Scenario("boundary_zero", 0.0, MomentSample, _boundary_zero, False,
             "λ0 = 0 на границе домена; двойной корень ровно в истине"),
    Scenario("boundary_signed", 0.0,
             lambda: CatalogueSample(BOUNDARY_SIGNED_CATALOGUE),
             _catalogue_draw(BOUNDARY_SIGNED_WEIGHTS), True,
             "λ0 = 0 при НЕвырожденной статистике; B < 0 — стресс, не DGP"),
    Scenario("degenerate_variance", 1200.0,
             lambda: CatalogueSample(DEGENERATE_CATALOGUE),
             _catalogue_draw(DEGENERATE_WEIGHTS), False,
             "нулевая дисперсия на сегменте, содержащем λ0"),
)

#: Семейный `z` ЭТОЙ суиты. Одалживать поправку суиты S5b на семь сценариев
#: значит брать более слабый порог для десяти.
SUITE_Z = NormalDist().inv_cdf(1.0 - SIMULTANEOUS_ALPHA / len(SCENARIOS))

Z_DECLARED = PR.Z_PER_COMPARISON
Z_UNADJUSTED = NormalDist().inv_cdf(1.0 - (1.0 - 0.95) / 2.0)   # 1.9600
Z_NARROW = 0.5
CONFIGS = (("объявленный alpha/12", Z_DECLARED),
           ("БЕЗ поправки (alpha)", Z_UNADJUSTED),
           ("НАМЕРЕННО узкое z=0.5", Z_NARROW))


@dataclass
class Tally:
    covered: int = 0
    trials: int = 0
    stopped_at: dict = field(default_factory=dict)
    per_look_miss: dict = field(default_factory=dict)
    per_look_trials: dict = field(default_factory=dict)
    disconnected: int = 0
    #: ВТОРИЧНАЯ, ОБЪЯВЛЕННАЯ ДО ПРОГОНА величина: покрытие на том просмотре,
    #: на котором процедура ОСТАНОВИЛАСЬ. Научно работает именно она —
    #: промах на непоследнем просмотре вердикта не порождает, потому что
    #: вердикт выносится один раз и на остановке. Гейт стоит НЕ на ней, а на
    #: совместном покрытии: именно совместное и заявляет B-5, и именно ради
    #: него введена поправка. Совместное — консервативная мажоранта
    #: остановочного, поэтому пара чисел показывает ЦЕНУ консерватизма.
    covered_at_stop: int = 0


def replicate(scenario: Scenario, index: int, tallies=None,
              configs=CONFIGS, ladder=PR.LOOKS, delta: float = DELTA):
    """Один прогон процедуры. Потоки общие для всех `z` — см. докстринг.

    Возвращает `{label: PR.Outcome}` плюс флаг покрытия; `tallies`, если
    передан, накапливает сводку. Общий поток на три конфигурации — это
    common random numbers: оценки остаются несмещёнными, а сравнение
    конфигураций становится точнее, потому что различие не размывается
    разными выборками.
    """
    rng = random.Random(f"{scenario.name}:{index}")
    sample = scenario.new_sample()
    live = {label: True for label, _ in configs}
    covered = {label: True for label, _ in configs}
    at_stop = {label: True for label, _ in configs}
    outcome = {}
    drawn = 0
    for size in ladder:
        if not any(live.values()):
            break
        while drawn < size:
            scenario.draw(rng, sample)
            drawn += 1
        segments = sample.segments(LO, HI)
        point = root_from_segments(segments, LO, HI)
        for label, z in configs:
            if not live[label]:
                continue
            components = accept_from_segments(segments, z=z, lo=LO, hi=HI)
            radius = PR.radius(components, point)
            if tallies is not None:
                tally = tallies[label]
                if len(components) > 1:
                    tally.disconnected += 1
                tally.per_look_trials[size] = tally.per_look_trials.get(size, 0) + 1
            here = any(a <= scenario.truth <= b for a, b in components)
            if not here:
                covered[label] = False
                if tallies is not None:
                    tally.per_look_miss[size] = tally.per_look_miss.get(size, 0) + 1
            if PR.is_precise(radius, delta, z=z):
                live[label] = False
                at_stop[label] = here
                outcome[label] = PR.Outcome(PR.PrecisionStatus.ACHIEVED, size,
                                            radius, PR.target(delta))
                if tallies is not None:
                    tallies[label].stopped_at[size] = \
                        tallies[label].stopped_at.get(size, 0) + 1
            elif size == ladder[-1]:
                live[label] = False
                at_stop[label] = here
                outcome[label] = PR.Outcome(PR.PrecisionStatus.INSUFFICIENT,
                                            size, radius, PR.target(delta))
    for label, _ in configs:
        if tallies is not None:
            tally = tallies[label]
            tally.trials += 1
            tally.covered += covered[label]
            tally.covered_at_stop += at_stop[label]
            if outcome[label].status is PR.PrecisionStatus.INSUFFICIENT:
                tally.stopped_at["потолок"] = tally.stopped_at.get("потолок", 0) + 1
    return covered, outcome


def accepted(tally: Tally) -> bool:
    """ОБА порога: объявленный семейный `z` суиты S5b и семейный `z` этой."""
    return (coverage_is_accepted(tally.covered, tally.trials)
            and wilson_lower(tally.covered, tally.trials, z=SUITE_Z)
            >= COVERAGE_ACCEPTANCE_FLOOR)


def main() -> int:
    print(f"лестница {PR.LOOKS} (ПРОИЗВОДСТВЕННАЯ), реплик {REPLICATES}, "
          f"delta = {DELTA} (0.01 * H, самая тесная на сетке)")
    print(f"концов {PR.ENDPOINTS_PER_CELL} x просмотров {len(PR.LOOKS)} = "
          f"{PR.COMPARISONS} сравнений, z = {Z_DECLARED:.4f}")
    print(f"пол {COVERAGE_ACCEPTANCE_FLOOR}, семейный z суиты S5b "
          f"{NormalDist().inv_cdf(1 - SIMULTANEOUS_ALPHA / 7):.4f}, "
          f"этой суиты {SUITE_Z:.4f} ({len(SCENARIOS)} сценариев)")
    print("потоки ОБЩИЕ для трёх конфигураций z (common random numbers)\n")
    header = (f"{'сценарий':<21}{'конфигурация':<24}"
              f"{'покрытие':>20}  {'Уилсон':>7} {'Уилсон10':>8}  "
              f"{'вердикт':<10}{'остановки'}")
    print(header)
    verdicts = {}
    for scenario in SCENARIOS:
        tallies = {label: Tally() for label, _ in CONFIGS}
        for index in range(REPLICATES):
            replicate(scenario, index, tallies)
        for label, _ in CONFIGS:
            tally = tallies[label]
            ok = accepted(tally)
            verdicts[(scenario.name, label)] = ok
            stops = ", ".join(f"{k}:{v}" for k, v in
                              sorted(tally.stopped_at.items(), key=lambda kv: str(kv[0])))
            print(f"{scenario.name:<21}{label:<24}"
                  f"{tally.covered}/{tally.trials} = {tally.covered/tally.trials:>7.4f}  "
                  f"{wilson_lower(tally.covered, tally.trials):>7.4f} "
                  f"{wilson_lower(tally.covered, tally.trials, z=SUITE_Z):>8.4f}  "
                  f"{'принято' if ok else 'отклонено':<10}{stops}", flush=True)
        miss = tallies["объявленный alpha/12"]
        print(f"{'':<21}{'на остановке (вторичн.)':<24}"
              f"{miss.covered_at_stop}/{miss.trials} = "
              f"{miss.covered_at_stop / miss.trials:>7.4f}")
        detail = ", ".join(
            f"M={m}: {miss.per_look_miss.get(m, 0)}/{miss.per_look_trials.get(m, 0)}"
            for m in PR.LOOKS if m in miss.per_look_trials)
        print(f"{'':<21}{'промахи по просмотрам':<24}{detail}")
        if miss.disconnected:
            print(f"{'':<21}{'несвязных множеств':<24}{miss.disconnected} "
                  f"из {sum(miss.per_look_trials.values())} построений")
    print()
    main_ok = all(v for (_, label), v in verdicts.items()
                  if label == "объявленный alpha/12")
    print(f"ОСНОВНАЯ КОНФИГУРАЦИЯ: {'ПРИНЯТА' if main_ok else 'ОТКЛОНЕНА'} "
          f"(худший сценарий решает)")
    for label in ("БЕЗ поправки (alpha)", "НАМЕРЕННО узкое z=0.5"):
        fell = [s.name for s in SCENARIOS if not verdicts[(s.name, label)]]
        held = [s.name for s in SCENARIOS if verdicts[(s.name, label)]]
        print(f"{label}: отклонено {len(fell)}/{len(SCENARIOS)} -> {fell}")
        if held:
            print(f"{'':<24}устояли: {held}")
    broken = [s.name for s in SCENARIOS if s.narrow_control_must_fail
              and verdicts[(s.name, "НАМЕРЕННО узкое z=0.5")]]
    print(f"объявленное ДО прогона ожидание контроля: "
          f"{'исполнено' if not broken else 'НАРУШЕНО ' + str(broken)}")
    return 0 if main_ok and not broken else 1


if __name__ == "__main__":
    sys.exit(main())
