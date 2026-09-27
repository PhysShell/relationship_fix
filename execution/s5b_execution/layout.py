"""Раскладки ключей для 64000, сбалансированные внутри блока δ.

Смежная `key_slices(12)` режет каждый 18-ключевой блок ровно по уровням
days: три группы блока δ = 60 совпадают с окнами 14 / 28 / 56 дней, и
дымовой прогон на просмотре 40 дал на них 1.7 / 2.6 / 5.9 с. Раскладка
полностью конфаундит days, а days сильно влияет на стоимость.

Эта раскладка сохраняет число групп и пар (группа, δ) — каждая группа
лежит внутри одного δ, лишнего `to_bins` нет, — но делит каждый блок
сбалансированно по всем трём остальным координатам. d, h, x — индексы
days, horizon и maximise:

    g = 12   группа блока = (d + h + x) mod 3
             6 ключей: по 2 каждого days, по 2 каждого horizon, 3/3 maximise
    g = 24   r = (h − d) mod 3, b = x XOR (d mod 2), группа = 2r + b
             3 ключа: по одному каждого days и horizon, maximise 2/1

Запасная g = 24 заморожена ДО пилота g = 12, чтобы её не проектировали по
увиденным данным. Других размеров нет.
"""

from __future__ import annotations

from .scheduler import KEYS

BALANCED_GROUPS = (12, 24)

DELTAS = tuple(sorted({k[0] for k in KEYS}))
DAYS = tuple(sorted({k[1] for k in KEYS}))
HORIZONS = tuple(sorted({k[2] for k in KEYS}))


def local_group(groups: int, key) -> int:
    """Номер группы ключа внутри его блока δ."""
    d, h, x = DAYS.index(key[1]), HORIZONS.index(key[2]), int(key[3])
    if groups == 12:
        return (d + h + x) % 3
    if groups == 24:
        r = (h - d) % 3
        b = x ^ (d % 2)
        return 2 * r + b
    raise ValueError(f"сбалансированная раскладка есть только для {BALANCED_GROUPS}")


def balanced_slices(groups: int) -> tuple:
    """Группы по блокам δ в порядке возрастания δ; ключи — в порядке KEYS."""
    if groups not in BALANCED_GROUPS:
        raise ValueError(f"сбалансированная раскладка есть только для {BALANCED_GROUPS}")
    per_block = groups // len(DELTAS)
    out = []
    for delta in DELTAS:
        buckets = [[] for _ in range(per_block)]
        for key in KEYS:
            if key[0] == delta:
                buckets[local_group(groups, key)].append(key)
        out.extend(tuple(b) for b in buckets)
    return tuple(out)


def counts(group) -> dict:
    """Сколько ключей группы приходится на каждый уровень каждой координаты."""
    return {"days": [sum(k[1] == v for k in group) for v in DAYS],
            "horizon": [sum(k[2] == v for k in group) for v in HORIZONS],
            "maximise": [sum(k[3] is v for k in group) for v in (False, True)]}
