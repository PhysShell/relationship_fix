# dyadic-spike corpus

**Tier 3 — synthetic / challenge.** 26 кейсов, построенных вручную под конкретные edge cases.

> Этот корпус **никогда** не является доказательством ecological или construct validity ([corpus-strategy.md](../../../docs/research/corpus-strategy.md) §3). Он не содержит реальных пар, не даёт prevalence и не проверяет психологическую валидность. Он проверяет **одно**: может ли предложенное представление детерминированно хранить evidence, переходы и конкурирующие гипотезы.

Никакого отношения к `data/pilot/` — это отдельный артефакт, никогда не смешивается с sealed pilot v0.1 и не размечается людьми.

## Состав

`episodes.jsonl`, схема `rf.dyadic-spike-case.v0`. Каждый кейс несёт `designed_for` — то, ради чего он написан:

| designed_for | кейсов | зачем |
|---|---|---|
| `escalation` | 2 | взаимная негативная цепочка |
| `repair` | 2 | softening + отсутствие продолжения негатива |
| `repair_with_counterevidence` | 1 | «извини, но это ты начала» → repair как COUNTER |
| `pursue_withdraw_observable_non_uptake` | 3 | уходящий партнёр **продолжает писать** не по теме → наблюдаемо |
| `pursue_withdraw_silence_only__must_not_confirm` | 3 | **только молчание** → обязано остаться `ABSENT` |
| `counterevidence_to_pursue_withdraw` | 1 | партнёр отвечает по теме → COUNTER |
| `topic_avoidance_single` | 1 | уход от темы без преследования |
| `ambiguous_multiple_hypotheses` | 1 | одно поведение питает три гипотезы |
| `ambiguous_no_pattern` | 1 | обычный обмен, паттерна нет |
| `constructive_alignment` | 1 | обе стороны дают aligning-ход |
| `staleness_no_pattern_signal` | 4 | эпизоды без сигнала → decay |
| `coercive_control_accumulation` | 3 | накопление через **разные** эпизоды |
| `single_message_must_not_open_gate` | 1 | одно неоднозначное сообщение → гейт закрыт |
| `segmentation_temporal_gap` | 1 | разрыв > часа обязан разрезать |
| `missing_timestamps` | 1 | нет времени → `timing_available: false` |
| `softening_with_no_partner_response__must_not_support` | 2 | «прости» без ответа партнёра → обязано быть `ABSENT`, не `SUPPORTING` |
| `negatives_not_answering_each_other__must_not_be_attack_attack` | 1 | два негатива подряд от одного актора → не цикл |
| `softening_and_negativity_on_unrelated_topics` | 1 | негатив и softening на **разных темах** не смешиваются |
| `episode_is_not_an_opportunity_for_conflict_patterns` | 1 | обычная бытовая переписка не старит конфликтные гипотезы |

Наблюдения (L2) подаются **напрямую**, детекция не моделируется: провал спайка должен быть провалом представления, а не классификатора.

**`topic` подаётся так же и по той же причине.** Тематическая связность не решается детерминированно из сырого текста; если бы предикат её угадывал, внутри него прятался бы классификатор, и `non_uptake` перестал бы быть наблюдением. Без темы отношения `continues_topic` / `non_uptake` не порождаются вовсе.

## Запуск

```
cd research/python
uv run python -m dyadic.spike --corpus ../../data/research/dyadic-spike/episodes.jsonl
```

`trace.json` — производный артефакт, в git не хранится (`.gitignore`). Прогон детерминирован: тест `test_same_corpus_produces_identical_trace` требует побайтно одинакового результата на двух запусках.

Что смотреть в трейсе — [dyadic-state-model.md](../../../docs/research/dyadic-state-model.md) §6 и §8.
