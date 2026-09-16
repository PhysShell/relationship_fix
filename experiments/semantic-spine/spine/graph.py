"""Типизированный граф поверх IR: смежности, обходы и поиск циклов.

Никакой семантики проверок здесь нет — только структура. Verifier задаёт
вопросы, graph умеет на них отвечать.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence

from .ir import ACYCLIC_RELATIONS, Edge, Entity


@dataclass
class Graph:
    entities: dict[str, Entity]
    edges: list[Edge]

    def __post_init__(self) -> None:
        self._out: dict[str, list[Edge]] = defaultdict(list)
        self._in: dict[str, list[Edge]] = defaultdict(list)
        for edge in self.edges:
            self._out[edge.source_id].append(edge)
            self._in[edge.target_id].append(edge)

    def out_edges(self, node: str, relations: Iterable[str] | None = None) -> list[Edge]:
        wanted = None if relations is None else set(relations)
        return [e for e in self._out.get(node, []) if wanted is None or e.relation in wanted]

    def in_edges(self, node: str, relations: Iterable[str] | None = None) -> list[Edge]:
        wanted = None if relations is None else set(relations)
        return [e for e in self._in.get(node, []) if wanted is None or e.relation in wanted]

    def incident(self, node: str, relations: Iterable[str] | None = None) -> list[Edge]:
        return self.out_edges(node, relations) + self.in_edges(node, relations)

    def nodes(self) -> Iterator[str]:
        seen: set[str] = set()
        for node in self.entities:
            seen.add(node)
            yield node
        for edge in self.edges:
            for node in (edge.source_id, edge.target_id):
                if node not in seen:
                    seen.add(node)
                    yield node

    def find_cycles(self, relations: Iterable[str] = ACYCLIC_RELATIONS) -> list[list[str]]:
        """Простые циклы по заданному набору рёбер. Детерминированный порядок."""

        wanted = set(relations)
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in sorted(self.edges, key=lambda e: e.key()):
            if edge.relation in wanted:
                adjacency[edge.source_id].append(edge.target_id)

        cycles: list[list[str]] = []
        seen_cycles: set[tuple[str, ...]] = set()
        colour: dict[str, int] = {}
        stack: list[str] = []

        def visit(node: str) -> None:
            colour[node] = 1
            stack.append(node)
            for nxt in adjacency.get(node, []):
                state = colour.get(nxt, 0)
                if state == 0:
                    visit(nxt)
                elif state == 1:
                    cycle = stack[stack.index(nxt) :] + [nxt]
                    key = tuple(cycle)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        cycles.append(cycle)
            stack.pop()
            colour[node] = 2

        for node in sorted(adjacency):
            if colour.get(node, 0) == 0:
                visit(node)
        return cycles

    def expand(
        self,
        seeds: Sequence[str],
        relation_order: Sequence[str],
        max_nodes: int,
        typed: bool = True,
    ) -> list[str]:
        """Обход от seed'ов по типам рёбер в заданном приоритете.

        `typed=False` — абляция: те же рёбра, но порядок обхода не знает их
        типа. Это и проверяет, несут ли типы рёбер что-то сверх связности.
        """

        order = list(relation_order) if typed else [None]  # type: ignore[list-item]
        visited: list[str] = []
        seen: set[str] = set()
        for seed in seeds:
            if seed not in seen:
                seen.add(seed)
                visited.append(seed)

        current = list(visited)
        while current and len(visited) < max_nodes:
            nxt: list[str] = []
            for node in current:
                for relation in order:
                    relations = None if relation is None else [relation]
                    for edge in sorted(self.incident(node, relations), key=lambda e: e.key()):
                        for candidate in (edge.target_id, edge.source_id):
                            if candidate in seen or candidate == node:
                                continue
                            seen.add(candidate)
                            visited.append(candidate)
                            nxt.append(candidate)
                            if len(visited) >= max_nodes:
                                return visited
            current = nxt
        return visited
