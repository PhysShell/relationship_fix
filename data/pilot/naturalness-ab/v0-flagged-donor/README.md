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

## Что не сделано

- Ничего не принято. Acceptance на этой генерации — решение фасилитатора с записанной причиной (для обоих kind), не A/B и не автоматика.
- Корпус, пакеты и generation 1 не тронуты. Кода нет.
- Cutover work (не сейчас): `build` должен пропускать `kind=replacement`, если A/B на donor-ревизиях когда-нибудь понадобится; представление retired status и связи «новый original ← retired item» в схеме item (в `rf.pilot-item.v2` такого поля нет).

## Provenance принятого кандидата (при сборке v0.1)

`authoring.origin` остаётся `llm_assisted`; способ пишется отдельно: `method: external_dialogue_seeded`, `source_kind`, `source_corpus`, `source_revision`, `source_ref` (точные `name` реплик), `source_license`, `source_text_copied: false`, `transformation: interaction_structure_only`. На pilot это даёт кросс-таб `unnatural_example` × способ авторинга (handcrafted v0 / minimal edit gen 1 / external_dialogue_seeded) — **exploratory diagnostic** на двух разметчиках, не тест причинного превосходства метода: items не рандомизированы по способу авторинга, а выбраны по флагам.

```
uv run python -m metrics.naturalness_ab check --ab-dir ../../data/pilot/naturalness-ab/v0-flagged-donor
```
