# Semantic spine — research harness

**Статус: Phase 2.5, результаты заморожены.** Subject приколочен к
`base_commit`, ground truth двухуровневый (файлы + якоря), снимки в
`eval/results/` пересчитываются побайтно. Ничего в графе, порядке связей и
задачах не меняется до появления held-out задач — см. §Заморозка.

Изолированный эксперимент. Он не участвует в сборке продукта, ничего не
деплоит и **не является source of truth**: production-онтология по-прежнему
лежит в `data/ontology/behavior-v0.1.json`, а `OntologyValidator` остаётся на
своём месте и не переписан.

Вопрос, на который он отвечает: **помогает ли semantic/literate representation
агенту на реальных задачах этого репозитория** — и отвечает измеримо, а не
ощущением, что «стало чище».

## Почему Python, а не C#

Исходный план предполагал `src/SemanticSpine/*.cs`. Это единственная часть
плана, которая здесь не выполнена, и причина не косметическая:

1. **В research-окружении нет .NET SDK.** C#-код, который невозможно
   скомпилировать и прогнать, — это не harness, а обещание harness'а. Verifier,
   который никогда не запускался, ловит ровно ноль мутаций.
2. **ADR-0001 §Python легализует ровно эту роль.** Read-only аналитический
   консьюмер версионированных артефактов, stdlib-only, `uv` + lock. Harness
   читает `data/` и `src/`, не мутирует ничего и остаётся структурно вне
   trusted state — а C#-проект внутри `experiments/` либо попал бы в solution и
   в layer-тесты ADR-0001, либо остался бы мёртвым `.csproj`, который никто не
   собирает.
3. **Прецедент уже есть**: `research/python/` — stdlib-only uv-проект с теми же
   правилами.

Сверка с `OntologyValidator` при этом никуда не делась, но называть её parity
было неправильно. Это **drift tripwire**: `tests/test_verifier.py::
OntologyValidatorDriftTripwire` матчит известные сообщения и считает
`issues.Add(` внутри `Validate`.

- **Ловит**: добавление или удаление проверки в C# без зеркала в spine.
- **Не ловит**: изменение СМЫСЛА существующей проверки при сохранённом
  сообщении и том же числе вызовов.

Для research harness охранной сигнализации достаточно. Выдавать её за
доказательство эквивалентности — нет.

## Что здесь есть

```
spec/                literate spec: обычный Markdown + typed fenced blocks
schema/              block.schema.json, graph.schema.json (load-bearing, см. ниже)
spine/               parser -> IR -> graph -> verifier -> selector
  subject.py         worktree на base_commit: что именно читают стратегии
  targets.py         anchor-level ground truth (строка-определение, не файл)
generated/           ontology.json, graph.json, fixtures.json (закоммичены)
eval/tasks/          8 задач: base_commit + oracle_files + oracle_targets
eval/protocol.json   версия протокола, точка заморозки, surface digest, запись v1
eval/score.py        измерение отбора контекста (Phase 2, работает)
eval/runner.py       граница агент-раннера (Phase 3, адаптер НЕ подключён)
eval/results/        замороженные снимки, воспроизводятся побайтно
tests/               91 тест, включая мутационный набор из 19 мутаций
```

## Формат spec: человек по-прежнему пишет документ

Проза остаётся прозой, Markdown-списки — списками, а typed blocks несут ровно
то, что обязано быть machine-checked. Никакого XML, притворяющегося
литературой:

    # B.VALIDATION

    ```rf-label
    id: B.VALIDATION
    allowed_units:
      - utterance
      - turn
    directionality: other_directed
    evidence_required: true
    confusable_with:
      - B.REPAIR_ATTEMPT
    status: draft
    ```

    ## Operational definition

    Высказывание явно признаёт переживание/точку зрения партнёра...

    ## Inclusion

    - явное признание эмоции или позиции партнёра

Тело блока — **не YAML**, а строгое подмножество (`spine/blocks.py`):
`key: scalar`, `key:` + `  - item`, комментарии. Всё остальное роняет разбор с
номером строки. Мягкий парсер в verification harness — это врун: он молча
превращает опечатку в валидные данные.

## Типизированные рёбра

Именно это отличает harness от обычного RAG. Пара (kind источника, kind цели)
закрыта таблицей `spine/ir.py::RELATIONS`; ребро вне таблицы — ошибка.

| relation | направление | сколько сейчас |
|---|---|---:|
| `confusable_with` | label → label | 4 |
| `exemplifies` | example → label | 17 |
| `specified_by` | label → doc#heading | 11 |
| `implements` | code#symbol → label | 11 |
| `tested_by` | label → test#symbol | 5 |
| `evidenced_by` | label → data (+ sha256) | 8 |
| `materialized_in` | label → ontology artifact | 4 |
| `depends_on` | label → unit | 8 |
| `supersedes` | ontology → ontology | 1 |
| `generated_from` | generated → label | 4 |

Цели разрешаются **по настоящему репозиторию**: заголовок обязан существовать в
документе, символ — в файле, артефакт — на диске с объявленным
`ontology_version`. Закрытые множества (`allowed_units`, `directionality`) не
скопированы, а вычитываются из C#-smart-enum'ов `UnitOfAnalysis.cs` и
`Directionality.cs` — добавили единицу в домене, spine увидел.

## Fail-closed verifier

16 проверок, каждая роняет сборку, ни одна не предупреждает:

`spec_compile`, `duplicate_stable_id`, `duplicate_edge`, `dangling_reference`,
`illegal_edge_type`, `forbidden_cycle`, `asymmetric_relation`,
`missing_required_example`, `language_coverage`, `example_unit_not_allowed`,
`unknown_verdict`, `schema_violation`, `generated_stale`,
`declared_test_missing`, `declared_implementation_missing`, `stale_evidence`.

## Мутационный набор

Самая злая часть и единственная причина верить остальному. 19 мутаций,
**каждая обязана быть поймана**:

| мутация | ловит |
|---|---|
| переименовать label только в Markdown | `spec_compile` |
| удалить `B.REPAIR_ATTEMPT` | `dangling_reference` |
| сломать `confusable_with` | `asymmetric_relation` |
| поменять `allowed_units` | `example_unit_not_allowed` |
| изменить сгенерированный JSON руками | `generated_stale` |
| править `graph.json` без сдвига `spec_digest` | `generated_stale` |
| переписать `ontology_version` в сгенерированном файле | `generated_stale` |
| удалить объявленный тест | `declared_test_missing` |
| удалить объявленную реализацию | `declared_implementation_missing` |
| подсунуть stale evidence | `stale_evidence` |
| развернуть `implements` задом наперёд | `illegal_edge_type` |
| завести цикл `depends_on` | `forbidden_cycle` |
| продублировать stable id / ребро | `duplicate_stable_id` / `duplicate_edge` |
| выкинуть все positive / все английские примеры | `missing_required_example` / `language_coverage` |
| выдумать verdict / status | `unknown_verdict` / `schema_violation` |
| сослаться на несуществующий заголовок | `dangling_reference` |

Плюс мета-проверка `test_every_check_has_a_mutation`: **проверка без мутации —
это обещание, а не гарантия**, поэтому новая проверка без мутации роняет тест.

## Phase 2.5: что было починено и почему прошлая формулировка была слишком сильной

Три дефекта, найденные при ревью первой версии.

**1. `base_commit` был декоративным.** Он лежал в манифесте задачи, `TaskSpec`
его не читал, а стратегии ходили по текущему рабочему дереву. Слово
«воспроизводимо» было незаслуженным: числа ездили от любого файла, который
завтра появится в основном репозитории — и в первой версии они действительно
поехали. Теперь `base_commit` управляет отдельным `git worktree --detach`, из
которого читают ВСЕ стратегии:

    task.base_commit -> git worktree --detach -> subject repo
                                                      |
              raw / docs / lexical / bm25 / symbol / oracle / spine

Harness и `spec/` остаются на экспериментальной ветке. Коммит недоступен
(shallow clone в CI) — прогон падает, а не откатывается молча на рабочее
дерево. Побочная выгода: на `c6cf909` каталога `experiments/semantic-spine`
ещё не существует, поэтому защита от self-contamination теперь двойная.

Проверено: два прогона подряд, прогон из другого каталога и прогон после
полного стирания кеша worktree дают **побайтно одинаковый** результат. Поэтому
в CI вернулось байт-равенство снимков — раньше оно было невозможно.

**2. Метрика была file recall, а не localization recall.** `selected =
set(bundle.files())` засчитывает файл найденным, если стратегия принесла из
него хоть что-нибудь. Это давало chunk-стратегиям структурное преимущество над
whole-file oracle'ом, а вывод вырождался в «наш chunking лучше, чем читать файл
целиком».

Старая метрика осталась, к ней добавлен второй уровень: `oracle_targets` с
якорями, и цель считается покрытой, только если в контекст попала **именно
строка-определение** (заголовок, символ, ключ артефакта):

    "oracle_targets": [
      "data/ontology/behavior-v0.1.json#B.VALIDATION",
      "docs/annotation-protocol-v0.md#3. Решения разметчика",
      "src/.../OntologyValidator.cs#ValidateAnnotation"
    ]

**3. Добавлены две стратегии.** `bm25` — дешёвый, но заметно более сильный
sparse baseline, чем tf-idf. `oracle-sections` — настоящая верхняя граница: он
знает идеальные якоря, но не знает графа. Обгонять whole-file oracle
неинтересно; догонять oracle-sections — содержательно.

## Результаты (заморожены)

Subject `c6cf909`, harness `88f6dfb`, бюджет 8000 токенов, 8 задач:

| стратегия | target recall | file recall | target precision | токенов |
|---|---:|---:|---:|---:|
| `oracle-sections` | 0.97 | 0.96 | 1.00 | 3223 |
| `oracle` | 0.64 | 0.62 | 0.88 | 4540 |
| `raw+oracle-file-list` | 0.64 | 0.62 | 0.81 | 4928 |
| `semantic-spine` | 0.54 | 0.83 | 0.15 | 4614 |
| `semantic-spine/+irrelevant-docs` | 0.54 | 0.83 | 0.09 | 7098 |
| `semantic-spine/-rationale` | 0.54 | 0.83 | 0.15 | 4521 |
| `bm25` | 0.30 | 0.35 | 0.12 | 7505 |
| `semantic-spine/-typed-edges` | 0.27 | 0.27 | 0.14 | 2539 |
| `symbol-graph` | 0.25 | 0.29 | 0.13 | 6878 |
| `lexical` | 0.21 | 0.42 | 0.05 | 7475 |
| `docs` | 0.00 | 0.00 | 0.00 | 6956 |
| `raw` | 0.00 | 0.00 | 0.00 | 5359 |

### Главный результат — отрицательный

**На уровне якорей spine проигрывает whole-file oracle'у: 0.54 против 0.64** —
при том что по файлам он ведёт 0.83 против 0.62. Инверсия зафиксирована тестом
`test_spine_loses_to_whole_file_oracle_on_targets` и обязана падать, если
перестанет держаться.

То есть spine надёжно приносит **нужный файл** и заметно хуже приносит **нужное
место в нём**. Ровно это и скрывала file-level метрика.

### Диагноз промахов

7 из 10 промахов spine — одна и та же причина: ребро `materialized_in`
рендерит ШАПКУ артефакта (`schema_version`, `ontology_version`, список id
label'ов), а якорь указывает на строку `"id": "B.VALIDATION"` внутри этого же
файла. Spine говорит «label живёт вот здесь» и показывает обложку, а не запись.

Остальные три промаха честные и содержательные:

- `UnitOfAnalysis.cs#Exchange` — у `B.REPAIR_ATTEMPT` нет `exchange` в
  `allowed_units`, поэтому ребра к этой единице нет. Задача просит его
  ДОБАВИТЬ; граф про будущее ничего не знает и знать не должен.
- `RuleStubAnnotator.cs#Rules` — у `B.PRESSURE_FOR_CHANGE` намеренно нет ребра
  `implements`, потому что стаб этот label действительно не назначает. Граф
  кодирует ОТСУТСТВИЕ связи, а метрика требует принести файл. Здесь метрика
  недооценивает spine: структурно он знает ответ, но retrieval'ом его не
  выражает.
- `item-authoring-v0.1.md#Главное правило` — цель в двух прыжках от seed'ов.

### Предсказание, сделанное до правки

Рендеринг `materialized_in` — настоящий дефект, а не артефакт бенчмарка: ребро
знает, о каком label речь, и всё равно показывает не его. Чинить его **сейчас
нельзя**: правка после того, как увидел цифры, — это подкрутка под восемь уже
знакомых задач.

Поэтому фиксируем фальсифицируемое предсказание: *если рендерить объект самого
label'а вместо шапки артефакта, target recall при 8000 должен вырасти с 0.54
примерно до 0.85–0.95, а file recall не измениться.* Проверять — на held-out
задачах Phase 3, вместе с правкой. Предсказание, сделанное заранее, стоит
дороже числа, полученного после.

### Зависимость от бюджета

Выводы держатся не на всех бюджетах, и это надо знать до того, как цитировать:

| | 4000 | 8000 | 16000 |
|---|---:|---:|---:|
| `oracle-sections` | 0.85 | 0.97 | 1.00 |
| `oracle` | 0.42 | 0.64 | 0.84 |
| `semantic-spine` | 0.44 | 0.54 | 0.67 |
| `semantic-spine/-typed-edges` | 0.27 | 0.27 | **0.67** |
| `bm25` | **0.14** | 0.30 | 0.50 |
| `lexical` | **0.17** | 0.21 | 0.48 |

- **Типы связей связывают только когда связывает бюджет.** При 16000 абляция
  `-typed-edges` догоняет spine ровно: всё достижимое помещается, и приоритет
  обхода перестаёт что-либо решать. Утверждение «типы рёбер несут нагрузку»
  верно при 4000–8000 и ложно при 16000.
- **BM25 сильнее tf-idf при 8000 и 16000, но слабее при 4000.** На узком
  бюджете нормировка по длине документа играет против него.

### Что осталось верным из первой версии

- `compile(spec) == behavior-v0.1 subset`, поле в поле.
- `raw` и `docs` дают ноль не из-за соломенности: `raw` честно тратит бюджет на
  CI-YAML и contract-фикстуры, не дойдя до `data/ontology/`.
- Rationale не помогает ПОИСКУ (`-rationale` не хуже и дешевле). Помогает ли он
  агенту ПОНЯТЬ — вопрос Phase 3.
- Шум никогда не помогает.

## Чего НЕ доказано — читать обязательно

- **Ни один агент не запускался.** `resolved`, `tests_passed`, `edit_precision`
  не измерены. Phase 2 меряет отбор контекста, и только его. Скрытых
  acceptance-тестов нет, адаптер не подключён, `UnconfiguredAdapter` **падает
  вместо возврата нулей**.
- **Улучшение понимания кода не показано.** Показано, что типизированный граф
  лучше выбирает контекст на маленьком авторском наборе задач — и что на
  anchor-уровне он всё ещё хуже, чем просто открыть нужные файлы целиком.
- **Восемь задач написаны автором harness'а.** Граф, `SPINE_RELATION_ORDER`,
  задачи и oracle-файлы — один человек. Среди восьми задач есть
  `confusable-drift`, а первым в порядке обхода стоит `confusable_with`. Это не
  доказательство подкрутки, но это именно та конфигурация, в которой мозг
  прекрасно подкручивает «универсальную архитектуру» под знакомые вопросы.
- **Счётчик токенов — детерминированный прокси, не BPE-токенизатор.**
  Сравнение стратегий корректно (смещение общее), абсолютные числа — нет.
- **`lexical` — это tf-idf, а не эмбеддинги.** Настоящий dense baseline тащит
  модель и остаётся дырой до Phase 3; для integrity-CI он не нужен.
- **Четыре label'а — лаборатория, а не репозиторий.** 22 сущности, 73 ребра.

## Заморозка и версия протокола

Два коммита — две разные вещи, и путать их нельзя:

| коммит | что это |
|---|---|
| `88f6dfb` | **development harness v0**. Anchor-level ground truth здесь ещё НЕТ: были только `oracle_files`, метрика была file recall, subject не был приколочен. |
| `2ef1e5c` | **selection protocol v1 freeze**. Якоря, pinned subject, BM25 и oracle-sections появились именно здесь. |

Это кажется педантством ровно до того момента, когда через четыре месяца
придётся доказывать, выбирались ли якоря до или после просмотра результатов.
Поэтому на вопрос отвечает `eval/protocol.json`, а не память.

**Заморожено с `2ef1e5c`** и проверяется машинно:

    surface_digest = sha256( eval/tasks/*.json
                           + spec/*.md
                           + SPINE_RELATION_ORDER )

Поведение — рендеринг узлов, упаковка бюджета, формулы стратегий — заморожено
вторым способом: побайтным равенством снимков в `eval/results/`. Любое
изменение двигает числа, и `test_reproducibility` краснеет.

Последующие коммиты вправе менять CI, документацию и метаданные протокола, но
не его поверхность: `test_protocol` падает и требует **поднять версию**, а не
перезаморозить дайджест на месте.

**Поправка к арифметике отчёта.** Macro-средние считались через `round()` поверх
уже округлённых float'ов. CPython 3.12 добавил компенсированное суммирование в
`sum()` для float'ов, поэтому 3.11 и 3.13 расходились в четвёртом знаке на
значениях у десятичной границы (5/6 → 0.83335), а сложение float'ов вдобавок не
ассоциативно — результат зависел и от порядка задач. Локально было зелено, CI
краснел. Теперь средние считаются точными дробями с одним правилом округления
(`Fraction` + `Decimal` ROUND_HALF_UP), порядок и платформа не влияют.

Поведение при этом не менялось, и это проверено, а не заявлено: на 96 строках
снимка при 8000 — ноль расхождений в `context_tokens`, `chunks`, `files`,
счётчиках oracle, `missed_files`, `missed_targets` и `truncated`, и ноль
расхождений в округлении на уровне строк. Изменились только macro-средние в
`summary`, в четвёртом знаке; все числа таблиц README на двух знаках те же.
`surface_digest` не сдвинулся.

### v1 immutable / v2 prospective

    selection protocol v1          selection protocol v2
      subject:  c6cf909              held-out задачи
      freeze:   2ef1e5c              materialized_in fix
      tasks:    8 (автора harness'а) Phase 3
      result:   spine 0.54 < oracle 0.64
      status:   immutable            предсказание: 0.54 -> 0.85-0.95

Отрицательный результат v1 хранится в замороженных снимках и в
`eval/protocol.json`. Живой тест `test_spine_loses_to_whole_file_oracle_on_targets`
пока сторожит его на текущей реализации, но он **не вечен**: когда в v2 починят
рендеринг, тест архивируется вместе с протоколом (`skipTest` по версии), а не
правится до зелёного. Иначе CI начнёт требовать сохранять известный
retrieval-баг на том основании, что когда-то мы честно доказали его
существование.

Предсказание 0.85–0.95 тестируется именно как **prospective prediction v2**.
Записано до правки — в этом вся его ценность.

## Правила, которые держат бенчмарк честным

1. **Ни один oracle-файл и якорь не принадлежит harness'у.**
2. **Harness не входит в корпус.** Двойная защита: исключение по префиксу плюс
   subject, в котором каталога harness'а ещё не существует.
3. **Общий бюджет и общий счётчик** на всех стратегиях.
4. **Subject приколочен**, поэтому снимки сравниваются побайтно.
5. **Каждый якорь обязан разрешаться** в своём subject'е — тест падает иначе.
6. **Выводы README защищены тестами** (`tests/test_claims.py`), включая
   отрицательный вывод про проигрыш oracle'у.
7. **Заморозка проверяется, а не обещается** (`tests/test_protocol.py`): правка
   задач, якорей, графа или порядка связей двигает `surface_digest` и требует
   поднять версию протокола.

## Запуск

```
cd experiments/semantic-spine

python -m spine compile            # spec -> generated/
python -m spine compile --check    # упасть, если generated/ устарел
python -m spine verify             # fail-closed проверки против репозитория
python -m spine equivalence        # compile(spec) == behavior-v0.1 subset
python -m spine graph              # рёбра по типам

python -m unittest discover -t . -s tests -v
python eval/score.py --budget 8000
```

Зависимостей нет (stdlib-only). `-t .` обязателен: `tests` — пакет.

Стратегии читают `git worktree` на `base_commit` задачи. Кеш деревьев —
`$TMPDIR/rf-spine-worktrees`, переопределяется `SPINE_WORKTREE_DIR`; прибрать
записи после ручного удаления — `git worktree prune`. Нужен полный clone: при
shallow checkout коммит недоступен и прогон падает намеренно.

## Порядок работ

- **Phase 1 — сделано.** Формат, парсер, IR, типизированный граф, verifier,
  мутационный набор, равенство с production-онтологией.
- **Phase 2 — сделано.** Селектор, 7 стратегий + 3 абляции + 2 oracle-контроля,
  8 задач, метрики отбора.
- **Phase 2.5 — сделано.** Pinned subject, anchor-level ground truth, BM25,
  oracle-sections, переименование tripwire, заморозка.
- **Phase 3 — не сделано.** Held-out задачи (не от автора harness'а), скрытые
  acceptance-тесты, `AgentAdapter`, изолированный workdir.

Условия Phase 3, все с одинаковыми инструментами агента:

    A  raw repo
    B  BM25 / dense initial context
    C  symbol / dependency retrieval
    D  semantic spine
    E  oracle-sections

Измеряется уже не retrieval: `resolved`, скрытые тесты, edit precision,
unrelated edits, tool calls, input/output tokens, время, first-useful-file
latency. Два режима — context-only и full agentic tools: вполне возможно, что
spine резко помогает слабому one-shot агенту и почти ничего не даёт хорошему
агенту с grep/read. **Отрицательный результат здесь тоже результат**, и его
надо опубликовать так же громко.

Смена authoritative источника онтологии **не обсуждается** до тех пор, пока
Phase 3 не даст числа. Пока их нет, это папка `experiments/`, которая честно
измеряет одну вещь и честно молчит про остальные.

## Текущий verdict

> Phase 1 доказал, что literate/semantic spec можно связать с настоящим
> relationship_fix fail-closed и не потерять эквивалентность четырёх labels.
> Phase 2 дал предварительный сигнал, что типизированный semantic graph
> заметно улучшает выбор КОНТЕКСТА на маленьком авторском наборе задач — и
> одновременно показал, что на уровне якорей он пока хуже, чем просто открыть
> нужные файлы целиком. Улучшение понимания кода и улучшение
> coding-agent performance не доказаны.
