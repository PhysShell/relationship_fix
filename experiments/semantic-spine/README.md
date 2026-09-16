# Semantic spine — research harness

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

Сверка с `OntologyValidator` при этом никуда не делась, она просто стала
явной: `tests/test_verifier.py::DotNetParity` считает `issues.Add(` внутри
`Validate` и требует зеркало для каждой проверки. **Новая проверка в C# роняет
этот тест** — то есть расхождение обнаруживается, а не накапливается.

## Что здесь есть

```
spec/                literate spec: обычный Markdown + typed fenced blocks
schema/              block.schema.json, graph.schema.json (load-bearing, см. ниже)
spine/               parser -> IR -> graph -> verifier -> selector
generated/           ontology.json, graph.json, fixtures.json (закоммичены)
eval/tasks/          8 задач по этому репозиторию
eval/score.py        измерение отбора контекста (Phase 2, работает)
eval/runner.py       граница агент-раннера (Phase 3, адаптер НЕ подключён)
eval/results/        снимки чисел
tests/               63 теста, включая мутационный набор из 19 мутаций
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

## Что уже доказано

**1. `compile(spec) == behavior-v0.1 subset`, поле в поле.**
Spec-файлы породили те же четыре label'а, что лежат в production-онтологии, со
всеми примерами, критериями и рационалями. Это не подгонка глазами: тест
сравнивает распарсенные объекты (`tests/test_compiler.py`). Пока это равенство
держится, менять authoritative источник незачем — и именно поэтому оно и не
меняется.

**2. Отбор контекста измерен.** Одна задача, один бюджет, один счётчик токенов
на все стратегии. Бюджет заполняется строгим префиксом: под тестом находится
**ранжирование**, а не везение упаковщика.

Снимок на коммите `c6cf909`, бюджет 8000 токенов, 8 задач:

| стратегия | recall | precision | токенов | задач с полным recall |
|---|---:|---:|---:|---:|
| `semantic-spine` | 0.83 | 0.19 | 4614 | 4/8 |
| `semantic-spine/-rationale` | 0.83 | 0.19 | 4521 | 4/8 |
| `semantic-spine/+irrelevant-docs` | 0.83 | 0.12 | 7098 | 4/8 |
| `oracle` | 0.62 | 0.88 | 4540 | 3/8 |
| `raw+oracle-file-list` | 0.62 | 0.81 | 4928 | 3/8 |
| `lexical` | 0.42 | 0.16 | 7698 | 1/8 |
| `symbol-graph` | 0.29 | 0.15 | 7020 | 0/8 |
| `semantic-spine/-typed-edges` | 0.27 | 0.10 | 3342 | 0/8 |
| `docs` | 0.00 | 0.00 | 6956 | 0/8 |
| `raw` | 0.00 | 0.00 | 6630 | 0/8 |

**3. Типы рёбер несут нагрузку.** Абляция `-typed-edges` ходит по тем же
рёбрам, но без приоритета по типу: 0.27 против 0.83. Это и есть ответ на
вопрос, отличается ли harness от «папки со ссылками».

**4. `raw` и `docs` дают ноль не из-за соломенности.** `raw` честно тратит 8000
токенов на CI-YAML и contract-фикстуры, не дойдя до `data/ontology/`; `docs`
читает README и research-доки и не находит ни одного oracle-файла. Так
выглядит «прочитай репозиторий» при реальном бюджете.

**5. Rationale не помогает ПОИСКУ.** `-rationale` не хуже полного spine и
дешевле. Честный отрицательный результат; помогает ли rationale агенту
**понять** — вопрос Phase 3, на который эта метрика ответить не может.

## Чего НЕ доказано — читать обязательно

- **Ни один агент не запускался.** `resolved`, `tests_passed`, `edit_precision`
  не измерены. Phase 2 меряет **отбор контекста**, и только его. Скрытых
  acceptance-тестов нет (`acceptance.status: not_authored` во всех восьми
  задачах), адаптер не подключён, а `UnconfiguredAdapter` **падает вместо
  возврата нулей**: единственное, что хуже отсутствующего эксперимента, —
  эксперимент, который отчитался, не состоявшись.
- **Spine обгоняет `oracle` по гранулярности, а не по семантике.** Oracle читает
  файлы целиком, а `dialogue-naturalness-gate.md` — это 14137 токенов, больше
  всего бюджета. Spine достаёт нужный раздел. Это правда о бюджете, а не
  доказательство понимания, и подавать это как «мы побили oracle» нечестно.
- **Счётчик токенов — детерминированный прокси, не BPE-токенизатор.**
  Абсолютные числа приблизительны. Сравнение стратегий — нет: смещение общее
  для всех, и подменяется счётчик одной функцией.
- **`lexical` — это tf-idf, а не эмбеддинги.** Настоящий dense-retrieval
  baseline требует модели и остаётся объявленной дырой. Называть tf-idf
  «embedding baseline» — враньё, поэтому стратегия называется `lexical`.
- **Четыре label'а — это лаборатория, а не репозиторий.** 22 сущности и 73
  ребра. Разрыв между spine и baseline'ами при росте графа может и сузиться, и
  вырасти; пока неизвестно.
- **Задач восемь, они написаны автором harness'а.** Oracle-файлы выбирал тот же
  человек, который строил граф. Смягчено единственным жёстким правилом (см.
  ниже), но не устранено.

## Правила, которые держат бенчмарк честным

1. **Ни один oracle-файл не принадлежит harness'у.** Иначе spine выигрывает по
   построению. Проверяется тестом `test_no_oracle_file_belongs_to_the_harness`.
2. **Harness не входит в корпус, по которому ищут стратегии.** `spec/*.md`
   пересказывают онтологию — `lexical` и `raw` нашли бы «правильный» текст в
   файлах эксперимента. Проверяется `test_harness_files_are_not_in_the_searched_corpus`.
3. **Общий бюджет и общий счётчик.** Проверяется на всех стратегиях × бюджетах.
4. **Выводы README защищены тестами** (`tests/test_claims.py`), а не цифрами:
   `raw`/`docs`/`lexical` читают весь репозиторий, поэтому числа поедут от
   любого нового файла, а утверждения — нет.

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

## Порядок работ

- **Phase 1 — сделано.** Формат, парсер, IR, типизированный граф, verifier,
  мутационный набор, равенство с production-онтологией.
- **Phase 2 — сделано.** Селектор, 6 стратегий + 3 абляции + oracle-контроль,
  8 задач, метрики отбора.
- **Phase 3 — не сделано.** Нужны, в этом порядке: скрытые acceptance-тесты по
  каждой задаче; `AgentAdapter`; изолированный workdir на `base_commit`. Только
  после этого имеет смысл говорить `resolved` и `edit_precision`.

Смена authoritative источника онтологии **не обсуждается** до тех пор, пока
Phase 3 не даст числа. Пока их нет, это папка `experiments/`, которая честно
измеряет одну вещь и честно молчит про остальные.
