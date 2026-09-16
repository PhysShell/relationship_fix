"""Verifier против настоящего репозитория + drift tripwire по OntologyValidator.

Существующий OntologyValidator уже реализует часть этого набора инвариантов, и
переписывать его ради архитектурного фэншуя не нужно. .NET SDK в
исследовательском окружении нет, поэтому здесь охранная сигнализация, а НЕ
доказательство эквивалентности.

Что тест ловит: исчезновение известного сообщения и изменение числа
`issues.Add(` — то есть добавление или удаление проверки в C# без зеркала.

Чего тест НЕ ловит, и это важно не путать: если поменять СМЫСЛ существующей
проверки, сохранив её сообщение и общее число вызовов, тест останется зелёным.
Это drift cross-check, а не semantic parity. Для research harness этого
достаточно; выдавать сигнализацию за доказательство — нельзя.
"""

import unittest
from pathlib import Path

from spine.compiler import compile_spec_dir
from spine.refs import parse_ref
from spine.verifier import (
    DIRECTIONALITY_ENUM_FILE,
    UNIT_ENUM_FILE,
    Verifier,
    _read_enum_members,
    verify_spec_dir,
)

from ._harness import REPO_ROOT, SPEC_DIR

ONTOLOGY_VALIDATOR = "src/RelationshipFix.Evaluation/Ontology/OntologyValidator.cs"

# Маркер сообщения в OntologyValidator.Validate -> зеркальная проверка spine.
# Список закрыт: новая проверка в C# роняет test_no_unmirrored_dotnet_check.
DOTNET_CHECK_MIRROR = {
    "duplicate label id": "duplicate_stable_id",
    "allowed_units must be non-empty": "spec_compile",
    "operational_definition is required": "spec_compile",
    "not in allowed_units": "example_unit_not_allowed",
    "is not a working language (ru/en)": "language_coverage",
    "missing examples for language": "language_coverage",
    "needs at least one positive and one negative example": "missing_required_example",
    "confusable_with references unknown label": "dangling_reference",
}


class RealRepository(unittest.TestCase):
    def test_spec_verifies_clean_against_this_repository(self) -> None:
        findings = verify_spec_dir(REPO_ROOT, SPEC_DIR)
        self.assertEqual([str(f) for f in findings], [])

    def test_closed_sets_are_read_from_the_domain_not_copied(self) -> None:
        units = _read_enum_members(REPO_ROOT, UNIT_ENUM_FILE)
        directionalities = _read_enum_members(REPO_ROOT, DIRECTIONALITY_ENUM_FILE)
        self.assertEqual(units, {"utterance", "turn", "exchange", "episode"})
        self.assertEqual(
            directionalities, {"other_directed", "self_directed", "interaction_directed"}
        )

    def test_every_declared_unit_and_directionality_is_a_domain_member(self) -> None:
        compilation = compile_spec_dir(SPEC_DIR)
        units = _read_enum_members(REPO_ROOT, UNIT_ENUM_FILE)
        directionalities = _read_enum_members(REPO_ROOT, DIRECTIONALITY_ENUM_FILE)
        for label in compilation.labels:
            with self.subTest(label=label.attributes["id"]):
                self.assertTrue(set(label.attributes["allowed_units"]) <= units)
                self.assertIn(label.attributes["directionality"], directionalities)


class Resolution(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = Verifier(REPO_ROOT, SPEC_DIR)

    def test_resolves_real_targets(self) -> None:
        for raw in [
            "unit:utterance",
            "ontology:behavior-v0.1",
            "ontology:behavior-v0.2-candidate",
            "doc:docs/annotation-protocol-v0.md#3. Решения разметчика",
            "code:src/RelationshipFix.Evaluation/Ontology/OntologyValidator.cs#Validate",
            "test:src/annotation-web/test/PilotSpec.hs#activeLabels",
            "data:data/pilot/v0.1/items.jsonl",
        ]:
            with self.subTest(ref=raw):
                self.assertIsNone(self.verifier.resolve(parse_ref(raw)))

    def test_refuses_targets_that_are_not_there(self) -> None:
        for raw in [
            "unit:paragraph",
            "ontology:behavior-v9.9",
            "doc:docs/annotation-protocol-v0.md#a heading nobody wrote",
            "doc:docs/there-is-no-such-file.md",
            "code:src/RelationshipFix.Evaluation/Ontology/OntologyValidator.cs#NoSuchSymbol",
        ]:
            with self.subTest(ref=raw):
                self.assertIsNotNone(self.verifier.resolve(parse_ref(raw)))


class OntologyValidatorDriftTripwire(unittest.TestCase):
    """Сигнализация, а не переписывание: OntologyValidator остаётся на месте.

    Границы охвата описаны в docstring модуля. Тест ловит появление и
    исчезновение проверок, но не подмену их смысла.
    """

    def setUp(self) -> None:
        self.source = (REPO_ROOT / ONTOLOGY_VALIDATOR).read_text(encoding="utf-8")

    def test_every_known_dotnet_check_is_still_there(self) -> None:
        for marker in DOTNET_CHECK_MIRROR:
            with self.subTest(check=marker):
                self.assertIn(marker, self.source)

    def test_no_unmirrored_dotnet_check(self) -> None:
        validate = self.source[
            self.source.index("public static IReadOnlyList<string> Validate(") :
            self.source.index("/// <summary>Проверка аннотации")
        ]
        emitted = validate.count("issues.Add(")
        self.assertEqual(
            emitted,
            len(DOTNET_CHECK_MIRROR),
            "OntologyValidator.Validate emits a check with no mirror in the spine verifier; "
            "add it to DOTNET_CHECK_MIRROR and to spine/verifier.py. This tripwire counts "
            "checks and matches messages; it cannot see a check whose meaning changed.",
        )

    def test_mirrors_name_real_spine_checks(self) -> None:
        from .test_mutations import DECLARED_CHECKS

        for marker, check in DOTNET_CHECK_MIRROR.items():
            with self.subTest(check=marker):
                self.assertIn(check, DECLARED_CHECKS)


if __name__ == "__main__":
    unittest.main()
