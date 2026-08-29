# ADR-0001: Package & architectural dependency policy

Статус: **accepted** (2026-08-29)

## Контекст

Домен проекта инвариантно-тяжёлый (provenance, abstention, закрытые множества исходов), и главный риск зависимостей — не «плохие библиотеки», а зоопарк из нескольких способов представить одно и то же (`Result`/`Option`/union) и дрейф границ между слоями. Принцип: **зависимость появляется после доказанной боли, а не потому что красиво выглядит на белой доске.**

## Решение

### Стек

- **.NET 10 LTS / C#**, CLI-first (без сервера до реальной нужды).
- **Domain algebra: Thinktecture.Runtime.Extensions** — Value Objects, Smart Enums, discriminated unions с exhaustive `Switch`/`Map` (добавление case ломает компиляцию старых Switch).
- **Время: NodaTime.** `DateTime` в Domain/DataContracts запрещён: longitudinal engine обязан различать `Instant` / `LocalDateTime` / зоны, а temporal provenance (`SourceTimestamp`: exact_instant | local_with_assumed_zone | local_unknown_zone) хранится так же строго, как text provenance.
- **CLI: System.CommandLine** (механика) + **Spectre.Console** (только рендеринг, только в Cli; `--json`-вывод идёт мимо Spectre).
- **LLM: собственный `IModelClient`** (RelationshipFix.AI.Abstractions) + **один provider-адаптер** на старте (официальный Anthropic SDK). Второй провайдер — по ADR, когда возникнет кросс-провайдерный вопрос: baseline A/B/C сравнивает промптинг/архитектуру, не провайдеров. Batch — capability-интерфейс (`IBatchModelClient`), не обязательный метод.
- **Хранилище: JSONL/JSON артефакты** (immutable), SQLite прямым Microsoft.Data.Sqlite — когда появятся реальные запросы. EF Core не тащим.
- **Тесты: xunit.v3 (MTP-режим dotnet test) + Shouldly + FsCheck** (property-тесты контрактов) + **ArchUnitNET** (границы слоёв) + reflection-факты по `GetReferencedAssemblies` (запреты «неустановленных» библиотек).

### Не разрешены без отдельного ADR

`LanguageExt`, `ErrorOr`, `FluentResults`, `OneOf`, `CSharpFunctionalExtensions`, `Vogen` — и любой другой Result/Option/Union framework. **Правило симметрично**: LanguageExt получит ADR тогда, когда в коде накопится реальная боль (N× ручной Traverse / аппликативная композиция) и diff покажет выигрыш, а не потому что «мы функциональные люди». Известная цена отказа: у Thinktecture-юнионов exhaustiveness обеспечивается generated Switch/Map, а v5-LanguageExt заставляет доменные error-типы наследовать библиотечные трейты (Monoid) — это инфекция доменных типов, которую мы не покупаем по умолчанию.

Для накопительной валидации до тех пор достаточно ручного `ValidationResult<TError,TValue>` (значение + `ImmutableArray<TError>`) или закрытого union `Valid | Invalid` — заводится при первой реальной необходимости, не заранее.

Mapperly — предодобрен (source-generated, читаемый вывод) и добавляется, когда появится реальный mapping-объём; пока domain↔wire маппится явно руками (`WireMapping`) — это заодно исполняет правило «никаких auto-derived дискриминаторов».

### Central Package Management

Все версии — только в `Directory.Packages.props`: добавление зависимости = видимый diff в одном файле.

### Границы слоёв (enforced, не договорённость)

```
Domain          → Thinktecture + NodaTime + BCL. Больше ничего.
DataContracts   → Domain; единственный проект с System.Text.Json.
Evaluation      → Domain, DataContracts, AI.Abstractions. Без провайдеров.
AI.Abstractions → ничего (provider-free, domain-free).
AI.Anthropic    → AI.Abstractions + Anthropic SDK.
Cli             → всё выше; единственный владелец Spectre.
```

Правила закреплены тестами `RelationshipFix.Architecture.Tests` (ArchUnitNET по типам + reflection-факты по ссылкам сборок, включая запрет `System.Text.Json` вне DataContracts и Result-фреймворков везде). Нарушение границы = красный CI, а не code-review-замечание.

### Python

Легален в двух ролях, обе — вне trusted state:
1. **Paper reproduction / внешние ML-модели** (`research/`): вход JSONL → чужой код → выход JSONL.
2. **Read-only analytical consumer** версионированных артефактов: Krippendorff α, bootstrap, calibration, plots.

Запрещено: мутировать gold/annotations/manifest, сохранять гейтящие числа из интерактивного notebook-состояния. Любое число, которое гейтит решение, воспроизводится версионированным скриптом от pinned-артефактов (`uv` + lock).

## Последствия

- Стартовый production-бюджет: Thinktecture, NodaTime (+ NodaTime.Serialization.SystemTextJson в DataContracts), System.CommandLine, Spectre.Console, Anthropic. Всё.
- Честно признанная цена: C# sealed-иерархии сами по себе не дают compile-time exhaustiveness — поэтому union-типы идут через Thinktecture-генератор, а не «голые» sealed records со switch.
- Изменение этого ADR — новый ADR со ссылкой на конкретный diff/боль.
