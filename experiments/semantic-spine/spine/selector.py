"""Стратегии отбора контекста под общий бюджет.

Одна задача, один бюджет, один счётчик токенов — и шесть способов решить, что
агент вообще увидит. Без baseline'ов это был бы эксперимент «мы построили нашу
штуку и сравнили её с соломенным человеком».
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .budget import ContextBudget, approx_tokens
from .compiler import Compilation, compile_spec_dir
from .graph import Graph
from .ir import KIND_CODE, KIND_DATA, KIND_DOC, KIND_EXAMPLE, KIND_LABEL, KIND_ONTOLOGY, KIND_TEST
from .refs import RefSyntaxError, parse_ref
from .targets import TargetUnresolvable, locate, parse_target

TEXT_SUFFIXES = {".md", ".cs", ".hs", ".py", ".json", ".jsonl", ".yaml", ".yml", ".sh", ".csv", ".slnx", ".props", ".nix", ".cabal", ".wit", ".mjs", ".c"}
SKIP_DIRS = {".git", "generated", "result", "node_modules", "__pycache__", ".venv", "dist-newstyle", ".stack-work"}

# Harness не входит в корпус, по которому ищут стратегии. Две причины, обе
# дисквалифицирующие: spec/*.md пересказывают онтологию, поэтому lexical и raw
# нашли бы «правильный» текст в файлах самого эксперимента; и любой файл,
# добавленный сюда, сдвигал бы числа baseline'ов, делая результат
# невоспроизводимым от коммита к коммиту.
EXCLUDED_PREFIXES = ("experiments/semantic-spine",)

# Приоритет обхода графа. Порядок — это и есть «типизированность» рёбер:
# сначала то, что различает спутанные конструкты, потом спецификация, потом код.
SPINE_RELATION_ORDER = (
    "confusable_with",
    "exemplifies",
    "specified_by",
    "implements",
    "materialized_in",
    "tested_by",
    "depends_on",
    "evidenced_by",
    "supersedes",
    "generated_from",
)

MAX_EXCERPT_LINES = 60


@dataclass(frozen=True)
class TaskSpec:
    id: str
    prompt: str
    base_commit: str
    seeds: tuple[str, ...]
    oracle_files: tuple[str, ...]
    oracle_targets: tuple[str, ...]
    expected_touched_area: str
    keywords: tuple[str, ...] = ()

    @staticmethod
    def load(path: Path) -> "TaskSpec":
        payload = json.loads(path.read_text(encoding="utf-8"))
        # base_commit обязателен: задача без зафиксированного subject'а
        # невоспроизводима, а невоспроизводимый прогон не результат.
        base_commit = payload.get("base_commit")
        if not base_commit:
            raise ValueError(f"{path.name}: task manifest has no base_commit")
        return TaskSpec(
            id=payload["task_id"],
            prompt=payload["prompt"],
            base_commit=base_commit,
            seeds=tuple(payload.get("seeds", [])),
            oracle_files=tuple(payload["oracle_files"]),
            oracle_targets=tuple(payload.get("oracle_targets", [])),
            expected_touched_area=payload.get("expected_touched_area", ""),
            keywords=tuple(payload.get("keywords", [])),
        )


@dataclass(frozen=True)
class Chunk:
    origin: str
    path: str | None
    text: str
    reason: str

    @property
    def tokens(self) -> int:
        return approx_tokens(self.text)


@dataclass
class ContextBundle:
    strategy: str
    task_id: str
    chunks: list[Chunk] = field(default_factory=list)
    truncated: bool = False

    @property
    def tokens(self) -> int:
        return sum(chunk.tokens for chunk in self.chunks)

    def files(self) -> list[str]:
        seen: list[str] = []
        for chunk in self.chunks:
            if chunk.path and chunk.path not in seen:
                seen.append(chunk.path)
        return seen

    def tokens_on(self, paths: Iterable[str]) -> int:
        wanted = set(paths)
        return sum(chunk.tokens for chunk in self.chunks if chunk.path in wanted)

    def render(self) -> str:
        parts = []
        for chunk in self.chunks:
            header = chunk.path or chunk.origin
            parts.append(f"--- {header} ({chunk.reason}) ---\n{chunk.text}")
        return "\n\n".join(parts)


# Политика упаковки. Под тестом находится РАНЖИРОВАНИЕ стратегии, поэтому
# по умолчанию бюджет заполняется строгим префиксом: дошли до чанка, который
# не влезает, — остановились.
#
# Альтернатива "backfill" (пропустить большой чанк и добрать мелкими) ближе к
# тому, что делает реальный упаковщик контекста, но она позволяет стратегии
# выигрывать случайно: пропуск одного большого чанка впускает несколько мелких,
# и абляция «+irrelevant-docs» начинает обгонять чистый spine. Это артефакт
# упаковки, а не эффект. Обе политики доступны, применённая пишется в результат.
FILL_PREFIX = "prefix"
FILL_BACKFILL = "backfill"
FILL_POLICIES = (FILL_PREFIX, FILL_BACKFILL)


def _fill(
    bundle: ContextBundle,
    budget: ContextBudget,
    chunks: Iterable[Chunk],
    policy: str = FILL_PREFIX,
) -> ContextBundle:
    if policy not in FILL_POLICIES:
        raise ValueError(f"unknown fill policy {policy!r}; known: {', '.join(FILL_POLICIES)}")

    used = 0
    for chunk in chunks:
        size = chunk.tokens
        if not budget.fits(used, size):
            bundle.truncated = True
            if policy == FILL_PREFIX:
                break
            continue
        bundle.chunks.append(chunk)
        used += size
    return bundle


# --- источники текста -------------------------------------------------------


def repo_text_files(repo: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(repo.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(repo)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if str(relative).startswith(EXCLUDED_PREFIXES):
            continue
        out.append(path)
    return out


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _excerpt_around(text: str, anchor: str | None, is_heading: bool) -> str:
    lines = text.split("\n")
    if anchor is None:
        return "\n".join(lines[:MAX_EXCERPT_LINES])

    if is_heading:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") and stripped.lstrip("#").strip() == anchor:
                level = len(stripped) - len(stripped.lstrip("#"))
                end = index + 1
                while end < len(lines):
                    nxt = lines[end].strip()
                    if nxt.startswith("#") and (len(nxt) - len(nxt.lstrip("#"))) <= level:
                        break
                    end += 1
                return "\n".join(lines[index : min(end, index + MAX_EXCERPT_LINES)])
        return ""

    leaf = anchor.rsplit(".", 1)[-1]
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(leaf)}(?![A-Za-z0-9_])")
    for index, line in enumerate(lines):
        if pattern.search(line):
            start = max(0, index - 4)
            return "\n".join(lines[start : start + MAX_EXCERPT_LINES])
    return ""


# --- стратегии --------------------------------------------------------------


class Selector:
    """Единый интерфейс: одна задача + один бюджет -> один бандл."""

    name = "abstract"

    def __init__(self, repo: Path, compilation: Compilation, fill: str = FILL_PREFIX) -> None:
        self.repo = repo
        self.compilation = compilation
        self.fill = fill
        self.graph = Graph(compilation.entities, compilation.edges)

    def select(self, task: TaskSpec, budget: ContextBudget) -> ContextBundle:
        raise NotImplementedError

    def _bundle(self, task: TaskSpec) -> ContextBundle:
        return ContextBundle(strategy=self.name, task_id=task.id)


class RawSelector(Selector):
    """Никакого отбора: репозиторий в детерминированном порядке, пока лезет."""

    name = "raw"

    def select(self, task: TaskSpec, budget: ContextBudget) -> ContextBundle:
        chunks = [
            Chunk(origin=str(path), path=str(path.relative_to(self.repo)), text=_read(path), reason="repo order")
            for path in repo_text_files(self.repo)
        ]
        return _fill(self._bundle(task), budget, chunks, self.fill)


class DocsSelector(Selector):
    """То, что агент прочитает, если его вежливо попросить «прочитай доки»."""

    name = "docs"

    def select(self, task: TaskSpec, budget: ContextBudget) -> ContextBundle:
        ordered: list[Path] = []
        readme = self.repo / "README.md"
        if readme.is_file():
            ordered.append(readme)
        ordered += [p for p in repo_text_files(self.repo) if p.suffix == ".md" and p != readme]
        chunks = [
            Chunk(origin=str(p), path=str(p.relative_to(self.repo)), text=_read(p), reason="documentation")
            for p in ordered
        ]
        return _fill(self._bundle(task), budget, chunks, self.fill)


class SparseRankingSelector(Selector):
    """Общий каркас лексических baseline'ов: одинаковое чанкование и запрос.

    Разница между tf-idf и BM25 должна быть разницей в формуле ранжирования,
    а не в том, что одному нарезали корпус удобнее.
    """

    CHUNK_LINES = 40
    reason = "sparse rank"

    def _chunks(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for path in repo_text_files(self.repo):
            relative = str(path.relative_to(self.repo))
            lines = _read(path).split("\n")
            for start in range(0, len(lines), self.CHUNK_LINES):
                body = "\n".join(lines[start : start + self.CHUNK_LINES])
                if body.strip():
                    out.append((relative, body))
        return out

    @staticmethod
    def _terms(text: str) -> Counter:
        return Counter(re.findall(r"\w+", text.lower(), re.UNICODE))

    def _query(self, task: TaskSpec) -> Counter:
        return self._terms(" ".join([task.prompt, *task.keywords, *task.seeds]))

    def _score(self, query: Counter, terms: Counter, stats: dict) -> float:
        raise NotImplementedError

    def select(self, task: TaskSpec, budget: ContextBudget) -> ContextBundle:
        chunks = self._chunks()
        documents = [self._terms(body) for _, body in chunks]
        document_frequency: Counter = Counter()
        for terms in documents:
            document_frequency.update(set(terms))
        lengths = [sum(terms.values()) for terms in documents]
        stats = {
            "n": max(1, len(documents)),
            "df": document_frequency,
            "avgdl": (sum(lengths) / len(lengths)) if lengths else 1.0,
        }
        query = self._query(task)
        scores = [self._score(query, terms, stats) for terms in documents]

        ranked = sorted(range(len(chunks)), key=lambda i: (-scores[i], chunks[i][0], i))
        ordered = [
            Chunk(origin=chunks[i][0], path=chunks[i][0], text=chunks[i][1], reason=self.reason)
            for i in ranked
            if scores[i] > 0
        ]
        return _fill(self._bundle(task), budget, ordered, self.fill)


class LexicalSelector(SparseRankingSelector):
    """tf-idf по чанкам, без модели и без сети.

    Названа lexical, а не embedding, потому что это tf-idf, а не эмбеддинги.
    Настоящий dense baseline требует модели и остаётся объявленной дырой —
    см. README §Ограничения.
    """

    name = "lexical"
    reason = "tf-idf rank"

    def _score(self, query: Counter, terms: Counter, stats: dict) -> float:
        numerator = 0.0
        for term, count in query.items():
            if term not in terms:
                continue
            idf = math.log(stats["n"] / (1 + stats["df"][term]))
            numerator += count * terms[term] * max(idf, 0.0)
        norm = math.sqrt(sum(v * v for v in terms.values())) or 1.0
        return numerator / norm


class Bm25Selector(SparseRankingSelector):
    """Okapi BM25 — дешёвый, но заметно более сильный sparse baseline.

    Обгонять tf-idf несложно; если spine не обгоняет BM25, заявлять преимущество
    над retrieval'ом нельзя.
    """

    name = "bm25"
    reason = "bm25 rank"
    K1 = 1.5
    B = 0.75

    def _score(self, query: Counter, terms: Counter, stats: dict) -> float:
        length = sum(terms.values()) or 1
        total = 0.0
        for term in query:
            frequency = terms.get(term, 0)
            if not frequency:
                continue
            df = stats["df"][term]
            idf = math.log(1 + (stats["n"] - df + 0.5) / (df + 0.5))
            denominator = frequency + self.K1 * (1 - self.B + self.B * length / (stats["avgdl"] or 1.0))
            total += idf * frequency * (self.K1 + 1) / denominator
        return total


class SymbolGraphSelector(Selector):
    """grep по идентификаторам задачи: связность без семантики."""

    name = "symbol-graph"

    def select(self, task: TaskSpec, budget: ContextBudget) -> ContextBundle:
        identifiers = [seed.split(":", 1)[-1].split("#")[-1] for seed in task.seeds] + list(task.keywords)
        patterns = [re.compile(re.escape(identifier)) for identifier in identifiers if identifier]
        scored: list[tuple[int, str, Chunk]] = []
        for path in repo_text_files(self.repo):
            text = _read(path)
            hits = sum(len(p.findall(text)) for p in patterns)
            if not hits:
                continue
            relative = str(path.relative_to(self.repo))
            lines = text.split("\n")
            first = next(
                (i for i, line in enumerate(lines) if any(p.search(line) for p in patterns)), 0
            )
            start = max(0, first - 5)
            body = "\n".join(lines[start : start + MAX_EXCERPT_LINES])
            scored.append((-hits, relative, Chunk(relative, relative, body, f"{hits} identifier hit(s)")))
        scored.sort(key=lambda item: (item[0], item[1]))
        return _fill(self._bundle(task), budget, [chunk for _, _, chunk in scored], self.fill)


class SpineSelector(Selector):
    """Обход типизированного графа от seed'ов задачи.

    Отдаёт не файлы, а именно те фрагменты, на которые указывают рёбра:
    определение, спутанный сосед, примеры, абзац протокола, тело символа.
    """

    name = "semantic-spine"
    typed = True
    with_rationale = True
    noise = False

    MAX_NODES = 40

    def _render_node(self, node: str) -> Chunk | None:
        entity = self.compilation.entities.get(node)
        if entity is not None and entity.kind == KIND_LABEL:
            attributes = entity.attributes
            body = [
                f"# {attributes['id']} — {attributes['canonical_name']}",
                "",
                attributes["operational_definition"],
                "",
                "Inclusion:",
                *[f"  - {c}" for c in attributes["inclusion_criteria"]],
                "Exclusion:",
                *[f"  - {c}" for c in attributes["exclusion_criteria"]],
                f"allowed_units: {', '.join(attributes['allowed_units'])}",
                f"directionality: {attributes['directionality']}",
                f"confusable_with: {', '.join(attributes['confusable_with']) or '—'}",
            ]
            path = entity.source.file if entity.source else None
            return Chunk(node, self._spec_path(path), "\n".join(body), "label definition")

        if entity is not None and entity.kind == KIND_EXAMPLE:
            attributes = entity.attributes
            lines = [
                f"[{attributes['verdict']}/{attributes['language']}/{attributes['unit']}] {attributes['text']}"
            ]
            if self.with_rationale:
                lines.append(f"  rationale: {attributes['rationale']}")
            path = entity.source.file if entity.source else None
            return Chunk(node, self._spec_path(path), "\n".join(lines), "labelled example")

        try:
            ref = parse_ref(node)
        except RefSyntaxError:
            return None
        if ref.kind == KIND_ONTOLOGY:
            return self._render_ontology(ref.locator)
        if not ref.is_path:
            return None
        path = self.repo / ref.locator
        if not path.is_file():
            return None
        text = _read(path)
        excerpt = _excerpt_around(text, ref.anchor, is_heading=ref.kind == KIND_DOC)
        if not excerpt.strip():
            return None
        reason = {KIND_DOC: "specified_by", KIND_CODE: "implements", KIND_TEST: "tested_by", KIND_DATA: "evidenced_by"}.get(
            ref.kind, "graph neighbour"
        )
        return Chunk(node, ref.locator, excerpt, reason)

    @staticmethod
    def _spec_path(path: str | None) -> str | None:
        return None if path is None else f"experiments/semantic-spine/{path}"

    def _render_ontology(self, version: str) -> Chunk | None:
        relative = f"data/ontology/{version}.json"
        path = self.repo / relative
        if not path.is_file():
            return None
        payload = json.loads(_read(path))
        head = {k: v for k, v in payload.items() if k != "labels"}
        head["labels"] = [label["id"] for label in payload.get("labels", [])]
        body = json.dumps(head, ensure_ascii=False, indent=2)
        return Chunk(f"ontology:{version}", relative, body, "materialized_in")

    def _noise_chunks(self) -> list[Chunk]:
        """Абляция: подмешать заведомо нерелевантные документы в тот же бюджет."""

        picked = [
            p
            for p in repo_text_files(self.repo)
            if (p.suffix == ".md" and "deploy" in str(p).lower())
            or p.name in ("landscape-2026-08.md",)
        ]
        return [
            Chunk(str(p), str(p.relative_to(self.repo)), _read(p), "injected noise")
            for p in picked
        ]

    def select(self, task: TaskSpec, budget: ContextBudget) -> ContextBundle:
        order = SPINE_RELATION_ORDER
        nodes = self.graph.expand(task.seeds, order, self.MAX_NODES, typed=self.typed)
        chunks = [chunk for chunk in (self._render_node(node) for node in nodes) if chunk is not None]
        if self.noise:
            noise = self._noise_chunks()
            chunks = noise[:1] + chunks + noise[1:]
        return _fill(self._bundle(task), budget, chunks, self.fill)


class SpineNoRationaleSelector(SpineSelector):
    name = "semantic-spine/-rationale"
    with_rationale = False


class SpineUntypedSelector(SpineSelector):
    name = "semantic-spine/-typed-edges"
    typed = False


class SpineNoisySelector(SpineSelector):
    name = "semantic-spine/+irrelevant-docs"
    noise = True


class OracleSelector(Selector):
    """Верхняя граница: ровно те файлы, которые задача объявила нужными."""

    name = "oracle"

    def select(self, task: TaskSpec, budget: ContextBudget) -> ContextBundle:
        chunks = []
        for relative in task.oracle_files:
            path = self.repo / relative
            if path.is_file():
                chunks.append(Chunk(relative, relative, _read(path), "oracle file list"))
        return _fill(self._bundle(task), budget, chunks, self.fill)


class OracleSectionsSelector(Selector):
    """Верхняя граница на уровне якорей: знает идеальные места, но не граф.

    Это честный потолок для сравнения. `oracle` (файлы целиком) проигрывает
    из-за гранулярности, а не из-за незнания — обгонять его неинтересно.
    Обгонять или догонять oracle-sections уже содержательно.
    """

    name = "oracle-sections"

    def select(self, task: TaskSpec, budget: ContextBudget) -> ContextBundle:
        chunks: list[Chunk] = []
        for raw in task.oracle_targets:
            target = parse_target(raw)
            try:
                location = locate(self.repo, target)
            except TargetUnresolvable:
                continue
            lines = _read(self.repo / target.path).split("\n")
            start = max(0, location.line_no - 1 - 4)
            body = "\n".join(lines[start : start + MAX_EXCERPT_LINES])
            chunks.append(Chunk(raw, target.path, body, "oracle anchor"))
        return _fill(self._bundle(task), budget, chunks, self.fill)


class RawPlusOracleSelector(Selector):
    """Контроль, отделяющий «не нашёл файл» от «нашёл, но не понял»."""

    name = "raw+oracle-file-list"

    def select(self, task: TaskSpec, budget: ContextBudget) -> ContextBundle:
        oracle = set(task.oracle_files)
        first = [
            Chunk(relative, relative, _read(self.repo / relative), "oracle file list")
            for relative in task.oracle_files
            if (self.repo / relative).is_file()
        ]
        rest = [
            Chunk(str(p), str(p.relative_to(self.repo)), _read(p), "repo order")
            for p in repo_text_files(self.repo)
            if str(p.relative_to(self.repo)) not in oracle
        ]
        return _fill(self._bundle(task), budget, first + rest, self.fill)


STRATEGIES: dict[str, type[Selector]] = {
    cls.name: cls
    for cls in (
        RawSelector,
        DocsSelector,
        LexicalSelector,
        Bm25Selector,
        SymbolGraphSelector,
        SpineSelector,
        SpineNoRationaleSelector,
        SpineUntypedSelector,
        SpineNoisySelector,
        RawPlusOracleSelector,
        OracleSelector,
        OracleSectionsSelector,
    )
}


def build_selector(name: str, repo: Path, spec_dir: Path, fill: str = FILL_PREFIX) -> Selector:
    if name not in STRATEGIES:
        known = ", ".join(sorted(STRATEGIES))
        raise KeyError(f"unknown strategy {name!r}; known: {known}")
    return STRATEGIES[name](repo, compile_spec_dir(spec_dir), fill)
