# naturalness-ab-v0-flagged-donor — donor-grounded generation для 13 flagged items

Что это: вторая генерация кандидатов для тех же 13 items, что и [v0-flagged](../v0-flagged/README.md) (generation 1, LLM minimal edits). Отличие в методе: кандидат не «делается живее» с нуля, а строится на **скелете реального импровизированного диалога** из внешнего корпуса. Из донора берётся только структура взаимодействия (ходы, длины, маркеры, adjacency), текст не копируется. Это не generation 2 порядка работ: та зарезервирована для auditor-only находок слепого аудита.

Порядок, восстановимый из provenance каждого кандидата:

```
donor fragments (RESD, MIT) → interaction skeleton → target construct на скелет → candidate → V1–V10
```

## Что лежит

- [donor-report.md](donor-report.md) — какие корпуса проверены, лицензии по первичным источникам, tiers, кто отсеян и почему, цитаты использованных донорских реплик с идентификаторами, результат механической проверки на некопирование.
- `candidates.json` — 13 items, по одному admissible кандидату на item: `donors_considered` (3–7 фрагментов с id, текстом и причиной, включая контрпримеры), `skeleton`, `messages`, `inherited`, `changed`, `v1_v10`, `provenance`, `kind`, `facilitator_review`; у четырёх items первый кандидат лежит в `vetoed` с пунктами чек-листа и причиной; `review_log` — след review 2026-09-08.
- `ab-manifest.json` — чтобы `metrics.naturalness_ab check` работал без изменений кода. Пакеты **не собраны и не собираются**: слепой A/B на этой генерации не запускается (решение 2026-09-08: на этом этапе без людей); `build` на этом каталоге не запускать — он не различает `kind` и собрал бы пары и для replacement.

## Два вида кандидатов и два пути принятия

- `kind: revision` — факты и сюжет сохранены, изменён регистр или контекстная реплика (pc-06, pc-09, pc-12, pc-13, pc-16, pc-17, pn-10, dg-05, dg-06). При принятии — revision с `parent_item_version`; `accepted_via` по тому, как принято: `blinded_ab`, если был A/B, `facilitator` — если принят фасилитатором без A/B, с записанной причиной.
- `kind: replacement` — сюжет и факты новые (pc-02, pc-05, dg-04, dg-09). При сборке v0.1 это **новый original item** с явно унаследованным design intent (`origin: llm_assisted`, `accepted_via: facilitator`, `parent_item_version: null`); старый item получает retired status. Притворяться, что это revision, запрещено — lineage не должен врать.

Два решения 2026-09-08 (после review генерации):

1. **Replacement не идёт через preregistered A/B acceptance gate.** Тот gate сравнивает варианты одного и того же item; сравнение нового сюжета со старым измеряло бы предпочтение сюжета, а не правку. Путь replacement: donor → facilitator acceptance по V1–V10 против design intent → новый original в v0.1 → сигнал естественности только с pilot (`unnatural_example`).
2. **Для `kind: replacement` V3/V4 применяются к observable actions, которых требует design intent, а не к конкретным фактам и сюжету retired original.** Для revision V3/V4 по-прежнему против оригинала.

Форма (число сообщений и последовательность авторов) сохранена у всех кандидатов, чтобы `check` работал одинаково. Для revision это ещё и оставляет возможность A/B-пары с оригиналом, если люди когда-нибудь появятся; для replacement такой пары нет по решению 1.

## Review 2026-09-08 (фасилитатор, только V1–V10)

- **Вето → переписаны как d2:** pc-02-d1 (V1/V2: target стал совместным «давай сделаем», а не требованием A к B), pc-12-d1 (V7/V3/V5: «not after you're already there» противоречит контексту — B предупредил(а) до ухода; настойчивость ниже оригинала), pc-09-d1 (V4: потерян «Я помню, что это важно» — нужно короткое «я помню»), pc-05-d1 (V3/V5: «тебе и так тошно» приписывает несообщённое состояние, «ляпнул не подумав» добавляет объяснение).
- **Без вето:** pc-06-d1, pc-16-d1, pn-10-d1, dg-04-d1, dg-09-d1. Это не acceptance.
- **Без явного вердикта, проверить по V1–V10:** pc-13-d1, pc-17-d1, dg-05-d1, dg-06-d1.
- Что изменилось в d2: pc-02 — императив к B «Сделай второй комплект и оставь мне» + «чтобы это было в последний раз»; pc-05 — состояние теперь называет сам(а) A («от этой темы тошно»), B перефразирует и берёт ответственность без объяснения; pc-09 — «Я помню.» хвостом, без мета-«что это важно», без «не забыл» (род B); pc-12 — контраст «the day before, not the day of», который следует из сообщения B, и «every time, I mean it» на уровне оригинала.
- Спорные места, названные в самих d2: pc-02 «чтобы это было в последний раз» (нажим, не оценка); pc-05 «мне от этой темы тошно» (разговорное называние состояния, не отчёт в регистре оригинала); pc-12 хвост «every time, I mean it» ближе всего к SCRIPTED_DEMAND, но именно его вето потребовало вернуть.

## Verdicts 2026-09-08 (второй проход фасилитатора, после d2)

| Кандидат | Решение | Причина (фасилитатор) |
|---|---|---|
| pc-02-d2 | ACCEPT | требование адресовано B во втором лице, direction восстановлен; pressure-for-change без характеристики личности |
| pc-05-d2 | ACCEPT | A сам сообщает состояние, B его не выдумывает; validation + responsibility + apology — отдельные наблюдаемые действия; объяснение из d1 убрано |
| pc-09-d2 | ACCEPT | конкретный возврат сохранён, «Я помню» возвращает потерянный acknowledgement и не вводит род |
| pc-12-d2 | VETO V3/V4 (возможно V5) | «the day before» — новый temporal contract: original требует сообщать, когда планы меняются, а не за день до события |
| pc-13-d1 | ACCEPT | «that's rough / I'd have been fuming» — содержательное acknowledgement без apology/explanation; «fuming» сильнее «upset» — допустимая одна ступень V5 |
| pc-17-d1 | VETO V3 | новый факт «А я там час торчу»: в original нет ни часа ожидания, ни того, что A уже на месте |
| dg-05-d1 | ACCEPT | substantive validation, а не голое «понятно»; род B не вводится |
| dg-06-d1 | ACCEPT | пауза + конкретный возврат сохранены; шероховатость формы — naturalness-вопрос, не veto |
| pc-06-d1, pc-16-d1, pn-10-d1, dg-04-d1, dg-09-d1 | ACCEPT | переведены из `no_veto` первого прохода в явное facilitator acceptance (при согласии checker'а: замечаний по V1–V10 нет; у pn-10 — только лексика, V9) |
| pc-12-d3 | ACCEPT (проход 3) | восстановлен исходный behavioural contract — сообщать, когда планы меняются, без «за день»; настойчивость сохранена, фактов нет, direction тот же; парадоксальность сцены — свойство frozen original |
| pc-17-d2 | ACCEPT с оговоркой V7/V5 (проход 3) | факты ровно исходные, emotion-report исчез, род A не введён; «Ну нормально вообще?» слегка сдвигает обиду к возмущению и делает «Понимаю.» менее идеальным ответом — adjacency не сломана, интенсивность в пределах ступени; скорее будущий `unnatural_example`, чем veto |

Итог: **13/13 accepted, 0 pending**. Запись каждого решения — `facilitator_review` у кандидата (`outcome`, причина, `caveat` где есть, `at_build`), сводка — `review_log`, статус — `acceptance_status`. Carve-out для pn-10 сужен до формулировки фасилитатора (правило 6 authoring guide; `rule_basis` у pn-10-d1).

## Что не сделано

- Статус: 13/13 donor candidates accepted · 0 pending facilitator verdicts · **v0.1 not built** · human naturalness evidence: none · next gate: explicit v0.1 build/cutover. Принятие записано только здесь, корпус не изменён. Сборка v0.1 — отдельная работа с отдельным «го», не «собрать как очевидно»: четыре replacement, retirement, новые ids, lineage, dogfood/Catalog cutover — достаточно мест, где можно аккуратно соврать самому себе.
- Корпус, пакеты и generation 1 не тронуты. Кода нет.
- Сборка v0.1 (после 13/13): новые item ids для четырёх replacement (старые ids не переиспользуются — retired), `parent_item_version` для revision из `at_build` (content hash родителя посчитан из frozen v0 для pc-*; dg-* живут в dogfood yaml, не в v2-пакете — lineage там cutover work), `accepted_via: facilitator`, `revision_reason: naturalness`, `validate_items` как гейт, presentation перегенерировать.
- Cutover work (не сейчас): `build` должен пропускать `kind=replacement`, если A/B на donor-ревизиях когда-нибудь понадобится; представление retired status и связи «новый original ← retired item» в схеме item (в `rf.pilot-item.v2` такого поля нет).

## Provenance принятого кандидата (при сборке v0.1)

`authoring.origin` остаётся `llm_assisted`; способ пишется отдельно: `method: external_dialogue_seeded`, `source_kind`, `source_corpus`, `source_revision`, `source_ref` (точные `name` реплик), `source_license`, `source_text_copied: false`, `transformation: interaction_structure_only`. На pilot это даёт кросс-таб `unnatural_example` × способ авторинга (handcrafted v0 / minimal edit gen 1 / external_dialogue_seeded) — **exploratory diagnostic** на двух разметчиках, не тест причинного превосходства метода: items не рандомизированы по способу авторинга, а выбраны по флагам.

```
uv run python -m metrics.naturalness_ab check --ab-dir ../../data/pilot/naturalness-ab/v0-flagged-donor
```
