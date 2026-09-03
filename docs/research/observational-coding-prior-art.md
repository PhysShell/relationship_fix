# Observational coding prior art for BehaviorOntology

Status: research note. This document records construct provenance and adaptation boundaries. It is **not** permission to copy copyrighted coding manuals verbatim and it does not make Relationship Fix labels validated merely by citation.

## Executive conclusion

The current BehaviorOntology is not scientifically isolated. Several labels have close predecessors in established couple-interaction observational coding systems:

| Relationship Fix | Primary prior art | Relationship |
|---|---|---|
| `B.BLAME_CRITICISM` | CIRS/CIRS2 `Blame` | event-level adaptation; SPAFF `Criticism` is supplementary construct support |
| `B.PRESSURE_FOR_CHANGE` | CIRS/CIRS2 `Pressure for Change` | close adaptation |
| `B.VALIDATION` | IDCS-CMC `Support/Validation`; SPAFF `Validation` | CMC-focused adaptation |
| `B.REPAIR_ATTEMPT` | Repair Attempts Observational Coding System | deliberately collapsed super-category over a richer repair family |
| `B.WITHDRAWAL` | CIRS/CIRS2 `Withdrawal`; IDCS-CMC `Withdrawal` | construct-aligned, but unit mismatch; deferred from utterance-only pilot |
| `B.AVOIDANCE_TOPIC_SHIFT` | CIRS/CIRS2 `Avoidance` | event-level adaptation |

The scientific claim should therefore be:

> We select established observational constructs, adapt them to text/CMC and smaller units of analysis, document each adaptation, and then test whether the adapted definitions remain independently annotatable.

Not:

> We invented five psychologically meaningful categories and citations happen to resemble them.

## 1. CIRS / CIRS2

The Couples Interaction Rating System is especially relevant because the demand/withdraw literature operationalizes constructs very close to our current negative-interaction labels. Published papers using CIRS describe demand through `Blame` and `Pressure for Change`, and withdrawal through `Withdrawal`, `Avoidance`, and reverse-coded discussion/engagement.

Useful public descriptions:

- Christensen/Heavey demand-withdraw operationalization and later CIRS studies: https://pmc.ncbi.nlm.nih.gov/articles/PMC3014221/
- Related CIRS coding descriptions in couple-conflict work: https://pmc.ncbi.nlm.nih.gov/articles/PMC7891293/

### Mapping

#### `B.BLAME_CRITICISM`

Primary origin: CIRS `Blame`.

Borrowed semantic core:
- assigning responsibility/blame to the partner;
- criticism/negative evaluation directed at the partner;
- character-attack/generalizing forms are strong observable cues.

Relationship Fix adaptation:
- binary/multi-label event decision rather than global/session rating;
- evidence span required;
- observable text only;
- benign/playful insult is explicitly excluded when context supports that reading;
- no personality inference.

SPAFF `Criticism` is useful as supplementary construct support, but it should not be treated as identical because SPAFF incorporates affective/nonverbal information unavailable in plain text.

#### `B.PRESSURE_FOR_CHANGE`

Primary origin: CIRS `Pressure for Change`.

Borrowed semantic core:
- requests/demands/nagging or related pressure intended to obtain behavioral change;
- distinction from blame, which attacks/evaluates rather than merely presses for change.

Relationship Fix adaptation:
- neutral one-off requests are excluded to prevent ordinary logistics from being coded as pressure;
- unit is utterance/turn;
- exact text evidence required.

#### `B.WITHDRAWAL`

Primary origin: CIRS `Withdrawal`; supplementary CMC prior art: IDCS-CMC `Withdrawal`.

Important unit constraint:
- withdrawal is often inferred from participation across an exchange, latency/non-uptake, reduced engagement, or refusal to continue;
- therefore an isolated short reply is insufficient by design.

Relationship Fix policy:
- allowed only at turn/exchange level;
- deferred from the utterance-only pilot;
- a declared timeout with a concrete return is excluded.

This is a substantive design choice, not a missing implementation detail.

#### `B.AVOIDANCE_TOPIC_SHIFT`

Primary origin: CIRS `Avoidance`.

Borrowed semantic core:
- active evasion of problem discussion through topic changes, diversion, hesitation or indefinite delay.

Relationship Fix adaptation:
- narrower text-visible subset: observable topic shift/diversion/indefinite deferral;
- a short/cold answer is not enough;
- concrete postponement with an explicit return is excluded;
- context must establish that a topic was actually raised before a `topic shift` can be coded.

### Critical confound: topic shift can have different functions

A topic shift is not intrinsically avoidance. Repair literature includes strategies that can interrupt or redirect a destructive conflict sequence. Therefore Relationship Fix must code the **observable relation to the raised topic and surrounding sequence**, not `topic changed => avoidance`.

Challenge cases should explicitly distinguish:

```text
raised issue -> unrelated diversion with no uptake
    => candidate avoidance

escalating conflict -> explicit de-escalation / mutually accepted pause / concrete return
    => not automatically avoidance; may belong to repair family
```

This is one reason event labels still require context.

## 2. IDCS-CMC: unusually close prior art for text chat

Martha S. Rackets, *The Development of a Couple Observational Coding System for Computer-Mediated Communication* (University of Kentucky, 2020):

- landing page: https://uknowledge.uky.edu/hes_etds/85/
- dissertation/manual copies may also circulate elsewhere; use the institutional source as canonical bibliographic reference.

The work adapts the Interactional Dimensions Coding System to computer-mediated romantic-couple conversations. Dimensions include `Support/Validation`, `Withdrawal`, `Conflict`, communication skills, affect and other interactional dimensions. The dissertation is particularly relevant because it discusses cues specific to text/CMC rather than assuming face-to-face prosody and body language.

### `B.VALIDATION`

Primary prior art for our text-focused definition: IDCS-CMC `Support/Validation`.
Supplementary prior art: SPAFF `Validation`.

Borrowed semantic core:
- observable acknowledgement/understanding of the partner's experience or position;
- paraphrase/listening/support cues can contribute;
- acknowledgement of receipt alone is not necessarily validation.

Relationship Fix adaptation:
- isolate validation from broader `support` where possible;
- binary/multi-label event decision instead of a global dimension score;
- exact evidence span;
- no assumption that `I understand`, `ok`, `I see`, etc. automatically validates the experience.

### Reliability warning rather than source rejection

The CMC adaptation also illustrates that some dimensions are harder to code reliably than others. In particular, `Withdrawal` was problematic relative to several other dimensions in that study. That does **not** prove withdrawal is invalid; it strengthens our decision to avoid forcing it into an utterance-only micro-pilot.

## 3. Repair Attempts Observational Coding System

Relevant sources:

- Tabares, Driver & Gottman chapter on the Repair Attempts Observational Coding System: https://www.taylorfrancis.com/chapters/edit/10.4324/9781410610843-17/repair-attempts-observational-coding-system-measuring-de-escalation-negative-affect-marital-conflict-amber-tabares-janice-driver-john-gottman
- later repair/process work: https://www.tandfonline.com/doi/full/10.1080/08975353.2015.1038962

The repair literature treats `repair attempts` as a family of strategies rather than one tiny lexical pattern. Published coding systems distinguish multiple repair forms and partner responses.

### `B.REPAIR_ATTEMPT`

Relationship Fix intentionally **lumps** these forms into one broad early-stage code:

- apology / taking responsibility;
- explicit restart;
- observable de-escalation;
- tension-directed affiliative/humorous move when the function is visible in context.

This is a pragmatic v0 choice. The label must not imply:

- that the repair succeeded;
- that every apology is repair (`sorry, but you started it` is a counterexample);
- that every joke/topic change is repair;
- that the actor's private intention is known.

Repair *success* belongs to a derived transition/trajectory layer (`T.*`).

Future data may justify splitting `B.REPAIR_ATTEMPT` into established repair subtypes. Do not split merely because a manual contains many categories; require prevalence, reliability and product utility.

## 4. SPAFF

SPAFF is useful for construct ancestry, especially `Validation` and `Criticism`, but is not a ready-made text annotation manual. SPAFF coding traditionally uses verbal content together with affective, vocal, facial or other observable cues.

Example overview source:
https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2023.980739/full

Policy:
- cite SPAFF as construct support;
- do not silently import nonverbal criteria into text-only labels;
- do not claim SPAFF equivalence for our message-level codes.

## 5. Granularity warning: more labels are not automatically better

Relationship coding research has repeatedly faced the tradeoff between many specific codes and broader dimensions. Rare narrow codes can become hard to estimate reliably and may collapse empirically into broader factors.

Relevant RMICS/RMICS2 examples:
- multisite observational aggregation work: https://pubmed.ncbi.nlm.nih.gov/33180516/
- RMICS2 description/application: https://pmc.ncbi.nlm.nih.gov/articles/PMC10656039/

Relationship Fix policy:

> New labels enter the active ontology because they add independently annotatable and product-relevant information, not because psychology has a noun for them.

This applies directly to candidate concepts such as passive aggression. Prefer observable components and trajectory hypotheses over identity/motive labels.

## 6. Provenance contract for ontology labels

Starting with the next ontology candidate, each label should distinguish:

```json
{
  "construct_provenance": [
    {
      "system": "CIRS",
      "source_code": "Pressure for Change",
      "relation": "adapted_from",
      "citation_url": "...",
      "borrowed_semantics": ["..."],
      "adaptation_notes": ["..."]
    }
  ]
}
```

Allowed `relation` values for now:

- `adapted_from`: source construct is a direct ancestor but unit/rules were adapted;
- `construct_aligned`: conceptually close supporting construct, not treated as equivalent;
- `inspired_by`: weaker design inspiration;
- `contrast_only`: source is useful primarily for a boundary/counterexample.

`source_frameworks` may remain as a short compatibility field, but it is not sufficient provenance by itself.

## 7. Copyright / wording policy

A source manual being academically available does not make its wording public domain.

For respondent-facing and commercial artifacts:

1. preserve bibliographic provenance;
2. extract the construct and operational distinctions;
3. write our own concise operational wording;
4. write independent examples or use separately licensed/public stimuli;
5. quote source manuals only minimally where legally appropriate and clearly attributed;
6. keep any source-manual excerpts out of product-facing assets unless licensing has been reviewed.

This keeps the useful science while avoiding a product whose core intellectual property is Ctrl+C with a citation attached.

## 8. What remains genuinely ours and must be validated

Even with established construct ancestry, the following are Relationship Fix design choices and need empirical validation:

- utterance/turn/exchange unitization;
- multi-label rather than single global ratings;
- exact evidence-span requirement;
- `assigned / none_observed / abstained` epistemic decision model;
- observable-text-only restriction;
- multilingual RU/EN adaptation;
- retrieval over long chat archives;
- trajectory composition (`B.* -> T.*`);
- counterevidence requirements;
- participant elicitation and provenance separation;
- calibrated finding publication.

Citing a validated source construct does not validate these adaptations. The human pilot exists precisely to test the first layer of that bridge.
