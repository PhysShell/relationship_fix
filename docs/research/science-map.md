# Научная карта Relationship Engine

Источники сгруппированы по слоям engine. Для каждого фиксируется: что это, что можно взять, и что **нельзя** из него заключать. Статус «есть paper/product» не равен валидности конкретного product claim.

```
RELATIONSHIP ENGINE
        │
 ┌──────┼──────────┬───────────┐
 │      │          │           │
OBSERVATION    DYNAMICS      MEMORY
 │      │          │           │
 └──────┴────┬─────┴─────┬─────┘
             │           │
         EVIDENCE   SUBJECTIVITY
             │           │
         FAITHFULNESS
             │
             └──────────┬──────────────┐
                        ▼              ▼
                     FINDING       SAFETY GATE
                        │
                 INTERVENTION
                        │
                    OUTCOME/EVAL
```

## UMBRELLA — GenAI как «третий голос» в паре

- **[Generative AI as a third voice in human couple relationships: A systematic review](https://www.sciencedirect.com/science/article/pii/S2451958826003295)** (Computers in Human Behavior Reports, 2026) — systematic review 21 studies (2024–2026) про AI как advisor/mediator в human-human relationships. Отмечает одновременно perceived helpfulness/empathy и слабости reliability/risk assessment, а также необходимость longitudinal, dyadic и safety-focused work. **Взять:** umbrella framing проекта и список рисков; **не брать:** доказательство эффективности конкретного AI coach.
- **[“Chat, Should I Leave Him?” Risks, Rewards, and Roles for AI in Relationship Advice](https://www.microsoft.com/en-us/research/publication/chat-should-i-leave-him-risks-rewards-and-roles-for-ai-in-relationship-advice/)** (CHI 2026) — реальные пользователи AI для sex/dating/relationship advice; sycophancy, overreliance, folk theories и пользовательские tactics против ограничений модели. **Взять:** domain-specific threat model для advice/replay UX.

## OBSERVATION — что считать наблюдаемым поведением

- **CIRS — Couples Interaction Rating System** (Heavey/Gill/Christensen) — operationalized demand-withdraw: blame, pressure for change, withdrawal, avoidance и др. [Пример применения](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3728718). **Взять:** основу BehaviorOntology v0; не переносить исследовательские scales напрямую в consumer diagnosis.
- **BOLT / behavioral-data** — multi-label coding психотерапевтических conversational techniques. **Взять:** `utterance → несколько labels`, а не один mutually-exclusive verdict.
- **[ESConv](https://aclanthology.org/2021.acl-long.269/)** — emotional-support strategies и staged support dialogue. **Взять:** taxonomy candidate для coach-mode, не доказательство эффективности в парах.
- **USC SAIL / Couples behavioral coding** — родословная автоматического behavioral coding пар. [Один из foundational sources](https://www.sciencedirect.com/science/article/abs/pii/S0167639311001762). **Взять:** task formulations/taxonomies; сам Couples Therapy Corpus не использовать без ясной лицензии.
- **ConvoKit** — corpus representation, speaker/context features, linguistic coordination. **Взять:** laboratory toolbox, не продуктовый фундамент.

## DYNAMICS — паттерн как траектория

- **[State Space Grids, 2024](https://www.tandfonline.com/doi/full/10.1080/19312458.2024.2413973)** — dyadic conversation как trajectory по state grid; доступны flexibility/transitions/attractor-like descriptions. **Взять:** representation и UI primitive. **Оговорка:** опубликованные metrics не дают автоматической predictive validity для нашей задачи. Synthetic corpus может проверить reconstruction (E0), но construct validity требует real dyadic data + blind annotation (E1).
- **Repair research** — repair определяется outcome перехода, а не только красивой репликой; affective repairs (humor, affection, self-disclosure, understanding, responsibility) — кандидаты для ontology/intervention logic. [Driver & Gottman](https://www.researchgate.net/publication/281415188_Repair_During_Marital_Conflict_in_Newlyweds_How_Couples_Move_from_Attack-Defend_to_Collaboration). **Взять:** искать transitions, которые исторически обрывали негативную петлю; не утверждать причинность без experiment design.
- **[RELATE-Sim](https://arxiv.org/abs/2510.00414)** — LLM-agent simulation turning points на longitudinal couples data. **Взять:** adjacent formulation «turning points + interpretable state changes + holdout outcome» как research inspiration. **Не брать:** право делать consumer relationship prediction; наш safety policy запрещает breakup probability/future score.

## MEMORY — многолетняя история без каши

- **LongMemEval** — extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention. **Взять:** E0 benchmark grammar: timestamped planted facts/changes/counterexamples/unsupported queries.
- **LoCoMo** — multi-session long conversation QA + temporal reasoning. **Взять:** long-memory regression before intimate real data.
- **Graphiti / Zep** — bi-temporal facts + provenance + hybrid retrieval. **Взять:** `valid_from / valid_to / observed_at / source_message`; **не брать в MVP стек автоматически** — сначала простое storage, graph когда нужны graph queries.
- **IR branch** (LLM4IR-Survey, Awesome-Robustness-in-IR) — второй этап для evidence/counterevidence recall в многолетнем архиве. Пропущенный counterexample превращает хороший language model в очень убедительного адвоката одной версии событий.

## EVIDENCE — вывод обязан иметь проверяемое основание

- **RECCON / ECDaily** — task formulation `effect/claim → prior causal/evidence spans`. **Взять:** evidence indices/spans и explicit source linking.
- **behavioral-data / Empathy-Mental-Health** — labels + human rationales. **Взять:** rationale-aware annotation format.
- **Breakup prediction, 2026** ([Uhlich et al.](https://journals.sagepub.com/doi/10.1177/08902070261455278)) — умеренная balanced accuracy даже на настоящих relationship predictors. **Взять:** отрицательный урок: никакого consumer `87% breakup risk`.

## FAITHFULNESS — rationale может быть красивой декорацией

Citation/rationale — необходимый, но недостаточный слой.

- **[ERASER, ACL 2020](https://aclanthology.org/2020.acl-main.408/)** — разделяет agreement с human rationales и **faithfulness**; вводит sufficiency/comprehensiveness-style evaluation. **Взять:** removal/support tests и дисциплину «объяснение должно влиять на prediction».
- **[FaithLM, EACL 2026](https://aclanthology.org/2026.eacl-long.177/)** — intervention-based faithfulness: противоречащее explanation содержание должно менять prediction ожидаемым образом. **Взять:** counterevidence intervention test как часть publication gate.
- **[Faithful Serum, ACL 2026](https://aclanthology.org/2026.acl-long.300/)** — показывает widespread epistemic unfaithfulness natural-language explanations и оценивает её через counterfactuals. **Взять:** не считать fluent rationale доказательством происхождения решения.

Практический контракт: [evaluation-contract.md](evaluation-contract.md).

## SUBJECTIVITY — archive ≠ полная реальность

- **IPR — Interpersonal Process Recall** ([conversation analysis + IPR](https://www.tandfonline.com/doi/full/10.1080/14780887.2020.1780356)) — возвращает participant к конкретному моменту за недоступными наблюдателю thoughts/feelings/context. **Взять:** UX feedback. **Оговорка:** resonance ≠ ground truth; разделять observational correctness, participant resonance, partner corroboration, missing context, evidence fidelity.

## INTERVENTION — из insight в эксперимент

- **OurRelationship / IBCT** ([RCT](https://pubmed.ncbi.nlm.nih.gov/32134290/)) — Observe → Understand → Respond, individual work → structured joint conversation. **Взять:** product grammar `evidence before interpretation before intervention`.
- **JITAI / Micro-Randomized Trials** ([JITAI principles](https://academic.oup.com/abm/article/52/6/446/4733473), [MRT overview](https://ajph.aphapublications.org/doi/10.2105/AJPH.2022.307150)) — decision rules и repeated randomization для proximal effects. **Взять:** formal experiment design future couples loop; не объявлять observational transition причинным эффектом.
- **Deliberate practice** — evidence существует в training contexts, в том числе therapists. **Оговорка:** перенос на обычных партнёров — [research hypothesis](research-hypotheses.md), а не established fact.
- **Digital couple interventions** — meta-analyses/reviews подтверждают, что structured digital interventions как класс могут иметь эффекты, но гетерогенны. [BMC Psychology 2025](https://link.springer.com/article/10.1186/s40359-025-03444-y).

### Adjacent 2026 intervention work

- **[SpeakSoftly](https://arxiv.org/abs/2604.05382)** — LLM-powered just-in-time NVC scaffolding в intimate text conflict; mixed-methods study с couples. **Взять:** intervention-depth/cognitive-load trade-off и real-vs-simulated evaluation distinction.
- **[Reducing Conversational Escalation with NVC Constraints](https://arxiv.org/abs/2606.26106)** — lightweight process constraints уменьшают escalation в dual-agent simulations. **Взять:** prompt-level de-escalation baseline; **не брать:** synthetic simulation как proof real-couple effect.
- **[Scaffolded Vulnerability](https://arxiv.org/abs/2602.07508)** — chatbot-mediated reciprocal disclosure, randomized study 36 couples; mediation layer помогает partner-provided need support/closeness. **Взять:** AI как scaffold между людьми, а не substitute-partner.

## COUPLES OUTCOMES / CAUSAL DISCIPLINE

- **[Agapé 2026 — A Blueprint for Connection](https://www.mdpi.com/2076-328X/16/7/1182)** — 405 couples / 810 participants; за первый месяц 15/16 measured relationship processes улучшились, network analysis выделяет quality time, perceived partner responsiveness и gratitude как центрально связанные с relationship-quality change. **Критическая оговорка:** observational longitudinal design без randomized control group не даёт права говорить, что app caused эти изменения. **Взять:** candidate process measures + урок против causal language.

## EVAL — fidelity, harm, generalization

- **Persona fidelity:** InCharacter / PersonaGym / PersonaEval. [PersonaEval](https://openreview.net/forum?id=wZbkQStAXj) — LLM judges ненадёжны для role-play fidelity; нужен blind human holdout evaluation.
- **Agent attachment:** использовать валидированный инструмент; текущие кандидаты [EHARS](https://www.sciencedaily.com/releases/2025/06/250602155325.htm) и [AI Attachment Scale](https://www.sciencedirect.com/science/article/pii/S2451958825003276), но конкретный выбор не является invariant.
- **Affective use:** [MIT Media Lab + OpenAI](https://www.media.mit.edu/posts/openai-mit-research-collaboration-affective-use-and-emotional-wellbeing-in-ChatGPT/) — useful threat-model evidence для dependence/usage-tail monitoring; не переносить population correlation в индивидуальный диагноз.

E0/E1/E2, baseline A/B/C и risk/coverage зафиксированы в [evaluation contract](evaluation-contract.md).

## SAFETY / REGULATORY / TRANSPARENCY

- **[WHO — intimate partner violence](https://www.who.int/publications/i/item/WHO-RHR-12.36)** — physical/sexual/psychological harm, sexual coercion и controlling behaviours входят в IPV framing. **Взять:** no-forced-symmetry capability gate; **не брать:** автоматический diagnosis from chat.
- **[SB 243](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260SB243)** — §22601(b)(2)(A) исключает из companion chatbot бота, `used only` для перечисленных задач, включая productivity/analysis related to source information. **Взять:** explicit support Microscope-first + capability gradient; **не трактовать** как blanket exemption для Replay/coach/persona.
- **[EU AI Act, Article 50](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng)** — general transparency obligations для direct AI interaction и synthetic-content marking where applicable. **Взять:** общий transparency layer, не simulator-only checklist.
- **[De Freitas et al.](https://arxiv.org/abs/2508.19258)** — manipulation in companion farewell messages. **Взять:** regression taxonomy для own outputs.
- **[Cambridge griefbot ethics](https://link.springer.com/article/10.1007/s13347-024-00744-w)** — retirement/closure design vocabulary.

Подробные запреты: [safety-policy.md](safety-policy.md).

## TOOLS — ingestion не является moat

- [whatstk](https://github.com/lucasrodes/whatstk), [Chatistics](https://github.com/MasterScrat/Chatistics), [messaging-chat-parser](https://github.com/pistocop/messaging-chat-parser), [WhatsApp-Chat-Exporter](https://github.com/KnugiHK/Whatsapp-Chat-Exporter) — готовые ingestion candidates. **Не писать parser первым.**
- `ginger_wechat_portrait` — смотреть ingestion/normalization/reporting; не строить ядро на personality-from-chat без construct validation.

## Приоритет

- 🟢 **Core сейчас:** CIRS/SSIRS/SPAFF literature, behavioral-data, ConvoKit, RECCON/ECDaily, LongMemEval, faithfulness (ERASER/FaithLM/Faithful Serum), IPR, State Space representation с E1-оговоркой, JITAI/MRT как future experiment design.
- 🟡 **После proof of task:** robust IR, transfer/domain adaptation, temporal graph memory.
- 🔴 **Архив/история:** PROP, NTMC/MatchZoo до появления конкретной retrieval-проблемы, которую они реально решают.
