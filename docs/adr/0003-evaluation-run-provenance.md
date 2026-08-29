# ADR-0003: Evaluation run provenance

Статус: **accepted** (2026-08-29). Ожидаемо эволюционирует быстрее ADR-0002 — потому и отделён.

## Контекст

Evaluation contract (§8) требует, чтобы удачный demo нельзя было перепутать с evidence качества. Для этого каждый запуск обязан носить своё происхождение с собой. Важная честность: manifest гарантирует **воспроизводимость provenance/конфигурации** (что именно было отправлено, посчитано и на чём), а не побитовое воспроизведение LLM-вывода — детерминизма модель не обещает, «temperature=0» тем более.

## Решение

### 1. Каждый run — каталог артефактов

```
runs/<run-id>/
  manifest.json        rf.run-manifest.v1
  annotations.jsonl    выход
  metrics.json         rf.slice-metrics.v1 (или eval-метрики)
  report.html          человекочитаемый срез
  requests/NNNNNN.json raw LLM-запросы (когда есть модель)
  responses/NNNNNN.json raw LLM-ответы
```

`runs/` не версионируется git'ом (локальные артефакты), но формат файлов — часть wire-контракта (ADR-0002).

### 2. Manifest (rf.run-manifest.v1)

Обязательные поля: `run_id`, `started_at` (Instant), `git {commit, dirty}`, `ontology {id, sha256}`, `dataset {id, sha256}`, `annotator_id`, опционально `model {provider, model_id, inference_params}`.

- **`inference_params` — provider-specific bag**, не фиксированные поля: на текущих моделях Anthropic sampling-параметры удалены из API, а на воспроизводимость влияют thinking/effort-настройки. Никакого захардкоженного `temperature`.
- `git.dirty=true` — валидный, но видимый факт: результат с грязного дерева не может тихо притвориться результатом коммита.

### 3. Raw invocations (когда появляется LLM-аннотатор)

Каждый вызов: `call_id`, provider/model, `request_sha256`, пути к request/response-артефактам, тайминги, `usage {input_tokens, cached_input_tokens, output_tokens}`, `cost {currency, estimated, pricing_version}`. **`pricing_version` обязателен**: цены API меняются, и пересчёт старого run по сегодняшнему прайсу — фальсификация экономической истории. Usage/cost аккумулируются в metrics — это baseline для будущего cost-тюнинга.

### 4. Prompt-слои и кэш

Запрос делится на STATIC (system policy + онтология + annotation guide + схема ответа) и DYNAMIC (эпизод, единица, контекстное окно). STATIC — стабильный кэшируемый префикс (cache breakpoint), DYNAMIC — после него. Manifest хэширует слои раздельно (`system_sha256`, `guide_sha256`, `item_template_sha256`): когда скор изменился, можно спросить «что именно поменялось — онтология, guide, item-шаблон или модель», а не сравнивать два гигантских SHA.

### 5. Batch

`IBatchModelClient` — capability-интерфейс: harness выбирает native batch (−50% стоимости на корпусных прогонах, latency неважна) либо bounded-parallel одиночные вызовы. Адаптер без batch ничего не эмулирует и не врёт про семантику.

### 6. Python-потребители

Читают `runs/` и `data/gold/` read-only; свои выходы пишут новыми артефактами (например `runs/<id>/analysis/`), manifest не мутируют. Гейтящие числа — только из версионированных скриптов от pinned-артефактов.

### 7. Отложено сознательно

- Server-side refusal fallbacks и structured-output-режим Anthropic-адаптера — в ADR будущего LlmAnnotator (текущий адаптер обрабатывает refusal исключением `ModelRefusalException`).
- `ModelInvocationDto` как wire-схема — вместе с первым реальным LLM-прогоном (формат выше — обязательство этого ADR).

## Последствия

- E0/E1/E2-прогоны сравнимы между собой и через месяцы: у каждого числа есть паспорт.
- Slice уже исполняет ядро контракта: manifest с git/ontology/dataset-хэшами пишется в каждый запуск.
