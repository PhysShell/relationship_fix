# B.VALIDATION

```rf-label
id: B.VALIDATION
canonical_name: "Validation"
plain_language_name_en: "Acknowledging the partner's experience"
plain_language_name_ru: "Признание переживания партнёра"
allowed_units:
  - utterance
  - turn
directionality: other_directed
evidence_required: true
source_frameworks:
  - "ESConv (affirmation/reflection)"
  - "BOLT (reflection)"
confusable_with:
  - B.REPAIR_ATTEMPT
status: draft
```

## Operational definition

Высказывание явно признаёт переживание/точку зрения партнёра как понятную или значимую (не обязательно соглашаясь с выводами). Маркеры: называние эмоции партнёра, «понимаю/вижу/слышу», подтверждение права на реакцию.

## Inclusion

- явное признание эмоции или позиции партнёра
- перефразирование переживания партнёра без обесценивания

## Exclusion

- формальное «понятно» без содержания признания
- согласие с фактом без отклика на переживание
- сарказм («ну конечно, тебе виднее»)

## Examples

```rf-example
id: validation-pos-ru-01
language: ru
unit: utterance
verdict: positive
text: "Понимаю, звучит обидно, я бы тоже разозлилась."
rationale: "признание эмоции + нормализация"
```

```rf-example
id: validation-neg-ru-01
language: ru
unit: utterance
verdict: negative
text: "Понятно."
rationale: "формальный маркер без признания переживания"
```

```rf-example
id: validation-pos-en-01
language: en
unit: utterance
verdict: positive
text: "I get why that hurt — it makes sense you were upset."
rationale: "explicit acknowledgement of the partner's emotion"
```

```rf-example
id: validation-neg-en-01
language: en
unit: utterance
verdict: negative
text: "Ok noted."
rationale: "acknowledgement of information, not of experience"
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
note: "keyword-стаб покрывает понимаю/understand"
```

```rf-edge
relation: specified_by
to: "doc:docs/research/dialogue-naturalness-gate.md#1.3 Почему это не косметика"
note: "маркеры из operational_definition просочились в регистр stimulus-корпуса"
```

```rf-edge
relation: evidenced_by
to: "data:data/pilot/v0.1/items.jsonl"
sha256: c100db894cef93cdc7b9dd69860dc805e1acdeabf7b8a58fd6dd9a651d8271d9
note: "40 items пилота v0.1; хэш ловит подмену evidence после заморозки"
```
