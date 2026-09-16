"""Бюджет контекста и его счётчик.

Честность эксперимента держится на одном: все стратегии считают токены ОДНИМ
и тем же счётчиком. Если spine получает 30k токенов, а baseline 8k, научный
результат называется «мы потратили больше денег».

Счётчик — детерминированный прокси, не настоящий BPE-токенизатор: stdlib-only
(ADR-0001 §Python), никакой сети и никаких весов. Абсолютное число поэтому
приблизительно; сравнение стратегий — нет, потому что смещение общее для всех.
Подменить на настоящий токенизатор можно одной функцией.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def approx_tokens(text: str) -> int:
    """Прокси длины в токенах.

    Берём максимум из двух оценок: по «словам» (латиница дробится слабо) и по
    символам/3.2 (кириллица и эмодзи дробятся сильнее). Максимум, а не среднее,
    потому что недооценка бюджета — это молчаливое преимущество для стратегии
    с многоязычным текстом.
    """

    if not text:
        return 0
    words = len(_WORD.findall(text))
    chars = len(text) / 3.2
    return int(max(words, chars)) + 1


@dataclass(frozen=True)
class ContextBudget:
    max_tokens: int

    def fits(self, used: int, addition: int) -> bool:
        return used + addition <= self.max_tokens
