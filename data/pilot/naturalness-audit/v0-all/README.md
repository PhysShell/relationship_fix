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

**auditor ≠ A/B rater ≠ pilot annotator — hard separation.** Единственное разрешённое исключение описано ниже как fallback, и оно записывается до выдачи, а не после. Аудитор, ставший оценщиком A/B, узнаёт сторону оригинала; оценщик, ставший аудитором, заранее видел альтернативы для 13 items; любой из них в pilot — нарушенный `has_not_seen_items`. Авторы кандидатов и veto-reviewer тоже не оценщики A/B. Если людей физически не хватает, уменьшается число оценщиков или откладывается этап; роли не смешиваются молча, а вынужденное отклонение записывается в ledger **до** выдачи, не объясняется постфактум.

**Единственный разрешённый fallback при нехватке людей (решение 2026-09-08).** Сначала A/B generation 1 на трёх оценщиках; затем один из них может аудировать **только complement из 33 items, которых в A/B не было**. Это записывается в `contamination-ledger.json` до выдачи аудит-пакета. Потеря evidence называется явно: клетка «critic flagged → human says fine» для 13 gen-1 items больше не независима и как blind-audit evidence не интерпретируется; клетка `auditor_only` на 33 unseen items остаётся чистой. Любой другой способ смешать роли — не деградация, а нарушение blindedness.

**Item-level contamination.** Exposure заражает человека для тех item ids, которые он видел, а не глобально: `seen via dogfood → contaminated only for those item_ids`. Все, кто проходил dogfood в annotation-web, включая фасилитатора, заражены для dg-04…dg-09; оценщик A/B gen 1 — для своих 13. В ledger это записывается как `exposures` (item ids + причина + дата); та же запись годится для любого частичного exposure.

**Поверхности.** XLSX (`metrics.xlsx_interface`) — текущая operational human surface для аудита и A/B; она остаётся и не считается временной из-за того, что позже появится веб. При cutover на v0.1 annotation-web становится тупым renderer/collector, привязанным к sha256 выданного пакета и токену: порядок, сторона оригинала и состав приходят из immutable packet, приложение само ничего не рандомизирует. Это нужно самому pilot, не только naturalness.

**Generation 2.** Если Pass A даёт auditor-only находки (человек флагует item, которого нет у critic-1), они не откладываются в v0.2: для них создаются кандидаты generation 2 в отдельном каталоге `naturalness-ab/`, с собственным veto-review, собственными пакетами и теми же или другими независимыми оценщиками; generation 1 при этом не перевыдаётся и не меняется. Gen-1 оценщики для gen 2 слепы по построению: наборы items не пересекаются. Auditor-only находка не означает «item надо менять»: если admissible edit без нарушения V1–V10 не получается, оригинал остаётся, причина записывается. v0.1 собирается один раз после закрытия обеих генераций.

**Lock.** `report` записывает sha256 ответов Pass A в момент запуска; lock — это первый закоммиченный `audit-result.json`, а не сам факт запуска. Расхождение выданного пакета с `packets/checksums.json` инвалидирует выдачу: --force после записи выдачи запрещён процедурой, а не кодом.

Кто открыл audit- или A/B-пакет, записывается **до выдачи** в [`data/pilot/contamination-ledger.json`](../../contamination-ledger.json) под псевдонимным ключом, без персональных данных. При cutover на v0.1 eligibility пакета получает критерий `did_not_participate_in_naturalness_audit_or_ab`, проверяемый по ledger (cutover work, здесь только правило).

Аудитор не должен быть автором items и не должен был видеть их раньше.

## Как выдать человеку, который не знает, что такое GitHub

Пакет JSON человеку не показывается. Из него делается один .xlsx на человека (лист «Инструкция» простыми словами + лист «Оценка» с выпадающими списками; жёлтые ячейки — единственное, что заполняется), а возвращённый .xlsx превращается обратно в canonical JSONL:

```
uv run --group human-interface python -m metrics.xlsx_interface render  --kind audit --dir ../../data/pilot/naturalness-audit/v0-all
uv run --group human-interface python -m metrics.xlsx_interface collect --kind audit --dir ../../data/pilot/naturalness-audit/v0-all --person auditor-1 --returned ~/Downloads/auditor-1.xlsx
```

- `xlsx/auditor-N.xlsx` — derived artifact; source of truth — `packets/auditor-N.json`. В книге спрятаны sha256 пакета, схема и opaque ids; canonical ids, strata и флаги critic-1 туда не попадают, их нет и в пакете.
- Один файл = один человек. Файл, отправленный человеку, не перерисовывается: его sha256 записывается в issuance record; `--force` — только до выдачи.
- Инструкция человеку в трёх словах: «откройте файл, выберите ответы в жёлтых ячейках, сохраните и пришлите обратно».
- `collect` отказывает, если книга сделана из другого пакета, выдана другому человеку, если изменены заголовки или текст переписок, удалены или продублированы строки, значение не из списка, «неприменимо» стоит не там, где положено. Только после чистой проверки пишется `responses/auditor-N.jsonl`; возвращённый файл копируется как получен в `responses/returned/` и получает sha256. Существующий JSONL не перезаписывается никогда; вторая версия ответов с другим sha256 не принимается.
- Дальше как раньше: `metrics.naturalness_audit report`.
- openpyxl разрешён только в этом слое (dependency group `human-interface` в `pyproject.toml`); core tooling его не видит.

## Фасилитатору

```
uv run python -m metrics.naturalness_audit build  --audit-dir ../../data/pilot/naturalness-audit/v0-all   # Pass A пакеты (--force только до выдачи)
uv run python -m metrics.naturalness_audit report --audit-dir ../../data/pilot/naturalness-audit/v0-all   # заморозка Pass A + Pass B report
```

- Источники запинены по sha256 в `audit-manifest.json`: `items.jsonl` (v0) и `dogfood-v6-items.yaml` через `sources/dogfood-v6-items.snapshot.json` (stdlib-only инструменты YAML не читают; snapshot — производная проекция, пересобирается при изменении YAML, на устаревшем snapshot'е `build` отказывает).
- Facilitator-only: `critic-1-triage.json` (флаги и severity первого критика по всем 46, включая «none»), `packet-map/`, `../../v0/strata.json`. Аудитор их не видит до Pass B.
- Пакеты стерильны по построению: в них только `audit_item_id`, `language`, `messages`; лишний ключ или canonical id — отказ сборки.
- Два пакета сгенерированы (auditor-1, auditor-2); если аудитор один, второй пакет просто не выдаётся.
