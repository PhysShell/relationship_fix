"""Инверсия теста: ПОЛНОЕ множество принятия, а не интервал вокруг корня.

ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ МОДУЛЬ И ПОЧЕМУ ТОЧНО. Найдено восьмым враждебным
чтением, и находка не про изломы.

Соблазнительно рассуждать так: g строго убывает, ноль единственный, значит
множество неотвергнутых λ — интервал вокруг корня, и его концы можно найти
двумя дихотомиями. ПЕРВАЯ ЧАСТЬ ВЕРНА, ВЫВОД НЕТ. Тестируется не g, а
СТЬЮДЕНТИЗОВАННАЯ статистика

    T(λ) = sqrt(n) · mean ψ(λ) / sd ψ(λ)

и знаменатель тоже зависит от λ. Числитель монотонен, отношение — нет.

Это семейство эффектов Филлера: доверительные множества для ОТНОШЕНИЙ бывают
несвязными и неограниченными. Контрпример, в котором нет ни одного излома,
корень единственный и внутренний, а наблюдения ограничены:

    период 1:     N = 100,  B = 131520
    периоды 2-25: N = 1,    B = 720

Единственный корень 1200, а множество принятия при z = 1.96 равно

    [0, 1273.95] U [1535.81, +inf)

Дырка ровно посередине. Взять компоненту вокруг корня значит молча выбросить
вторую — то есть заявить, что данные исключают режим, который они НЕ
исключают. Уродливость такого множества здесь информация, а не дефект
интерфейса.

Считается всё ТОЧНО. На участке между соседними изломами каждая ψ_i аффинна,
поэтому mean(λ) линейна, var(λ) квадратична, и граница теста

    n · mean(λ)² = z² · var(λ)

— обычное квадратное уравнение. Никаких дихотомий и никаких предположений о
связности.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Вырожденная дисперсия: ПРИНИМАЕМ. Обоснование уточнено девятым чтением,
#: прежнее было неверным. Писалось: «в истинном λ0 среднее равно нулю, значит
#: отвергнуть там — потерять покрытие». Не следует: из E[ψ(λ0)] = 0 НЕ
#: вытекает, что выборочное среднее равно нулю. Дискретный DGP вполне может
#: выдать 25 одинаковых НЕнулевых значений — тогда s = 0 при популяционном
#: нуле.
#:
#: Правильная формулировка — соглашение теста, а не вывод о покрытии:
#:
#:     s² = 0  ->  стьюдентизованная статистика не определена
#:             ->  соглашение: НЕ ОТВЕРГАТЬ
#:
#: Оно жертвует МОЩНОСТЬЮ, а не покрытием: принять лишнее λ значит расширить
#: множество, а расширение покрытие не роняет. Частота таких λ отчётна.
ZERO_VARIANCE_IS_ACCEPTED = True
ZERO_VARIANCE_COSTS_POWER_NOT_COVERAGE = True


@dataclass(frozen=True, slots=True)
class Piece:
    """Достижимая пара (N, B): ψ вносит B − λN."""

    n: float
    b: float


def psi(pieces: tuple[Piece, ...], lam: float) -> float:
    return min(p.b - lam * p.n for p in pieces)


def _breakpoints(periods, lo: float, hi: float) -> list[float]:
    out = {lo, hi}
    for pieces in periods:
        for i, a in enumerate(pieces):
            for b in pieces[i + 1:]:
                if a.n != b.n:
                    lam = (a.b - b.b) / (a.n - b.n)
                    if lo < lam < hi:
                        out.add(lam)
    return sorted(out)


#: Наружное расширение корней. Как и у скобок `generalized_inverse`, численная
#: ошибка обязана РАСШИРЯТЬ множество принятия, а не сужать: сузить значит
#: выбросить λ, которое данные не исключают.
OUTWARD_EPS = 1e-9

#: Допуск на дискриминант. Двойной корень — самый мерзкий случай: ошибка на
#: пару ulp превращает крошечную принимаемую область в «корней нет». Проиграть
#: покрытие функции sqrt() после всего остального было бы издевательством.
DISCRIMINANT_TOLERANCE = 1e-12


def _widen(lo: float, hi: float, span: float) -> tuple[float, float]:
    eps = OUTWARD_EPS * max(1.0, abs(lo), abs(hi), span)
    return lo - eps, hi + eps


def _roots(a: float, b: float, c: float) -> tuple[float, float] | None:
    """Корни, устойчивой формулой. None — если их нет ЗАВЕДОМО.

    Прямая формула (−b ± sqrt(D))/(2a) теряет значащие цифры, когда b² >> 4ac:
    один из корней считается вычитанием близких чисел. Классический приём
    q = −(b + sign(b)·sqrt(D))/2 от этого избавляет.
    """
    disc = b * b - 4.0 * a * c
    scale = max(abs(b * b), abs(4.0 * a * c), 1.0)
    if disc < -DISCRIMINANT_TOLERANCE * scale:
        return None
    root = math.sqrt(max(0.0, disc))          # |disc| в допуске -> двойной корень
    if b == 0.0:
        first = root / (2.0 * a)
        return (-abs(first), abs(first)) if a > 0 else (abs(first), -abs(first))
    q = -0.5 * (b + math.copysign(root, b))
    first, second = q / a, (c / q if q != 0.0 else q / a)
    return (min(first, second), max(first, second))


def _solve(coefficients: tuple[float, float, float], lo: float, hi: float):
    """{λ ∈ [lo, hi] : Aλ² + Bλ + C <= 0}, с округлением НАРУЖУ."""
    a, b, c = coefficients
    span = hi - lo
    if abs(a) < 1e-12:
        if abs(b) < 1e-12:
            return [(lo, hi)] if c <= 0.0 else []
        edge = -c / b
        left, right = (lo, min(hi, edge)) if b > 0 else (max(lo, edge), hi)
        left, right = _widen(left, right, span)
        left, right = max(lo, left), min(hi, right)
        return [(left, right)] if left <= right else []

    found = _roots(a, b, c)
    if a > 0:
        if found is None:
            return []
        left, right = _widen(*found, span)
        left, right = max(lo, left), min(hi, right)
        return [(left, right)] if left <= right else []

    if found is None:
        return [(lo, hi)]
    # a < 0: принимается ВНЕ корней, поэтому наружу = границы сдвигаются внутрь
    low, high = found
    eps = OUTWARD_EPS * max(1.0, abs(low), abs(high), span)
    low, high = low + eps, high - eps
    out = []
    if lo < low:
        out.append((lo, min(hi, low)))
    if high < hi:
        out.append((max(lo, high), hi))
    return out


def acceptance_set(periods, *, z: float, lo: float = 0.0, hi: float,
                   tolerance: float = 1e-9) -> list[tuple[float, float]]:
    """ПОЛНОЕ множество принятия двустороннего теста. Список компонент.

    Компонент может быть НЕСКОЛЬКО, и это не ошибка — см. докстринг модуля.
    """
    count = len(periods)
    if count < 2:
        return [(lo, hi)]

    pieces_at = lambda pieces, lam: min(pieces, key=lambda p: p.b - lam * p.n)
    found: list[tuple[float, float]] = []
    edges = _breakpoints(periods, lo, hi)

    for left, right in zip(edges, edges[1:]):
        if right - left < tolerance:
            continue
        middle = (left + right) / 2.0
        active = [pieces_at(pieces, middle) for pieces in periods]
        mean_b = sum(p.b for p in active) / count
        mean_n = sum(p.n for p in active) / count
        s_bb = sum((p.b - mean_b) ** 2 for p in active)
        s_bn = sum((p.b - mean_b) * (p.n - mean_n) for p in active)
        s_nn = sum((p.n - mean_n) ** 2 for p in active)
        scale = z * z / (count - 1)
        # mean(λ) = mean_b − λ·mean_n;  var(λ) = (s_bb − 2λ s_bn + λ² s_nn)/(n−1)
        a = count * mean_n * mean_n - scale * s_nn
        b = -2 * count * mean_b * mean_n + 2 * scale * s_bn
        c = count * mean_b * mean_b - scale * s_bb
        if s_nn == 0.0 and s_bb == 0.0 and ZERO_VARIANCE_IS_ACCEPTED:
            found.append((left, right))          # разброса нет: принимаем
            continue
        found.extend(_solve((a, b, c), left, right))

    found.sort()
    merged: list[tuple[float, float]] = []
    for piece in found:
        if merged and piece[0] - merged[-1][1] <= tolerance:
            merged[-1] = (merged[-1][0], max(merged[-1][1], piece[1]))
        else:
            merged.append(piece)
    return merged


def convex_hull_interval(components) -> tuple[float, float] | None:
    """[inf A, sup A]. ЕДИНСТВЕННОЕ безопасное превращение множества в интервал.

    Оболочка только РАСШИРЯЕТ, поэтому покрытие не падает. Брать компоненту,
    содержащую λ̂, без отдельного доказательства покрытия НЕЛЬЗЯ: именно это
    и выбрасывает вторую компоненту в примере Филлера.
    """
    if not components:
        return None
    return components[0][0], components[-1][1]
