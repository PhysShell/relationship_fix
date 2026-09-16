# Preregistration: анализ annotation-pilot-v0.1

Дата: 2026-09-16. Статус: **preregistration**. Зафиксировано **до просмотра любого ответа аннотатора**.

> **Заявление о состоянии знания на момент написания.** На момент фиксации этого документа ни один ответ аннотатора не прочитан, не экспортирован и не проинспектирован ни в каком виде. В репозитории под `data/pilot/v0.1/responses/` отслеживается **единственный файл — `README.md`** (описание формата слоя). Слоёв `annotator-1.jsonl` / `annotator-2.jsonl` не существует. `metrics.agreement` при их отсутствии завершается кодом 2 и отчёта не строит.

Этот документ **ничего не меняет** в: sealed pilot, ontology, items, instructions, presentation, Tally/form content, existing response data, порогах. Пороги здесь **цитируются** из [annotation-protocol-v0.md](../annotation-protocol-v0.md) §4, а не назначаются заново.

---

## 0. Provenance

| Артефакт | Значение |
|---|---|
| Pilot package | `annotation-pilot-v0.1`, sealed 2026-09-08 |
| `CHECKSUMS.sha256` (seal) | `c87fc7cec2f4e931acd9a8680f639c5a1b765b17b9c760e1bd15acefc7eb50a0` |
| `items.jsonl` | `c100db894cef93cdc7b9dd69860dc805e1acdeabf7b8a58fd6dd9a651d8271d9` |
| `pilot-manifest.json` | `e5d5754ca8ef48feb6b0b453fc45c3548dafe322dc5465160840f8e2efb20222` |
| `presentation/annotator-1.jsonl` | `3847d6572b8efac7fcdec73781122493d0e604906e8bd71ae754c0a8faaca615` |
| `presentation/annotator-2.jsonl` | `221a8a7f4af062e2866009d57d56e0df8ef3d9e0c84d9bc4b01c2085f8aeae2d` |
| Ontology | `behavior-v0.1`, `3c067acc1685c42f6f26b6581c10e56bb806ab8137a517dca0d77f01ac5a67c3` |
| Instructions (binding at issuance) | `docs/pilot-v0.1-instructions.md`, `4916d178a5e582346169e0d86d1e988b0199cc796d6fea852156254cef8c4cbc` |
| Analysis code | `research/python/metrics/agreement.py`, `4c6c34266adbcab15260c7fedcfd80de665e4aacd9ee691bc3fcf052700f4d15` |
| Parent commit | `875aed667d1c4245bac1735717bb30698ece7c37` |
| Prereg commit SHA | этот коммит — идентификатор указан в его сообщении; последующие правки **не** переписывают документ на месте, а добавляют датированный `AMENDMENT` (§8) |

Проверка seal — из каталога пакета: `sha256sum -c CHECKSUMS.sha256` (12 файлов). Повторно выполнена после изменений в `agreement.py`: 12/12 OK. `agreement.py` в seal не входит и входить не должен — это аналитический потребитель, не содержимое пакета.

Активные labels (из sealed manifest): `B.BLAME_CRITICISM`, `B.PRESSURE_FOR_CHANGE`, `B.VALIDATION`, `B.REPAIR_ATTEMPT`, `B.AVOIDANCE_TOPIC_SHIFT`.
Deferred: `B.WITHDRAWAL` → `not_applicable` (`deferred_until_exchange_segmentation`; «не искали», не «не нашли»).
Состав: 40 items, 20 challenge + 20 natural, 30 ru + 10 en. Unit: `utterance` (решение о `target_message_id` внутри предъявленного обмена из 2–4 сообщений).

---

## 1. Анализы

### 1.1–1.7 Primary

Все семь **уже реализованы** в `metrics.agreement` и здесь фиксируются как primary, а не добавляются.

| # | Анализ | Разрез | Реализация |
|---|---|---|---|
| 1.1 | Krippendorff α, бинарно, per label | label × {all, challenge, natural} | `label_stats` |
| 1.2 | Bootstrap CI 95% для α (resample pairable units, 2000 итераций, seed 42) | то же | `bootstrap_ci` |
| 1.3 | Positive agreement (Dice: `2·both/(pos_a+pos_b)`) | то же | `label_stats` |
| 1.4 | Abstention rate + reasons, по слоям | per annotator | `abstention_reasons` |
| 1.5 | Confusion: `label↔label`, `label↔NONE_OBSERVED`, decision matrix | {all, challenge, natural} | `confusion_analysis` |
| 1.6 | Стратификация challenge vs natural | сквозная по 1.1–1.5 | `run` |
| 1.7 | **Observed sample prevalence / estimability** | label × stratum | `label_stats` |

> **1.7 — что это НЕ.** Это **observed sample prevalence** внутри authored-набора из 40 items, где challenge-страта **сконструирована намеренно**. Это **не** prevalence поведения в реальных отношениях и не может ею быть: prevalence в challenge-страте есть артефакт дизайна ([corpus-strategy.md](corpus-strategy.md) §3). Назначение величины — одно: определить, какие labels вообще **оценимы** на этом объёме. Формулировки вида «в отношениях X% реплик содержат BLAME» из этих данных **запрещены**.

### 1.8–1.10 Exploratory-but-preregistered

Регистрируются здесь, чтобы не быть выданными за primary потом. **Ни один из них не является гейтом** и ни один не может отменить или переопределить решение, принятое по 1.1–1.7.

**1.8 — Boundary-collapse diagnostic.** Зарегистрированные пары (константа `BOUNDARY_COLLAPSE_PAIRS` в коде, не только в прозе):

- `B.BLAME_CRITICISM ∪ B.PRESSURE_FOR_CHANGE`
- `B.VALIDATION ∪ B.REPAIR_ATTEMPT`

Считается: α объединённого решения («хоть один из двух присутствует») против α каждого label по отдельности; `delta_union_minus_max_part`; `both_union_positive`; `split_on_which_label` (оба видят «что-то из пары», но расходятся какой именно).

> **Это не тест размерности и не доказательство одного latent construct.** См. §2.3. Ограничение вшито в сам артефакт: каждая запись несёт поле `interpretation_note` со строкой «NOT a dimensionality test», и в markdown-отчёте под таблицей стоит та же оговорка. Убрать её из вывода нельзя, не изменив код.

**1.9 — Annotator directional bias.** По каждому активному label: `n_positive_a`, `n_positive_b`, `signed_difference_a_minus_b`, `disagreements`, `one_sidedness` = `|only_a − only_b| / disagreements`.

Назначение — различение Krippendorff (2011) между **систематическим** и **случайным** разногласием: `one_sidedness → 1.0` означает сдвиг порога у одного из слоёв (проблема определения или инструкции), `→ 0.0` — рассеянное разногласие (неоднозначность стимулов). Отсутствие расхождений даёт `null`, а не `0.0`.

> **Никакого вывода «кто прав».** Gold-стандарта не существует, следовательно ни один слой не является более верным. Утверждения вида «annotator-1 понял label правильнее» из этих чисел **запрещены**. Ограничение так же вшито в артефакт полем `interpretation_note` («no gold standard exists, so neither layer is 'correct'»).

**1.10 — Descriptive unit-risk comparison.** Сопоставление α у labels, требующих контекста обмена (`B.VALIDATION`, `B.AVOIDANCE_TOPIC_SHIFT`, `B.REPAIR_ATTEMPT`, `B.PRESSURE_FOR_CHANGE`), с α у единственного label, локализуемого в реплике (`B.BLAME_CRITICISM`) — см. [ontology-crosswalk.md](ontology-crosswalk.md) §3.

> **Это descriptive comparison, а не causal test эффекта контекста или unit'а.** Эти labels различаются не только unit-требованием, но и prevalence, observability, ambiguity и структурой границ. Разница α между ними **не идентифицирует** вклад контекста. Настоящий unit-тест обязан предъявлять **один и тот же конструкт** в разных unit-условиях — это A/B-эксперимент из [next-research-design.md](next-research-design.md) §3, а не этот анализ.

---

## 2. Правила, фиксируемые до результатов

### 2.1 Estimability

Пороги **не назначаются здесь** — они уже существуют в [annotation-protocol-v0.md](../annotation-protocol-v0.md) §4 и в коде как версионированные константы:

| Константа | Значение | Источник |
|---|---|---|
| `ALPHA_FAIL_THRESHOLD` | `0.67` | protocol §4 |
| `ALPHA_TARGET` | `0.80` | protocol §4 |
| `MIN_PAIRABLE_UNITS` | `10` | код, версионирован |
| `MIN_POSITIVE_UNION` | `5` | код, версионирован |
| `BOOTSTRAP_ITERATIONS` / `BOOTSTRAP_SEED` | `2000` / `42` | код, версионирован |

Присвоение статуса (порядок проверок фиксирован, реализован в `label_stats`):

1. label отсутствует в sampling frame (из `manifest.deferred_labels`) → **`not_applicable`**;
2. иначе `n_pairable < 10` **или** `positive_union < 5` **или** α неопределена → **`underpowered_not_estimable`**;
3. иначе α < 0.67 → **`failed`**;
4. иначе → **`passed`**; `meets_target` = α ≥ 0.80.

Pairable unit для label = **оба** слоя вынесли решение ∈ {`assigned`, `none_observed`}. `abstained` исключается из α этого label и учитывается отдельно: право не решать не наказывается.

> **Запрещено явно.** «α = 0.64, почти 0.67, считаем приемлемым» — нарушение этого документа. Порог либо пройден, либо нет. Изменение любого порога после просмотра ответов допустимо **только** отдельным датированным обоснованием, которое называет себя `POST_HOC`, и **никогда** не задним числом внутри этого файла.
>
> `underpowered_not_estimable` **не является ни успехом, ни провалом** label. Это утверждение о нашей выборке, а не о конструкте. `not_applicable` — принципиально иное состояние («не искали»); смешивать их запрещено.

### 2.2 Что означает α — и чего не означает

**Высокая α означает ровно одно:** при **данном** instrument / task / unit / instructions два человека воспроизводимо применяли label к этим стимулам.

Высокая α **НЕ** означает: construct validity · ecological validity · полноту онтологии · клиническую валидность · что label полезен продукту · что он измеряет то, что названо в его имени.

**Низкая α НЕ означает автоматически:** что психологический конструкт плох · что label надо удалить · что definition надо переписать.

Совместимые объяснения низкой α, ни одно из которых не исключается остальными:

- boundary ambiguity (граница между двумя labels);
- низкая prevalence (α нестабильна на скошенных маргиналах — prevalence-парадокс, [next-research-design.md](next-research-design.md) §5/R5);
- недостаточный контекст;
- недостаточное обучение аннотаторов (наш режим — **low-training ordinary humans**, не trained coders);
- неоднозначность стимула;
- unit mismatch;
- подлинное перспективное расхождение между людьми.

> **Три вопроса, которые нельзя смешивать** ([next-research-design.md](next-research-design.md) §4): low-training ordinary-human reliability (**это и меряет наш pilot**) ≠ trained coder reliability (ICC .75–.92 из литературы) ≠ expert construct validity. Сравнивать наши числа с литературными как однородные — запрещено.

### 2.3 Что означает union agreement — и чего не означает

Более высокая union-α означает: **широкая граница воспроизводится лучше, чем узкая граница внутри неё.**

Она **не означает**, что два labels суть один construct. Тот же результат порождают минимум пять положений дел, и данные pilot между ними **не различают**:

1. один латентный конструкт;
2. два реальных конструкта с плохой operational boundary;
3. нехватка контекста для проведения границы;
4. плохая инструкция;
5. низкая prevalence одного из двух labels.

Настоящая проверка размерности требует другой measurement model, ≥100 единиц и многолейбловой матрицы — то есть следующей фазы, не этой.

### 2.4 Что означает directional bias

Означает: расхождения по label распределены систематически либо рассеянно.
**Не означает:** что один из слоёв точнее. Gold-стандарта нет.

---

## 3. Выбор primary pair (deterministic, до просмотра)

### Как устроено фактически

`annotation-pilot-v0.1` имеет **ровно два presentation-слота**, `annotator-1` и `annotator-2`, происходящих из `pilot-manifest.json → annotators`. В simple pilot mode (2026-09-12, коммит `9273cd0`) одна общая ссылка; `POST /` занимает следующий свободный слот через `insertUnique` на `PilotBinding.annotator_id` — атомарно, first-come-first-served. **Когда оба слота заняты, третий отвечающий получает страницу отказа.** `metrics.agreement` читает ровно `responses/annotator-1.jsonl` и `responses/annotator-2.jsonl` (`manifest["annotators"][:2]`).

> Следовательно **через annotation-web более двух primary-слоёв получить структурно невозможно**, и «после шести ответов выбрать двух самых внимательных» — тоже. Детерминированное правило здесь не декларация, а свойство системы: **порядок занятия слота**.

### Правило на случай, когда это перестанет быть верным

Если будущий пакет объявит N > 2 слотов, или ответы будут собраны иной поверхностью (Tally/xlsx, ручной сбор), действует правило, фиксируемое **сейчас**:

1. Primary pair — **первые два eligible завершённых слоя в порядке занятия слота** (`annotator-1`, затем `annotator-2`, …), то есть по возрастанию номера слота. Механически. **Не** по качеству, не по agreement, не по «внимательности».
2. Все прочие завершённые eligible ответы **не выбрасываются**. Они анализируются как **secondary / exploratory multi-rater evidence** и помечаются как таковые.
3. **Замена primary pair после просмотра agreement запрещена.** Если слой оказался непригоден по причине, независимой от его содержания (технический сбой, неполнота, нарушение eligibility), замена допустима — но причина фиксируется письменно **до** просмотра agreement заменяющего слоя.

### Language condition — проверено, применять нечего

Оба presentation-слоя содержат **одни и те же 40 items с одинаковым языковым составом: 30 ru + 10 en** (проверено по файлам presentation; тексты идентичны, различаются только opaque ids и порядок). Язык — свойство **item'а**, а не условие, различающее аннотаторов. **Cross-language primary pair в этом пакете невозможна**, и оговорка о смешении language effect с ontology reliability здесь неприменима.

Что из этого следует для анализа: разрез α **по языку item'а** (ru 30 / en 10) технически возможен, но с 10 английскими items он заведомо `underpowered_not_estimable` и регистрируется как **descriptive only** — без вывода о том, что онтология работает на одном языке лучше, чем на другом.

### Ограничение, фиксируемое честно

Слой не несёт метаданных версии/варианта сверх `annotator_id`. Соответствие «псевдоним человека ↔ слот» существует только как **личная запись фасилитатора**, а не как криптографическая (per-person issuance снят в `9273cd0` сознательно). Реконструировать это задним числом **нельзя** и не будет.

---

## 4. Feedback channel — отдельно от разногласия

Коды (из `Feedback.hs`, константа `FEEDBACK_FLAGS`): `unnatural_example`, `insufficient_context`, `wording_or_translation`, `other`.

> **Feedback — это НЕ annotation disagreement.** Это отдельный канал и отдельная таблица. Флаг на item не делает разметку этого item'а недействительной и не входит ни в α, ни в confusion.

Предопределённая сводка (реализована в `feedback_crosstab`): `flag_totals`; counts per item; counts per stratum; `unnatural × disagreement`; `unnatural × decision-disagreement`; `unnatural × abstention`.

Порядок: **сначала количественные результаты, потом качественный разбор свободного текста.** Не наоборот — иначе свободный текст станет объяснением чисел, которые ещё не получены.

> **Правило правки items:** item **не переписывается** потому, что один человек пожаловался. `unnatural_example` — вход в naturalness gate ([dialogue-naturalness-gate.md](dialogue-naturalness-gate.md) §3, §9), а не команда на правку. Любое изменение item'а — это **новый пакет** с новым seal, а не редактирование v0.1.

---

## 5. Post-hoc rule

> Любой анализ, придуманный **после** первого просмотра ответов людей, маркируется `POST_HOC / EXPLORATORY` и **никогда** не описывается как preregistered.
>
> Это относится и к очень красивой гипотезе, про которую «очевидно же, она у нас была в голове». Если её здесь нет — она post-hoc. Список выше является исчерпывающим: primary — 1.1–1.7, exploratory-but-preregistered — 1.8–1.10, всё остальное post-hoc по определению.
>
> Это же относится к: изменению порогов; смене primary pair; добавлению разрезов; исключению items; смене определения «pairable»; переопределению `estimability_status`.

---

## 6. Что НЕ делается в этой фазе

Не добавляется `B.DENIAL_MINIMIZATION`. Не возвращается `B.WITHDRAWAL`. Не меняется `B.REPAIR_ATTEMPT`. Не меняются `B.BLAME_CRITICISM` / `B.PRESSURE_FOR_CHANGE`. Не меняется unit. Не собирается новый корпус. Не строится A/B-эксперимент. **Не считается power для следующего эксперимента до получения observed v0.1 inputs.** Не открываются ответы.

---

## 7. После анализа

Отчёт строится **только** версионированным скриптом от pinned-артефактов (ADR-0001 §Python), не интерактивно:

```
cd research/python
uv run python -m metrics.agreement --pilot-dir ../../data/pilot/v0.1
```

Выход: `data/pilot/v0.1/report/pilot-report.json` + `pilot-report.md`. Гейтящие числа берутся **оттуда и только оттуда**. Блок `preregistration` в JSON-отчёте ссылается на этот документ и перечисляет зарегистрированные пары.

---

## 8. Amendments

Правок нет. Любая будущая правка добавляется сюда датированной записью `AMENDMENT <дата>` с указанием, была ли она внесена **до** или **после** первого просмотра ответов. Правка документа на месте без такой записи означает, что preregistration недействительна.
