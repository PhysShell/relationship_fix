# naturalness-ab-v0-flagged — blinded human A/B по 13 flagged items

Что решается: какие minimal edits из [candidates.json](candidates.json) войдут в `annotation-pilot-v0.1` (и в dogfood-набор для dg-*). Откуда взялись items и кандидаты: [dialogue-naturalness-gate](../../../../docs/research/dialogue-naturalness-gate.md) §7–8. Оракул — люди; кандидаты модели — только вход.

## Оценщику

Вам выдан **только** ваш файл `packets/rater-N.json`. В нём пары коротких переписок: слева и справа два варианта одного и того же обмена между A и B. Внутри пары варианты отличаются одной-двумя репликами.

По каждой паре ответьте на два независимых вопроса:

1. `more_natural` — **Какой из двух вариантов больше похож на реальную переписку пары?** `left` / `right` / `no_difference`.
2. `meaning_shift` — **Отличаются ли варианты по смыслу или по накалу сказанного?** `same` / `slight` / `substantial`.

Второй вопрос не про «какой лучше», а про «то же ли самое сказано и с той же ли силой». Вариант может быть естественнее и при этом говорить другое — это важно отметить.

Не ищите категории и не гадайте, какой вариант «исходный»: этого в задаче нет. Отвечайте по ощущению читателя реальной переписки. Идите в порядке файла; до сдачи можно править свои ответы, после сдачи — нет. Не обсуждайте пары с другими оценщиками.

Формат ответа — одна строка JSON на пару, файл `responses/rater-N.jsonl`:

```json
{"schema_version":"rf.naturalness-ab-response.v1","pair_id":"pair-3f9a2c","rater_id":"rater-1","more_natural":"left","meaning_shift":"same"}
{"schema_version":"rf.naturalness-ab-response.v1","pair_id":"pair-b04e11","rater_id":"rater-1","more_natural":"no_difference","meaning_shift":"slight","note":"правый чуть резче"}
```

`note` необязателен. На каждую пару из вашего файла — ровно одна строка.

Кто может быть оценщиком: не автор items, не разметчик будущего pilot v0.1, свободно читает по-русски и по-английски (две пары на английском).

## Фасилитатору

```
uv run python -m metrics.naturalness_ab build --ab-dir ../../data/pilot/naturalness-ab/v0-flagged   # пакеты (до выдачи; --force только до выдачи)
uv run python -m metrics.naturalness_ab score --ab-dir ../../data/pilot/naturalness-ab/v0-flagged   # ab-result.json + ab-result.md
```

- `candidates.json` и `packet-map/` — facilitator-only: там item ids, флаги, edit constraints и сторона оригинала. Оценщик их не видит.
- Пакеты детерминированы от per-rater seed в `ab-manifest.json`: у каждого оценщика свой порядок пар и своя сторона оригинала (position bias не коррелирован между оценщиками). `packets/checksums.json` фиксирует выданные байты.
- Правило рекомендации (`ab-manifest.json` → `acceptance_rule`): любой `substantial` — кандидат отклоняется; иначе кандидат `eligible`, если его предпочли строго больше оценщиков, чем оригинал; ничья — остаётся оригинал. **Рекомендация — не решение**: accept/reject делается вручную (порядок работ, шаг 6) и записывается в `authoring` новой версии item (`accepted_via: blinded_ab`, `origin: llm_assisted`, `parent_item_version` → v0).
- Для pn-10 (natural-страта) правило жёстче, чем рекомендация: принимается только чисто лексическая замена; если Q2 даёт хотя бы `slight` у большинства — остаётся оригинал.
- Принятые правки pc-*/pn-* уходят в `annotation-pilot-v0.1` (новый пакет, новый hash, regenerated presentation); принятые правки dg-* — в `data/pilot/v0/form/dogfood-v6-items.yaml` и `src/annotation-web/src/Catalog.hs` (как это делалось для dg-04), с обновлением тестов, которые цитируют точные span'ы.
- Отклонённые кандидаты вместе с причиной сохраняются: это негативные примеры для критика следующего корпуса.
