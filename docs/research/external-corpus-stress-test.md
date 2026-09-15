# External corpus stress-test for the Relationship Fix annotation ontology (2026-09-15)

Status: research/evaluation only. This document does not modify, regenerate, or contaminate the sealed pilot, and it does not add, remove, or edit any label in `data/ontology/`. Every proposed idea below is a proposal, external to the active pilot. Guardrails from the task brief were followed: no pilot artifact was touched, no external example was merged into corpus data, no model was trained or fine-tuned, and no LLM-generated dialogue was treated as evidence of natural human behavior.

Companion files: [external-corpus-crosswalk.csv](external-corpus-crosswalk.csv) · [external-stress-sample.jsonl](external-stress-sample.jsonl) · [external-corpus-license-matrix.md](external-corpus-license-matrix.md).

Crosswalk target: the actual operational definitions, inclusion/exclusion criteria and examples in `data/ontology/behavior-v0.1.json` (the active pilot ontology, six labels, one — `B.WITHDRAWAL` — deferred from the active pilot per its own `pilot_status`), not any remembered paraphrase and not `behavior-v0.2-candidate.json` (read for context, not the crosswalk target).

## Evidence discipline used throughout

- **VERIFIED** — read directly from a primary artifact (dataset card, repository file, paper text, or this repo's own files) during this research pass.
- **INFERENCE** — this project's interpretation, judgment call, or crosswalk reasoning built on top of VERIFIED material.
- **OPEN** — could not be reliably determined in this pass; flagged rather than guessed.

---

## 1. Executive summary

**Strongest finding.** A repeated, independently-occurring construct exists in two unrelated external corpora (BenSyc, Bengali Reddit; Relationship Advice, English Reddit) that the current Relationship Fix ontology cannot represent without distortion: **treating a stated concern or feeling as illegitimate or trivial — via calm dismissal, minimization, or mockery — without a generalizing personal attack.** Under `data/ontology/behavior-v0.1.json` today this pattern is not `B.BLAME_CRITICISM` (its inclusion criteria require generalization or a negative characterization of personality/pattern, and its own exclusion criteria explicitly route a non-generalizing complaint about a single episode to "this may be `B.PRESSURE_FOR_CHANGE` or nothing" — §Special investigation: invalidation, below, works through this line by line). It is not `B.VALIDATION`'s absence either — RF's own protocol is explicit that "none observed" is the ordinary, valid, most common outcome, not evidence of a distinct negative construct. The two are different claims, and the evidence below supports the stronger one: a repeatable **NO_MATCH**, not a soft "sort of covered."

That said, applying this project's own decision rule (§7 below) in full, this finding clears the "occurs repeatedly / current categories distort it / matters to the product" tests but has **not** cleared the reliability test: the same document trail that surfaces this gap (`docs/annotation-protocol-v0.md` §7, `docs/research/dialogue-naturalness-gate.md`) already shows that the *adjacent* boundary — generalizing vs. non-generalizing criticism — is one of the hardest, most confusable distinctions the current five-label micro-pilot has to get through, and that contempt/sarcasm was deliberately excluded from v0.1 for exactly this reliability reason. Adding a sixth boundary-adjacent construct before the first micro-pilot cycle completes would repeat a known failure mode, not avoid one.

**Overall verdict: B — potential gap found, needs post-pilot investigation.** Not A (there is a real, reproducible gap, not "no gap"). Not C (the current sealed pilot must not be touched or reopened over this — the finding is real but not urgent enough, nor validated enough on reliability grounds, to justify disturbing a live pilot).

**Datasets worth keeping (with a specific, scoped role):**
- **BenSyc** — the single richest external comparison point found: an explicit five-way alignment taxonomy (Invalidation → Neutral → Support → Validation → Escalation) with human-validated labels, rationale, and evidence spans on real Reddit post/comment pairs. Role: **STRESS_TEST** for the Validation/Support boundary and the Invalidation question, **not** a donor (research-only license; not couple-specific; Bengali/Banglish).
- **Relationship Advice** (Koifman/Hari/Cohen, Technion) — the closest thing to a purpose-built comparison corpus for "what happened here / what response would be better," with a genuinely relationship-specific source (r/relationship_advice, r/dating_advice) and a pairwise helpfulness signal. Role: **METHODOLOGY reference for a future response-quality-evaluation layer**, blocked from anything further by an explicitly unknown license.
- **ESConv** — already cited in this project's own ontology (`source_frameworks` for `B.VALIDATION`) and science map. This pass adds a delta: its eight-strategy decomposition of "support" is useful ammunition for the Validation/Support/Advice/Empathy section (§6) precisely because it shows a finer-grained published taxonomy splitting apart things RF currently keeps together or leaves out entirely (advice, self-disclosure, solicitation).
- **AnnoMI** — methodology-only, as instructed: a well-documented existence proof that fine-grained utterance-level subtype coding (exists/subtype flag pairs, annotator ID tracking) is workable at scale; explicitly not a construct source for romantic-partner behavior.

**Datasets worth dropping:** ProsocialDialog (generic toxicity/social-norm taxonomy, not couple-specific, adds no crosswalk value beyond what's already in the CIRS/SPAFF provenance work this project already has); LLM Council / Emotional Application (LLM-generated content — excluded by this project's own guardrails regardless of its permissive license); EmpatheticDialogues (already assessed in this repo's prior donor-corpus work — CC BY-NC 4.0, crowd-acted, "therapeutic register" — not re-derived here, no new information changes that verdict).

**License blockers, in one line each:** BenSyc is research/evaluation-only despite an arXiv page badge that could be misread as CC BY 4.0 (that badge covers the *paper*, not the dataset). Relationship Advice's license is explicitly `unknown` on its own dataset card — marked **NOT CLEARED FOR INGESTION** per the task's own instruction. ESConv's own GitHub repository contains an internal conflict between its `LICENSE` file (CC BY-NC 4.0) and its README ("academic research use only") — treated fail-closed as the more restrictive reading. Full detail in [external-corpus-license-matrix.md](external-corpus-license-matrix.md).

---

## 2. Dataset cards

### 2.1 BenSyc — Tier 1

- **Source**: Noshin, Dip, Prangon, Tamim, Ahmed, Zhang, Sultana. *BenSyc: Benchmarking Conversational Sycophancy and Human Alignment in LLMs for Bengali Contexts.* arXiv:2606.10061 (2026). Dataset mirror: `Sajib-006/bensyc` on Hugging Face; released via an "anonymized Zenodo repository" per the paper.
- **Size**: 11,840 Reddit posts and ~170k comments collected → 1,078 human-validated post–comment pairs retained (five-class subset ~1,037 after cleaning). VERIFIED, read from paper text.
- **Language**: Bengali, Banglish (Romanized Bengali), and English, code-mixed. VERIFIED.
- **Natural/synthetic/mixed**: Natural — real Reddit posts and real top comments, not LLM-generated. (LLM involvement is confined to a *labeling-assistance* role — GPT-5.5 proposes labels that two human annotators review/correct/overrule — not text generation. This is a different use of LLMs than the guardrail against treating LLM-generated dialogue as evidence of natural behavior; the dialogue itself is human-authored.) VERIFIED.
- **Annotation type**: Two native Bengali-speaking CS/NLP researchers, two-stage (binary sycophantic/non-sycophantic, then five-class), LLM-assisted first pass with mandatory human validation/override, ambiguous cases discussed to consensus or dropped rather than forced. Fields per example (per the HF dataset card): `post_text`, `selected_comment`, `binary_label`, `five_class_label`, `human_validated_rationale`, `human_validated_evidence_annotation`, `evidence_is_exact_span`, `example_id`, `subreddit`, `region`, `split`. VERIFIED for taxonomy/process from paper text; the exact field-name list is **INFERENCE** carried from a single automated dataset-card summarization pass on the HF page and was not independently re-verified against the raw parquet in this session — flagged OPEN for anyone relying on exact field names for tooling.
- **Relevant labels**: Invalidation, Neutral, Support, Validation, Escalation — mutually exclusive per the paper. Two human annotators reached Cohen's κ=0.76 on fine-grained labels on a validation subset (reported in the paper as "substantial agreement... before adjudication," most disagreement between Support and Validation) — VERIFIED from paper text read directly (§5.5 Human–LLM Judge Agreement).
- **License verdict**: **RESEARCH_ONLY_OR_RESTRICTED** (see license matrix; conflicting surfaces between arXiv's article-level CC BY 4.0 badge and the dataset card's explicit `other` + research-only restriction).
- **Relevance to Relationship Fix**: Moderate, not high — the corpus spans general Bengali/Bangladeshi and West Bengali social discourse (politics, career exams, dating, breakups, friendship), and only a minority of the sampled/inspected material is actually about a romantic dyad. Table 1's own five canonical examples include one about politics and one about a civil-service exam.
- **Recommended role**: **STRESS_TEST** for the Validation/Support boundary and dedicated input to the Invalidation investigation (§5, §6). Not a donor corpus (wrong language/register for this project's ru/en pilot, and licensed research-only regardless).

### 2.2 Relationship Advice — Tier 1

- **Source**: Koifman, Hari, Cohen. *Relationship Advice dataset card*, `yonatanko/Relationship_Advice` on Hugging Face — a course project for the NLP Research course, Data Science & Decisions Faculty, Technion. Not a peer-reviewed paper; no separate publication found. VERIFIED (dataset card is explicit about this provenance).
- **Size**: 400 posts sampled from r/dating_advice and r/relationship_advice (2022–2024), each with exactly two comments → 400 examples total (210 train / 40 validation / 150 test). VERIFIED.
- **Language**: English. VERIFIED.
- **Natural/synthetic/mixed**: Natural — genuine Reddit posts and comments, anonymously authored by real users; not LLM-generated. VERIFIED.
- **Annotation type**: Three escalating-quality batches. Batch 1 ("exploration," 80 items): the three dataset owners annotate to develop guidelines. Batch 2 ("evaluation," 80 items): two owners annotate per the drafted guidelines. Batch 3 ("part 3," 240 items, the highest-quality batch and the sole source of the test split): four external annotators (1 male, 3 female, ages 22–27, fellow Technion students, not dataset owners) annotate per finalized guidelines, after a 30-item guideline-refinement round. No inter-annotator agreement statistic (kappa/alpha) is reported anywhere on the card — VERIFIED absence, read the full README directly.
- **Relevant labels (Task 1, per-comment)**: Practical Advice, Emotional Support, Commentator's Opinion, Hurtful, Sarcasm, Not Relevant — exactly the six named in the task brief, confirmed verbatim on the primary card. **(Task 2, pairwise)**: `more_helpful_comment` ∈ {Comment 1, Comment 2} — a genuine pairwise helpfulness judgment made by the same annotators who saw both comments and the post together, not derived from Reddit upvote scores.
- **License verdict**: **UNKNOWN — explicitly marked NOT CLEARED FOR INGESTION** per task instruction. The dataset card's own YAML frontmatter states `license: unknown`; this is a direct declaration, not an absence to be filled in by inference.
- **Relevance to Relationship Fix**: High for the response-quality/advice question the task explicitly names ("what happened here / what response would be better"); low-to-none for the core BehaviorOntology crosswalk itself, because every label in this dataset describes a bystander-advisor's response to a stranger's post, not one partner's observable behavior toward the other (§4 works through why this matters for every label).
- **Recommended role**: **METHODOLOGY reference** for a future response-quality-evaluation layer (the pairwise-helpfulness task design is directly reusable as a template), contingent on either (a) the license being clarified with the actual authors, or (b) building an equivalent instrument from scratch using this dataset only as a design reference, not as reused text.

### 2.3 ProsocialDialog — Tier 2

- **Source**: Kim et al., *ProsocialDialog: A Prosocial Backbone for Conversational Agents*, EMNLP 2022 (arXiv:2205.12688). Official Ai2 HF org page `allenai/prosocial-dialog`.
- **Size**: 58K dialogues / 331K utterances / 160K unique rules-of-thumb / 497K safety labels with rationales.
- **Language**: English.
- **Natural/synthetic/mixed**: Mixed by design — GPT-3 generates the *unsafe* prompting utterance, crowdworkers write the *prosocial response*; source utterances are seeded from SBIC, Social Chemistry 101, raw Reddit, and the ETHICS dataset.
- **Annotation type**: Crowd-annotated safety labels (`casual`, `needs_caution`, `needs_intervention`, etc.) with free-form rationale, plus rules-of-thumb (RoTs) grounding each response.
- **License verdict**: **CLEAR_COMMERCIAL** for the Ai2-released layer (CC-BY-4.0, official org page); component upstream sources not independently re-verified (flagged OPEN, judged out of scope given the DROP recommendation).
- **Relevance to Relationship Fix**: Low. This is a generic social-norm/toxicity-severity taxonomy (bias, hate speech, unsafe advice, ethics violations), not a romantic-relationship-specific behavior taxonomy, and its "problematic utterance → prosocial response" pairing structure adds nothing this project doesn't already have from its own CIRS/SPAFF/repair-attempt provenance work (`docs/research/observational-coding-prior-art.md`).
- **Recommended role**: **DROP.**

### 2.4 ESConv — Tier 2

- **Source**: Liu et al., *Towards Emotional Support Dialog Systems*, ACL 2021. Primary repo: `thu-coai/Emotional-Support-Conversation` on GitHub.
- **Size**: 1,053 dialogues (per the paper; not independently re-counted this session — carried from prior knowledge, flagged as an unverified figure not directly re-checked this pass).
- **Language**: English.
- **Natural/synthetic/mixed**: Crowd-*enacted* — trained crowd workers play "supporter" and "help-seeker" roles in a structured protocol (pre-chat survey, staged exploration → comforting → action conversation), not spontaneous naturally occurring dialogue and not LLM-generated.
- **Annotation type**: Turn-level strategy labels (8 strategies: Reflection of Feelings, Self-Disclosure, Question, Affirmation and Reassurance, Providing Suggestions, Restatement or Paraphrasing, Information, Other), plus conversation-level help-seeker emotional-intensity change and post-survey empathy/relevance ratings.
- **License verdict**: **RESEARCH_ONLY_OR_RESTRICTED** — see license matrix for the internal conflict between the repo's `LICENSE` file (CC BY-NC 4.0) and its README ("academic research use only").
- **Relevance to Relationship Fix**: Already established in this project — `data/ontology/behavior-v0.1.json` cites `"ESConv (affirmation/reflection)"` as a `source_frameworks` entry for `B.VALIDATION`, and `docs/research/science-map.md` already lists ESConv as a "taxonomy candidate for coach-mode." This pass's delta: ESConv's granularity (8 strategies) is more useful as a *decomposition tool* for §6 than as new construct-provenance, because it shows several observable acts (advice-giving, self-disclosure, solicitation) that a published, cited framework treats as **distinct from** validation/affirmation — exactly the conflation risk the task asks about.
- **Recommended role**: **METHODOLOGY** (already in active use as construct provenance; this pass adds the delta above, does not replace it).

### 2.5 AnnoMI — Tier 2

- **Source**: Wu, Balloccu, Kumar, Helaoui, Reforgiato Recupero, Riboni. *Creation, Analysis and Evaluation of AnnoMI, a Dataset of Expert-Annotated Counselling Dialogues.* Future Internet 15(3):110 (2023); earlier version at ICASSP 2022. Primary repo `uccollab/AnnoMI` on GitHub.
- **Size**: 133 transcribed motivational-interviewing sessions (110 high-quality, 23 low-quality, per the paper), utterance-level rows.
- **Language**: English (transcribed from source video/audio).
- **Natural/synthetic/mixed**: Natural — real (or realistically enacted, in some source videos) counselling sessions published as demonstration videos, faithfully transcribed; not LLM-generated.
- **Annotation type**: The methodologically interesting part. `AnnoMI-simple`: per-utterance `main_therapist_behaviour` ∈ {reflection, question, therapist_input, other} for therapist turns, `client_talk_type` ∈ {change, neutral, sustain} for client turns, plus a session-level `mi_quality` ∈ {high, low}. `AnnoMI-full` adds `exists`/`subtype` flag pairs per attribute (e.g. `reflection_exists` + `reflection_subtype` ∈ {simple, complex}) and an `annotator_id` field for traceability. VERIFIED, read directly from the repository README.
- **License verdict**: **CLEAR_COMMERCIAL for the annotation/transcript layer if the reported CC0 statement is accurate — flagged OPEN pending a primary re-read** (see license matrix; the MDPI Data Availability Statement could not be independently re-opened in this session and the claim rests on a secondary description of it).
- **Relevance to Relationship Fix**: Methodology only, as the task instructs — counselling-client change-talk does not transfer to romantic-partner behavior, and this project does not treat it as if it did. What transfers is the *annotation-scheme pattern*: exists/subtype pairs, per-attribute rather than per-utterance labels, explicit annotator-ID provenance, and a documented high/low quality axis independent of the fine-grained labels.
- **Recommended role**: **METHODOLOGY.**

### 2.6 EmpatheticDialogues — optional, already assessed

Not re-investigated per the task's own instruction to avoid duplicating completed prior work. Carried forward verbatim from `data/pilot/naturalness-ab/v0-flagged-donor/donor-report.md`: CC BY-NC 4.0, crowd-*acted* empathy responses to a described emotional situation, already flagged in that document as risking a "therapeutic register" (the same register risk this project's own naturalness-gate work independently diagnosed in its own pilot items). No new information from this pass changes that verdict. **Recommended role: DROP** (as donor; unchanged from prior finding).

### 2.7 LLM Council / Emotional Application — optional

Briefly checked (`llm-council/emotional_application` on Hugging Face): CC-BY-4.0, but consists of LLM-generated responses to emotional dilemmas across personal/social contexts including some relationship scenarios. This project's own guardrails explicitly forbid treating LLM-generated examples as evidence of natural human dialogue, independent of licensing. **Recommended role: DROP** — the permissive license is moot given the content-type disqualification.

---

## 3. What "annotated" actually means in each Tier-1 dataset — the cross-cutting caveat

Before the crosswalk, one structural fact governs almost every row in it and is worth stating once instead of repeating in every cell: **every RF BehaviorOntology label describes one romantic partner's observable action toward or with the other partner inside a real exchange** (`directionality: other_directed` or `interaction_directed` in every label of `behavior-v0.1.json`). **Neither BenSyc nor Relationship Advice annotates that relationship.** Both annotate a **bystander's response to a stranger's self-disclosed situation** — a Reddit commenter reacting to a poster's post, not a partner reacting to their own partner. This is not a minor caveat; it is the single fact that determines whether most individual label pairs below are `CONSTRUCT_MISMATCH` or something weaker.

Two consequences follow, and both are used repeatedly in §4 and the CSV:

1. Labels whose surface *form* looks identical to an RF marker (a blunt personal insult, an explicit acknowledgment of feeling) can still be `CONSTRUCT_MISMATCH` rather than `CLEAN_MATCH`, because RF's scope restriction to the dyad is a deliberate project design choice, not a linguistic fact about the words used. The stress sample documents this directly (`example_id 178`, a bystander calling the poster "a scumbag" — lexically identical in form to `B.BLAME_CRITICISM`'s marker set, but structurally outside the ontology's scope).
2. This is exactly *why* BenSyc and Relationship Advice are more naturally suited to a future **response-quality-evaluation layer** ("given this situation, is this response supportive / dismissive / escalatory / helpful?") than to direct stress-testing of the six-label dyadic BehaviorOntology as it currently exists. The task's own framing anticipates this ("Could it support the future Relationship Fix layer: 'what happened here?' / 'what response would be better?'") — the answer, based on this pass, is: **yes for the second question, only weakly for the first.**

---

## 4. Taxonomy crosswalk

Full table with sources and per-row notes: [external-corpus-crosswalk.csv](external-corpus-crosswalk.csv) (21 rows). Summary by mapping type:

| Mapping type | Count | Representative row |
|---|---|---|
| NO_MATCH | 8 | BenSyc Neutral, Relationship Advice Commentator's Opinion/Sarcasm/Not Relevant, ESConv Providing Suggestions/Self-Disclosure/Question, AnnoMI change/sustain talk |
| CONSTRUCT_MISMATCH | 6 | BenSyc Invalidation, BenSyc Escalation, Relationship Advice Practical Advice/Emotional Support/Hurtful, ProsocialDialog safety_label |
| PARTIAL_MATCH | 4 | ESConv Affirmation and Reassurance, ESConv Reflection of Feelings, AnnoMI Reflection, EmpatheticDialogues empathetic response |
| MANY_TO_ONE | 2 | BenSyc Support and BenSyc Validation both → `B.VALIDATION` |
| NOT_APPLICABLE | 1 | Relationship Advice `more_helpful_comment` (pairwise judgment, not a behavior label) |
| CLEAN_MATCH | 0 | — |
| ONE_TO_MANY | 0 | — |

**Zero `CLEAN_MATCH` rows is itself a finding worth stating plainly.** No external label from any Tier-1 or Tier-2 dataset investigated maps cleanly onto an RF category without a caveat about directionality, breadth, or construct strength. Two structural reasons: (1) the directionality caveat in §3 downgrades many form-level matches to CONSTRUCT_MISMATCH; (2) where directionality isn't the issue (ESConv, AnnoMI — genuinely dyadic-*style* speech even if not couple-specific), the external taxonomies are consistently *finer-grained* than RF's five-to-six labels, splitting validation from support from advice from self-disclosure from solicitation in ways RF's v0.1 does not attempt to. That is evidence RF's granularity choice is a deliberate simplification holding up as intended (see `docs/research/observational-coding-prior-art.md` §5, "more labels are not automatically better"), not evidence that v0.1 is wrong — but it does mean no external label is a plug-and-play validity check for any single RF label.

---

## 5. Special investigation: invalidation

The task calls this the single most useful outcome of the whole exercise and asks for a forced verdict rather than a soft "sort of covered." Working through it against the actual text of `data/ontology/behavior-v0.1.json`, not a paraphrase:

### 5.1 What BenSyc's Invalidation actually is

Read directly from the paper (§3.2.2, quoted verbatim): *"Responses categorized as Invalidation oppose, dismiss, criticize, challenge, or analytically push back against the poster's framing or emotional interpretation... Importantly, invalidation does not necessarily imply hostility. Many invalidating responses remain constructive and analytical."* This is a **broad** category: it spans calm, well-reasoned disagreement all the way to hostile dismissal, unified only by the fact that the response opposes the poster's framing rather than reinforcing it. BenSyc's own confusion-matrix data (§4.3 of the paper) shows models most often confuse Support with Escalation and Support with Neutral, not Invalidation with anything — Invalidation and Validation were, per the paper, the two *most stable* categories for models to distinguish, which is itself informative: the hard boundary in BenSyc's own data is Support-vs-something-else, not Invalidation-vs-something-else.

### 5.2 Distinguishing what the task asks to distinguish

Working through the task's own list against `behavior-v0.1.json`:

- **Disagreement** — "I don't think that's true" / "I see it differently." Not `B.BLAME_CRITICISM` (no generalization, no negative characterization of the partner). Not any other current label. Correctly falls to `none_observed` — this is healthy, ordinary conversational disagreement and RF's protocol is explicit that `none_observed` is "the most frequent and fully valid outcome, NOT abstention" (`docs/annotation-protocol-v0.md` §3). No gap here.
- **Lack of validation** — a partner states a feeling and gets no acknowledgment at all (topic changes, or the other partner simply moves on). This is silence, not an act. RF's protocol is explicit that absence of a positive label is not itself evidence of a negative construct. The task's own instruction — *"Absence of validation is not automatically invalidation"* — is already respected by the current design. No gap here.
- **Explicit invalidation** — "That's ridiculous, you're not actually upset about that" / "You're overreacting" said about a *specific, just-stated* feeling, without any generalizing claim about the partner's personality or pattern. This is the case that has **no home** in v0.1. Traced through `B.BLAME_CRITICISM`'s own exclusion criteria: *"жалоба на конкретный эпизод без генерализации (это может быть B.PRESSURE_FOR_CHANGE или ничего)"* — a complaint about a specific episode without generalization is explicitly routed to `B.PRESSURE_FOR_CHANGE` or **nothing**. "You're overreacting" is neither a complaint about the *speaker's own* treatment nor a demand for behavior change — it fails `B.PRESSURE_FOR_CHANGE`'s inclusion criteria too (no request, no demand). It lands on **nothing**: `none_observed`, despite being a directly observable, textually explicit act of rejecting the legitimacy of a stated feeling. This is a genuine `NO_MATCH`, and it is **repeatable**: two independent examples surfaced unprompted in the stress sample (`example_id-222-comment_2`, `example_id-92-comment_1`), both showing dismissal-of-a-concern's-legitimacy via mockery rather than direct criticism, and BenSyc's own five-way split independently carves out the same phenomenon as its own top-level category. Three independent sources (BenSyc's taxonomy, and two unrelated Relationship Advice examples) converging on the same uncovered pattern is stronger evidence than a single dataset's design choice.
- **Criticism/blame** — already covered by `B.BLAME_CRITICISM` when generalization or personality-level negative characterization is present. Not a gap; this is where the ontology already draws its line, correctly, per its own stated design.
- **Mockery/sarcasm** — deliberately and explicitly excluded already, for a *documented* reason: `docs/annotation-protocol-v0.md` §7 states outright, before any pilot ran, that *"contempt/sarcasm-with-hostility в онтологию v0.1 сознательно НЕ включён — ожидаемо худший по α в тексте"* (deliberately not included — expected to be the worst-performing construct on text alone). This is not a newly discovered gap; it is a known, pre-registered, deliberate omission for reliability reasons, and this pass's finding does not overturn that reasoning — if anything it reinforces it, because the two clearest external examples of "invalidation" this pass found (`example_id-222-comment_2`, `example_id-92-comment_1`) are *both* sarcasm-flavored, meaning any future INVALIDATION label would inherit the exact reliability risk sarcasm was excluded for in the first place.
- **Minimization** — "It's not a big deal," "everyone goes through that." Same analysis as explicit invalidation above: no generalization, no demand, falls to `none_observed`. Same gap, same caveat.
- **Emotional dismissal** — same pattern again; changing the subject without engaging (which *is* covered, separately, by `B.AVOIDANCE_TOPIC_SHIFT` when a topic shift actually occurs) versus staying engaged but rejecting the feeling's legitimacy (which is *not* covered by anything). This distinction between "leaves the topic" (covered) and "stays and dismisses" (not covered) is itself a useful, previously implicit boundary this investigation makes explicit.

### 5.3 Forced verdict

**Genuine, repeatable `NO_MATCH`.** BenSyc's Invalidation does not decompose cleanly into existing RF categories. The specific uncovered slice is narrower than BenSyc's own five-way category (BenSyc's Invalidation also includes plain disagreement and analytical pushback, which RF already correctly leaves as `none_observed` by design) — the real gap is the subset of BenSyc's Invalidation that is: (a) about a specific, already-stated feeling or concern, (b) non-generalizing, (c) rejects the concern's legitimacy rather than merely disagreeing with a conclusion. That subset currently has no representation at all in v0.1, and its absence is not a design choice this project has previously reasoned through and rejected the way sarcasm/contempt and `B.WITHDRAWAL`'s unit constraint were — there is no equivalent line in `docs/research/observational-coding-prior-art.md` or `docs/annotation-protocol-v0.md` addressing this specific slice. It was not previously considered, not previously declined.

### 5.4 Decision-rule test against the six criteria (§7 below, applied here specifically)

1. Occurs repeatedly across independent natural examples — **passes**: BenSyc's independently-designed taxonomy, plus two unrelated Relationship Advice examples surfaced without searching for this pattern specifically.
2. Current categories cannot represent it without distortion — **passes**: shown line-by-line against `B.BLAME_CRITICISM`'s own exclusion criteria above.
3. Different annotators could reasonably identify it from observable text — **uncertain, not tested**: this is precisely the same kind of boundary judgment (is this generalizing or not? is this dismissive or just disagreeing?) that `docs/research/dialogue-naturalness-gate.md` documents as the hardest, most naturalness-sensitive boundary already in the ontology (blame vs. pressure), and that BenSyc's own annotators found their *only* substantial disagreement zone to be the structurally similar Support/Validation boundary (§5.5 of the BenSyc paper, κ=0.76 "before adjudication," most disagreements between "semantically adjacent categories").
4. Matters to the product/research question — **passes**: directly named in the task brief, and adjacent to established literature (DBT's "invalidating environment" construct, Gottman's contempt research already cited in this project's own prior-art doc).
5. Not merely a latent motive/personality judgment — **passes if scoped narrowly** to the observable act (explicit rejection of a stated feeling's legitimacy) rather than to an inferred trait ("dismissive person"); this mirrors how `B.BLAME_CRITICISM` already stays observable rather than diagnostic (invariant 7, `docs/research/invariants.md`).
6. Adding it would improve explanatory power more than it increases annotation ambiguity — **not established**: the current five/six-label micro-pilot has not yet completed even its first cycle (`docs/annotation-protocol-v0.md` §5.1: "micro-pilot до расширения"), and the project's own prior experience is that boundary-adjacent labels are exactly where reliability breaks first (the entire `dialogue-naturalness-gate.md` document exists because boundary items kept turning into "answer keys" rather than natural speech).

Four of six tests pass; the fifth is plausible-but-unscoped; the sixth is explicitly not yet answerable because the prerequisite empirical step (a completed micro-pilot cycle) has not happened. Per this project's own default ("новых лейблов не добавлять, пока не пройдены все шесть"), that is not a green light — it is exactly what **B — needs post-pilot investigation** means.

---

## 6. Special investigation: validation vs. support vs. empathy vs. advice vs. repair vs. agreement

Building the conceptual grid the task asks for, anchored in the three example sentences it names:

| Utterance | Observable act | Closest RF label (if partner-directed) | External label(s) that would also apply |
|---|---|---|---|
| "I understand why you're upset, but…" | Acknowledges a stated feeling as understandable | `B.VALIDATION` (the "but…" clause needs separate coding — validation of the feeling does not certify what follows) | BenSyc Support *or* Validation (ambiguous which, by BenSyc's own definitions); ESConv Reflection of Feelings |
| "You should call them tomorrow and ask for a refund." | Directive suggestion | **No RF label** | Relationship Advice Practical Advice; ESConv Providing Suggestions |
| "I'm sorry. I shouldn't have said that." | Apology + taking responsibility | `B.REPAIR_ATTEMPT` | No clean external analogue found in Tier 1/2 corpora (repair-specific literature is in this project's own existing CIRS/Gottman provenance, not in BenSyc/Relationship Advice/ESConv/AnnoMI) |

These three are correctly *not* the same observable behavior, and RF's own ontology already separates the third from the first two (`B.REPAIR_ATTEMPT` vs. `B.VALIDATION`, listed as `confusable_with` each other precisely because they co-occur but aren't identical). The finding worth stating is narrower and sharper: **the first two are not obviously separated by any of the taxonomies inspected in this pass either, including RF's own.**

**Do two datasets use the same word for different constructs? Yes, repeatedly, and in a specific, checkable direction.**

- BenSyc defines **Support** and **Validation** as different constructs along a single axis — whether the response reinforces the poster's own interpretation/framing, not whether it acknowledges an emotion. Its own central methodological finding (stated as the paper's contribution) is that models confuse exactly this pair most often.
- RF's `B.VALIDATION` operational definition explicitly and deliberately does *not* require agreement with the partner's conclusions ("не обязательно соглашаясь с выводами") — meaning RF's single label is, by its own text, closer to BenSyc's *Support* definition than to BenSyc's *Validation* definition, yet RF applies one label where BenSyc uses two. **RF's `B.VALIDATION` is a `MANY_TO_ONE` target for BenSyc's Support+Validation split** (also reflected in the crosswalk CSV). Whether this collapsing is a problem or a deliberate simplification is exactly the kind of "granularity is not automatically better" tradeoff this project has already reasoned through once (`docs/research/observational-coding-prior-art.md` §5) — but it had not previously been tested against an external taxonomy that treats the split as *the* central research question. That is new information from this pass, even though the recommendation (§7) is not to split the label pre-pilot.
- **Advice is not represented as a construct anywhere in RF**, and three independent external sources (Relationship Advice's "Practical Advice," ESConv's "Providing Suggestions"/"Information," and BenSyc's Neutral category, which explicitly includes "practical advice without clear alignment") treat it as a first-class, frequently-occurring category. This is worth naming plainly even though it does not pass the decision rule for addition yet: RF's roadmap already anticipates a coach/advice-adjacent layer (`science-map.md`'s ESConv citation for "coach-mode"), so this is confirmatory of an already-planned direction, not a new discovery — but it is a discovery that the *behavior* of giving advice inside a couple's own conversation (one partner telling the other what to do) is currently uncoded even though `B.PRESSURE_FOR_CHANGE` sits right next to it conceptually (a demand for change vs. a suggestion for what to do are close but were never explicitly distinguished in the ontology's own documentation until this comparison).
- **Self-disclosure and solicitation ("what happened? tell me more") are both named as distinct strategies in ESConv but have no RF analogue at all** — not even a deferred or considered one, unlike `B.WITHDRAWAL`. This project's own protocol document already names `PERSPECTIVE_SOLICITATION` and `SUPPORT_OFFER`/`SUPPORT_RESPONSE` as unbuilt future-candidate labels (`docs/annotation-protocol-v0.md` §5.1) — so this pass's contribution is confirming, from an independent external source, that those candidates correspond to real, separately-coded constructs elsewhere, which is modest positive evidence for that already-planned future batch, not a new proposal.

**Conclusion for this section**: validation, support, empathy, advice, and repair are *not* consistently the same construct across datasets, and RF's own single `B.VALIDATION` label sits in the middle of at least two external splits (BenSyc's Support/Validation axis; ESConv's Reflection/Affirmation/Suggestion/Self-Disclosure/Question five-way split) without RF having previously had to reconcile either. This is useful, well-evidenced information for the *next* ontology batch — it is not, on its own, grounds to touch v0.1 before or during the current pilot.

---

## 7. Decision rule, applied

Per the task's own instruction, the default is **do not add a category**, and every candidate must individually clear all six tests, not benefit from a tidy external taxonomy turning into equally many new RF labels. Two candidates were seriously considered in this pass:

**Candidate: a narrow, non-generalizing "invalidation of a stated feeling" construct** (§5). Clears tests 1, 2, 4, plausibly 5; test 3 (reliable inter-annotator identification) and test 6 (net benefit vs. ambiguity) are **not yet answerable** because the prerequisite empirical step — a completed micro-pilot cycle on the current five labels — has not run. **Verdict: does not clear the bar today. Revisit after the current pilot, using its own boundary-confusion data (§4 of `docs/annotation-protocol-v0.md` already plans exactly this kind of label↔label and label↔NONE_OBSERVED confusion matrix) as the first evidence, before writing a new operational definition from scratch.**

**Candidate: splitting `B.VALIDATION` into a BenSyc-style Support/Validation pair, or an ESConv-style five-way strategy split** (§6). Does **not** clear test 6 at all: the entire point of RF's granularity policy (`docs/research/observational-coding-prior-art.md` §5, "New labels enter the active ontology because they add independently annotatable and product-relevant information, not because psychology has a noun for them") argues against pre-emptively splitting a label that has not yet been pilot-tested even in its current, coarser form, on the strength of two external taxonomies disagreeing with each other about exactly where the split should go (BenSyc: reinforcement-of-interpretation axis; ESConv: strategy-type axis — these are not the same split). **Verdict: does not clear the bar. Interesting for the ontology's next design cycle, not actionable now.**

No other candidate construct surfaced in this pass (advice, self-disclosure, solicitation, escalation-toward-a-third-party) was judged to have cleared even a majority of the six tests without first requiring a directionality reframing (partner-to-partner, not bystander-to-discloser) that none of the inspected external corpora actually provide.

### Ranked recommendations

- **P0 — investigate before ontology freeze**: **none.** Nothing found in this pass meets the bar for touching the ontology before or during the current pilot; the guardrails also explicitly forbid it regardless.
- **P1 — useful after current pilot**:
  1. Re-examine the narrow non-generalizing-invalidation gap (§5) using the current pilot's own label↔label and label↔`NONE_OBSERVED` confusion data as the first evidence source, before drafting any new operational definition.
  2. Use BenSyc's Support/Validation distinction and ESConv's strategy taxonomy as design references — not text donors — if/when `B.VALIDATION` is reconsidered for the next ontology batch (this pass does not recommend initiating that reconsideration on its own; it recommends having this comparison ready when the batch is planned).
  3. Design a small internal response-quality-evaluation pilot modeled on Relationship Advice's pairwise-helpfulness task (Task 2), built from RF's own material rather than reused Relationship Advice text (license blocks direct reuse), to test the "what response would be better?" product question the task names.
- **P2 — future product/eval work**:
  4. If a coach/advice-adjacent product surface is ever built (already anticipated in `science-map.md`), ESConv's 8-strategy taxonomy and AnnoMI's exists/subtype annotation-scheme pattern are both directly reusable design references (methodology only, license-gated for ESConv, likely-clear-pending-verification for AnnoMI).
  5. If BenSyc's license terms are ever separately negotiated with its authors (current terms are explicitly research/evaluation-only), its evidence-span + rationale annotation format is a strong template for RF's own evidence-discipline requirements.
- **DROP**: ProsocialDialog (generic, non-couple-specific, redundant with existing CIRS/SPAFF provenance); LLM Council/Emotional Application (LLM-generated content, guardrail violation regardless of license); EmpatheticDialogues (unchanged from prior internal finding — crowd-acted, therapeutic register, CC BY-NC 4.0).

---

## 8. Phase C — adversarial sample

Full records: [external-stress-sample.jsonl](external-stress-sample.jsonl) — **13 inspected examples** (5 BenSyc, 8 Relationship Advice), each with dataset, source id, external label, minimal excerpt, candidate RF label(s), a forced `clean_match | ambiguous | missing_construct | insufficient_context | not_applicable` classification, and a reasoned justification.

**Stated limitation, per the task's own Phase C allowance**: this is materially smaller than the target 50–100 examples per dataset, and the reason is the licensing findings from Phase A, not an effort shortcut. BenSyc's dataset card is explicitly research/evaluation-only and its full 1,078-example set was not downloaded or reproduced in bulk for that reason (only the paper's own five published Table 1 examples, already public in the paper text, were used). Relationship Advice's license is explicitly `unknown`; the guardrail against copying bulk dataset contents into the repository, combined with the license verdict, means only a small number of individual rows were inspected via the dataset's public viewer for analysis purposes, with minimal quotation rather than reproduction of the full 400-example set. **Neither dataset was downloaded in bulk, and no external example was merged into any pilot or corpus artifact.**

Distribution across the forced categories in the 13-record sample: `not_applicable` — 5 (topic/speaker-role mismatch, mostly BenSyc's non-relationship Table 1 examples and pure advice-giving); `ambiguous` — 4 (mostly the Support/Validation looseness from §6); `missing_construct` — 3 (the invalidation-via-mockery pattern from §5, twice independently, plus BenSyc's Escalation); `insufficient_context` — 1 (an advisor-scripted hypothetical partner utterance, `example_id-171-comment_2`, which cannot be coded because it was never actually said); `clean_match` — 0.

Zero `clean_match` records out of 13 is consistent with §4's zero-`CLEAN_MATCH` crosswalk finding and is not an artifact of a small sample — it follows directly from the structural directionality mismatch documented in §3, which applies regardless of sample size.

---

## 9. Final answer

**B. Potential gap found, needs post-pilot investigation.**

A real, repeatable construct — non-generalizing invalidation of a stated feeling, distinct from disagreement, distinct from mere absence of validation, distinct from generalizing blame/criticism, and distinct from the already-excluded sarcasm/contempt construct — is not representable in `data/ontology/behavior-v0.1.json` without distortion, and this is supported by convergent evidence from BenSyc's independently-designed taxonomy and two unrelated Relationship Advice examples. It clears four of the six tests in this project's own decision rule outright. It does not clear the reliability test (annotator identifiability) or the net-benefit test (explanatory power vs. added ambiguity), because the prerequisite empirical step — a completed cycle of the current five/six-label micro-pilot — has not happened yet, and this project's own documented history (the entire naturalness-gate exercise, the pre-registered exclusion of sarcasm/contempt) shows that boundary-adjacent constructs are exactly where this ontology's reliability problems have concentrated so far. The current sealed pilot must not be reopened, modified, or rebalanced over this finding. It should be the first thing re-examined, using the pilot's own confusion-matrix data, once that pilot cycle completes.
