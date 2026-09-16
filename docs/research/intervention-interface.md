# InterventionOntology: interface contract

Дата: 2026-09-16. Статус: **research-only**. Реализация: `research/python/dyadic/interface.py`.

Companion: [intervention-ontology-review.md](intervention-ontology-review.md) (обзор литературы и skeleton) · [dyadic-state-model.md](dyadic-state-model.md) (то, что подаётся на вход).

---

## 0. Границы этого документа

Здесь определяется **только форма входа и выхода**. Здесь **нет**: таксономии стратегий сверх пяти уже зафиксированных классов, политики принятия решений, генерации текста, советов пользователю.

`decide()` в коде — **заглушка, которая всегда воздерживается** и перечисляет причины. Она существует, чтобы контракт прогонялся end-to-end, а не потому, что политика есть. Написать политику до фальсификации DyadicState означало бы построить тот самый advice generator, который из этой фазы исключён.

---

## 1. Input: что DyadicState обязан отдать

```
InterventionContext
    episode_id
    candidate_hypotheses[]        все живые гипотезы с их ledger'ами
    recent_transitions[]          переходы, случившиеся в этом эпизоде
    evidence_event_ids[]
    counterevidence_event_ids[]
    uncertainty
        observation_coverage_per_hypothesis[]   список, НЕ среднее
        unobservable_slots[]
        n_concurrent_hypotheses
        has_recurring_hypothesis
    safety_flags
```

### Чего в контракте намеренно нет

| Отсутствует | Почему |
|---|---|
| relationship score / индекс здоровья | safety-policy §3 |
| атрибуты человека | инвариант 7 |
| прогноз исхода | инвариант 10 |
| свободнотекстовое summary состояния | инвариант 1: иначе LLM-пересказ станет фактическим входом политики |
| **усреднённая** уверенность | схлопывание coverage в одно число — первый шаг к score |

Тест `test_context_exposes_no_score_and_no_person_attributes` проверяет отсутствие строк `score`, `health`, `compatibility`, `personality`, `breakup` в `uncertainty`. Тест `test_uncertainty_keeps_coverage_per_hypothesis_not_averaged` — что coverage остаётся списком.

> Если будущему слою понадобится что-то, чего здесь нет, это **изменение контракта**, рассматриваемое отдельно. Не «добавим поле по дороге».

---

## 2. Output

```
InterventionDecision
    act                  intervene | abstain
    target               участник | диада | none
    strategy_class       reflect | reframe | slow_down | surface_perspective | none
    rationale_evidence[] ссылки на event_id
    contraindications[]  вычисленные блокеры
```

**`abstain` записывается так же явно, как `intervene`.** Без этого `unnecessary intervention` и `missed intervention` невычислимы: они выводятся из `act × observed_effect × user_response`, и если воздержания не пишутся, обе категории исчезают из данных ([intervention-ontology-review.md](intervention-ontology-review.md) §3).

**Outcome здесь отсутствует по построению.** Эффект измеряется **после**, как сдвиг DyadicState — в нашей модели это переход статуса гипотезы. Прямая аналогия с `B.REPAIR_ATTEMPT`, который кодирует попытку, а не успех. Внешнее подтверждение: метрика MAD в ProMediConv считает «average shift in each party's behavioral state across dialogue turns».

**Пять классов стратегий, не одиннадцать.** Обоснование краткости — PCA по 31 item CIRS+SSIRS даёт 4 фактора; одиннадцать стратегий ProMediConv заточены под юридическую медиацию с третьей стороной.

---

## 3. Contraindications — вычисляются, не авторствуются

```python
safety_gate_open__symmetric_advice_suppressed     # safety-policy §9-§10
no_recurring_pattern__single_episode_is_not_a_pattern
concurrent_hypotheses_unresolved
pattern_depends_on_unobservable_slots
```

Все четыре — **функции от состояния**, не аннотации к случаю. Это принципиально: блокер, который кто-то проставляет руками, становится оценочным суждением без носителя истины.

Два из них видны в реальном трейсе постоянно, и это сознательно:

- `no_recurring_pattern…` — паттерн из одного эпизода не паттерн (`distinct_episodes ≥ 2`);
- `pattern_depends_on_unobservable_slots` — срабатывает всегда, когда жива гипотеза `pursue_withdraw`, потому что слот `withdrawer_internal_disengagement` объявлен ненаблюдаемым **в схеме**.

> **Чего из спайка НЕ следует.** На синтетическом корпусе ни одно решение не дошло до `intervene` — но `decide()` **запрограммирован всегда воздерживаться**. Ноль вмешательств здесь является unit-тестом заглушки, а не эмпирической находкой о правильной частоте abstention. Прежняя редакция этого документа делала из нуля вывод о том, как будет вести себя реалистичная система; вывод снят.
>
> Что действительно можно изучать по трейсу — **какие блокеры срабатывают и на каком материале**. Частоту действий нельзя: для неё нужна политика, которой нет, и данные, которых нет.

---

## 4. Safety: почему гейт не конкурирует с паттернами

`SafetyAccumulator` **структурно отделён** от `HypothesisLedger`. Он не является паттерном и не может быть «перевешен» позитивным паттерном: `constructive_alignment` со статусом `RECURRING` не закрывает открытый гейт.

Требования из safety-policy, реализованные в коде:

| Требование | Реализация |
|---|---|
| §9 no forced symmetry | `pursue_withdraw` асимметричен по построению (роли в `participants`, обратное направление — **отдельная** гипотеза с отдельным id) |
| §12 не выводить паттерн из совместной встречаемости | предикаты построены на `InteractionRelation`: требуется, чтобы ход **отвечал** ходу |
| §10 no mediation that can amplify harm | открытый гейт → `safety_gate_open__symmetric_advice_suppressed` в contraindications |
| §12 gating, не диагноз | вывод гейта содержит строку «**NOT a determination about any person**»; тест запрещает слово `abuser` |
| не выводить abuse из одного сообщения | гейт требует **≥3 различных эпизодов И ≥4 событий**; шесть событий внутри одного эпизода гейт не открывают |

Пороги гейта (`SPIKE_ONLY_SAFETY_MIN_EPISODES = 3`, `SPIKE_ONLY_SAFETY_MIN_EVENTS = 4`) выше порога повторяемости паттернов (`RECURRENCE_EPISODES = 2`) намеренно: safety-гейт должен быть труднее достижим, чем обычная гипотеза.

> **Но это не safety threshold, и имена констант теперь об этом кричат.** Числа ниоткуда не выведены: они больше порога повторяемости, и это всё их обоснование. Вывод гейта несёт `policy_provenance: "synthetic_placeholder"` и `thresholds_are_placeholders: true`, а тест это проверяет — потому что через полгода кто-нибудь найдёт готовый boolean `gate_open` и, как положено человечеству, решит, что раз код существует, значит число научное. Настоящий порог требует safety review и доказательств, которых нет.

---

## 5. Открытые вопросы

1. **Оба внешних прецедента — third-party-present.** RESCUE-Bench (терапевт в кадре) и ProMediConv (медиатор) определяют «intervention timing» для **легитимно присутствующей третьей стороны**. У пары наедине её нет. Переносимость timing-конструкта на систему, которая не является участником разговора, **не проверена никем**.
2. **Порог «сколько блокеров = не вмешиваться» не определён** и определяться сейчас не должен: это политика.
3. **`target` для диадического паттерна неочевиден.** `pursue_withdraw` асимметричен — кому адресовано вмешательство? Обе возможности имеют разные риски, и это вопрос к safety review, а не к схеме.
4. **`transfer_observed`** (применил ли пользователь предложенное в реальном обмене) — единственное «мягкое» измерение с определённым носителем истины, но его измерение требует доступа к последующей переписке. В контракте пока отсутствует.
