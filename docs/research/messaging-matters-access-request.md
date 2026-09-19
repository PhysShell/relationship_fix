# S4 — запрос доступа к Messaging Matters (готов к отправке человеком)

Статус: **НЕ ТРЕБУЕТСЯ** (2026-09-19). Письмо сохранено, но отправлять его
сейчас незачем: S4 перенацелен на Copenhagen Networks Study, который
скачивается сразу и под MIT. Messaging Matters отложен, не отвергнут — если
понадобится relationship-specific корпус, письмо готово.

Отправляет человек; агент почту не шлёт.

Адресат: corresponding author статьи «Messaging matters: Investigating
differences in WhatsApp communication patterns across different relationship
constellations» (ScienceDirect `S2451958826000709`). Файлы связанной
Zenodo-записи restricted, см. [S4 prereg §0](external-async-calibration-s4-prereg.md).

## Почему в письме нет чисел

В тексте намеренно отсутствуют «133 чата», «2 187 981 сообщение», «последние
3 месяца», «129 / 372 229». Эти величины **проверку не прошли** (S4 prereg
§0.3), и упоминать их значило бы заставить авторов исправлять нашу разведку
вместо ответа на запрос.

## Почему в письме подчёркнуто, что текст не нужен

Для S4 нужна структурная метаданная, а не содержание переписки. Это и правда
так, и это заметно упрощает разговор о приватности. Обещание отрезать текст на
входе — не вежливость, а то, что будет исполнено гейтом приёма
(`acquisition/admission.py`, проверка `schema.text_discarded`).

---

## Текст письма

```
Dear authors,

I am working on a research prototype studying passive communication-process
measures in dyadic messaging, in particular response timing, message-run
structure, opportunity incidence, and ambiguity introduced by timestamp
resolution.

I would like to request access to the dyadic messaging dataset used in
Messaging Matters.

For the analysis I am planning, I do not need message content. The required
information is limited to structural metadata such as:

- anonymized conversation/dyad identifier;
- anonymized sender/participant identifier;
- message timestamp and its resolution;
- observation or coverage period, if available;
- any information needed to distinguish ordinary messages from
  non-message/system events.

The immediate purpose is an external calibration/stress test of a pre-registered
simulation model. The dataset would be used to estimate baseline properties such
as message/opportunity incidence over multi-day periods, run topology,
response-time distributions, and same-timestamp ambiguity. It would not be used
to train or fine-tune an AI model.

The analysis plan is being fixed before access to the data, specifically to
avoid adapting the comparisons after observing the corpus. Results from this
dataset would be treated as calibration evidence rather than as an independent
validation set.

Could you let me know the process and conditions for obtaining access, including
any data-use agreement or other requirements?

If message text is included in the distributed files, I am also happy to discard
it immediately at ingestion and retain only the structural fields required for
the analysis.

Best regards,
[Name]
```

## После ответа

Любой исход фиксируется, включая молчание. Отказ — не провал этапа, а
записанный отрицательный результат (S4 prereg §5): density остаётся
некалиброванным, заморозка генератора не снимается, `S5b` остаётся
BLOCKED_ON_S4.
