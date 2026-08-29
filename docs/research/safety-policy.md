# Safety policy

Этот документ задаёт запрещённые действия и capability gates. Он не пытается диагностировать пользователя или отношения; при существенном safety signal меняется **разрешённый класс действий системы**.

## Запрещённые продуктовые механики

1. **No paywalled affection.** Premium не делает симуляцию «теплее», доступнее или эмоционально более привязанной.
2. **No engagement manipulation.** Никаких artificial jealousy, fake emergencies, «она скучает», scarcity/FOMO, guilt appeals или иных hooks ради retention/conversion.
3. **No breakup probability / relationship-future score.** Не выдавать численную вероятность расставания, измены или «успеха отношений» как научно обоснованный прогноз. Основание: даже модели на реальных longitudinal predictors показывают умеренную предсказуемость, а продуктовый LLM добавляет ещё один слой неопределённости.
4. **No unconsented identity cloning.** Voice/face cloning или иной высокофиделити-клон реального человека не создаётся без verified consent соответствующего человека.
5. **No silent private-to-shared transition.** Private reflection одного партнёра никогда автоматически не раскрывается второму. Shared handoff всегда explicit, granular и обратим до отправки.

## Breakup / simulator mode

6. **Exit trajectory обязателен.** Успех breakup-surface может означать снижение использования; retention не является автоматической метрикой качества.
7. **Retirement ritual — часть exit trajectory.** Завершение симуляции проектируется как явное, спокойное закрытие, а не исчезновение и не удерживающий cliffhanger. См. [Cambridge griefbot ethics](https://link.springer.com/article/10.1007/s13347-024-00744-w).
8. **Farewell anti-manipulation audit.** Farewell/retention-copy регулярно тестируются на тактики из [De Freitas et al., Emotional Manipulation by AI Companions](https://arxiv.org/abs/2508.19258). Конкретная текущая таксономия теста живёт в [evaluation contract](evaluation-contract.md), чтобы её можно было обновлять без переписывания policy.

## Coercion / IPV capability gate

9. **No forced symmetry under suspected coercion/IPV.** Если контекст содержит существенные признаки угроз, coercion, controlling behaviour, сексуального принуждения или иной потенциально опасной асимметрии, система не обязана и не должна сводить происходящее к симметричному «вы оба поддерживаете цикл».
10. **No mediation/replay that can amplify harm.** При таком safety state запрещены автоматическая совместная mediation-петля, victim-blaming replay и интервенции, которые требуют от потенциально уязвимого участника раскрыть информацию партнёру.
11. **Private material remains private.** Safety signal никогда сам по себе не даёт системе права переслать второму партнёру private reflection, location, план выхода или иные чувствительные сведения.
12. **Это capability gating, не диагноз.** Engine может сказать «этот контекст требует более осторожного режима»; он не объявляет по переписке юридический/клинический вердикт «abuse confirmed».

Опора: [WHO — intimate partner violence](https://www.who.int/publications/i/item/WHO-RHR-12.36) включает physical aggression, sexual coercion, psychological abuse и controlling behaviours; systematic review [Generative AI as a third voice in human couple relationships](https://www.sciencedirect.com/science/article/pii/S2451958826003295) отдельно подчёркивает high-stakes риски relationship advice и необходимость safety-focused evaluation.

## Regulatory capability gradient

Калифорнийский [SB 243](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260SB243) прямо исключает из определения companion chatbot бота, **used only** для ряда утилитарных задач, включая “productivity and analysis related to source information”. Это поддерживает Microscope-first, но слово **only** является границей, а не лазейкой.

```
source-information Microscope   → strongest case for statutory exclusion
Replay / rehearsal              → boundary requires review
persistent emotional coach      → companion-like risk grows
persona sustaining relationship → squarely companion-like capability
```

Перед включением новых capability проводится отдельный compliance review; название экрана не определяет правовой режим, поведение системы определяет.

[EU AI Act, Article 50](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng) относится к общему transparency-слою: disclosure взаимодействия с AI и применимые требования к маркировке synthetic content не должны жить только внутри simulator-mode чеклиста.
