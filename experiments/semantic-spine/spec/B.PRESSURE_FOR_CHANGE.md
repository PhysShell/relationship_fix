# B.PRESSURE_FOR_CHANGE

```rf-label
id: B.PRESSURE_FOR_CHANGE
canonical_name: "Pressure for change"
plain_language_name_en: "Pressuring the partner to change"
plain_language_name_ru: "Давление с требованием измениться"
allowed_units:
  - utterance
  - turn
directionality: other_directed
evidence_required: true
source_frameworks:
  - "CIRS (pressure for change)"
confusable_with:
  - B.BLAME_CRITICISM
status: draft
```

## Operational definition

Высказывание требует, настаивает или повторно добивается изменения поведения партнёра (просьба с нажимом, ультиматум, повторение требования), без негативной характеристики личности.

## Inclusion

- явное требование/настаивание на изменении поведения
- повторение просьбы с эскалацией нажима
- условия/ультиматумы

## Exclusion

- однократная нейтральная просьба без нажима
- критика личности без требования (это B.BLAME_CRITICISM)

## Examples

```rf-example
id: pressure-for-change-pos-ru-01
language: ru
unit: utterance
verdict: positive
text: "Сколько можно повторять — убери за собой, я серьёзно."
rationale: "повторное требование с нажимом"
```

```rf-example
id: pressure-for-change-neg-ru-01
language: ru
unit: utterance
verdict: negative
text: "Можешь завтра забрать посылку?"
rationale: "нейтральная разовая просьба"
```

```rf-example
id: pressure-for-change-pos-en-01
language: en
unit: utterance
verdict: positive
text: "I need you to actually start calling when you are late. Every time."
rationale: "insistent demand for behavior change"
```

```rf-example
id: pressure-for-change-neg-en-01
language: en
unit: utterance
verdict: negative
text: "Could you grab milk on the way home?"
rationale: "ordinary request, no pressure"
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
relation: specified_by
to: "doc:docs/research/dialogue-naturalness-gate.md#1.3 Почему это не косметика"
note: "EN-пример этого label'а назван источником терапевтического регистра корпуса"
```

```rf-edge
relation: evidenced_by
to: "data:data/pilot/v0.1/items.jsonl"
sha256: c100db894cef93cdc7b9dd69860dc805e1acdeabf7b8a58fd6dd9a651d8271d9
note: "40 items пилота v0.1; хэш ловит подмену evidence после заморозки"
```
