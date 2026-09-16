# B.REPAIR_ATTEMPT

```rf-label
id: B.REPAIR_ATTEMPT
canonical_name: "Repair attempt"
plain_language_name_en: "Attempt to de-escalate / repair"
plain_language_name_ru: "Попытка снизить накал / починить контакт"
allowed_units:
  - utterance
  - turn
directionality: interaction_directed
evidence_required: true
source_frameworks:
  - "Gottman/Driver (repair attempts)"
confusable_with:
  - B.VALIDATION
status: draft
```

## Operational definition

Действие, направленное на прекращение негативной петли: извинение, принятие части ответственности, юмор-разрядка, явное предложение перезапустить разговор. Успешность repair — свойство ПЕРЕХОДА (T.*), не этого label: здесь кодируется только попытка.

## Inclusion

- извинение или принятие части ответственности
- явное предложение остановиться/начать заново
- разряжающий юмор, адресованный напряжению (не партнёру)

## Exclusion

- «извини, но…» с немедленной контратакой
- уступка под давлением без признания ('ладно, как скажешь')

## Examples

```rf-example
id: repair-attempt-pos-ru-01
language: ru
unit: utterance
verdict: positive
text: "Прости, я правда затупил. Давай сначала?"
rationale: "извинение + предложение перезапуска"
```

```rf-example
id: repair-attempt-neg-ru-01
language: ru
unit: utterance
verdict: negative
text: "Извини конечно, но это ты всё начала."
rationale: "форма извинения, содержание — контратака"
```

```rf-example
id: repair-attempt-pos-en-01
language: en
unit: utterance
verdict: positive
text: "I'm sorry, that came out wrong — let me try again."
rationale: "apology + restart offer"
```

```rf-example
id: repair-attempt-neg-en-01
language: en
unit: utterance
verdict: negative
text: "Fine. Whatever you say."
rationale: "capitulation/withdrawal marker, not repair"
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
note: "keyword-стаб покрывает прости/извини/sorry"
```

```rf-edge
relation: specified_by
to: "doc:docs/item-authoring-v0.1.md#Главное правило"
note: "item проверяет construct, а не формулировку — критично для confusable-пары"
```

```rf-edge
relation: evidenced_by
to: "data:data/pilot/v0.1/items.jsonl"
sha256: c100db894cef93cdc7b9dd69860dc805e1acdeabf7b8a58fd6dd9a651d8271d9
note: "40 items пилота v0.1; хэш ловит подмену evidence после заморозки"
```
