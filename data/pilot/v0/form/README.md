# Annotation form artifacts

This directory preserves the Tally UX prototypes that preceded the dedicated annotation web app.

## Legacy render target

- Tally form id: `kdP6do`
- Public URL: https://tally.so/r/kdP6do
- Final Tally revision: `v7`
- Status: **legacy UX dogfood only; not the frozen scientific annotation run**

Tally is no longer the planned annotation runtime. The replacement lives in `src/annotation-web/` and uses server-rendered Go + `a-h/templ` with a JavaScript-free baseline.

## Files

- `form-spec.yaml` — provider-neutral semantic snapshot of Tally v6: instructions, categories, items, branching and evidence rules.
- `dogfood-v6-items.yaml` — six fresh debug-only boundary cases.
- `tally-v7-legacy.md` — exact conceptual delta from v6 to the final Tally v7 and the reason the Tally surface was retired.

We deliberately do **not** rewrite the v6 spec and pretend it was always v7. Historical artifacts stay historical.

## Reproducibility rule

Any form used for a scientific annotation run MUST be versioned before the first eligible annotator opens it and bound to:

- ontology version + hash;
- item corpus + hash;
- presentation-language translations + provenance/version;
- annotation instructions + hash;
- presentation ordering/mapping;
- eligibility contract;
- response schema;
- form/app spec + hash.

Once the first annotator opens the scientific package/form, edits create a new run/version. Prototype dogfooding submissions do not count as scientific annotations and do not start this freeze.

## Why keep hosted prototypes in Git

A hosted form can change while retaining the same URL. Git gives us an auditable answer to: **what exactly was the respondent instructed to do and what stimuli could they see at a given revision?**

A hosted surface is therefore never accepted as the sole provenance record.
