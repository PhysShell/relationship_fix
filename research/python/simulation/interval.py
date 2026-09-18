"""Квантиль Стьюдента на stdlib — потому что z = 1.96 здесь недокрывает.

Повторов у симуляции мало, и SD контраста оценивается по ним же. Нормальный
квантиль предполагает, что SD известна; она не известна, и интервал выходит уже
правды. На четырёх base_seed по четырём эстимандам это дало три MISMATCH из
шестнадцати при номинальных пяти процентах — то есть инструмент обвинял
пайплайн в смещении втрое чаще, чем имел право.

Поправка стандартная и ровно одна: квантиль Стьюдента с n-1 степенями свободы
вместо нормального. Реализация — регуляризованная неполная бета непрерывной
дробью (Ленц) плюс бисекция по CDF. Бисекция, а не Ньютон: производная тут не
нужна, а монотонность CDF даёт сходимость без единого условия на старт.

Проверяется против печатной таблицы, а не против самой себя.
"""

from __future__ import annotations

import math

_TINY = 1e-300


def _beta_continued_fraction(a: float, b: float, x: float,
                             *, iterations: int = 400, eps: float = 1e-14) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _TINY:
        d = _TINY
    d = 1.0 / d
    h = d
    for m in range(1, iterations + 1):
        m2 = 2 * m
        for numerator in (
            m * (b - m) * x / ((qam + m2) * (a + m2)),
            -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2)),
        ):
            d = 1.0 + numerator * d
            if abs(d) < _TINY:
                d = _TINY
            c = 1.0 + numerator / c
            if abs(c) < _TINY:
                c = _TINY
            d = 1.0 / d
            step = d * c
            h *= step
        if abs(step - 1.0) < eps:
            return h
    raise ArithmeticError(f"incomplete beta did not converge at a={a}, b={b}, x={x}")


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b). Continued fraction is used on the side where it converges."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                 + a * math.log(x) + b * math.log1p(-x))
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def student_t_cdf(t: float, df: float) -> float:
    if df <= 0:
        raise ValueError(f"degrees of freedom must be positive, got {df}")
    tail = 0.5 * regularized_incomplete_beta(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - tail if t >= 0 else tail


def student_t_quantile(p: float, df: float, *, tolerance: float = 1e-10) -> float:
    """Обратная CDF Стьюдента бисекцией. `p = 0.975`, `df = n - 1`."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"probability must lie strictly inside (0, 1), got {p}")
    if p < 0.5:
        return -student_t_quantile(1.0 - p, df, tolerance=tolerance)
    if p == 0.5:
        return 0.0
    low, high = 0.0, 1.0
    while student_t_cdf(high, df) < p:
        high *= 2.0
        if high > 1e12:
            raise ArithmeticError(f"quantile not bracketed for p={p}, df={df}")
    while high - low > tolerance * max(1.0, high):
        mid = 0.5 * (low + high)
        if student_t_cdf(mid, df) < p:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def half_width(se: float, n: int, *, confidence: float = 0.95) -> float:
    """Полуширина интервала для среднего по `n` повторам с оценённой SD."""
    if n < 2:
        raise ValueError(f"an interval needs at least 2 observations, got {n}")
    return student_t_quantile(0.5 + confidence / 2.0, n - 1) * se
