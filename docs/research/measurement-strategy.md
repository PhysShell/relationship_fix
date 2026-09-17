# Measurement strategy: внешние измерения прежде собственной аннотации

Дата: 2026-09-16. Статус: **смена north star**. Документ меняет порядок работ, а не содержание уже сделанного.

---

## 1. Что меняется

**Было:**

> построить хорошую ontology и научиться надёжно размечать relationship dialogue.

**Стало:**

> собрать проверяемую модель взаимодействия из уже валидированных человеческих измерений, внешних corpora и персональной калибровки, а собственную аннотацию использовать только для действительно новых constructs.

Собственная аннотация перестаёт быть **основным** способом доказательства. Сначала — существующие human-annotated corpora и валидированные psychometric instruments. Свои люди подключаются только там, где остаётся специфический незакрытый вопрос, **или где сама калибровка является частью продукта**.

Следствие для moat: он перестаёт быть «у нас шесть labels» и становится

```
external evidence + formal interaction representation + recipient-specific perception
+ personal calibration + longitudinal correction + intervention outcomes
```

## 2. Что происходит с пилотами

| Пилот | Статус | Условие запуска |
|---|---|---|
| **Pilot A** (`annotation-pilot-v0.1`, BehaviorOntology) | **не запускается сейчас** | сначала атаковать couple-coding datasets и crosswalk. Более вероятно понадобится позже: нашу конкретную операционализацию `BLAME_CRITICISM` / `PRESSURE_FOR_CHANGE` / `VALIDATION` / `REPAIR_ATTEMPT` точь-в-точь никто за нас не размечал |
| **Pilot B** (`interaction-primitives-v0`) | **заморожен на `e8a020b` как contingency experiment** | достаётся и запускается, если внешний census покажет, что P1/P2/P5 закрыты плохо или совсем другим конструктом |

Ни один не выброшен. Оба уже несколько раз обнаружили архитектурные дефекты **до** того, как к ним подошёл хоть один человек — это не wasted work.

> Прибор собран. Это не обязывает нас бить им по всему подряд только потому, что мы три недели его полировали.

## 3. Карта слоёв и чем проверяем сначала

| Слой | Что хотим знать | Чем проверяем сначала | Свой human study |
|---|---|---|---|
| Conversation topology | кто на что отвечает, ветвление, antecedent | Kummerfeld / NOESIS-II | скорее не нужен |
| Topic / segmentation | смена темы, границы эпизода | TIAGE + discourse corpora | только если останется gap |
| Discourse relation | acknowledgement, contrast, response structure | Molweni + STAC | скорее не нужен |
| Observable behavior | blame, pressure, validation | couple-coding systems + наши mapping experiments | **возможно да** — taxonomy наша |
| Empathic/supportive response | validation, emotional reaction, exploration | EPITOME и родственные | скорее внешний benchmark |
| **Perceived impact** | как ответ реально воспринял получатель | Perceived Empathy / recipient-rated datasets | **важнее случайных аннотаторов** |
| Longitudinal state | повторяющиеся паттерны | RESCUE, CIRS/IDCS + compositional experiments | позже, только для gaps |
| Intervention/outcome | что сделали и что изменилось | therapy/support datasets + outcome literature | отдельный front |
| User personalization | как **этот** пользователь воспринимает коммуникацию | validated self-report + calibration vignettes | **часть продукта**, не лабораторная повинность |

## 4. PerceivedImpact становится боковой осью, а не следующим состоянием

Прежняя архитектура была линейной. Это было ошибкой: perceived impact — не ещё одно состояние разговора.

```
                         ┌→ observer interpretation
message → interaction ───┤
                         └→ recipient perception
```

Эти две ветки **могут расходиться**, и расхождение само по себе информация:

```
observer:   VALIDATION
recipient:  «меня этим только сильнее выбесили»
```

Для relationship product это фундаментально. Поэтому датасеты, где **сам получатель** оценивает empathy/helpfulness/felt-understood, ценнее ещё одного корпуса expert labels: только они позволяют проверить наше же правило `observable behavior ≠ perceived impact` ([invalidation-review.md](invalidation-review.md) §4/R-C2, где зафиксировано, что поле этот мост не построило).

Intervention layer получает честный вход **только после** этого.

## 5. Трёхслойная персонализация

```
VALIDATED SELF-REPORT      что человек говорит, что он обычно делает/чувствует
        ↓
CALIBRATION VIGNETTES      как он интерпретирует конкретные ambiguous exchanges
        ↓
LONGITUDINAL REAL DATA     что фактически происходит + его исправления
        ↓
PERSONAL MODEL
```

**Ни один слой не объявляется ground truth.** Если валидированная шкала говорит одно, калибровка второе, а реальные корректировки третье — система не обязана выбирать победителя. Расхождение информативно.

Калибровочные виньетки — это наша механика аннотации, развёрнутая продуктово:

```
A: Прости, я перегнул.
B: Ладно.

Для вас B скорее:
○ принимает извинение   ○ отвечает нейтрально
○ дистанцируется        ○ невозможно понять без контекста
```

**Здесь нет gold answer.** Измеряется `user-specific interpretation profile`, а не сдача экзамена по нашей онтологии. Запрещено: «ваша эмпатия 84%». Это не гороскоп для подписчиков ([safety-policy.md](safety-policy.md) §3).

## 6. Corpus QA как подсистема

Не модель отношений, а шаг пайплайна, применимый к внешним корпусам, нашим synthetic challenges, пользовательским виньеткам и будущим real-message eval sets:

```
corpus → embedding/similarity → duplicate & near-duplicate detection
       → outlier candidates → review: garbage? unnatural? mislabeled? rare useful case?
```

## 7. Что запрещено на ближайшее время

Новый BehaviorOntology label · новый human pilot · улучшение Pilot B · новый DyadicState spike · CRF/HSMM · AMR parser · новый web annotation UI · поиск датасетов без mapping к конкретному architectural question.

> Иначе снова начнётся замена решения задачи строительством инфраструктуры вокруг задачи.

## 8. Четыре трека

```
TRACK 1  External benchmark suite   Kummerfeld/NOESIS · Molweni · STAC · TIAGE
                                    EPITOME · Perceived Empathy · RESCUE/couple
                                        ↓ adapters + mapping + empirical probes
TRACK 2  Measurement audit          IRI · TEQ · PPRS/PRIS · CSI
                                        ↓ onboarding candidates
TRACK 3  Product calibration        6–12 виньеток, no right answers
TRACK 4  PerceivedImpact            observer vs recipient, schema, датасеты, интерфейс
```

И только после этого — два решения:

```
Does Pilot A still answer a unique unanswered question?
Does Pilot B still answer a unique unanswered question?
```

Ответ «нет» — прекрасный исход. Ответ «да» — запускаем **конкретный gap**, а не «потому что мы уже сделали пакеты».

---

## 9. Дополнение 2026-09-17 — north star уточнён после TRACK 4

Запись дополняет §1, не переписывает её. Формулировка §1 осталась верной как описание *порядка работ*; после TRACK 4 к ней добавилось требование к *поведению системы*.

**Было:**

> построить хорошую ontology и научиться надёжно размечать relationship dialogue → затем: собрать проверяемую модель взаимодействия из уже валидированных измерений, внешних corpora и персональной калибровки.

**Стало:**

> система должна отделять то, что наблюдает, от того, что предполагает, учиться на расхождениях с опытом конкретных участников и никогда не выдавать одно за другое.

Обещаний меньше, инженерной проверяемости больше. «Правильно понять отношения» не проверяемо ничем; «никогда не выдавать одно за другое» проверяется тестом — и проверяется в [personal-calibration-loop.md](personal-calibration-loop.md).

Треки §8 при этом закрыты или запаркованы, а главным фронтом стала не следующая исследовательская тема, а первая продуктовая:

| трек | статус |
|---|---|
| TRACK 1 corpus map | **PARKED** после [external-measurement-audit.md](external-measurement-audit.md) §5 |
| TRACK 2 corpus QA | не начат |
| TRACK 3 product calibration | **поглощён** Personal Calibration Loop v0 §6: виньетки = гипотезы с весом 0 |
| TRACK 4 PerceivedImpact | **закрыт**, [perceived-impact-audit.md](perceived-impact-audit.md) |
| **MAIN** | **Personal Calibration Loop v0** |

Два решения из конца §8 получили ответы ([audit §13.3](perceived-impact-audit.md)):

- *Does Pilot B still answer a unique unanswered question?* — **нет**. Внешние корпуса покрывают topology и discourse дешевле, чем человеческое время. Остаётся frozen contingency.
- *Does Pilot A still answer a unique unanswered question?* — **да**, его вопрос специфичен к нашим операциональным определениям. Но не сейчас: более ценный вопрос для человеческого времени теперь «система считает этот ход validation — а как он реально дошёл до вас?», и именно там внешний корпус заканчивается.

