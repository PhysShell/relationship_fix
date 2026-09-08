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

Кто может быть оценщиком: не автор items и не автор кандидатов, не veto-reviewer, не аудитор слепого аудита, не разметчик будущего pilot v0.1; свободно читает по-русски и по-английски (четыре пары на английском). Роли разделены жёстко: при нехватке людей уменьшается число оценщиков, роли не смешиваются.

## Veto-review до выдачи (фасилитатор)

Перед выдачей пакетов кандидаты проходят **veto-review, а не выбор победителя**. Вопрос «какой из двух мне больше нравится?» здесь запрещён: так вы отберёте варианты своим вкусом до слепых оценщиков. Единственный вопрос: **нарушает ли кандидат MUST / MUST NOT** (`candidates.json` → `veto_checklist`, V1–V10):

- construct сохранён; направленность сохранена;
- не появилось новое действие (извинение, объяснение, обобщение, новый факт) и не исчезло старое;
- интенсивность в пределах ступени; род и роль говорящих те же, неустановленный род не введён;
- adjacency не ухудшилась; нет текстов примеров онтологии и психологической лексики; для pn-* правка чисто лексическая; evidence остаётся точной подстрокой.

Кандидат, не прошедший чек-лист, **не исчезает**: он переносится из `candidates` в `vetoed` того же item с `candidate_id`, текстом, `checklist` (пункты) и `reason`. Замена, если она нужна, добавляется как новый кандидат с новым id под теми же инвариантами. Четыре `rejected` — negative controls протокола редактирования, они не переписываются и в A/B не идут.

```
uv run python -m metrics.naturalness_ab check --ab-dir ../../data/pilot/naturalness-ab/v0-flagged
```

`check` сверяет оригиналы pc-*/pn-* с `items.jsonl` (sha256 запинен в `ab-manifest.json` → `sources`), требует у каждого кандидата `checker`-заметку, у каждого vetoed — причину и пункт чек-листа, и не даёт одному id жить в двух списках. `build` отказывает, пока `check` не чист, поэтому из записи всегда видно: A/B сравнивал только admissible candidates, а не весь модельный выхлоп. Оригиналы dg-* `check` сверить не может (источник — YAML), это отмечается в выводе как note.

## Как выдать человеку, который не знает, что такое GitHub

Пакет JSON человеку не показывается. Из него делается один .xlsx на человека (лист «Инструкция» простыми словами + лист «Оценка» с выпадающими списками; жёлтые ячейки — единственное, что заполняется), а возвращённый .xlsx превращается обратно в canonical JSONL:

```
uv run --group human-interface python -m metrics.xlsx_interface render  --kind ab --dir ../../data/pilot/naturalness-ab/v0-flagged
uv run --group human-interface python -m metrics.xlsx_interface collect --kind ab --dir ../../data/pilot/naturalness-ab/v0-flagged --person rater-1 --returned ~/Downloads/rater-1.xlsx
```

- `xlsx/rater-N.xlsx` — derived artifact; source of truth — `packets/rater-N.json`. В книге спрятаны sha256 пакета, схема и opaque ids; item ids, флаги и сторона оригинала туда не попадают, их нет и в пакете.
- Один файл = один человек. Файл, отправленный человеку, не перерисовывается: его sha256 записывается в issuance record; `--force` — только до выдачи.
- Инструкция человеку в трёх словах: «откройте файл, выберите ответы в жёлтых ячейках, сохраните и пришлите обратно».
- `collect` отказывает, если книга сделана из другого пакета, выдана другому человеку, если изменены заголовки или текст переписок, удалены или продублированы строки, значение не из списка, ответ пуст. Только после чистой проверки пишется `responses/rater-N.jsonl`; возвращённый файл копируется как получен в `responses/returned/` и получает sha256. Существующий JSONL не перезаписывается никогда; вторая версия ответов с другим sha256 не принимается.
- Дальше как раньше: `metrics.naturalness_ab score`.
- openpyxl разрешён только в этом слое (dependency group `human-interface` в `pyproject.toml`); core tooling его не видит.

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
- **Preregistered decision rule (2026-09-07, код не меняется):** любой `substantial` → ineligible; eligible при `candidate > original` среди направленных голосов; `no_difference` нейтрален; `slight` не блокирует. Пример: candidate 2, original 1, no_difference 2, substantial 0 → eligible.
- **Adjudication:** ineligible-кандидат **не может** быть принят. Eligible-кандидат **может** быть отклонён, но причина записывается и не может быть личным предпочтением естественности — для этого и существовали слепые оценщики. Числовой extra-threshold на adjudication не вводится.
- **Issuance record и --force:** после veto-review записываются sha256 `candidates.json`, число vetoed/admissible, issued_at и псевдоним ревьюера. С этого момента `--force` запрещён процедурой: любое расхождение выданного пакета с `packets/checksums.json` инвалидирует выдачу и требует новой; ответы на старую выдачу к новой не относятся. Это provenance/detection, не запрет кодом, и сейчас этого достаточно.
- **Generation 2:** auditor-only находки слепого аудита получают собственный каталог кандидатов рядом с этим, собственный veto-review и собственные пакеты; этот каталог (generation 1) не перевыдаётся. v0.1 собирается один раз после закрытия обеих генераций.
