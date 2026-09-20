"""Квалификация OPERATIONAL STOPPING PROCEDURE правила точности (редакция 4).

ЧТО КВАЛИФИЦИРУЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО. Редакция 3 требовала покрытия на
КАЖДОМ просмотре лестницы и провалилась на `fieller`. Разбор показал, что
требование было СИЛЬНЕЕ научной задачи: Stage 1 не использует `A_M`, если
точность не достигнута — такая ячейка получает `MC_PRECISION_INSUFFICIENT`
и научного вердикта не получает вовсе. Покрытие множества, которое алгоритм
заведомо не собирается использовать, операционного смысла не имеет.

Объект редакции 4 — момент остановки и ВОЗВРАЩЁННОЕ множество:

    tau = min{ M_j из лестницы : r_{M_j} <= z · 0.1 · GATE_MARGIN_FRACTION · δ }
    tau = inf, если точность не достигнута ни на одном просмотре

    FALSE_CERTIFICATION = (tau < inf) И (λ0 не в A_tau)

Гейтящая величина — вероятность ЛОЖНОЙ СЕРТИФИКАЦИИ:

    p_false_cert = P(tau < inf, λ0 не в A_tau)

то есть вероятность РАЗРЕШИТЬ научное использование конца и вернуть при
этом множество, не покрывающее истину.

ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ. Не confidence sequence, не always-valid CI и не
утверждение о валидности при произвольном моменте остановки. Соседние
понятия сильнее; здесь квалифицируется ОДНА заранее заданная
трёхступенчатая лестница и ОДНО заранее заданное правило `tau`.
Одновременное покрытие всех просмотров (редакция 3) — достаточный, но
более сильный способ обеспечить то же свойство.

ЧЕГО ЗДЕСЬ СОЗНАТЕЛЬНО НЕТ. Прежнее обоснование «на M = 4000 остановиться
невозможно» выброшено из основания. Доказано только
`a <= 0 => r >= H/2 => остановка невозможна`; для `a > 0` такой теоремы
нет, а ноль остановок из 4000 — наблюдение, а не доказательство. Новому
гейту теорема и не нужна: если редкая ранняя остановка случится и
промахнётся, она попадёт в `FALSE_CERTIFICATION` сама. Классификации
просмотров на «возможные» и «невозможные» здесь нет нигде.

ЧТО МЕРЯЕТСЯ, А ЧТО НЕТ. Меряется `p_false_cert` для ОДНОГО конца, плюс
отдельный сценарий на ЧЕТЫРЁХ концах, где ячейка получает вердикт только
когда точны все четыре. Переход «конец -> ячейка» через союзную границу
остаётся консервативным мостом; четвёрка добавлена не потому, что граница
неверна, а потому, что одна человеческая ошибка в `all(endpoint.precise)`
прекрасно переживает тысячу теорем.

ДИАГНОСТИКИ, КОТОРЫЕ НЕ ГЕЙТЯТ, но печатаются рядом с каждым вердиктом:
`P(tau < inf)`, `P(покрыл | tau < inf)`, распределение просмотра остановки,
доля `MC_PRECISION_INSUFFICIENT`, и — отдельно — промахи на ФИКСИРОВАННЫХ
просмотрах, как их считала редакция 3. Последнее чтобы прежние 307
промахов `fieller` были видны, а не растворились в смене определения.

Условным покрытием `P(покрыл | tau < inf)` гейтить нельзя: при редком
сертификате знаменатель мал и величина капризна. И отдельно: процедура,
которая почти никогда не сертифицирует, имеет `p_false_cert = 0` и прошла
бы ВАКУУМНО. Поэтому `P(tau < inf)` печатается всегда, вакуумные
утверждения считаются и называются, а в суиту добавлен
`fieller_certifying` — та же филлеровская геометрия, но доходящая до
сертификата.

БЫСТРЫЙ ПУТЬ И ПОЧЕМУ ЕМУ МОЖНО ВЕРИТЬ. Производственный `acceptance_set`
на каждом сегменте проходит по ВСЕМ периодам; при `M = 64000` и 24000
репликах это сутки. Здесь агрегаты сегмента считаются инкрементально
(двумерный Уэлфорд) или по счётчикам типов, а численно тонкая часть —
`_solve` — берётся из `coarsening.inversion` КАК ЕСТЬ и не дублируется.
Эквивалентность проверяется в `tests/test_s5b_qualify.py` на всех
сценариях, на РАБОЧИХ `M`, для каждого объявленного `z` и для обоих
направлений (`min` и `max`), и не только по числам, но и по СОВПАДЕНИЮ
РЕШЕНИЙ — покрыл/не покрыл и точен/не точен.
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
from simulation.s5b_prereg import (CONFIDENCE_LEVEL, COVERAGE_ACCEPTANCE_FLOOR,
                                   DELTA_FRACTIONS_OF_HORIZON,
                                   GATE_POWER_FAMILY_BUDGET,
                                   SIMULTANEOUS_ALPHA, wilson_lower)

LO = 0.0
HI = 3600.0
#: САМАЯ ТЕСНАЯ δ объявленной сетки для H = 3600 (0.01 * H). Берётся худший
#: случай, а не удобный: цель по точности от δ пропорциональна. Редакция 4
#: проходит по ВСЕЙ оси `DELTAS`; это значение — её первый элемент.
DELTA = 36.0


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

    def segments(self, lo: float = LO, hi: float = HI,
                 maximise: bool = False):
        #: период однокусочный, поэтому min и max по нему совпадают и
        #: `maximise` ни на что не влияет — параметр принят ради единого
        #: интерфейса, а не ради вида
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

    def segments(self, lo: float = LO, hi: float = HI,
                 maximise: bool = False):
        picked = max if maximise else min
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
                       picked(self.catalogue[i],
                              key=lambda p: p.b - middle * p.n))
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


#: FIELLER, КОТОРЫЙ ДОХОДИТ ДО СЕРТИФИКАТА. Гейт редакции 4 считает событие
#: «сертификат выдан И множество промахнулось». У исходного `fieller`
#: P(tau < inf) = 0 при любом `z`: радиус там огромен, точность не
#: достигается никогда, и гейт прошёл бы ВАКУУМНО. Метод, безопасный
#: исключительно потому, что всегда отвечает «не знаю», гейта не проходит —
#: он его обходит.
#:
#: Поэтому добавлен второй сценарий с ТОЙ ЖЕ геометрией `N` (значит та же
#: несвязность при M = 4000), но с малым разбросом `psi`: тяжёлый кусок
#: несёт почти ровно свою долю бремени.
#:
#:     тяжёлый  N = 10 000,  B = 12 000 499.5     p = 1/1000
#:     лёгкий   N = 1,       B = 1 199.5          p = 999/1000
#:
#: Корень тот же и так же точен: E[B]·1000 = 13 198 800 = 1200 · 10 999.
#: На M = 4000 геометрия по-прежнему филлеровская, на M = 16000 она
#: схлопывается в вальдову и процедура сертифицирует. Ранняя остановка при
#: M = 4000 остаётся ВОЗМОЖНОЙ (реплики без тяжёлых наблюдений), и если она
#: случится и промахнётся, это автоматически ложная сертификация — никакой
#: классификации просмотров на «возможные» и «невозможные» гейт не требует.
FIELLER_CERTIFYING_CATALOGUE = ((Piece(10_000.0, 12_000_499.5),),
                                (Piece(1.0, 1_199.5),))
FIELLER_CERTIFYING_WEIGHTS = (0.001, 1.0)

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
    Scenario("fieller_certifying", 1200.0,
             lambda: CatalogueSample(FIELLER_CERTIFYING_CATALOGUE),
             _catalogue_draw(FIELLER_CERTIFYING_WEIGHTS), True,
             "та же несвязность при M = 4000, но процедура ДОХОДИТ до "
             "сертификата — иначе гейт редакции 4 вакуумен"),
)

# --------------------------------------------------------------------------
# РЕДАКЦИЯ 4: квалифицируется OPERATIONAL STOPPING PROCEDURE
# --------------------------------------------------------------------------
#
# Редакция 3 требовала покрытия на КАЖДОМ просмотре и провалилась на
# `fieller`. Разбор показал, что требование было СИЛЬНЕЕ научной задачи:
# Stage 1 не использует `A_M`, если точность не достигнута, — такая ячейка
# получает `MC_PRECISION_INSUFFICIENT` и научного вердикта не получает
# вовсе. Покрытие неиспользуемого промежуточного множества операционного
# смысла не имеет.
#
# Объект редакции 4 — момент остановки и ВОЗВРАЩЁННОЕ множество:
#
#     tau = min{ M_j из лестницы : r_{M_j} <= порог }
#     tau = inf, если точность не достигнута ни на одном просмотре
#
#     FALSE_CERTIFICATION = (tau < inf) И (λ0 не в A_tau)
#
# Гейтящая величина — вероятность ЛОЖНОЙ СЕРТИФИКАЦИИ:
#
#     p_false_cert = P(tau < inf, λ0 не в A_tau)
#
# ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ, сказано прямо, потому что соседние понятия сильнее:
# это НЕ confidence sequence, НЕ always-valid CI и НЕ утверждение о
# валидности при произвольной остановке. Квалифицируется одна заранее
# заданная трёхступенчатая лестница и одно заранее заданное правило `tau`.
#
# ЧЕГО ЗДЕСЬ СОЗНАТЕЛЬНО НЕТ. Прежнее обоснование «на M = 4000 остановиться
# невозможно» выброшено. Доказано только `a <= 0 => r >= H/2 => остановка
# невозможна`; для `a > 0` такой теоремы нет, а 0 остановок из 4000 —
# наблюдение, а не доказательство. Новому гейту теорема и не нужна: если
# редкая ранняя остановка случится и промахнётся, она попадёт в
# `FALSE_CERTIFICATION` сама. Классификации просмотров на «возможные» и
# «невозможные» здесь нет нигде.
#
# КРИТИЧЕСКОЕ ЗНАЧЕНИЕ НЕ МЕНЯЕТСЯ. Редакция 4 меняет ЦЕЛЬ квалификации, а
# не `z`. Остаётся максимально консервативная конструкция `alpha/(4*3)`,
# `z = 2.8653`. Менять одновременно критерий, `z` и семейную арифметику
# после увиденного `fieller` — слишком много свободы за один раз.
# Возможное снятие временного Бонферрони по просмоторам после прямой
# квалификации stopping rule — DEFERRED, отдельным решением.

#: Пространство seed'ов редакции 4. Ни одно число прогона редакции 3 не
#: переиспользуется как свидетельство приёмки.
SEED_NAMESPACE = "r4"

#: δ — ОСЬ сетки, а не параметр. Суита проходится по ВСЕЙ объявленной оси:
#: при самой тесной δ половина сценариев не доходит до сертификата вообще,
#: и гейт на них вакуумен. Вакуум — не приёмка, поэтому ось покрывается
#: целиком, а `P(tau < inf)` печатается рядом с каждым вердиктом.
DELTAS = tuple(f * HI for f in DELTA_FRACTIONS_OF_HORIZON)

#: Число гейтящих утверждений: сценарий x δ.
STATEMENTS = (len(SCENARIOS) + 1) * len(DELTAS)      # +1: четвёрка концов
SUITE_Z = NormalDist().inv_cdf(1.0 - SIMULTANEOUS_ALPHA / STATEMENTS)

Z_DECLARED = PR.Z_PER_COMPARISON
Z_UNADJUSTED = NormalDist().inv_cdf(1.0 - (1.0 - CONFIDENCE_LEVEL) / 2.0)
Z_NARROW = 0.5
CONFIGS = (("объявленный alpha/12", Z_DECLARED),
           ("БЕЗ поправки (alpha)", Z_UNADJUSTED),
           ("НАМЕРЕННО узкое z=0.5", Z_NARROW))

#: НОМИНАЛ ложной сертификации по союзной границе: остановка может
#: произойти на любом из трёх просмотров, каждое множество строится на
#: 1 − α/12, поэтому P(tau < inf, промах) <= 3·α/12 = α/4.
NOMINAL_FALSE_CERT = len(PR.LOOKS) * PR.ALPHA_PER_COMPARISON

#: ПОЛ ВЫВЕДЕН ИЗ УЖЕ СУЩЕСТВУЮЩЕГО ПРАВИЛА, а не выбран. Объявленная пара
#: проекта — пол 0.93 при номинале 0.95, то есть допуск по промаху ровно
#: в 1.4 раза. Тот же множитель применён к НОВОМУ номиналу.
#:
#: Оставить буквально 0.93 было бы нельзя: при номинале 0.9875 процедура
#: БЕЗ поправки на множественность даёт около 0.95 и прошла бы пол 0.93 —
#: отрицательный контроль потерял бы зубы. Пол обязан соответствовать
#: номиналу той величины, на которой стоит.
FLOOR_RATIO = ((1.0 - COVERAGE_ACCEPTANCE_FLOOR) / (1.0 - CONFIDENCE_LEVEL))
FALSE_CERT_FLOOR = 1.0 - FLOOR_RATIO * NOMINAL_FALSE_CERT


def accepted(bad: int, trials: int) -> bool:
    """Приёмка по ложной сертификации. ОБА порога, решает строгий.

    Первый — выведенный из правила проекта пол под новый номинал.
    Второй — буквальный пол проекта 0.93, оставленный как жёсткий минимум.
    """
    good = trials - bad
    return (wilson_lower(good, trials, z=SUITE_Z) >= FALSE_CERT_FLOOR
            and wilson_lower(good, trials) >= COVERAGE_ACCEPTANCE_FLOOR)


def power_of(trials: int, rate: float = NOMINAL_FALSE_CERT) -> float:
    """Мощность гейта против ХУДШЕГО ДОПУСТИМОГО метода.

    Худший допустимый — тот, чья истинная частота ложной сертификации равна
    границе союзной оценки `3·α/12`. Гейт, отвергающий такой метод, сломан
    в другую сторону: он объявляет негодным то, что сам же разрешает.
    """
    passing = 0
    while accepted(passing + 1, trials):
        passing += 1
    mean = trials * rate
    spread = math.sqrt(trials * rate * (1.0 - rate))
    return NormalDist(mean, spread).cdf(passing + 0.5)


#: МОЩНОСТЬ — СОЮЗНОЙ ГРАНИЦЕЙ, как и в prereg: корреляция между потоками
#: сценариев неизвестна, произведение вероятностей писать нельзя.
GATE_POWER_REQUIRED = 1.0 - GATE_POWER_FAMILY_BUDGET / STATEMENTS

#: ЧИСЛО РЕПЛИК ВЫБРАНО ПРАВИЛОМ, А НЕ ВКУСОМ, и правило то же самое, что
#: однажды уже подняло `R` с 1000 до 4000: `GATE_POWER_RULE`. Прежние 4000
#: выбирались под величину «покрытие с номиналом 0.95». Величина сменилась
#: (номинал 0.9875, пол 0.9825, запас 0.005 вместо 0.02), и то же правило
#: даёт другое число:
#:
#:     R      проходит при    мощность против p = 0.0125
#:     4000   <= 45           0.261
#:     8000   <= 105          0.710
#:     16000  <= 230          0.985
#:     20000  <= 295          0.998109
#:     24000  <= 359          0.999727   <- требуется >= 0.998485
#:
#: Пол НЕ понижался. Поднято `R`. Ровно как в прошлый раз.
REPLICATES = 24_000


@dataclass
class Tally:
    """Сводка по одной паре (сценарий, δ) при одной конфигурации `z`."""

    trials: int = 0
    #: ГЕЙТ: сертификат выдан и множество промахнулось
    false_cert: int = 0
    #: диагностика полезности: сертификат выдан вообще
    achieved: int = 0
    #: диагностика: промахи на ФИКСИРОВАННЫХ просмотрах, как в редакции 3
    fixed_look_miss: dict = field(default_factory=dict)
    fixed_look_trials: dict = field(default_factory=dict)
    stopped_at: dict = field(default_factory=dict)
    disconnected: int = 0

    def conditional(self) -> float:
        """P(покрыл | сертифицировал). ДИАГНОСТИКА, не гейт.

        Гейтить условным покрытием нельзя: при редком сертификате
        знаменатель мал и величина капризна, а процедура, которая почти
        никогда не сертифицирует, выглядела бы великолепной.
        """
        if not self.achieved:
            return float("nan")
        return (self.achieved - self.false_cert) / self.achieved


def _look_state(sample, z_values, truth, maximise=False):
    """Для одного просмотра: (радиус, покрыл ли, несвязно ли) по каждому `z`."""
    segments = sample.segments(LO, HI, maximise=maximise)
    point = root_from_segments(segments, LO, HI)
    out = {}
    for label, z in z_values:
        components = accept_from_segments(segments, z=z, lo=LO, hi=HI)
        out[label] = (PR.radius(components, point),
                      any(a <= truth <= b for a, b in components),
                      len(components) > 1)
    return out


def replicate(scenario: Scenario, index: int, tallies=None,
              ladder=PR.LOOKS, deltas=DELTAS, configs=CONFIGS):
    """Одна реплика. Все δ и все `z` — на ОБЩЕМ потоке (common random numbers).

    Возвращает `{(δ, label): (сертифицирован, покрыл_в_tau, tau)}`, где
    `tau = None` означает `MC_PRECISION_INSUFFICIENT`.
    """
    rng = random.Random(f"{SEED_NAMESPACE}:{scenario.name}:{index}")
    sample = scenario.new_sample()
    live = {(d, label): True for d in deltas for label, _ in configs}
    result = {}
    drawn = 0
    for size in ladder:
        if not any(live.values()):
            break
        while drawn < size:
            scenario.draw(rng, sample)
            drawn += 1
        state = _look_state(sample, configs, scenario.truth)
        for label, _ in configs:
            radius, covered, split = state[label]
            if tallies is not None:
                for d in deltas:
                    if not live[(d, label)]:
                        continue
                    tally = tallies[(d, label)]
                    tally.fixed_look_trials[size] = \
                        tally.fixed_look_trials.get(size, 0) + 1
                    tally.disconnected += split
                    if not covered:
                        tally.fixed_look_miss[size] = \
                            tally.fixed_look_miss.get(size, 0) + 1
            for d in deltas:
                key = (d, label)
                if live[key] and PR.is_precise(radius, d, z=dict(configs)[label]):
                    live[key] = False
                    result[key] = (True, covered, size)
    for key, still in live.items():
        if still:
            result[key] = (False, None, None)
    if tallies is not None:
        for key, (certified, covered, look) in result.items():
            tally = tallies[key]
            tally.trials += 1
            tally.achieved += certified
            tally.false_cert += certified and not covered
            tally.stopped_at[look if certified else "insufficient"] = \
                tally.stopped_at.get(look if certified else "insufficient", 0) + 1
    return result


# --------------------------------------------------------------------------
# ЧЕТВЁРКА КОНЦОВ: то, чего на самом деле боимся, — ячейка с вердиктом
# --------------------------------------------------------------------------
#
#     F_cell = { ячейка получила научный вердикт
#                И хотя бы один из четырёх концов промахнулся мимо истины }
#
# Союзная граница по четырём концам остаётся консервативным мостом. Но
# одна человеческая ошибка в `all(endpoint.precise)` прекрасно переживает
# тысячу теорем, поэтому четвёрка проходит НАСТОЯЩУЮ вложенную процедуру,
# а не подставляется в формулу.

#: Руки нарочно с РАЗНЫМИ истинами: перепутанные местами руки обязаны
#: вылезти как массовая ложная сертификация, а не спрятаться в симметрии.
CELL_TREATED = ((Piece(1.0, 1160.0), Piece(1.0, 1560.0)),
                (Piece(1.0, 1240.0), Piece(1.0, 1640.0)))
CELL_TREATED_WEIGHTS = (0.5, 1.0)
CELL_TREATED_TRUTH = (1200.0, 1600.0)          # (λ⁻, λ⁺)

CELL_CONTROL = ((Piece(1.0, 860.0), Piece(1.0, 1260.0)),
                (Piece(1.0, 940.0), Piece(1.0, 1340.0)))
CELL_CONTROL_WEIGHTS = (0.5, 1.0)
CELL_CONTROL_TRUTH = (900.0, 1300.0)

CELL_ARMS = (("treated", CELL_TREATED, CELL_TREATED_WEIGHTS, CELL_TREATED_TRUTH),
             ("control", CELL_CONTROL, CELL_CONTROL_WEIGHTS, CELL_CONTROL_TRUTH))
CELL_NAME = "cell_four_endpoints"


def cell_gets_verdict(certified) -> bool:
    """Ячейка получает научный вердикт ТОЛЬКО когда точны ВСЕ четыре конца.

    Один неточный конец — и ячейка не оценена. `any` здесь был бы ровно той
    человеческой ошибкой, ради которой сценарий и написан.
    """
    certified = list(certified)
    return len(certified) == 4 and all(certified)


def replicate_cell(index: int, tallies=None, ladder=PR.LOOKS, deltas=DELTAS,
                   configs=CONFIGS):
    """Четыре конца, каждый со СВОИМ `tau`; вердикт — только когда все точны."""
    rngs, samples, truths = {}, {}, {}
    for arm, catalogue, weights, (low, high) in CELL_ARMS:
        rngs[arm] = random.Random(f"{SEED_NAMESPACE}:{CELL_NAME}:{index}:{arm}")
        samples[arm] = CatalogueSample(catalogue)
        truths[(arm, False)] = low
        truths[(arm, True)] = high
    draws = {arm: _catalogue_draw(w) for arm, _, w, _ in CELL_ARMS}
    ends = tuple(truths)
    live = {(e, d, label): True
            for e in ends for d in deltas for label, _ in configs}
    outcome = {}
    drawn = 0
    for size in ladder:
        if not any(live.values()):
            break
        for arm, _, _, _ in CELL_ARMS:
            for _ in range(size - drawn):
                draws[arm](rngs[arm], samples[arm])
        drawn = size
        for end in ends:
            arm, maximise = end
            state = _look_state(samples[arm], configs, truths[end],
                                maximise=maximise)
            for label, z in configs:
                radius, covered, _ = state[label]
                for d in deltas:
                    key = (end, d, label)
                    if live[key] and PR.is_precise(radius, d, z=z):
                        live[key] = False
                        outcome[key] = (True, covered)
    for key, still in live.items():
        if still:
            outcome[key] = (False, None)

    result = {}
    for d in deltas:
        for label, _ in configs:
            four = [outcome[(e, d, label)] for e in ends]
            verdict = cell_gets_verdict(c for c, _ in four)
            missed = verdict and not all(cov for _, cov in four)
            result[(d, label)] = (verdict, not missed if verdict else None, None)
            if tallies is not None:
                tally = tallies[(d, label)]
                tally.trials += 1
                tally.achieved += verdict
                tally.false_cert += missed
                mark = "verdict" if verdict else "insufficient"
                tally.stopped_at[mark] = tally.stopped_at.get(mark, 0) + 1
    return result


# --------------------------------------------------------------------------
# отчёт
# --------------------------------------------------------------------------

def _run_one(name, runner, deltas, configs):
    tallies = {(d, label): Tally() for d in deltas for label, _ in configs}
    for index in range(REPLICATES):
        runner(index, tallies)
    return tallies


def _print_block(name, tallies, deltas, configs, verdicts):
    for d in deltas:
        for label, _ in configs:
            tally = tallies[(d, label)]
            ok = accepted(tally.false_cert, tally.trials)
            verdicts[(name, d, label)] = (ok, tally)
            stops = ", ".join(f"{k}:{v}" for k, v in
                              sorted(tally.stopped_at.items(), key=lambda kv: str(kv[0])))
            conditional = tally.conditional()
            shown = "  —   " if conditional != conditional else f"{conditional:.4f}"
            print(f"{name:<20}{d:>6.0f}  {label:<24}"
                  f"{tally.false_cert:>5}/{tally.trials} = {tally.false_cert/tally.trials:.4f}  "
                  f"серт {tally.achieved/tally.trials:.4f}  "
                  f"недост {1 - tally.achieved/tally.trials:.4f}  "
                  f"усл {shown}  "
                  f"{'принято' if ok else 'ОТКЛОНЕНО':<10}{stops}", flush=True)


def main() -> int:
    print(f"РЕДАКЦИЯ 4: квалифицируется stopping procedure, не покрытие "
          f"каждого просмотра")
    print(f"лестница {PR.LOOKS}, реплик {REPLICATES}, "
          f"seed namespace {SEED_NAMESPACE!r}")
    print(f"концов {PR.ENDPOINTS_PER_CELL} x просмотров {len(PR.LOOKS)} = "
          f"{PR.COMPARISONS} сравнений, z = {Z_DECLARED:.4f} (НЕ меняется)")
    print(f"δ по всей объявленной оси {tuple(int(d) for d in DELTAS)} "
          f"= {DELTA_FRACTIONS_OF_HORIZON} x H")
    print(f"гейт: p_false_cert = P(tau < inf И λ0 не в A_tau)")
    print(f"номинал {NOMINAL_FALSE_CERT:.6f} (= 3·α/12), "
          f"множитель пола {FLOOR_RATIO:.1f} (из пары 0.93/0.95 проекта), "
          f"пол {FALSE_CERT_FLOOR:.4f}")
    print(f"утверждений {STATEMENTS}, семейный z {SUITE_Z:.4f}; "
          f"жёсткий минимум {COVERAGE_ACCEPTANCE_FLOOR} тоже требуется")
    print("потоки ОБЩИЕ для всех δ и всех z (common random numbers)\n")
    print(f"{'сценарий':<20}{'δ':>6}  {'конфигурация':<24}"
          f"{'ложная сертификация':<22}{'серт':<12}{'недост':<14}"
          f"{'усл':<11}{'вердикт':<10}остановки")

    verdicts = {}
    for scenario in SCENARIOS:
        tallies = _run_one(
            scenario.name,
            lambda i, t, s=scenario: replicate(s, i, t), DELTAS, CONFIGS)
        _print_block(scenario.name, tallies, DELTAS, CONFIGS, verdicts)
        if scenario.name.startswith("fieller"):
            tally = tallies[(DELTAS[0], CONFIGS[0][0])]
            detail = ", ".join(
                f"M={m}: {tally.fixed_look_miss.get(m, 0)}/"
                f"{tally.fixed_look_trials.get(m, 0)}"
                for m in PR.LOOKS if m in tally.fixed_look_trials)
            print(f"{'':<20}{'':>6}  {'фиксированный просмотр':<24}{detail}")
            print(f"{'':<20}{'':>6}  {'несвязных множеств':<24}"
                  f"{tally.disconnected}")

    tallies = _run_one(CELL_NAME, lambda i, t: replicate_cell(i, t),
                       DELTAS, CONFIGS)
    _print_block(CELL_NAME, tallies, DELTAS, CONFIGS, verdicts)

    print()
    main_rows = {k: v for k, v in verdicts.items() if k[2] == CONFIGS[0][0]}
    failed = [k for k, (ok, _) in main_rows.items() if not ok]
    vacuous = [k for k, (_, t) in main_rows.items() if t.achieved == 0]
    print(f"ОСНОВНАЯ КОНФИГУРАЦИЯ: "
          f"{'ПРИНЯТА' if not failed else 'ОТКЛОНЕНА'} "
          f"({len(main_rows) - len(failed)}/{len(main_rows)} утверждений)")
    if failed:
        print(f"  отклонено: {[(n, int(d)) for n, d, _ in failed]}")
    print(f"ВАКУУМНЫХ (сертификат не выдан ни разу): {len(vacuous)}/"
          f"{len(main_rows)} -> {[(n, int(d)) for n, d, _ in vacuous]}")
    for label, _ in CONFIGS[1:]:
        rows = {k: v for k, v in verdicts.items() if k[2] == label}
        fell = [k for k, (ok, _) in rows.items() if not ok]
        live = [k for k, (_, t) in rows.items() if t.achieved]
        fell_live = [k for k in fell if rows[k][1].achieved]
        print(f"{label}: отклонено {len(fell)}/{len(rows)}; "
              f"среди НЕвакуумных {len(fell_live)}/{len(live)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
