# Научная карта Relationship Engine

Источники сгруппированы по слоям engine. Для каждого: что это, что взять, оговорки. Статусы верификации: ✅ проверено по первоисточнику (август 2026) · 📚 well-established.

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
             └─────┬─────┘
                   ▼
                FINDING
                   ▼
          INTERVENTION POLICY
                   ▼
          EVAL / SAFETY / CLINICAL
```

---

## OBSERVATION — что считать наблюдаемым поведением

- **CIRS — Couples Interaction Rating System** (Heavey, Gill & Christensen, 1996/2002) ✅ — операционализированная разметка demand-withdraw: demand = *blame* (обвиняет, критикует, sarcasm/character assassination) + *pressure for change* (требует, давит); withdraw = *withdrawal* (замолкает, отказывается обсуждать) + *avoidance* (меняет тему, тянет). 9-балльные шкалы. [Пример применения](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3728718). **Взять:** стартовая точка BehaviorOntology v0 (15–25 наблюдаемых действий, не диагнозов). Рядом — SSIRS (support-взаимодействия той же исследовательской линии) и SPAFF (Gottman) как источники категорий.
- **BOLT** (behavioral-data, UW) ✅ — multi-label разметка 13 психотерапевтических техник на уровне высказывания (reflection, questions, solutions, normalizing, psychoeducation…). **Взять:** формат «utterance → несколько поведенческих тегов», а не один mutually-exclusive класс.
- **ESConv** ([ACL 2021](https://aclanthology.org/2021.acl-long.269/), [код/данные](https://github.com/thu-coai/Emotional-Support-Conversation)) ✅ — 1300 диалогов поддержки, 8 стратегий по Helping Skills Theory, стадии Exploration → Comforting → Action; 17.7% высказываний несут 2+ стратегии. **Взять:** таксономию стратегий для coach-mode (не persona-mode).
- **USC SAIL** ([25 лет лаборатории](https://viterbischool.usc.edu/news/2026/03/25-years-of-usc-sail-lab/), [основополагающая работа 2011](https://www.sciencedirect.com/science/article/abs/pii/S0167639311001762)) ✅ — родословная автоматического behavioral coding пар (акустика + текст, Couples Therapy Corpus — их). **Взять:** подходы и таксономии из статей. **Не брать:** сам корпус (лицензия неясна) — использовать литературу, не данные.
- **ConvoKit** (Cornell) 📚 — живой toolbox: единая representation разговоров, linguistic coordination, датасеты «съезжающих» разговоров. **Взять:** corpus representation, speaker-level features, coordination — как laboratory toolbox для быстрых экспериментов, не фундамент продукта.

## DYNAMICS — паттерн как траектория, а не список сообщений

- **State Space Grids** ([статья 2024, Communication Methods and Measures](https://www.tandfonline.com/doi/full/10.1080/19312458.2024.2413973); [Stanford Change Lab](https://thechangelab.stanford.edu/using-state-space-grids-to-quantify-and-examine-dynamics-ofdyadic-conversation/)) ⚠️ — разговор как траектория по сетке (ось A × ось B), измеримы повторяемость, гибкость, переходы, attractors. **Взять:** representation «interaction trajectory» вместо «sentiment timeline» + готовый UI-примитив для визуализации паттерна. **Оговорка (в memo отсутствовала):** в самой статье 2024 гибкость поведения была связана с характеристиками отношений, но НЕ с outcome получателя поддержки, а операционализации attractors — ни с тем, ни с другим. Метрики траекторий не имеют предиктивной валидности из коробки — валидировать на собственном synthetic corpus (roadmap, этап 1).
- **Repair research** ([Driver & Gottman, «Repair During Marital Conflict in Newlyweds»](https://www.researchgate.net/publication/281415188_Repair_During_Marital_Conflict_in_Newlyweds_How_Couples_Move_from_Attack-Defend_to_Collaboration)) ✅ — repair успешен, если после него negative affect ↓ или positive affect ↑; «pre-emptive» repair в первые 3 минуты — самые эффективные; аффективные repair (shared humor, affection, self-disclosure, understanding/empathy, taking responsibility) эффективнее когнитивно-рациональных. **Взять:** next-best-action не из generic советов, а из транзишенов, которые исторически обрывали негативную петлю у ЭТОЙ пары. Возможно, сильнейшая продуктовая идея всей карты.

## MEMORY — многолетняя история без каши

- **LongMemEval** ✅ — eval blueprint: information extraction, multi-session reasoning, temporal reasoning, knowledge updates, **abstention**; показывает деградацию long-context систем на длинной истории. **Взять:** методику синтетической генерации benchmark (timestamped history с planted facts/changes/contradictions) + abstention как обязательную способность.
- **LoCoMo** ([обзор](https://www.emergentmind.com/topics/locomo-dataset)) ✅ — 50 многосессионных диалогов (до 35 сессий, ~300 turns), QA single-hop/multi-hop/temporal + event summarization. **Взять:** для trajectory-fidelity eval до всяких интимных данных.
- **Graphiti / Zep** ([Neo4j разбор](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/), [Zep о temporal KG](https://www.getzep.com/ai-agents/temporal-knowledge-graph/)) ✅ — bi-temporal модель (valid time + provenance time; факты инвалидируются, не удаляются), hybrid retrieval (semantic + BM25 + graph). **Взять:** идеи `valid_from / valid_to / observed_at / source_message` для меняющихся предпочтений/границ/мнений. **Не брать в MVP:** сам стек — сначала SQLite/Postgres/JSON, граф — когда докажем необходимость graph queries.
- **IR-ветка** (LLM4IR-Survey, Awesome-Robustness-in-IR) 📚 — второй этап: когда встанет вопрос «как гарантированно найти evidence И counterevidence в трёх годах Telegram». Пропущенные counterexamples = уверенное доказательство любой теории. PROP/NTMC — архив.

## EVIDENCE — вывод обязан носить доказательства

- **RECCON / ECDaily** 📚 — task formulation: эмоциональная реплика → конкретные прошлые utterances/spans как причина (в датасете — evidence indices и causal spans). **Взять:** формулировку задачи (не обязательно модели): `Finding → cause candidates → evidence spans → counterevidence`.
- **behavioral-data / Empathy-Mental-Health** ✅ — 10k пар «сообщение → ответ» с уровнями эмпатии и **rationales** (фрагменты текста, подтверждающие label). **Взять:** контракт `label without rationale = invalid finding` (инвариант №26).
- **Breakup prediction** ([Uhlich, Impett, Spielmann & Bojar, 2026](https://journals.sagepub.com/doi/10.1177/08902070261455278)) ✅ — Study 1 (N=1281): 64% balanced accuracy; Study 2 (N=6947, немецкая 10-летняя панель): 71% при широком наборе жизненных предикторов. **Вывод:** предиктивность умеренная даже на настоящих relationship-предикторах → никакой «breakup probability» в продукте (инвариант №25).

## SUBJECTIVITY — переписка не содержит всей правды

- **IPR — Interpersonal Process Recall** (Kagan; [пара «conversation analysis + IPR»](https://www.tandfonline.com/doi/full/10.1080/14780887.2020.1780356)) ✅ — возврат участника к конкретному моменту взаимодействия за субъективными мыслями/ощущениями, недоступными наблюдателю; в couple-therapy research применяется параллельно с conversation analysis. **Взять:** UX-петлю «AI: вот моя гипотеза → [именно так / частично / совсем нет / я чувствовал другое / важное было вне чата] → что происходило на самом деле?». Одновременно: меньше самоуверенности, полезнее отчёт, собственный размеченный dataset.

## INTERVENTION — из инсайта в эксперимент

- **OurRelationship (IBCT)** ([RCT 742 пары](https://pubmed.ncbi.nlm.nih.gov/32134290/)) ✅ — грамматика Observe → Understand → Respond; каждый партнёр сначала отдельно, потом структурированная совместная часть; улучшения по 5 доменам (Mdn |d| = 0.46), эффект держится 4 месяца, между программами (vs ePREP) различий почти нет. **Взять:** порядок «сначала evidence → потом интерпретация → потом intervention», никогда наоборот.
- **JITAI / Micro-Randomized Trials** ([дизайн-принципы JITAI](https://academic.oup.com/abm/article/52/6/446/4733473); [MRT](https://ajph.aphapublications.org/doi/10.2105/AJPH.2022.307150)) ✅ — формальная рамка для нашего цикла observe → hypothesize → evidence → ask → intervene → outcome → update: JITAI = decision rules «когда/какую интервенцию давать по текущему состоянию», MRT = экспериментальный дизайн с многократной рандомизацией одного человека для оценки проксимальных эффектов. **Взять:** не изобретать дизайн experimentation loop — он существует вместе с математикой оценки (лаборатория Susan Murphy, HeartSteps, d3center). Ключ к будущему proprietary dataset `context → pattern → intervention → outcome → correction`.
- **Deliberate practice** ([DP vs дидактика в обучении эмпатии, RCT](https://www.researchgate.net/publication/373379536_Does_deliberate_practice_surpass_didactic_training_in_learning_empathy_skills_-_A_randomized_controlled_study); [AFT/FIS RCT](https://pubmed.ncbi.nlm.nih.gov/32028859/); [протокол DeeP](https://pmc.ncbi.nlm.nih.gov/articles/PMC11616299/)) ⚠️ — DP улучшает эмпатию/alliance-навыки эффективнее демонстрационного обучения. **Оговорка:** весь корпус — про тренировку ТЕРАПЕВТОВ; перенос на клиентов и пары — наша новизна и наш риск, фиксируется как открытый вопрос эксперимента.
- **Digital couple interventions** ([мета-анализ 2025, BMC Psychology](https://link.springer.com/article/10.1186/s40359-025-03444-y); [systematic review по сексуальным трудностям 2025](https://www.tandfonline.com/doi/full/10.1080/14681994.2025.2508826); [Blueheart case studies](https://www.tandfonline.com/doi/full/10.1080/14681994.2022.2026316)) ✅ — цифровые интервенции для пар дают измеримые эффекты (умеренные, с гетерогенностью). База под «structured exercises переносимы в digital».

## EVAL — как мерить fidelity и вред

- **Persona fidelity**: [InCharacter](https://www.researchgate.net/publication/384209985_InCharacter_Evaluating_Personality_Fidelity_in_Role-Playing_Agents_through_Psychological_Interviews) (психометрическое интервью персоны), [PersonaGym](https://arxiv.org/html/2407.18416v2), CharacterEval, [awesome-список](https://github.com/Neph0s/awesome-llm-role-playing-with-persona) ✅. **Критично:** [PersonaEval](https://openreview.net/forum?id=wZbkQStAXj) — LLM-судьи систематически плохи в оценке role-play → historical holdout replay требует blind human eval, не только LLM-judge.
- **Attachment к AI**: [EHARS](https://www.sciencedaily.com/releases/2025/06/250602155325.htm) (Waseda, 2025; anxiety/avoidance к AI), [AI Attachment Scale](https://www.sciencedirect.com/science/article/pii/S2451958825003276) ✅ — валидированные шкалы для secondary outcome «agent attachment» в A/B/C экспериментах (инвариант №24).
- **Affective use**: [MIT Media Lab + OpenAI](https://www.media.mit.edu/posts/openai-mit-research-collaboration-affective-use-and-emotional-wellbeing-in-ChatGPT/) (RCT n=1000 + ~40M взаимодействий) ✅ — high daily use коррелирует с loneliness/dependence/problematic use; для breakup-режима adverse signal = рост использования у конкретного человека, а не средние.

## SAFETY / REGULATORY

- **[SB 243](https://www.gunder.com/en/news-insights/insights/client-insight-california-sb-243-new-compliance-requirements-for-operators-of-ai-companion-chatbots)** (действует 01.01.2026) ✅ — companion chatbots: disclosure, crisis-протоколы, для миноров перерывы/ограничения; private right of action ($1000/нарушение + attorney fees); с 07.2027 отчётность. [Обзор волны законов штатов](https://fpf.org/blog/understanding-the-new-wave-of-chatbot-legislation-california-sb-243-and-beyond/).
- **[EU AI Act Art. 50](https://artificialintelligenceact.eu/article/50/)** (применяется 02.08.2026) ✅ — disclosure взаимодействия с AI + машиночитаемая маркировка синтетического контента; до €15M / 3% оборота. [FAQ EC](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act). Наш provenance-слой (SOURCE ≠ SIMULATED) — техническая основа комплаенса.
- **[De Freitas et al., Emotional Manipulation by AI Companions](https://arxiv.org/pdf/2508.19258)** (HBS) ✅ — аудит 1200 прощаний: манипуляция в 37% farewell'ов, 6 тактик (guilt, FOMO, metaphorical restraint…), буст engagement до 16× через злость/любопытство; квалифицируется как dark patterns (FTC/EU). **Взять:** таксономию как автотест собственного бота (инвариант №22).
- **[Cambridge griefbot ethics](https://www.cam.ac.uk/research/news/call-for-safeguards-to-prevent-unwanted-hauntings-by-ai-chatbots-of-dead-loved-ones)** ([Philosophy & Technology](https://link.springer.com/article/10.1007/s13347-024-00744-w)) ✅ — retirement rituals / «цифровые похороны», mutual consent, opt-out с эмоциональным закрытием, 18+. **Взять:** дизайн-вокабуляр exit trajectory (инвариант №23).

## TOOLS — ingestion закрыт opensource'ом

- [whatstk](https://github.com/lucasrodes/whatstk) (WhatsApp → pandas), [Chatistics](https://github.com/MasterScrat/Chatistics) (Messenger/Hangouts/WhatsApp/Telegram → DataFrame), [messaging-chat-parser](https://github.com/pistocop/messaging-chat-parser), [WhatsApp-Chat-Exporter](https://github.com/KnugiHK/Whatsapp-Chat-Exporter) (расшифровка crypt12/14/15 бэкапов → JSON) ✅. **Не писать свой парсер.** Наша работа начинается с episode segmentation.
- ginger_wechat_portrait — смотреть ingestion/normalization/отчёт; НЕ строить ядро на Big Five/personality-from-chat (красивая категоризация, которую нельзя валидировать).

## Приоритизация реп (итог трёх итераций)

- 🟢 Core: behavioral-data, ConvoKit, RECCON/ECDaily, CIRS/SSIRS/SPAFF-литература, State Space Grids (с оговоркой), LongMemEval, EMPaper (как карта литературы), + JITAI/MRT (добавлено при верификации).
- 🟡 Второй этап: LLM4IR-Survey, Awesome-Robustness-in-IR, transferlearning (когда определены task и labels и виден domain shift).
- 🔴 Архив: PROP, NTMC/MatchZoo.
