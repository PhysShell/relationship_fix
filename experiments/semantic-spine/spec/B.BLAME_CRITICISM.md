# B.BLAME_CRITICISM

```rf-label
id: B.BLAME_CRITICISM
canonical_name: "Blame / criticism"
plain_language_name_en: "Blaming or criticizing the partner"
plain_language_name_ru: "Обвинение или критика партнёра"
allowed_units:
  - utterance
  - turn
directionality: other_directed
evidence_required: true
source_frameworks:
  - "CIRS (blame)"
  - "SPAFF (criticism)"
confusable_with:
  - B.PRESSURE_FOR_CHANGE
status: draft
```

## Operational definition

Высказывание приписывает партнёру вину или негативно характеризует его личность/паттерн поведения в целом (генерализация), а не описывает конкретный эпизод и его эффект. Маркеры: генерализующие кванторы (всегда/никогда), оценка личности вместо поведения, сарказм с враждебной окраской.

## Inclusion

- генерализация поведения партнёра (всегда/никогда/опять ты)
- негативная характеристика личности, а не конкретного действия
- приписывание вины за состояние/событие

## Exclusion

- жалоба на конкретный эпизод без генерализации (это может быть B.PRESSURE_FOR_CHANGE или ничего)
- игровое оскорбление с явными маркерами юмора/привязанности в контексте пары
- самокритика

## Examples

```rf-example
id: blame-criticism-pos-ru-01
language: ru
unit: utterance
verdict: positive
text: "Ты всегда обо всём забываешь."
rationale: "генерализующий квантор + приписывание вины"
```

```rf-example
id: blame-criticism-neg-ru-01
language: ru
unit: utterance
verdict: negative
text: "ну ты дебил 😂❤️"
rationale: "формально оскорбление, но маркеры юмора и привязанности; в паре с историей playful insults это не критика — канонический confusable-случай"
```

```rf-example
id: blame-criticism-pos-en-01
language: en
unit: utterance
verdict: positive
text: "You never listen to me."
rationale: "generalizing quantifier targeting the partner"
```

```rf-example
id: blame-criticism-neg-en-01
language: en
unit: utterance
verdict: negative
text: "I hate that we missed the bus today."
rationale: "frustration about an event, not an attribution of blame to the partner"
```

```rf-example
id: blame-criticism-amb-ru-01
language: ru
unit: utterance
verdict: ambiguous
text: "Опять ты со своими шуточками…"
rationale: "может быть и упрёком, и игрой — решает контекст и просодические маркеры (эмодзи, история пары)"
```

## Links

```rf-edge
relation: materialized_in
to: "ontology:behavior-v0.1"
note: "сегодня label живёт здесь; spec — эксперимент, не source of truth"
```

```rf-edge
relation: evidenced_by
to: "data:data/pilot/v0.1/pilot-manifest.json"
sha256: e5d5754ca8ef48feb6b0b453fc45c3548dafe322dc5465160840f8e2efb20222
note: "манифест пилота объявляет этот label активным и пинит хэш онтологии"
```

```rf-edge
relation: specified_by
to: "doc:docs/annotation-protocol-v0.md#2. Единицы, цели и контекст"
note: "единица и контекстное окно фиксированы протоколом, не автором label'а"
```

```rf-edge
relation: specified_by
to: "doc:docs/annotation-protocol-v0.md#3. Решения разметчика"
note: "assigned/none_observed/abstained и требование evidence span"
```

```rf-edge
relation: implements
to: "code:src/annotation-web/src/Domain.hs#labelCode"
note: "инструмент разметки знает этот label как закрытый конструктор"
```

```rf-edge
relation: implements
to: "code:src/RelationshipFix.Evaluation/Ontology/OntologyValidator.cs#Validate"
note: "структурные инварианты label'а проверяются здесь"
```

```rf-edge
relation: tested_by
to: "test:src/annotation-web/test/PilotSpec.hs#activeLabels"
note: "активный набор пилота v0.1 закреплён тестом"
```

```rf-edge
relation: implements
to: "code:src/RelationshipFix.Evaluation/Slice/RuleStubAnnotator.cs#RuleStubAnnotator"
note: "keyword-стаб покрывает всегда/никогда/always/never"
```

```rf-edge
relation: tested_by
to: "test:tests/RelationshipFix.DataContracts.Tests/GoldenContractTests.cs#Golden_fixture_matches_canonical_serialization"
note: "замороженные байты wire-контракта используют именно этот label"
```

```rf-edge
relation: evidenced_by
to: "data:data/pilot/v0.1/items.jsonl"
sha256: c100db894cef93cdc7b9dd69860dc805e1acdeabf7b8a58fd6dd9a651d8271d9
note: "40 items пилота v0.1; хэш ловит подмену evidence после заморозки"
```
