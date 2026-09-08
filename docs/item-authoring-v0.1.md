# Правила авторинга stimulus-items (с annotation-pilot-v0.1)

Статус: действует для пакета `annotation-pilot-v0.1` и последующих. `annotation-pilot-v0` заморожен как исторический ([data/pilot/v0/README.md](../data/pilot/v0/README.md)) и этими правилами задним числом не переписывается.

Откуда взялись правила: [dialogue-naturalness-gate](research/dialogue-naturalness-gate.md). Диагноз там простой: чем сильнее автор старался сделать label бесспорным, тем чаще он протаскивал формулировку definition в реплику. Получался методологически чистый пример и мёртвый диалог. Правила ниже атакуют источник, а не симптом.

## Главное правило

> **Preserve the construct, not the canonical wording.** Examples and definitions are diagnostic descriptions, not lexical templates for stimulus generation.
>
> Сохраняйте construct, а не каноническую формулировку. Примеры и definitions онтологии — диагностические описания, а не фразовые шаблоны для генерации stimulus'ов.

Определение B.VALIDATION вправе перечислять «понимаю / вижу / слышу» — это описание того, *что* наблюдается. Реплика «да блин, я бы тоже взбесилась» несёт тот же construct без единого маркера из списка. Если item нельзя написать так, чтобы он звучал как сообщение живого человека и при этом нёс construct, это сигнал о definition, а не повод написать мёртвую реплику.

## Правила

1. **Construct, не формулировка.** Не копировать в реплику маркеры из operational_definition и тексты примеров. Проверка: закройте definition и перечитайте реплику — это сообщение человека партнёру или конспект definition?
2. **Никакого переиспользования текстов в обе стороны.** Тексты примеров онтологии не появляются в корпусе (правило commit `07b5106`); тексты корпуса не появляются в примерах онтологии, glossary annotation-web и form-spec. Дословное совпадение target-реплики с примером в глоссарии — это answer key, а не naturalness issue.
3. **Adjacency.** Каждое сообщение после первого читается как ответ на предыдущее. Проверка: «мог ли человек напечатать именно это, прочитав предыдущее сообщение?» Вводные ремарки-признания («Я опять забыл предупредить, что задержусь») и пересказ партнёру его же слов — не реплики, а сценические указания для читателя.
4. **Согласованность говорящих.** Грамматический род одного говорящего не меняется внутри item (урок dg-04); если род не установлен, он и не вводится. Факты (кто что сделал, когда) не плавают между сообщениями.
5. **Регистр.** Эталон регистра — natural-страта: короткие реплики, эмодзи, lowercase в EN, незавершённые мысли. Книжный синтаксис допустим только когда персонаж правдоподобно так пишет. Naturalness ≠ безграмотность: мат и опечатки не добавляются «для живости».
6. **Natural-страта не обогащается и не правится под label.** Она существует ради base rates; любая правка в ней — только лексическая и только по результату A/B. Единственный узкий carve-out (2026-09-08): при явно выбранном пути без pre-pilot human naturalness evidence facilitator MAY принять заранее flagged natural-stratum item только при `kind=revision`, только при V9 lexical-only change и с явной записью `accepted_via=facilitator`; это не human evidence и не расширяет правило на semantic/content revisions. Прецедент: pn-10-d1.
7. **Provenance обязателен.** Каждая версия item несёт блок `authoring` (`rf.pilot-item.v2`): `origin` описывает текст именно этой версии (`human` | `llm_assisted` | `unrecorded`), `revision_reason` (`naturalness` | `adjacency` | `grammar` | `other`), `accepted_via` (`original` | `carried_over` | `blinded_ab` | `facilitator`), `parent_item_version` (пакет, item, content-hash родителя). Принятый LLM-кандидат — `llm_assisted`, даже если его принял человек: нужна история происхождения, а не ярлык. Инварианты проверяет `metrics.validate_items`.
8. **Naturalness-triage до freeze.** Перед заморозкой пакета каждый item проходит rubric критика (gate §5). Flagged items либо переписываются автором до freeze (это `human`-origin с `revision_reason`), либо идут в blinded A/B, либо принимаются фасилитатором из donor-grounded генерации с записанной причиной (`accepted_via: facilitator`; gate §11, решения 2026-09-08). После freeze — только новая версия пакета.
9. **Design note — facilitator-only.** У challenge-item записывается, какую границу он проверяет (как `design_note` в dogfood), и разметчику это не показывается.
10. **Два регистра на одну границу.** Если boundary-item существует только в терапевтическом регистре, он проверяет узнавание формулы, а не construct. Для каждой confusable-пары в challenge-страте должен быть хотя бы один item в живом регистре.
11. **Replacement ≠ revision.** Если правка меняет сюжет или факты, это не revision, а **новый original item** с явно унаследованным design intent (`origin` по тексту версии, `accepted_via: facilitator`, `parent_item_version: null`); старый item получает retired status, притворяться revision запрещено — lineage не должен врать. Для replacement проверки «нет нового действия / нет потерянного действия» (V3/V4 чек-листа) идут против observable actions, которых требует design intent, а не против фактов и сюжета retired original. Replacement не идёт через A/B gate: тот сравнивает варианты одного item, а сравнение нового сюжета со старым измеряло бы предпочтение сюжета. Сигнал естественности replacement даёт только pilot.

## Чек-лист перед freeze пакета

- `metrics.validate_items` проходит (структура, manifest↔ontology, presentation без утечки canonical id и `authoring`).
- Ни один текст корпуса не совпадает с примером онтологии / glossary / form-spec, и наоборот.
- Rubric критика пройден по всем items; результат записан; flagged items либо исправлены, либо прошли A/B.
- Аудит рода говорящих пройден (ручной, как dg-04).
- В инструкции разметчика есть необязательный `feedback` (`unnatural_example` и др.), чтобы отчёт мог построить `unnatural_example` × disagreement / abstention / stratum.
- Eligibility заполнен до выдачи; после выдачи — никаких правок и reshuffle.
