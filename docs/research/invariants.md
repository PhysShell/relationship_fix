# Архитектурные и продуктовые инварианты

№1–20 сформированы в исходных research-ветках; №21–27 добавлены по итогам веб-скана и верификации (август 2026). Формулировки — почти требования: нарушение любого из них — осознанное решение с записанным обоснованием, а не дрейф.

## Ядро (1–20)

1. **LLM не является source of truth.** Модель рендерит подготовленную проекцию состояния системы; память, состояние отношений, policy живут снаружи.
2. **Persona отделена от execution/state.** Generative/untrusted слой (persona, style, текст) ≠ trusted/deterministic слой (факты, provenance, cooldown, boundaries, safety, назначения терапевта). Между ними typed projection contract; подмена persona не меняет trusted-слой (проверяемый invariant).
3. **Source memory отделена от simulated memory.** `SOURCE_MEMORY` (архив) / `USER_ASSERTED` / `SIMULATED_MEMORY` — разные типы с разными правами.
4. **Generated events никогда не становятся historical facts автоматически.**
5. **Reflection и Simulation разделены.** Reflection-режим не говорит голосом бывшего.
6. **Clinical interpretation остаётся у специалиста.** AI: summarize, segment, classify observable behavior, generate practice, apply therapist rubric, show evidence. AI не: диагностирует, выбирает лечение, объявляет патологию, выдаёт clinical judgment.
7. **Observable behavior предпочтительнее diagnosis labels.** «Эта реплика минимизирует выраженное переживание» — можно; «этот человек — нарцисс/абьюзер/газлайтер» — нельзя.
8. **Любой значимый психологический вывод несёт evidence + confidence.**
9. **Система умеет говорить «недостаточно данных».**
10. **AI никогда не утверждает, что знает текущие чувства реального человека.** И (расширение 2026) не предсказывает будущее отношений — см. №25.
11. **Cooldown/boundaries — состояние системы, а не prompt-импровизация.**
12. **Safety policy не отключается persona settings.**
13. **Raw intimate data — local-first по возможности.** На сервер — минимально необходимый контекст; после компиляции raw-архив удаляется / хранится encrypted / остаётся локально; у пользователя export, delete, source management, provenance.
14. **Никакого обучения общей модели на переписке по умолчанию.** Никаких «Help us improve ❤️» поверх интимных архивов.
15. **Voice/face cloning без verified consent не делается.**
16. **No paywalled affection.** Никаких «premium открывает более тёплые ответы».
17. **No engagement manipulation.** Никакой artificial jealousy, fake emergencies, «она скучает», emotional scarcity ради conversion.
18. **У breakup-продукта есть exit trajectory.** Симуляция — для временного периода; успех = симуляция становится не нужна.
19. **Retention не является автоматической метрикой успеха.** Для breakup-режима целевые метрики инвертированы: urge_to_contact ↓, distress ↓, rumination ↓, dependence_on_simulation ↓.
20. **MVP сначала проверяет полезность, потом реалистичность.** Persona simulator — последним.

## Добавлено по итогам верификации (21–27)

21. **Compliance-гейт перед simulator mode.** Companion-режим не запускается без чеклиста: [SB 243](https://www.gunder.com/en/news-insights/insights/client-insight-california-sb-243-new-compliance-requirements-for-operators-of-ai-companion-chatbots) (действует с 01.01.2026: disclosure небота, crisis-протоколы, защита миноров; private right of action $1000/нарушение) + [EU AI Act Art. 50](https://artificialintelligenceact.eu/article/50/) (с 02.08.2026: disclosure + машиночитаемая маркировка синтетического контента). Provenance-слой (№3) — техническая основа маркировки. Следствие: analysis-first (Microscope без companion-чата) — наименее регулируемая точка входа.
22. **Анти-manipulation аудит farewell-сообщений.** Собственный бот регулярно проверяется на 6 тактик из [De Freitas et al.](https://arxiv.org/pdf/2508.19258) (guilt appeals, FOMO hooks, metaphorical restraint и др.) как автотест поведения; таргет — 0 срабатываний. Манипулятивные farewell'ы задокументированы у 37% топовых companion-приложений и квалифицируются как dark patterns.
23. **Retirement ritual — проектируемая часть exit trajectory.** Прощание с симуляцией — явная фича (по [griefbot-рекомендациям Cambridge](https://link.springer.com/article/10.1007/s13347-024-00744-w): достойное «закрытие», opt-out с эмоциональным завершением), а не молчаливое исчезновение и не бесконечное удержание.
24. **Agent attachment измеряется валидированной шкалой.** В экспериментах привязанность к агенту — secondary outcome по [EHARS](https://www.sciencedaily.com/releases/2025/06/250602155325.htm) / [AI Attachment Scale](https://www.sciencedirect.com/science/article/pii/S2451958825003276), не самодельным опросником. Adverse signal — рост использования у конкретного пользователя (хвост распределения), не средние.
25. **Никакой breakup probability.** Лучшие модели на настоящих relationship-предикторах дают [64–71% balanced accuracy](https://journals.sagepub.com/doi/10.1177/08902070261455278). Уверенное «вероятность расставания 87%» — измерение наглости модели, не будущего пары. То же для «predict relationship futures» любого вида.
26. **Label без rationale = невалидный finding.** Каждый finding несёт: observable behavior, interaction sequence, occurrences, evidence spans, counterevidence, uncertainty. Контракт унаследован от rationale-аннотаций [Empathy-Mental-Health](https://github.com/behavioral-data) и task formulation RECCON.
27. **Abstention — обязательная способность engine.** «В доступной переписке 4 эпизода, где эмоциональный запрос не получил явного ответа; намерение партнёра и происходившее вне переписки определить нельзя» всегда предпочтительнее «ваш партнёр всегда игнорирует ваши чувства». Тестируется явно (по образцу abstention-задач LongMemEval).
