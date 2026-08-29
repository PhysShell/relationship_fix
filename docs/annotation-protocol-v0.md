# Annotation Protocol v0 (BehaviorOntology, этап 0)

Цель этапа 0 — не «идеальная психология», а первый объект, который можно **независимо размечать и проверять**. Acceptance test этапа: два независимых человека размечают 50–100 коротких эпизодов, и если они постоянно спорят — чинится онтология, а не разметчики.

Связанные документы: [ontology v0.1](../data/ontology/behavior-v0.1.json) · [evaluation contract](research/evaluation-contract.md) · [ADR-0002](adr/0002-research-artifact-data-contract.md) (формат `rf.annotation.v1`).

## 1. Роли

- **Разметчики ≠ авторы онтологии.** Минимум один разметчик — наивный (не участвовал в написании определений): гайд обязан работать без телепатии intended meaning.
- **Три разметчика на подмножестве** (adjudication set): при двух несогласных не видно, кто ошибся; при трёх различимы systematic (чинить определение) и idiosyncratic (чинить инструктаж) расхождения.
- Adjudicated-решения пишутся в `data/gold/<ontology-version>/`, сырые слои каждого разметчика — в `data/annotations/<ontology-version>/<annotator>.jsonl`. Gold иммутабелен; новая версия онтологии = новый слой (см. ADR-0002 §7).

## 2. Единицы, цели и контекст

- Контракт аннотаций — `rf.annotation.v2`: цель задаётся **AnnotationTarget** (utterance → message_id; turn/exchange/episode → provenance-aware DerivedUnitRef с segmentation_version, составом сообщений и hash'ем состава — см. ADR-0002 §4.1). Kind цели и есть единица анализа — отдельного поля unit нет, рассинхрон невозможен.
- **Pilot v0 размечает только utterance-цели**; labels с `allowed_units: [turn, exchange]` (например `B.WITHDRAWAL`) технически недоступны — валидатор отвергает до сохранения. Turn/exchange-разметка откроется вместе с первым segmentation-алгоритмом (и его версией в DerivedUnitRef).
- **Контекстное окно фиксировано протоколом**: разметчик видит ±10 сообщений вокруг единицы (или границы эпизода, если он короче). Менять окно между сессиями нельзя — agreement перестаёт быть сравнимым.

## 3. Решения разметчика

По каждой единице ровно одно из:

1. **assigned** — ≥1 label из онтологии + evidence span(ы) для labels с `evidence_required` (координаты в code points, см. ADR-0002 §1);
2. **none_observed** — единица рассмотрена, ни одно поведение онтологии не наблюдается. Это самый частый и полностью валидный исход, НЕ abstention;
3. **abstained** — с причиной: `insufficient_context` | `ambiguous_between_labels` | `unit_not_applicable` | `source_corrupted` | `language_unsupported` | `other` (+ свободная заметка). Право не решать — зеркало инварианта abstention; разные причины диагностируют разные проблемы (неясный label ≠ нехватка контекста).

Multi-label разрешён (одна реплика может нести request + blame).

## 4. Метрика согласия и estimability

- **Krippendorff's alpha, per label, бинарно** (label присутствует/отсутствует на единице) — не сырой % agreement: на скошенных labels два человека получают 90% согласия, молча соглашаясь «здесь ничего нет».
- Пороги фиксируются ДО разметки: α < 0.67 → label уходит на доработку определения (или в v0.1-retired); целевой рабочий уровень α ≥ 0.8.
- **Отчёт по каждому label × stratum обязан содержать**: `n_units`, `n_positive_A`, `n_positive_B`, `positive_union`, `prevalence`, `alpha`, `bootstrap CI`, `estimability_status ∈ {passed | failed | underpowered_not_estimable}`. При prevalence уровня 1/80 α нестабилен или неинформативен — **underpowered не считается ни успехом, ни провалом label**; это сигнал «нужно больше label-relevant случаев в Challenge Set». Natural Set НИКОГДА не обогащается positives — иначе он перестаёт показывать натуральные base rates.
- Рядом с α публикуется **positive agreement** (согласие именно на positives) — как диагностика, не замена α: одно число умеет прятать ситуацию «прекрасно согласны на negatives, но не умеем одинаково находить positives».
- Расчёт — версионированным Python-скриптом от pinned-артефактов (ADR-0001 §Python), не интерактивным notebook.

## 5. Два страта gold-корпуса

- **Challenge Set** — намеренно обогащён трудным: ambiguous, confusable-пары (blame vs pressure, validation vs repair, humor vs contempt — «ну ты дебил 😂❤️»-класс), adversarial.
- **Natural Set** — случайная выборка, сохраняющая base rates (большинство единиц — none_observed).

Публикуются **обе** метрики: `α_challenge` и `α_natural`. Возможный исход «natural .91 / challenge .43» означает: онтология работает на очевидном и ломается там, где нужна. Challenge-α не используется для утверждений о «реальном» disagreement — мы сами насыпали туда худшее.

## 5.1 Последовательность: micro-pilot до расширения

```
engineering foundation
   → micro-pilot текущих 6 labels (2 разметчика × ~20 challenge + ~20 natural units)
   → доработка definitions/protocol по результатам
   → расширение онтологии по функциональным пробелам
   → полный exercise (50–100 units, 3-й разметчик на adjudication set)
```

Цель micro-pilot — не acceptance и не красивый α, а **сломать протокол и определения до того, как ошибки размножатся на 15 labels**: если уже на шести выяснится, что validation vs repair, blame vs pressure или avoidance vs none_observed люди понимают по-разному, это меняет дизайн следующих labels.

Кандидаты следующей партии (по функциональным пробелам, не все сразу): NEUTRAL_REQUEST, TAKING_RESPONSIBILITY, PERSPECTIVE_SOLICITATION, SUPPORT_OFFER, SUPPORT_RESPONSE, AFFECTION_WARMTH, HUMOR_PLAY, SELF_DISCLOSURE_VULNERABILITY, BOUNDARY_EXPRESSION, BOUNDARY_ACKNOWLEDGEMENT. Отдельное намерение: **вынести TAKING_RESPONSIBILITY из repair** — «Да, я действительно забыл тебе написать» — наблюдаемое принятие ответственности, но не обязательно repair attempt; repair-функция в конфликтном контексте потом выводится как candidate (`taking_responsibility + conflict context → repair_attempt?`) — простые observations снизу, более сильные claims сверху.

## 6. Источники эпизодов v0

Смесь (НЕ только собственный синтетический генератор — иначе E0-циркулярность просачивается в E1): рукописные эпизоды, адаптированные фрагменты, синтетика. Оба рабочих языка (ru/en) представлены и в примерах каждого label (валидатор требует), и в эпизодах корпуса.

## 7. Прогнозируемые жертвы v0

- `contempt/sarcasm-with-hostility` в онтологию v0.1 сознательно НЕ включён — ожидаемо худший по α в тексте; его случаи пока размечаются как ambiguous у `B.BLAME_CRITICISM`.
- `B.WITHDRAWAL` на текстовых данных проверяется только с turn/exchange-разметкой (v0.1+): для utterance его не существует по построению.

Провал label'а на acceptance test — это работа теста, а не поражение проекта.

## 8. Чего в v0 нет

Классификатора. Сначала human annotation guide + gold corpus; LLM-аннотатор сравнивается с человеческим gold (E1), а не с самим собой. Диагностических labels (attachment style, gaslighting, narcissism, abuse, toxic) нет и не будет в BehaviorOntology — см. инвариант №7.
