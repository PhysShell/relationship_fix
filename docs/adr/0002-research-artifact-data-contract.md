# ADR-0002: Stable research artifact / wire data contract

Статус: **accepted** (2026-08-29)

## Контекст

Все артефакты (source messages, annotations, findings, метрики, манифесты) читаются и C#-кодом, и Python-статистикой, и людьми, и живут годами. Контракт обязан пережить рефакторинги, смену библиотек и смену языка-потребителя. Главная ловушка — Unicode: C#-строки индексируются UTF-16 code units, Python — code points, байты — UTF-8; один 😂 = 1 code point = 2 UTF-16 units = 4 байта. Незафиксированная единица измерения превращает source-integrity проверку в генератор фантомных ошибок на каждом эмодзи.

## Решение

### 1. Unicode: канонические координаты — code points

- Все span-offsets считаются в **Unicode code points (scalar values)**. Не в UTF-16 units, не в байтах, не в графемах (ZWJ-семья 👨‍👩‍👧‍👦 = 7 code points — намеренно: код-пойнты однозначны на всех языках-потребителях).
- В C# любые преобразования — только через `System.Text.Rune` (`CodePointText`), никогда `string[i]`.
- **Никакой нормализации исходного текста перед вычислением offsets.** Source text хранится как есть; нормализованные представления для NLP — derived, не source.
- `EvidenceSpan` несёт избыточность: `quoted_text` + `source_text_sha256` (SHA-256 UTF-8 байтов, lowercase hex). Source-integrity проверка: hash сходится → срез по code points → точное сравнение с quoted_text. Ловится и смещение координат, и подмена источника.
- Контракт закреплён property-тестами (FsCheck: эмодзи, ZWJ, combining marks, RTL, кириллица) и golden fixtures.

### 2. Канонический сериализатор

Единственный — `RelationshipJson.Options` (DataContracts): snake_case, компактный вывод, null-поля опускаются, NodaTime ISO-8601. Экранирование: BMP-не-ASCII литерально, non-BMP — `\uXXXX` surrogate pair (поведение UnsafeRelaxedJsonEscaping; детерминированно и валидно). **Канон = байты, зафиксированные golden fixtures, а не эстетика.** Ад-хок `JsonSerializerOptions` вне DataContracts запрещены архитектурным тестом (только DataContracts ссылается на System.Text.Json).

### 3. Stable discriminators

Дискриминаторы и enum-ключи — замороженные строки (`WireConstants`, ключи Smart Enums), маппинг domain↔wire всегда явный (`WireMapping`). **Никогда не выводятся из имён C#-типов**: rename `AbstainedFinding → RejectedFinding` не имеет права изменить ни один старый JSONL. Неизвестный дискриминатор при чтении — громкий `FormatException`, не тихий пропуск.

### 4. Schema versioning

Каждая самостоятельная запись несёт namespaced id: `rf.source-message.v1`, `rf.annotation.v1`, `rf.finding.v1`, `rf.run-manifest.v1`, `rf.ontology.v1`, `rf.slice-metrics.v1`. Версии артефактов расходятся независимо. Breaking change = новый id (`…v2`) + явная миграция v1→v2; «десериализатор вроде съел» миграцией не считается.

### 4.1. Addendum (2026-08-29): rf.annotation.v2 — target union и derived-unit provenance

`rf.annotation.v1` был utterance-centric (`message_id` как ключ), тогда как онтология уже знает turn/exchange/episode. v2 вводит **AnnotationTarget**:

- `utterance` → `{kind, message_id}` (source fact);
- `turn | exchange | episode` → `{kind, unit_id, segmentation_version, member_message_ids, members_sha256}`.

Turn/exchange — **не source facts**: их границы выводит segmentation-алгоритм, поэтому одного `unit_id` мало — иначе смена алгоритма тихо переписывает, что означал «exchange-17». `members_sha256` = SHA-256 от UTF-8 байтов member-id, соединённых `\n`, в исходном порядке (состав не сортируется); id не содержат control-символов (валидация VO). Маппинг проверяет hash при чтении и отвергает: смешанные формы (utterance с derived-полями и наоборот), неизвестный kind, битый hash — всё громким `FormatException`.

Дисциплина версии: **v1 заморожен навсегда** (читается legacy-путём), миграция `AnnotationV1ToV2` тривиальна (`message_id → target{kind: utterance}`) и покрыта тестом — это первый реальный прогон правила §4. Пишется только v2.

`timestamp_resolution`: `exact_instant` | `local_time_with_assumed_zone` | `local_time_unknown_zone`. Экспорт без надёжной timezone не превращается в притворно точный Instant. NodaTime-типы (`Instant`/`LocalDateTime`) сериализуются ISO-8601.

### 6. Golden wire fixtures

`data/contracts/<schema>/<case>.json` — канонические байты, покрывающие трудные случаи (emoji, RTL, combining, все decision-кейсы). Тест-контракт двусторонний: (а) сериализация канонического объекта == файл байт-в-байт; (б) файл парсится и re-serialize даёт его же. Обновление — только явное (`RF_UPDATE_GOLDEN=1`), т.е. git-diff, а не тихая мутация. Исторические fixtures не удаляются.

### 7. Данные и слои разметки

```
data/items/         immutable source episodes
data/annotations/<ontology-version>/<annotator>.jsonl   сырые слои по разметчикам
data/gold/<ontology-version>/adjudicated.jsonl          frozen adjudicated
data/contracts/     golden wire fixtures
data/fixtures/      входы для slice/E0
```

Gold — не «истина, которую редактируют»: смена онтологии создаёт новый слой (`ontology-v0.2/...`), старый остаётся навсегда — иначе нельзя измерить, стало ли определение лучше.

## Последствия

- Python-потребитель читает те же координаты без конвертаций (code points = его родная индексация).
- Rename-рефакторинги безопасны для данных by construction.
- Цена: ручной `WireMapping` на каждый новый тип; принято сознательно — это же исполняет правило №3.
