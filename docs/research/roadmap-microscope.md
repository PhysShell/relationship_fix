# Roadmap: Relationship Microscope (этапы 0–5) и дальше

Первый MVP — не breakup-app и не couples-app, а общий исследовательский инструмент: **Relationship Microscope**. Ретроспективные (ex) данные выбраны как test bench, existing couples — как долгосрочный бизнес. Обоснование выбора и поправки — в конце.

## Форма MVP

Без mobile. Вход: один длинный chat export (Telegram/WhatsApp) или несколько выбранных конфликтных эпизодов. Выход: **ровно 3 findings**, каждый строго:

```
Finding
├── observable behavior        (из BehaviorOntology, не диагноз)
├── interaction sequence       (траектория A↔B)
├── occurrences                (сколько раз, за какой период)
├── evidence                   (конкретные сообщения/spans)
├── counterevidence            (контрпримеры, если есть)
├── uncertainty                (confidence + что неизвестно)
└── "Это похоже на ваш опыт?"  (IPR-петля)
```

Чего в MVP НЕТ: relationship score, attachment diagnosis, personality type, «ваши отношения токсичны», breakup probability (инвариант №25), AI-ex, dashboard, 80 графиков sentiment.

После findings — одна функция сверх анализа: **Replay** одного эпизода (original → пауза перед эскалацией → пользователь пишет альтернативу → 2–3 варианта системы → объяснение поведенческой разницы).

## Этапы

**Этап 0 — BehaviorOntology v0.** Не обучать модель. Собрать 15–25 наблюдаемых действий на базе couple-литературы: CIRS (blame, pressure for change, withdrawal, avoidance…) + SPAFF/SSIRS + BOLT-стиль multi-label + repair-категории (humor, affection, self-disclosure, understanding, taking responsibility). Каждое действие: operational definition + положительные/отрицательные примеры + tricky cases («ну ты дебил 😂❤️»).

**Этап 1 — Synthetic evaluation corpus** в стиле LongMemEval: длинные timestamped отношения с planted ground truth (episodes, patterns, counterexamples, изменившиеся предпочтения/границы). Сценарии — из relationship profiles (traits, tendencies, latent conflicts, event schedule), не «Claude, сгенерируй ссору». На этом же корпусе валидировать кандидат-метрики траекторий (см. SSG-оговорку ниже).

**Этап 2 — Microscope**: real chat → 3 evidence-grounded findings. Pipeline: parser (готовый opensource) → episode segmentation → multi-label annotation → pattern/trajectory mining → evidence+counterevidence retrieval → findings. Выход хоть HTML.

**Этап 3 — IPR-коррекция**: под каждым finding и под гипотезами об отдельных моментах — «именно так / частично / совсем нет / я чувствовал другое / важное происходило вне чата» + свободный ответ «что происходило на самом деле». Это одновременно: калибровка самоуверенности, рост полезности отчёта, собственный размеченный dataset.

**Этап 4 — Replay** одного эпизода (см. выше). Для ex-сценария — обучение для следующих отношений; для будущей couples-поверхности — «применить в следующем разговоре».

**Этап 5 — 10–20 реальных историй.** Почти вручную, качество отчёта важнее автоматизации.

### Метрики этапа 5

1. **Discovery**: «Узнали ли вы что-то важное и убедительное, чего раньше не понимали?» + «Покажите конкретное место анализа, которое изменило понимание».
2. **Uniqueness**: этого не дал бы обычный ChatGPT с тем же экспортом.
3. **Evidence acceptance**: доля findings с ответом «да/частично» в IPR-петле; доля «в переписке отсутствует важный контекст» (это не провал, а калибровка).
4. **Action**: прошёл ли пользователь Replay.
5. **Willingness to pay** (поправка к исходной дорожке — проба была потеряна в третьей итерации): после полученной ценности реальная оплата следующего анализа/пакета, не «а вы бы заплатили?».

Гейт на переход к couples: люди стабильно говорят «этого я сам не видел, но evidence действительно подтверждает» И метрика 5 ненулевая.

## Consent-протокол для донорских архивов (обязателен с этапа 5)

Архив содержит данные двух людей; анализируем по запросу одного. Минимум:
- explicit informed consent донора + понятное описание, что и как обрабатывается;
- local-first pipeline: parsing/segmentation/статистика локально; наружу — минимально необходимый контекст; raw-архив после компиляции удаляется или остаётся у донора;
- псевдонимизация второго лица в любых хранимых артефактах; никакие фрагменты не попадают в обучающие наборы (инвариант №14);
- позиционирование: «инструмент саморефлексии на собственной копии переписки», не «модель/клон человека X» — GDPR-риск обработки данных второго лица это не снимает полностью (special categories!), но существенно снижает и продуктово, и юридически;
- право донора на полное удаление, включая производные аннотации.

## После гейта: перенос на existing couples

```
Detect → Explain → Private reflection → Shared handoff → Micro-intervention → Measure outcome → Learn
```

- Продуктовая грамматика интервенций — Observe → Understand → Respond (OurRelationship/IBCT, RCT 742 пары).
- UX — private-per-partner пространства + explicit handoff (верифицированный образец: Harmony).
- Mutual desire matching — один из primitives (safe-reveal как у Mojo/Couplet), не позиционирование.
- **Дизайн экспериментов — JITAI/MRT**: цикл «micro-intervention → outcome → update» формально является just-in-time adaptive intervention; для оценки эффектов использовать micro-randomized trial методологию, не изобретать свою. Целевой proprietary dataset: `context → interaction pattern → intervention → outcome → human correction`.
- Persona simulator — последним, только после compliance-гейта (инвариант №21) и с exit trajectory + retirement ritual (№18, №23).

## Обоснование порядка и поправки к третьей итерации

**Почему Microscope first (а не couples mutual discovery, как во второй итерации):**
1. Матчинг-механика commodity трижды (Mojo/Couplet/Spicer+AI) — эксперимент с ней малоинформативен; проверять надо уникальное — evidence engine.
2. Ретроспективные данные — лучший test bench: завершённые эпизоды, один пользователь, есть у кого спросить «правда ли это», ничего не вмешивается в живой конфликт.
3. Регуляторно: Microscope без companion-чата в основном вне скоупа SB 243 — наименее регулируемая точка входа (в отличие от REMI/Closure-класса).

**Поправки, внесённые при верификации (29.08.2026):**
- **SSG-оговорка**: State Space Grids — representation и UI-примитив, но в [статье 2024](https://www.tandfonline.com/doi/full/10.1080/19312458.2024.2413973) метрики гибкости/attractors не показали связи с outcome; кандидат-метрики валидировать самим на synthetic corpus (этап 1).
- **Deliberate-practice оговорка**: RCT-база — про тренировку терапевтов; перенос на пары — открытый вопрос эксперимента, не факт.
- **Willingness-to-pay** возвращён в метрики этапа 5.
- **Revol и «Closer»** из конкурентной карты убраны как неверифицированные (см. [landscape](landscape-2026-08.md) §7); вывод о commoditization держится на подтверждённых продуктах.
- **Holdout replay / persona eval**: LLM-judge недостаточен ([PersonaEval](https://openreview.net/forum?id=wZbkQStAXj)) — blind human eval + психометрия персоны (InCharacter-метод).

## Открытые вопросы (могут убить/оправдать части продукта)

1. Персонализированная симуляция помогает двигаться дальше — или создаёт более качественный объект привязанности? (A/B/C дизайн: generic assistant / style-matched stateless / style+state+boundaries; primary: Δ urge_to_contact; secondary: EHARS-attachment, usage trajectory; adverse: рост использования.)
2. Deliberate practice на собственных эпизодах > generic psychoeducation по skill transfer? (Arm A generic / Arm B personalized; оценка на unseen scenarios, blinded.)
3. Проходит ли evidence-grounded анализ порог «сам не видел, но подтверждаю» + оплату? (этап 5.)
