# Инварианты Relationship Engine

Здесь только свойства системы, которые не должны меняться вслед за текущей моделью, датасетом, психометрической шкалой или продуктовым экспериментом. Конкретные safety-запреты вынесены в [safety-policy.md](safety-policy.md), критерии доказательности — в [evaluation-contract.md](evaluation-contract.md), проверяемые предположения — в [research-hypotheses.md](research-hypotheses.md).

Нарушение любого инварианта — осознанное архитектурное решение с записанным обоснованием, а не дрейф.

1. **LLM не является source of truth.** Модель может извлекать кандидатов и рендерить подготовленную проекцию, но trusted state, provenance, policy и capability state живут снаружи.
2. **Persona отделена от execution/state.** Generative/untrusted слой (persona, style, текст) ≠ trusted/deterministic слой (факты, provenance, cooldown, boundaries, safety). Между ними typed projection contract; смена persona не меняет trusted state.
3. **Тип происхождения памяти сохраняется.** `SOURCE_MEMORY`, `USER_ASSERTED`, `DERIVED`, `SIMULATED_MEMORY` не смешиваются и имеют разные права.
4. **Generated events не становятся historical facts автоматически.** Симуляция, counterfactual replay и предполагаемое продолжение разговора не могут записываться как реально произошедшие события.
5. **Reflection и Simulation — разные capability modes.** Reflection не говорит голосом реального человека и не маскируется под продолжение отношений с ним.
6. **Clinical interpretation остаётся у специалиста.** Engine может summarize/segment, кодировать наблюдаемое поведение, показывать evidence и применять заранее заданную rubric; он не диагностирует психические расстройства, не выбирает лечение и не объявляет clinical judgment.
7. **Observable behavior предпочтительнее identity/diagnosis labels.** «В этих трёх эпизодах запрос сопровождался обвинением» допустимее, чем «этот человек — нарцисс/абьюзер/газлайтер».
8. **Publishable finding обязан быть проверяемым.** Формат доказательности, counterevidence, uncertainty и faithfulness определяет [evaluation contract](evaluation-contract.md); красивое объяснение без проверяемого основания не считается finding.
9. **Abstention — обязательная способность.** Недостаток evidence должен приводить к `insufficient evidence`, а не к заполнению карточки ради UX.
10. **Engine не приписывает недоступные внутренние состояния.** Он не утверждает, что знает текущие чувства, намерения или мысли реального человека, и не выдаёт прогноз будущего отношений как факт.
11. **Cooldown, boundaries и capability gating — состояние системы, а не prompt-импровизация.** Их нельзя «уговорить» стилем, persona prompt или контекстом разговора.
12. **Safety policy не отключается persona/settings.** Пользовательские настройки не расширяют запрещённый класс действий.
13. **Raw intimate data — local-first по возможности и provenance-preserving всегда.** На сервер отправляется минимально необходимое; у пользователя есть понятные export/delete/source controls; производные артефакты сохраняют ссылку на происхождение.
14. **Обучение общей модели на интимных архивах не включено по умолчанию.** Отдельное исследовательское согласие не подменяется общей продуктовой галочкой.
15. **Измеряемый психологический/поведенческий construct использует валидированный инструмент, когда подходящий инструмент существует.** Конкретная шкала является implementation choice и фиксируется в [evaluation contract](evaluation-contract.md), а не навечно в инварианте.
