# naturalness-audit-v0-all — независимый слепой аудит 46 stimulus-items

Зачем: вывод «дефект рождается там, где конструкция stimulus обслуживает границу онтологии» (natural 1/20, challenge 8/20, dogfood 4/6; [gate](../../../../docs/research/dialogue-naturalness-gate.md) §1.2, §7) стоит на одном проходе одного критика, и этот критик — модель. Пока второй человек не пройдёт те же 46 items вслепую, это мнение, а не evidence.

Аудит идёт в два прохода. **Pass A** стерильный, **Pass B** диагностический, и открывается только после заморозки Pass A. Если сразу сказать аудитору «смотри, тут авторы копировали wording definition», он это найдёт: мозг для такого оптимизирован тысячелетиями.

## Pass A — аудитору

Вам выдан **только** ваш файл `packets/auditor-N.json`: 46 коротких фрагментов переписки между A и B, в вашем порядке, под непрозрачными id. Ничего другого вам не показывают, и это намеренно.

По каждому фрагменту три вопроса:

1. `natural` — **Звучит ли это как естественная переписка двух близких людей?** `yes` / `partly` / `no`.
2. `invisible_context` — **Требует ли ответ B существенного невидимого контекста между A и B, сцены, которой нет в переписке?** `yes` / `no`; если во фрагменте одно сообщение — `not_applicable`.
3. `other_problem` — **Есть ли другая наблюдаемая проблема формулировки?** Пустая строка, если нет; иначе коротко словами.

Не ищите категории, не гадайте, «что здесь проверяют», не додумывайте историю пары. Отвечайте как читатель реальной переписки. Идите в порядке файла; до сдачи можно править свои ответы, после сдачи — нет. Не обсуждайте фрагменты ни с кем до сдачи.

Формат — одна строка JSON на фрагмент, файл `responses/auditor-N.jsonl`:

```json
{"schema_version":"rf.naturalness-audit-response.v1","audit_item_id":"audit-3f9a2c","auditor_id":"auditor-1","natural":"partly","invisible_context":"yes","other_problem":""}
{"schema_version":"rf.naturalness-audit-response.v1","audit_item_id":"audit-b04e11","auditor_id":"auditor-1","natural":"yes","invisible_context":"not_applicable","other_problem":"","note":"необязательно"}
```

На каждый фрагмент из вашего файла — ровно одна строка.

## Pass B — после заморозки

1. Фасилитатор запускает `report`: ответы Pass A проверяются, их sha256 записываются в `audit-result.json`, ответы возвращаются в canonical пространство и сводятся против critic-1 по стратам. С этого момента Pass A не меняется.
2. Только теперь аудитору открываются strata, `critic-1-triage.json`, gate-документ, `candidates.json` A/B и definitions/examples онтологии, и задаётся вопрос Pass B: **почему именно эти items сломались, и согласуется ли это с гипотезой boundary construction pressure?**
3. Выводы Pass B пишутся в `pass-b/auditor-N.md` свободным текстом с датой. Они не правят ответы Pass A и не становятся gold.

`audit-result.md` — только counts: аудитор × critic-1 по стратам, invisible_context × adjacency-флаги critic-1, согласие между аудиторами. Это diagnostic association на ячейках размером с ладонь, не причинность и не значимость.

## Contamination accounting

**auditor ≠ A/B rater ≠ pilot annotator**, насколько позволяет число людей. Если людей мало, допустимо auditor = A/B rater, но **никогда** pilot annotator: аудитор видел все 46 items, оценщик A/B — 13 в двух версиях, и `has_not_seen_items` для них ложно по построению. Иначе eligibility criterion превращается в художественную литературу.

Кто открыл audit- или A/B-пакет, записывается **до выдачи** в [`data/pilot/contamination-ledger.json`](../../contamination-ledger.json) под псевдонимным ключом, без персональных данных. При cutover на v0.1 eligibility пакета получает критерий `did_not_participate_in_naturalness_audit_or_ab`, проверяемый по ledger (cutover work, здесь только правило).

Аудитор не должен быть автором items и не должен был видеть их раньше.

## Фасилитатору

```
uv run python -m metrics.naturalness_audit build  --audit-dir ../../data/pilot/naturalness-audit/v0-all   # Pass A пакеты (--force только до выдачи)
uv run python -m metrics.naturalness_audit report --audit-dir ../../data/pilot/naturalness-audit/v0-all   # заморозка Pass A + Pass B report
```

- Источники запинены по sha256 в `audit-manifest.json`: `items.jsonl` (v0) и `dogfood-v6-items.yaml` через `sources/dogfood-v6-items.snapshot.json` (stdlib-only инструменты YAML не читают; snapshot — производная проекция, пересобирается при изменении YAML, на устаревшем snapshot'е `build` отказывает).
- Facilitator-only: `critic-1-triage.json` (флаги и severity первого критика по всем 46, включая «none»), `packet-map/`, `../../v0/strata.json`. Аудитор их не видит до Pass B.
- Пакеты стерильны по построению: в них только `audit_item_id`, `language`, `messages`; лишний ключ или canonical id — отказ сборки.
- Два пакета сгенерированы (auditor-1, auditor-2); если аудитор один, второй пакет просто не выдаётся.
