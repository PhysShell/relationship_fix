# Annotation form artifact

This directory versions the UX prototype currently rendered in Tally.

## Current render target

- Tally form id: `kdP6do`
- Public URL: https://tally.so/r/kdP6do
- Recorded revision: `v4`
- Status: **UX prototype only; not the frozen scientific annotation run**

The repository specification is canonical. Tally is a presentation/rendering surface.

## Files

- `form-spec.yaml` — provider-neutral semantic specification of the current form: instructions, categories, items, branching and evidence rules.
- A provider-specific raw snapshot may be added later if export tooling becomes available in a stable machine-readable format. The semantic spec is preferred over depending on unstable Tally block UUIDs.

## Reproducibility rule

Any form used for a scientific annotation run MUST be versioned before the first eligible annotator opens it and bound to:

- ontology version + hash;
- item corpus + hash;
- presentation-language translations + provenance/version;
- annotation instructions + hash;
- presentation ordering/mapping;
- eligibility contract;
- response schema;
- form spec + hash.

Once the first annotator opens the scientific package/form, edits create a new run/version. Prototype dogfooding submissions do not count as scientific annotations and do not start this freeze.

## Why keep this in Git

A hosted form can change while retaining the same URL. Git gives us an auditable answer to: **what exactly was the respondent instructed to do and what stimuli could they see at a given revision?**

The hosted form is therefore never accepted as the sole provenance record.
