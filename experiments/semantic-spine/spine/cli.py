"""CLI: python -m spine <command>.

Команды детерминированы и не трогают ничего за пределами
experiments/semantic-spine/generated/. Trusted state (data/, src/) — read-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compiler import (
    ONTOLOGY_VERSION,
    CompileError,
    compile_spec_dir,
    dump_json,
    emit_fixtures,
    emit_graph,
    emit_ontology,
)
from .graph import Graph
from .verifier import Verifier, verify_spec_dir

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
SPEC_DIR = HERE / "spec"
GENERATED = HERE / "generated"


def cmd_compile(args: argparse.Namespace) -> int:
    compilation = compile_spec_dir(SPEC_DIR)
    GENERATED.mkdir(parents=True, exist_ok=True)
    written = {
        "ontology.json": dump_json(emit_ontology(compilation, ONTOLOGY_VERSION)),
        "graph.json": dump_json(emit_graph(compilation)),
        "fixtures.json": dump_json(emit_fixtures(compilation)),
    }
    changed = []
    for name, content in written.items():
        path = GENERATED / name
        previous = path.read_text(encoding="utf-8") if path.is_file() else None
        if previous != content:
            changed.append(name)
        if not args.check:
            path.write_text(content, encoding="utf-8")

    if args.check and changed:
        print("generated artifacts are stale: " + ", ".join(sorted(changed)), file=sys.stderr)
        return 1

    print(f"labels: {len(compilation.labels)}  entities: {len(compilation.entities)}  edges: {len(compilation.edges)}")
    print(f"spec_digest: {compilation.spec_digest}")
    print("written: " + ", ".join(sorted(written)) if not args.check else "up to date")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    findings = verify_spec_dir(REPO, SPEC_DIR)
    if not findings:
        print("OK: no findings")
        return 0
    for finding in findings:
        print(str(finding), file=sys.stderr)
    print(f"\n{len(findings)} finding(s)", file=sys.stderr)
    return 1


def cmd_equivalence(args: argparse.Namespace) -> int:
    """compile(spec) против production-онтологии. Пока spec — не source of truth."""

    compilation = compile_spec_dir(SPEC_DIR)
    produced = {label["id"]: label for label in emit_ontology(compilation, ONTOLOGY_VERSION)["labels"]}
    reference_path = REPO / "data/ontology" / f"{ONTOLOGY_VERSION}.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    expected = {label["id"]: label for label in reference["labels"] if label["id"] in produced}

    missing = sorted(set(produced) - set(expected))
    if missing:
        print(f"spec declares labels absent from {ONTOLOGY_VERSION}: {missing}", file=sys.stderr)
        return 1
    if produced != expected:
        for label_id in sorted(produced):
            for field, value in produced[label_id].items():
                if expected[label_id].get(field) != value:
                    print(f"{label_id}.{field} differs from {ONTOLOGY_VERSION}", file=sys.stderr)
        return 1
    print(f"OK: compile(spec) == {ONTOLOGY_VERSION} subset for {len(produced)} labels")
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    compilation = compile_spec_dir(SPEC_DIR)
    graph = Graph(compilation.entities, compilation.edges)
    by_relation: dict[str, int] = {}
    for edge in compilation.edges:
        by_relation[edge.relation] = by_relation.get(edge.relation, 0) + 1
    print(f"nodes: {len(list(graph.nodes()))}")
    for relation in sorted(by_relation):
        print(f"  {relation}: {by_relation[relation]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spine", description="semantic spine research harness")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_parser = sub.add_parser("compile", help="spec/*.md -> generated/*.json")
    compile_parser.add_argument("--check", action="store_true", help="fail if generated artifacts are stale")
    compile_parser.set_defaults(func=cmd_compile)

    sub.add_parser("verify", help="fail-closed invariants against the repository").set_defaults(func=cmd_verify)
    sub.add_parser("equivalence", help="compile(spec) == production ontology subset").set_defaults(
        func=cmd_equivalence
    )
    sub.add_parser("graph", help="edge counts per relation").set_defaults(func=cmd_graph)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except CompileError as exc:
        print(f"[{exc.check}] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
