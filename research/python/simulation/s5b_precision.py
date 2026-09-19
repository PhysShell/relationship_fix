"""Fixed-width правило точности Монте-Карло для конца λ∓.

ПОЧЕМУ НЕ «ОЦЕНЩИК MCSE». Предыдущая редакция предлагала

    MCSE := (sup A − inf A) / (2z)

и это НЕВЕРНО. Тождество «ширина = 2z·SE» принадлежит ВАЛЬДОВУ интервалу, а
инверсия теста выбиралась ровно за то, что вальдовой геометрии у неё нет:
множество бывает асимметричным, несвязным и упирающимся в границы домена.
Собственный golden проекта — немедленный контрпример:

    [0, 1273.95] U [1535.81, H]   ->   оболочка [0, H]

Поделить это на 2z и назвать стандартной ошибкой нельзя. Это может быть
прекрасной мерой неопределённости, но это ДРУГОЙ ОБЪЕКТ.

ЧТО ДЕЛАЕТСЯ ВМЕСТО. Prereg назвал требование через MCSE, но оценщика MCSE
не определил. Недоопределённая величина заменяется на НЕПОСРЕДСТВЕННО
ПРОВЕРЯЕМЫЙ критерий точности — радиус доверительного множества:

    r_M = max( λ̂_M − inf A_M ,  sup A_M − λ̂_M )

по ПОЛНОМУ множеству принятия (несвязное берётся целиком, «красивая
компонента возле корня» запрещена — это тот же shortcut, что уже запрещён
для самого инференса).

Критерий:

    r_M <= z · 0.1 · GATE_MARGIN_FRACTION · δ

В вальдовом случае A = λ̂ ± z·SE, значит r_M = z·SE, и критерий сводится
РОВНО к старому `SE <= target`. То есть численная шкала prereg сохранена, а
в нерегулярном случае критерий остаётся определённым без притворства, будто
ширина доверительного множества внезапно стала стандартным отклонением.

ТРИ ПРОСМОТРА ТРЕБУЮТ ЗАЩИТЫ. Остановка по ширине на M = 4000/16000/64000 —
это data-dependent stopping, и покрытие одного просмотра на всю процедуру не
переносится. Просмотров ровно три и они известны заранее, поэтому уровень
делится по Бонферрони: каждое множество строится на 1 − α/3. Порог при этом
НЕ меняется (z входит в обе стороны неравенства), меняется гарантия: с
вероятностью не ниже 1 − α истинный λ0 лежит в A_M на КАЖДОМ просмотре.

Fixed-width правила остановки — стандартный жанр в симуляционной литературе;
новизны здесь нет, есть только аккуратность с нерегулярной геометрией.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import NormalDist

from simulation.s5b_prereg import (CONFIDENCE_LEVEL, GATE_MARGIN_FRACTION,
                                   MEASUREMENT_MC_ESCALATION_FACTOR,
                                   MEASUREMENT_MC_MAX_PERIODS_PER_ARM,
                                   MEASUREMENT_MC_START_PERIODS_PER_ARM)


def looks() -> tuple[int, ...]:
    """Лестница M из замороженных констант. Ничего не выдумывается."""
    out, current = [], MEASUREMENT_MC_START_PERIODS_PER_ARM
    while current <= MEASUREMENT_MC_MAX_PERIODS_PER_ARM:
        out.append(current)
        current *= MEASUREMENT_MC_ESCALATION_FACTOR
    return tuple(out)


LOOKS = looks()
ALPHA = 1.0 - CONFIDENCE_LEVEL
#: Бонферрони по ТРЁМ заранее известным просмотрам.
ALPHA_PER_LOOK = ALPHA / len(LOOKS)
Z_PER_LOOK = NormalDist().inv_cdf(1.0 - ALPHA_PER_LOOK / 2.0)


def target(delta: float) -> float:
    """0.1 · GATE_MARGIN_FRACTION · δ — ровно как в prereg."""
    return 0.1 * GATE_MARGIN_FRACTION * delta


def radius(components, point: float) -> float:
    """r_M по ПОЛНОМУ множеству. Несвязное берётся целиком.

    Точка может лежать вне множества (при сильной асимметрии или когда
    оценка попала в «дырку»); радиус от этого только растёт, что
    консервативно и потому допустимо.
    """
    if not components:
        return float("inf")
    low = min(a for a, _ in components)
    high = max(b for _, b in components)
    return max(point - low, high - point)


def is_precise(radius_value: float, delta: float, *, z: float = Z_PER_LOOK) -> bool:
    """r_M <= z · target(δ). В вальдовом случае это SE <= target(δ)."""
    return radius_value <= z * target(delta)


class PrecisionStatus(Enum):
    """Исходы процедуры. Прогноз и вердикт — РАЗНЫЕ вещи."""

    #: точность достигнута на каком-то просмотре
    ACHIEVED = "MC_PRECISION_ACHIEVED"
    #: потолок исчерпан, точность не достигнута — вердикта у ячейки НЕТ
    INSUFFICIENT = "MC_PRECISION_INSUFFICIENT"
    #: пилотный прогноз, НЕ научный вердикт, автоматически в INSUFFICIENT
    #: не превращается
    PREDICTED_INSUFFICIENT = "MC_PRECISION_PREDICTED_INSUFFICIENT"


#: Статус ПОВЕРХНОСТИ для ячейки без установленной точности. Отдельный от
#: всего: не MEASUREMENT_AMBIGUOUS, не PASS, не FAIL, не структурный ноль и
#: не ошибка. Сливать их нельзя ни логически, ни визуально.
NOT_EVALUATED_MC_PRECISION = "NOT_EVALUATED_MC_PRECISION"


@dataclass(frozen=True, slots=True)
class Outcome:
    status: PrecisionStatus
    look: int
    radius: float
    target: float


def run_nested(evaluate, delta: float, *, ladder=LOOKS, z: float = Z_PER_LOOK
               ) -> Outcome:
    """Вложенная процедура 4000 -> 16000 -> 64000.

    `evaluate(M)` обязана вернуть `(components, point)` для ВЛОЖЕННОГО набора
    периодов `0..M-1`: набор потоков определяется только (tag, i), поэтому
    shard, worker, порядок и их количество в него не входят.

    Квалифицируется процедура ЦЕЛИКОМ, а не оценщик на одном M: именно
    последовательная остановка и создаёт риск, которого нет у одного
    просмотра.
    """
    limit = target(delta)
    last_radius = float("inf")
    for size in ladder:
        components, point = evaluate(size)
        last_radius = radius(components, point)
        if is_precise(last_radius, delta, z=z):
            return Outcome(PrecisionStatus.ACHIEVED, size, last_radius, limit)
    return Outcome(PrecisionStatus.INSUFFICIENT, ladder[-1], last_radius, limit)
