# Tally v7 — legacy dogfood snapshot

Form id: `kdP6do`

Public URL: https://tally.so/r/kdP6do

Status: **legacy UX dogfood prototype; do not extend as the annotation runtime**.

## Why it was retired

Tally v7 solved one bug by introducing another class of UX problems:

- RU/EN definitions and stimuli could be switched with conditional presentation blocks;
- answer controls needed stable question UUIDs, so they were changed to bilingual labels;
- this produced distracting duplicated RU/EN text even after a presentation language was chosen;
- `Show original` semantics became difficult to express cleanly across items whose source language matched or differed from the selected presentation language;
- each additional item multiplied provider-specific conditional logic.

The resulting surface no longer represented the desired invariant:

> presentation language changes presentation only; stored annotation semantics remain identical.

## v7 behavior relative to v6

- intro and category definitions gained separate RU/EN presentation blocks;
- items 4–9 gained prototype EN translations;
- selecting presentation language showed the corresponding instruction/glossary/stimulus blocks;
- answer controls remained one shared set and became bilingual;
- item 3's item-specific anti-inference hint was neutralized;
- the form remained debug-only and submissions remained non-scientific.

## Replacement

The successor is `src/annotation-web/`:

- Haskell + Yesod + Hamlet/Lucius, on Warp;
- server-rendered;
- JavaScript-free baseline, enforced by a CI source check;
- answers persisted server-side in SQLite rather than in the cookie;
- one stable internal value for each decision/label;
- fully localized respondent-facing presentation;
- exactly one source/original per item;
- `Show original` only when `source_language != presentation_language`;
- JSON debug export.

The earlier `form-spec.yaml` remains the v6 provider-neutral semantic snapshot; this document records the final v7 Tally delta rather than pretending that the v6 file describes v7 exactly.
