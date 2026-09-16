"""Semantic spine — изолированный research harness (experiments/, вне trusted state).

Ничего не мутирует в data/ и не является source of truth. Читает spec/*.md,
строит IR и типизированный граф, проверяет инварианты fail-closed и собирает
контекстные бандлы для сравнения стратегий.
"""

__all__ = ["ir", "blocks", "parser", "graph", "compiler", "verifier", "selector", "budget"]
