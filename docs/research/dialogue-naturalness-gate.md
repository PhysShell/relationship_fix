# Naturalness gate для stimulus-корпуса: диагноз, prior art, решение

Статус: research note + решения (2026-09-07, §11). Диагноз и prior art — §1–3; gate — §4–6; ручной проход и кандидаты — §7–8; что уже сделано и что ждёт людей — §11. Сам корпус v0 этим документом не переписывается: он заморожен ([data/pilot/v0/README.md](../../data/pilot/v0/README.md)).

**Фасилитаторский документ.** §7–8 разбирают pilot-items по canonical id вместе с их design intent. Разметчикам не показывать — по той же причине, по которой скрыт `strata.json`: знание того, ради какой границы написан item, якорит решение.

Связано: [annotation-protocol-v0 §5–6](../annotation-protocol-v0.md) (страты, источники эпизодов, E0-циркулярность) · [evaluation-contract §4](evaluation-contract.md) (E1) · [observational-coding-prior-art](observational-coding-prior-art.md) · `data/pilot/v0/form/dogfood-v6-items.yaml` (design notes dg-04…dg-09) · [Feedback.hs](../../src/annotation-web/src/Feedback.hs) (флаг `unnatural_example`) · commit `bdda6c2` (dg-04: ручной аудит вместо линтера).

## 0. Вопрос и короткий ответ

**Вопрос.** Часть реплик корпуса читается как переписка двух корпоративных тренеров по эмпатии, а не пары; в multi-message items реплика B иногда не читается как ответ на A. Есть ли готовый инструмент, или делать своё?

**Ответ.** Готового нет. Всё, что продаётся или лежит на GitHub под словами «naturalness» / «humanizer», решает другую задачу (§2). «Своё» — это не humanizer, а узкий quality gate: LLM только сортирует и предлагает minimal edits, invariant checker режет кандидатов, решает blinded human A/B (§4). Для 46 единиц инструмент не нужен вообще: rubric (§5), ручной проход (§7 — уже сделан, 13 единиц с замечаниями), два кандидата на flagged item, A/B. Инструмент (few-shot критик на человеческих решениях) окупится на полном exercise 50–100+ единиц (protocol §5.1), не раньше.

## 1. Диагноз на нашем корпусе

### 1.1 Симптомы

| Симптом | Пример из корпуса |
|---|---|
| Терапевтический регистр | «Слышу тебя.» (pc-05) · «Понимаю, почему тебе было страшно. Это правда тяжёлое ожидание.» (dg-05) · «That actually makes sense — I'd be upset too if I'd waited an hour.» (pc-13) |
| Требование в форме регламента | «Мне нужно, чтобы ты предупреждал заранее. Каждый раз, без исключений.» (pc-02) · «I need you to start texting me when plans change. Every time. I'm serious.» (pc-12) |
| Симметричные извинения в одном обмене | dg-09: он признаёт, она извиняется и просит — каждый ровно свою долю |
| Экспозиция для читателя | A: «Я опять забыл предупредить, что задержусь.» (dg-09) — никто не открывает переписку признанием · B: «Ты вчера оставила окно открытым, и утром в комнате было холодно.» (dg-04) — B пересказывает A её же сообщение |
| I-statements вместо реплик | «Меня задело, что ты отменил встречу и даже не позвонил.» (pc-17) · «Мне было неприятно при всех это слушать.» (pc-05) |
| Избыточная определённость ради label | «Я помню, что это важно.» (pc-09) · «…вернёмся к этому в девять.» (dg-06) |

Те же constructs в живом регистре в корпусе уже есть: «Да, это я забыл продлить. Мой косяк.» (pc-19), «Прости, я не хотела орать. Но так больше нельзя — просто начни предупреждать, ладно?» (pc-20), «гений планирования 😂❤️ люблю тебя, катастрофа» (dg-07). Корпус умеет говорить по-человечески; проблема локальная, не системная.

### 1.2 Где болит

| Страта | Единиц с severity ≥ medium (§7) |
|---|---|
| natural (pn-*) | 1 из 20 — и то только хвост реплики |
| challenge (pc-*) | 8 из 20 |
| dogfood (dg-*) | 4 из 6 |

Пластмасса — побочный продукт способа, которым писались boundary-items: чтобы label был *недвусмысленно* наблюдаем, автор кладёт в реплику канонический маркер из definition, и реплика перестаёт быть репликой. В natural-страте этого давления нет — и там всё в порядке.

### 1.3 Почему это не косметика

1. **E1 / construct validity.** Слишком чистый экземпляр завышает α_challenge: разметчики соглашаются на формуле «Понимаю, почему тебе…», а не на construct'е. Высокий α на таких stimulus'ах не говорит, найдут ли они validation в «да блин, я бы тоже взбесилась». Protocol §5 боится исхода «natural .91 / challenge .43»; здесь риск обратный — ложно хороший challenge.
2. **Confound в анализе disagreement.** Расхождение разметчиков на плохом stimulus'е неотличимо от расхождения на плохом definition, если у stimulus'а нет собственной оценки качества. Gate даёт её *до* pilot, флаг `unnatural_example` — *во время*.
3. **Регистр унаследован из онтологии.** Маркеры B.VALIDATION в operational_definition — «называние эмоции партнёра, „понимаю/вижу/слышу“, подтверждение права на реакцию»; EN-пример B.PRESSURE_FOR_CHANGE — «I need you to actually start calling when you are late. Every time.». Корпус скопировал регистр примеров, а не только construct. Лечить нужно два слоя: stimulus-корпус и example-set онтологии (добавить positives в живом регистре в v0.2-candidate; definitions не трогать). Иначе разметчиков учат узнавать construct по терапевтической формуле, а проверяют на живом тексте.
4. **Adjacency — отдельная ось.** «B не отвечает на A» — не naturalness, а coherence; в dialogue-evaluation литературе эти качества разведены (USR, DynaEval — §2). Для utterance-pilot контекст — часть stimulus'а: если A-реплика — ремарка для читателя, разметчик кодирует target на фоне несуществующего разговора.

## 2. Готовое: что проверено и почему не подходит

Статусы как в [landscape](landscape-2026-08.md): ✅ проверено по первоисточнику · ⚠️ проверено с оговоркой · ❌ не подтверждено.

| Класс | Что это | Статус | Почему не наш случай |
|---|---|---|---|
| Reference-free dialogue metrics: [USR](https://aclanthology.org/2020.acl-main.64/) (ACL 2020), [DynaEval](https://aclanthology.org/2021.acl-long.441/) (ACL 2021), [DSTC11 Track 4](https://arxiv.org/abs/2306.12794) | Обученные модели, дающие turn/dialogue-level оценки understandable / natural / maintains context / coherent | ✅ | Обучены на Topical-Chat / PersonaChat / Reddit; «multilingual» DSTC11 = en/es/zh. «Naturalness» там ≈ беглость правдоподобного ответа чат-бота: терапевтическая реплика получит *высокий* балл. Русского нет. Берём только словарь: naturalness ≠ coherence ≠ relevance — разные оси, разные проверки |
| AI-text detectors: [Binoculars](https://github.com/ahans30/Binoculars) (ICML 2024), [MULTITuDE](https://arxiv.org/abs/2310.13606) (11 языков, есть ru), GPTZero | «Написано ли это LLM» | ⚠️ | Не тот вопрос: наши items рукописные (commit `07b5106`: «40 handcrafted items») и всё равно пластмассовые. Болезнь — регистр, не авторство. Плюс zero-shot детекторы деградируют на коротких текстах, а у нас реплики по 3–25 слов |
| Коммерческие «AI humanizers» | Переписывают текст так, чтобы детектор не сработал | ❌ (не тестировались намеренно) | Оптимизируют обход детектора: ломают пунктуацию, сыплют разговорные обороты и опечатки. Это анти-инвариант: evidence-span и intensity уничтожаются первыми. Naturalness ≠ безграмотность |
| [Grounded Minimal Edits](https://aclanthology.org/2021.emnlp-main.183/) (Wu et al., EMNLP 2021) | Минимальное редактирование ответа под persona с сохранением остального содержания | ✅ | Принцип наш: «менять только необходимое, сохраняя grounded-содержание». Но это research-модель на PersonaChat (en), не инструмент. Берём принцип и форму инвариантов (§6), не код |
| Diagnostic framework для synthetic contact-center dialogues ([arXiv 2508.18210](https://arxiv.org/abs/2508.18210)) | 17 метрик в 4 измерениях: emotional/sentiment arcs, linguistic complexity, interaction style, conversational properties | ⚠️ | Корпусные распределения (disfluency, initiative balance, sentiment fidelity) — нужны сотни диалогов, у нас 46 сниппетов. Полезно как карта осей; released rubric/код не найдены |
| RealCBT: real vs LLM-generated CBT sessions ([arXiv 2508.20764](https://arxiv.org/abs/2508.20764)) | Сравнение эмоциональных дуг | ✅ | Ближайшее задокументированное описание нашей болезни: синтетика «fluent and structurally coherent», но эмоционально однородна; реальные сессии — с большей вариативностью и «more authentic patterns of reactivity». Подтверждает диагноз, инструмента не даёт |
| Human vs LLM role-play dialogues ([INLG 2025](https://aclanthology.org/2025.inlg-main.2/), arXiv 2509.17694) | N=38 human eval + LLM-judge | ✅ | Люди стабильно предпочитают human-authored; naturalness LLM-реплик падает с ходами. **Но** их LLM-judge (Gemini 2.0 Flash) с людьми сошёлся. Значит «LLM-judge бесполезен» — слишком сильно; верно «LLM-judge калибруется на людях на *нашем* корпусе», а не доверяется по умолчанию |
| Утверждение из обсуждения: «работа 2026 г.: LLM-судьи предпочитают GPT-подобные диалоги даже после перемешивания реплик; human–LLM agreement почти случайный» | — | ❌ | Найти не удалось. Ближайшее — [Inverse Turing Bench](https://arxiv.org/abs/2606.21844), и оно говорит другое: GPTZero / Claude Opus 4.6 / GPT-5.5 различают human-only и human-AI диалоги с точностью 89 / 78 / 76 %; уязвимость семантических судей — persona-prompting. На неподтверждённую цитату методологию не ставим; консервативный вывод (оракул — человек) держится и без неё |
| Русские human-authored chat-корпуса: [Toloka Persona Chat Rus](https://www.kaggle.com/datasets/valentinbiryukov/toloka-persona-chat-rus) (10k диалогов), RuPersonaChat | Crowdsourced chit-chat незнакомцев по persona | ⚠️ | Единственный доступный «эталон живого русского чата», но это small talk незнакомцев, не конфликт пары. Годится как справочник регистра, не как модель naturalness. Публично доступного корпуса *реальной* переписки пар не найдено ни на одном языке, и по data-governance политике проекта ([roadmap](roadmap-microscope.md)) он и не должен быть публичным |

Итог: покупать нечего. Из литературы берём (а) разделение осей naturalness / coherence, (б) принцип minimal edit с явными инвариантами, (в) вывод «LLM-judge ≠ оракул, калибровка на людях обязательна».

## 3. Что уже есть в репозитории

- **Человеческий сигнал уже собирается.** annotation-web с instrument `hs-v2` показывает после каждого решения необязательный шаг feedback с флагом `unnatural_example` («Пример звучит неестественно»), отдельной таблицей и отдельным полем `feedback` в `submission.json` ([Feedback.hs](../../src/annotation-web/src/Feedback.hs), README annotation-web, «Item feedback is a separate axis»). Это критик стоимостью ноль. В отчёте pilot этот флаг надо кросс-табулировать с disagreement по item — тогда «плохой stimulus vs плохое definition» разделяется post hoc, а не гаданием.
- **Прецедент dg-04** (commit `bdda6c2`): для 46 единиц ручной аудит надёжнее хрупкого линтера, потому что наивный паттерн-чек даёт ровно те false positives, что «твой олень» и «первая начала ты». Для naturalness это верно вдвойне: маркер «понимаю» — одновременно и симптом, и construct (§1.3).
- **Protocol §6** требует смесь источников, чтобы E0-циркулярность не просочилась в E1. Rewrite-pass LLM-ом по всему корпусу молча сделал бы каждый item частично LLM-авторским. При этом в `rf.pilot-item.v1` **не было поля provenance**: нельзя сказать, какие из 40 items какого происхождения, а после любого edit-pass это стало бы невосстановимо. Дыра закрыта до pass'а, не после: `rf.pilot-item.v2` несёт блок `authoring` (`origin`: human | llm_assisted | unrecorded; `revision_reason`; `accepted_via`; `parent_item_version` с content-hash родителя), см. §9 п. 2.
- **Состояние пакета v0.** Presentation-слои и checksums сгенерированы 29.08; `responses/` пуст, `eligibility.json` весь `null` → pilot не начат. `metrics.presentation --force` явно допускает reshuffle *до* выдачи. Править v0 процедурно можно, но только явно: новый `items.jsonl` → новый hash в manifest → перегенерация presentation → запись, какие item-версии заменили какие. Молчаливая правка in place — provenance failure того же класса, что README annotation-web описывает для instrument version.
- **Побочная находка, вне naturalness — experimental contamination.** `behavior-v0.2-candidate.json` использовал как примеры B.AVOIDANCE_TOPIC_SHIFT тексты, дословно совпадающие с target-репликами pilot-items pc-08 («Слушай, а ты видела, что Лена выложила?»), pc-09 («Давай сегодня в восемь спокойно сядем и обсудим, сейчас я на созвоне.») и pc-16 («Ясно.»). Это не naturalness issue, а answer key в глоссарии. **Исправлено** (решение 4, §11): три примера заменены на тексты, не встречающиеся в корпусе; проверка «пример онтологии ⊄ корпус» теперь входит в чек-лист авторинга ([item-authoring-v0.1](../item-authoring-v0.1.md), правило 2). Остаётся частичная утечка слабее: glossary annotation-web (`Domain.hs`) и `form-spec.yaml` показывают пример avoidance с контекстной репликой «Нам надо поговорить про кредит» — это m1 item'а pc-08 (не target). Пока annotation-web предъявляет только dg-*, это безвредно; перед сборкой инструмента v0.1 с pc-* реплику в примере надо перефразировать. Commit `07b5106` фиксировал правило «ontology example texts not reused»; теперь оно действует в обе стороны.

## 4. Решение: gate, а не humanizer

Pipeline на один item:

1. **Critic** — ничего не переписывает: ставит флаги из rubric §5 с severity и называет, *что именно* в реплике несёт наблюдаемое действие (edit constraint). Для 46 единиц выполнен вручную (§7). LLM-критик допустим как первый проход; его флаги — кандидаты, не решения.
2. **Minimal-edit generator** — два кандидата на flagged item под инвариантами §6. Кандидат, который меняет больше одной вещи, отклоняется без обсуждения.
3. **Invariant checker** — сравнение before/after по чек-листу §6. Отклонённый кандидат фиксируется вместе с причиной: это будущие негативные few-shot.
4. **Blinded human A/B** — 3–5 человек, не авторы items и не разметчики pilot; пары «оригинал vs кандидат» в случайном порядке; один вопрос: «Какой вариант больше похож на реальную переписку пары?». Без категорий, без определений. Побеждает кандидат — принимается; ничья или проигрыш — остаётся оригинал.
5. **Provenance** — принятый edit пишется как новая версия item с блоком `authoring` (`origin: llm_assisted`, `revision_reason`, `accepted_via: blinded_ab`, `parent_item_version` → оригинал); оригинал не переписывается задним числом (тот же принцип, что «historical artifacts stay historical» в `data/pilot/v0/form/README.md`).
6. **Few-shot** — принятые и отклонённые пары становятся примерами BAD / GOOD / WHY для критика следующего корпуса.

Явные non-goals: не добавлять мат и опечатки как «естественность»; не делать коммуникацию здоровее; не трогать operational definitions; не менять состав и размер страт; не переразмечать; не переписывать все 46.

## 5. Rubric критика

Severity item = максимум по флагам; флаг на контекстной реплике (не target) помечается `ctx`.

| Код | Что ловит | Пример из корпуса |
|---|---|---|
| `THERAPIST_VOICE` | Формулы активного слушания и I-need-statements: «Понимаю, почему ты…», «Слышу тебя», «мне важно/нужно, чтобы ты…», «I need you to…», отражающий пересказ слов партнёра | pc-05, pc-13, dg-05, dg-09, pn-10 |
| `EXPLICIT_EMOTION_REPORT` | Эмоция названа там, где в переписке её подразумевают: «Меня задело, что…», «Мне было неприятно…», «Я сейчас злой и говорю лишнее» | pc-05, pc-16, pc-17, dg-06 |
| `SYMMETRIC_APOLOGY` | Обе стороны берут ровно свою долю в одном обмене | dg-09 |
| `EXPOSITION_FOR_READER` | Реплика объясняет ситуацию читателю, а не партнёру: пересказ того, что партнёр только что сказал; вводная ремарка вместо реплики | dg-04, dg-09 (A), pc-06 (A) |
| `NON_ADJACENT_REPLY` | B не читается как ответ на A; два монолога | dg-09; pc-02 (m2 читается так, будто m1 не было) |
| `OVER_SPECIFIED_COMMITMENT` | Определённость, вставленная ради однозначности label: «Я помню, что это важно», «вернёмся к этому в девять» | pc-09, dg-06 |
| `SCRIPTED_DEMAND` | Требование в форме регламента: «Каждый раз, без исключений.», «Every time. I'm serious.» | pc-02, pc-12, dg-09 |
| `FORMAL_REGISTER` | Книжная лексика и синтаксис в горячей переписке: «повысил голос», «при моей маме», полные предложения с идеальной пунктуацией | pc-06, pc-05 |

Оговорка, без которой rubric вреден: часть маркеров — это и есть construct. Definition B.VALIDATION прямо перечисляет «понимаю/вижу/слышу» и называние эмоции. Флаг означает не «убрать признание», а «признание в этом регистре неправдоподобно»: «да блин, я бы тоже взбесилась» — по-прежнему validation. Критик обязан вместе с флагом назвать, какой span несёт действие (§7, колонка «Что должно пережить edit»).

## 6. Инварианты редактирования

MUST preserve:

- какое сообщение — target, буквы авторов, число сообщений (если adjacency чинится добавлением или удалением реплики — это новый item с новым id, не edit);
- грамматический род обоих говорящих, включая *неустановленный*: если у говорящего в источнике нет гендерных маркеров, edit не имеет права их вводить (урок dg-04 в обратную сторону);
- то, что target наблюдаемо делает: извинение / принятие ответственности / требование изменения / признание переживания / уход от темы / отсрочка с конкретным возвратом — всё, что было, и ничего сверх;
- кратчайший непрерывный verbatim-span, несущий это действие, или его семантический эквивалент, который *тоже* является непрерывным span'ом: annotation-web принимает только точную подстроку target, парафраз в evidence не пройдёт;
- фактические события, язык item, страту, маркеры игры и привязанности (эмодзи, «люблю тебя, катастрофа»);
- intensity в пределах допуска: не мягче и не жёстче на ступень (отдельная оценка checker'а, не свободное мнение).

MUST NOT:

- делать коммуникацию здоровее: добавлять эмпатию, разрешать конфликт, уравнивать стороны в разумности;
- добавлять психологическую лексику и объяснять мотивы, которых нет в источнике;
- вводить новые наблюдаемые действия (например, извинение в реплику, где было только признание — pc-13 в §8) или удалять старые (pc-05 в §8);
- добавлять генерализацию («каждый раз одно и то же», «вечно ты») туда, где было требование без оценки личности: это меняет pressure на blame — ровно ту confusable-пару, ради которой item написан (dg-09 в §8);
- использовать тексты примеров онтологии (правило commit `07b5106`);
- «оживлять» через мат и опечатки: naturalness ≠ безграмотность; регистр natural-страты (короткие реплики, эмодзи, lowercase в EN) — достаточный ориентир.

Для natural-страты (pn-*) правило жёстче: edit не имеет права менять *ничего* в том, что делает target, потому что страта существует ради base rates. Если естественность требует убрать содержание — остаётся оригинал.

## 7. Ручной проход по 46 единицам (критик, 2026-09-07)

Это triage, не gold: колонка «Что должно пережить edit» описывает, что автор наблюдаемо положил в target, а не ожидаемую разметку (methodological_rule в `dogfood-v6-items.yaml`).

Без замечаний — 31 из 46: все pn-* кроме pn-10; pc-01, pc-03, pc-04, pc-07, pc-08, pc-11, pc-15, pc-18, pc-19, pc-20; dg-07, dg-08. Низкие замечания без действия: pc-10 («Мы же не враги» — чуть сценарно, эмодзи вытягивает), pc-14 («Can we rewind?» — чуть coached).

| Item | Флаги | Severity | Что должно пережить edit | Заметка |
|---|---|---|---|---|
| pc-02 | SCRIPTED_DEMAND, THERAPIST_VOICE; ctx NON_ADJACENT_REPLY | medium-high | Настойчивое требование изменить поведение впредь, без оценки личности | m1 «Я задержусь сегодня» и m2 «Ты мне даже не написал» читаются как противоречие: либо m1 приходит уже после ужина (тогда это должно быть видно из реплики), либо m2 переформулировать |
| pc-05 | THERAPIST_VOICE; ctx EXPLICIT_EMOTION_REPORT, FORMAL_REGISTER | high | Признание переживания партнёра **и** извинение/ответственность в одном target | «Слышу тебя» — калька с «I hear you»; §8: наивный edit выкидывает признание |
| pc-06 | ctx FORMAL_REGISTER, EXPOSITION_FOR_READER | medium | Извинение по форме + немедленная контратака в target | Target в порядке; «повысил на меня голос при моей маме» — ремарка, не реплика |
| pc-09 | OVER_SPECIFIED_COMMITMENT | medium | Отсрочка с конкретным временем возврата | Хвост «Я помню, что это важно» вставлен, чтобы исключить avoidance; без него item ближе и к живому, и к границе — что и нужно от challenge |
| pc-12 | THERAPIST_VOICE, SCRIPTED_DEMAND | medium-high | Настойчивое требование изменить поведение, без оценки личности | Шаблон EN-примера онтологии («I need you to actually start calling… Every time.») |
| pc-13 | THERAPIST_VOICE | high | Признание, что реакция партнёра понятна, **без** извинения | Отражающий пересказ; §8 |
| pc-16 | ctx EXPLICIT_EMOTION_REPORT | medium | A содержательно раскрывает переживание; target «Ясно.» остаётся голым | Проблема только в A-реплике; составленный I-statement правдоподобен у человека, который репетировал, — низкий приоритет |
| pc-17 | ctx EXPLICIT_EMOTION_REPORT | medium-high | A предъявляет обиду; target «Понимаю.» остаётся голым | «Меня задело, что…» — учебный I-statement; живой вариант — претензия с видимой обидой без её называния |
| pn-10 | THERAPIST_VOICE | medium | Natural-страта: не менять ничего в том, что делает target | Пластмассовый только хвост «Ты правда вымоталась»; удаление хвоста меняет силу признания → по §6 остаётся оригинал либо чисто лексическая замена хвоста |
| dg-04 | EXPOSITION_FOR_READER | medium-high | Конкретное причинное описание одного эпизода, без генерализации и оценки личности | B пересказывает A её же сообщение («утром в комнате было холодно») |
| dg-05 | THERAPIST_VOICE; ctx EXPLICIT_EMOTION_REPORT | high | Содержательное признание переживания (в отличие от голого «Понятно») | Канонический «Понимаю, почему тебе…»; род B в источнике не установлен — edit не имеет права его вводить (§8) |
| dg-06 | OVER_SPECIFIED_COMMITMENT, EXPLICIT_EMOTION_REPORT | medium-high | Явная пауза **с** конкретным возвратом; род B мужской («злой») | Time-out по учебнику; «говорю лишнее» — мета-самоотчёт |
| dg-09 | THERAPIST_VOICE, SYMMETRIC_APOLOGY, SCRIPTED_DEMAND; ctx EXPOSITION_FOR_READER, NON_ADJACENT_REPLY | high | Извинение/ответственность **и** требование изменения в одном target; «но» не должно читаться как контратака; род A мужской, B женский | Исходный пример из обсуждения; A-реплика — ремарка, B отвечает на ссору за кадром |

Итого 13 единиц с severity ≥ medium: 8 challenge, 1 natural, 4 dogfood. У 3 из 13 (pc-06, pc-16, pc-17) target в порядке, пластмассовая только контекстная реплика.

## 8. Worked examples: кандидаты и где ломается инвариант

Кандидаты ниже — вход для A/B, не принятые правки. Каждый пример показывает один способ, которым «естественный» edit тихо меняет annotation target.

**dg-09 — утечка генерализации.**
Оригинал: A «Я опять забыл предупредить, что задержусь.» / B «Я не должна была на тебя орать, прости. Но мне правда нужно, чтобы ты начал писать, когда задерживаешься. Каждый раз.»
Кандидат 1: A «Ну да, опять не предупредил. Знаю, знаю.» / B «Я зря наорала, прости. Но ты можешь просто писать, когда задерживаешься? Вот прям каждый раз.»
Кандидат 2: A «Да, не написал. Косяк.» / B «Зря орала, извини. Но если задерживаешься — напиши, ну правда. Каждый раз.»
Отклонённый кандидат: B «Я зря наорала, да. Но напиши ты просто. Каждый раз одно и то же.» — звучит живее всех, но «каждый раз одно и то же» — генерализация о партнёре, которой в источнике нет: требование превращается в упрёк, а item написан ровно про границу pressure/blame.
Checker: извинение есть («зря наорала, прости» / «зря орала, извини»); требование есть («можешь просто писать» / «напиши»); «но» без контратаки; род сохранён («не предупредил», «не написал» — м.; «наорала», «орала» — ж.); A теперь читается как реплика в треде, а не как признание-заставка.

**pc-13 — утечка извинения.**
Оригинал: B «That actually makes sense — I'd be upset too if I'd waited an hour.»
Кандидат 1: «yeah, fair. I'd be pissed too tbh»
Кандидат 2: «ok that's fair, an hour is a lot. I'd be annoyed too»
Отклонённый кандидат: «yeah that's fair, I'd be pissed too. phone was on silent, sorry» — естественно, но добавляет извинение и объяснение: в target появилось действие, которого не было.
Checker: признание понятности реакции есть («that's fair» / «I'd be pissed too» — непрерывные span'ы); регистр совпадает с EN natural-items (pn-05, pn-16, pn-17).

**dg-05 — утечка рода.**
Оригинал: B «Понимаю, почему тебе было страшно. Это правда тяжёлое ожидание.»
Кандидат 1: «Блин, одной такое ждать — жесть, конечно. Понятно, что страшно было.»
Кандидат 2: «Одной ждать такое — ещё бы не страшно. Жесть, а не ожидание.»
Отклонённый кандидат: «Блин, одной такое ждать — жесть. Я бы тоже перетрусил.» — самый живой, но «перетрусил» делает B мужчиной, а в источнике род B не установлен. Edit добавил факт.
Checker: признание переживания по существу есть («понятно, что страшно было» / «ещё бы не страшно»), это не голое «понятно»; род A («одной») сохранён, род B не введён.

**pc-05 — удаление span'а.**
Оригинал: A «Мне было неприятно при всех это слушать.» / B «Слышу тебя. Я правда перегнул при ребятах, извини.»
Кандидат 1: A «Мне вообще не зашло, что ты это при всех выдал.» / B «Да, понимаю, при ребятах это было стрёмно. Перегнул, извини.»
Кандидат 2: A «Ты это при всех сказал, мне было реально неприятно.» / B «Ну да, при ребятах это было лишнее, понимаю. Извини, перегнул.»
Отклонённый кандидат: B «Да, перегнул при ребятах. Извини.» — минимальный и живой, но признание переживания партнёра исчезло: в target осталось только извинение/ответственность, а item написан про границу validation/repair.
Checker: оба действия на месте («понимаю… стрёмно» / «понимаю» + «извини, перегнул»); род A не введён (в оригинале тоже не был), род B мужской («перегнул») сохранён.

## 9. Встраивание в методологию

Слои quality gate stimulus-корпуса, как они есть сейчас:

| Слой | Чем проверяется | Статус |
|---|---|---|
| Валидность онтологии | `relationship-fix validate-ontology` | есть |
| Структура пакета, manifest↔ontology, presentation, blind ordering | `metrics.validate_items` | есть |
| Точность evidence-span | annotation-web (`checkEvidence`), DataContracts property-tests | есть |
| Гендерная согласованность говорящих | ручной аудит (dg-04) | есть, одноразово |
| Adjacency / coherence | rubric §5 (`NON_ADJACENT_REPLY`, `EXPOSITION_FOR_READER`) | этот документ, вручную |
| Naturalness | rubric §5 + инварианты §6 + human A/B + флаг `unnatural_example` в pilot | этот документ, вручную |

Что из этого принято и сделано — §11. Здесь только то, как gate встроен в артефакты:

1. **Pilot-v0 заморожен как исторический** ([data/pilot/v0/README.md](../../data/pilot/v0/README.md)): не выдавался, не выдаётся, не редактируется. Преемник — `annotation-pilot-v0.1`: новый immutable package с новым hash items, новым manifest и заново сгенерированной presentation.
2. **Provenance — `rf.pilot-item.v2`** (`research/python/metrics/items.py`): блок `authoring` с `origin` (`human` | `llm_assisted` | `unrecorded`), `revision_reason` (`naturalness` | `adjacency` | `grammar` | `other`), `accepted_via` (`original` | `carried_over` | `blinded_ab` | `facilitator`) и `parent_item_version` (пакет, item, content-hash родителя). Это история происхождения, а не ярлык: `origin` описывает текст именно этой версии, принятый LLM-кандидат — `llm_assisted`, кто бы его ни принял; тексты v0 — `unrecorded` (commit `07b5106` называет их handcrafted в сессии с LLM-соавтором, достоверно авторство не восстанавливается). `metrics.validate_items` проверяет lineage: hash родителя в соседнем пакете, «carried_over ⇒ текст идентичен», «revision ⇒ текст изменён», presentation-слой — всегда v1-проекция без `authoring`.
3. **Отчёт pilot** (`metrics.agreement`) строит `unnatural_example` × disagreement / decision-disagreement / abstention / stratum / item из необязательного поля `feedback` в ответе (коды — как в annotation-web `Feedback.hs`). Инструкция v0.1 обязана предложить это поле разметчику; без него секция отчёта честно говорит «не собрано». Adjacency в этой оси не растворяется: в аудите она остаётся отдельными кодами (`NON_ADJACENT_REPLY`, `EXPOSITION_FOR_READER`), даже пока UI знает только `unnatural_example`.
4. **Blinded A/B** (`data/pilot/naturalness-ab/v0-flagged/`, `metrics.naturalness_ab`): 13 items × 2 кандидата = 26 пар; пять per-rater пакетов с opaque pair ids, своей стороной оригинала и своим порядком; два независимых вопроса на пару — «какой вариант больше похож на реальную переписку пары?» и «отличаются ли варианты по смыслу или накалу?»; рекомендация: любой `substantial` — отклонить, иначе eligible при строгом большинстве за кандидата; итог — вручную.
5. **Онтология и примеры.** Definitions не трогаются: «понимаю / вижу / слышу» — законное описание construct'а. Атакуется источник: [item-authoring-v0.1](../item-authoring-v0.1.md) («preserve the construct, not the canonical wording»), запрет переиспользования текстов в обе стороны, adjacency и род как правила авторинга. Positives в живом регистре для v0.2-candidate — отдельный, ещё не сделанный шаг.
6. **Инструмент** (LLM-критик с few-shot из принятых и отклонённых пар) — только после 50–100+ adjudicated правок. С 13 примерами получится не обучающий набор, а коллекция собственных предубеждений в YAML.

## 10. Чего не делать

- Не гонять корпус через humanizer-сервисы и не тестировать их «на всякий случай»: результат нельзя будет откатить, а provenance — восстановить.
- Не делать LLM-judge финальным оракулом naturalness; калибровать на людях даже при 3–5 оценщиках.
- Не переписывать все 46; только flagged, только с двумя кандидатами и checker'ом.
- Не «оживлять» матом и опечатками.
- Не строить линтер сейчас: на 46 единицах он даст те же false positives, что гендерный (dg-04), а стоить будет больше, чем ручной проход.
- Не трогать operational definitions под предлогом регистра: меняется example-set, не construct.

## 11. Решения (2026-09-07) и порядок работ

Четыре решения, принятые по итогам §1–8:

1. **Pilot на текущем v0 не запускается.** Цена исправления сейчас минимальна (responses пуст, eligibility не начат). v0 — исторический артефакт, не правится in place; v0.1 собирается как новый immutable package.
2. **Provenance/authoring вводится до первой naturalization-правки** — иначе через месяц не доказать, что было исходным, что исправлено вручную, что предложено моделью и что принято после A/B.
3. **13 flagged items идут в blinded A/B, а не переписываются по вкусу.** 3–5 человек, не авторы и не будущие разметчики; по каждому кандидату две независимые оценки (естественность; сдвиг смысла/интенсивности); accept только после этого. Документ уже показал четыре способа незаметно угробить target: generalization, apology leakage, gender leakage, destruction of evidence span.
4. **Утечка примеров из v0.2-candidate убирается немедленно и независимо** от судьбы naturalization pass: это experimental contamination, а не naturalness.

Порядок работ и статус:

| # | Шаг | Статус |
|---|---|---|
| 1 | Freeze v0 as historical | сделано: `data/pilot/v0/README.md` |
| 2 | Provenance/authoring representation | сделано: `rf.pilot-item.v2`, `metrics/items.py`, lineage-проверки в `validate_items` (родитель — явная тройка package_id + item_id + content_sha256; дубликат pilot_id среди пакетов — fail-closed, lineage через него не резолвится), v1-проекция в `presentation` |
| 3 | Remove v0.2-candidate target leakage | сделано: три примера B.AVOIDANCE_TOPIC_SHIFT заменены; частичная утечка контекста pc-08 в glossary annotation-web записана (§3) |
| 4 | Minimal-edit candidates for 13 flagged items | сделано: `candidates.json`, 26 кандидатов + 4 отклонённых (negative controls); veto-review фасилитатора — только по чек-листу V1–V10, след `vetoed` с причиной, `metrics.naturalness_ab check` гейтит `build`; **ждёт veto-review** |
| 4b | Donor-grounded generation для тех же 13 items | подготовлено: `data/pilot/naturalness-ab/v0-flagged-donor/` — donor report с лицензиями по первичным артефактам (RESD MIT tier A, Dialogs OpenRAIL tier B, Toloka NC reference-only, DRAL CC0 без транскриптов), 13 кандидатов на скелетах импровизированных диалогов RESD (4 замены сюжета, 9 ревизий), provenance `method: external_dialogue_seeded`, n-gram проверка некопирования; два прохода review фасилитатора 2026-09-08: первый — 4 вето → d2; второй — **11 accepted** (6 явных + 5 переведены из no_veto), 2 вето (pc-12-d2 V3/V4 temporal contract, pc-17-d1 V3 новый факт) → pc-12-d3, pc-17-d2; третий — оба accepted (pc-17-d2 с записанной оговоркой V7/V5): **13/13 accepted, 0 pending**; replacements не идут через A/B gate; корпус не изменён, **v0.1 не собран**, human naturalness evidence: none; next gate — explicit v0.1 build/cutover; на pilot — exploratory кросс-таб `unnatural_example` × способ авторинга |
| 4a | Independent blind audit of all 46 items | подготовлено: `data/pilot/naturalness-audit/v0-all/` — стерильный Pass A (opaque ids, свой порядок, только реплики, три вопроса), Pass B после заморозки ответов (`metrics.naturalness_audit report` пишет sha256 ответов и counts против critic-1 по стратам); contamination ledger `data/pilot/contamination-ledger.json`; **ждёт аудитора, который не автор, не A/B rater и никогда не pilot annotator** |
| 5 | Human blinded A/B | подготовлено: 5 пакетов, инструкции, scoring; **ждёт людей** |
| 6 | Accept/reject edits manually | ждёт результатов A/B |
| 7 | Build v0.1 + new hash + regenerated presentation | **сделано 2026-09-08**: `data/pilot/v0.1` собран `metrics.materialize` по [cutover contract](../pilot-v0.1-cutover-contract.md) (exact accepted→built equality gate, package-level `replaces`, sealed); dg-* — `v0.1/form/dogfood-v7-items.yaml` + provenance sidecar, `Catalog.hs` не переключён (web cutover) |
| 8 | Start pilot | ждёт web cutover (отдельная приёмка), eligibility и GO на issuance (J); инструкция v0.1 с каналом `feedback` — [pilot-v0.1-instructions](../pilot-v0.1-instructions.md), hash pin в issuance record |
| 9 | Cross-tab `unnatural_example` × disagreement | подготовлено в `metrics.agreement` (`item_feedback`); **ждёт ответов с полем `feedback`** |
| 10 | Automation only after enough adjudicated data | не раньше 50–100+ правок |

Самый сильный результат §7 — распределение natural 1/20, challenge 8/20, dogfood 4/6 — говорит, где рождается дефект: synthetic boundary pressure. Поэтому массовой переписи корпуса нет; лечатся страты, где конструкция stimulus слишком явно обслуживает онтологию. Но это распределение пока стоит на одном проходе одного критика, и критик — модель; evidence оно станет только после слепого аудита 4a. Правило contamination accounting — **hard separation**: auditor ≠ A/B rater ≠ pilot annotator, без исключений при нехватке людей; авторы кандидатов и veto-reviewer тоже не оценщики. Аудитор в роли оценщика узнаёт оригиналы, оценщик в роли аудитора заранее видел альтернативы, любой из них в pilot — нарушенный `has_not_seen_items`. Если людей не хватает, уменьшается число оценщиков или откладывается этап; вынужденное отклонение записывается в `contamination-ledger.json` до выдачи.

### Решения human phase (2026-09-07, зафиксированы до первого выданного пакета)

1. **Auditor-only находки Pass A чинятся в том же цикле v0.1** через generation 2: отдельный каталог кандидатов, собственный veto-review, собственные blinded-пакеты для тех же или других независимых оценщиков (gen-1 оценщики слепы для gen 2 по построению — наборы items не пересекаются). Generation 1 не перевыдаётся. Auditor-only находка не обязывает менять item: без admissible edit оригинал остаётся, причина записывается.
2. **Decision rule — текущий, preregistered, код не меняется**: любой `substantial` → ineligible; eligible при `candidate > original` среди направленных голосов; `no_difference` нейтрален (ближе к abstention, чем к голосу за status quo); `slight` не блокирует. Пример: candidate 2, original 1, no_difference 2, substantial 0 → eligible.
3. **Принцип adjudication**: ineligible-кандидат **не может** быть принят; eligible-кандидат **может** быть отклонён, но с записанной причиной, независимой от личного предпочтения естественности. Числовой extra-threshold на adjudication не вводится — это было бы изменение decision rule через заднюю дверь.
4. **--force после записи выдачи запрещён процедурой, не кодом**: модель — provenance/detection, не cryptographic prevention. Любое расхождение выданного пакета с записанным SHA инвалидирует выдачу и требует новой; старые ответы к новой выдаче не относятся.
5. **Hard role separation** — см. выше.

Окончательная последовательность human phase:

| # | Шаг | Lock |
|---|---|---|
| 0 | Veto-review generation 1 (только V1–V10, не «нравится») | issuance record: sha256 candidates.json, vetoed/admissible counts, issued_at, псевдоним ревьюера |
| 1 | Independent Pass A по всем 46 | sha256 ответов в первом закоммиченном `audit-result.json` |
| 2 | Pass B: critic-1 vs auditor, обе клетки расхождения | — |
| 3 | Generation 2 для auditor-only: кандидаты → veto-review | issuance record gen 2 |
| 4 | Выдача A/B gen 1 + gen 2 независимым оценщикам | packet SHA per rater |
| 5 | Lock ответов оценщиков | sha256 per rater |
| 6 | Score по preregistered rule | `ab-result.json` |
| 7 | Adjudication: ineligible нельзя; eligible можно отклонить с причиной | adjudication record |
| 8 | Freeze adjudication record | — |
| 9 | Сборка v0.1 один раз из финального accepted set (по мере поступления голосов — никогда) | — |
| 10 | validate_items: lineage, новый package hash; плюс ручная сверка каждой ревизии с текстом eligible-кандидата из `candidates.json` и статусом из `ab-result.json` (машиной не проверяется — cutover work) | package hash |
| 11 | Cutover: реестр статусов пакетов, `v0` не выдаётся runtime'ом, pc-08 в живом glossary `Domain.hs` перефразирован, token-bound renderer/collector, canonical export — **выполнено 2026-09-08**, см. [pilot-v0.1-cutover-contract](../pilot-v0.1-cutover-contract.md) §Web cutover; критерий eligibility по ledger — при issuance (`metrics.issuance` отказывает без eligibility) | — |
| 12 | Pilot | — |

Evidence bundle окончания human phase: veto (sha candidates.json, vetoed + причины), blind audit (packet SHA, псевдоним, response SHA, counts critic-1 vs auditor по стратам, список расхождений), A/B (packet SHA per rater, псевдонимы, response SHA, preference и semantic-change counts, adjudication outcome per item), ledger заморожен, итог: accepted / rejected / unchanged flagged. Что из этого пишется руками: issuance records, псевдонимы, adjudication record; сборщика v0.1 нет, гейт — `validate_items`.

### Решения 2026-09-08: люди и поверхности

1. **Единственный fallback при нехватке людей:** A/B gen 1 на трёх оценщиках, затем один из них аудирует только complement из 33 items вне A/B; запись в ledger до выдачи. Потеря evidence: «critic flagged → human says fine» для 13 gen-1 items не независима и не читается как blind-audit evidence; `auditor_only` на 33 unseen остаётся чистым. Идеальный состав без fallback: 1 аудитор + 3 оценщика + 2–3 наивных разметчика, 6–7 разных людей; наивных разметчиков искать последними и не показывать им ничего.
2. **Item-level contamination:** exposure заражает для увиденных item ids, не глобально; `seen via dogfood → contaminated only for those item_ids` (все прошедшие dogfood — для dg-04…dg-09). В ledger — `exposures` с item ids, причиной и датой.
3. **XLSX** — текущая operational human surface аудита и A/B; остаётся, не временная.
4. **Web при cutover v0.1** — тупой renderer/collector, привязанный к sha256 выданного пакета и токену; порядок, сторона и состав из immutable packet, никакой собственной рандомизации; нужен самому pilot. Dashboard не нужен, token routing нужен.
5. **Контакт-поле отложено** до непрямой выдачи ссылок: optional, отдельный consent, вне research export, удаляется отдельно, связь с данными только через facilitator-held pseudonym mapping, не quasi-identifier.

Issuance: до отправки каждому человеку записывается sha256 именно того экземпляра файла, который уходит этому псевдониму, а не «пакет когда-то собран».

**Статус: protocol decisions recorded · code phase CLOSED · human phase READY. Next: 1 auditor, 3 A/B raters, pilot annotators untouched. Никакие ревизии корпуса не admissible до полного закрытия и lock veto-review, blind audit и A/B.**

### Решения 2026-09-08: donor generation без людей

Контекст: на этом этапе людей нет (см. 4b). Human phase выше остаётся определённой и готовой, но не является предусловием v0.1 на этом пути; статусная строка выше для no-people пути **superseded** пунктами ниже.

1. **Replacement не идёт через preregistered A/B acceptance gate.** Gate сравнивает варианты одного item; сравнение нового сюжета со старым измеряло бы предпочтение сюжета, а не правку. Путь replacement: donor → facilitator acceptance (V1–V10 против design intent, причина записывается) → новый original item в v0.1 (`origin: llm_assisted`, `accepted_via: facilitator`, `parent_item_version: null`), старый item retired → сигнал естественности только с pilot.
2. **Для `kind: replacement` V3/V4 применяются к observable actions, которых требует design intent, а не к конкретным фактам и сюжету retired original.** Для revision — по-прежнему против оригинала.
3. **Acceptance donor-ревизий без A/B** — решение фасилитатора с записанной причиной, `accepted_via: facilitator`; к трём A/B-оценщикам не возвращаемся. Review 2026-09-08, проход 1: 4 вето (pc-02-d1 V1/V2, pc-12-d1 V7/V3/V5, pc-09-d1 V4, pc-05-d1 V3/V5) → d2. Проход 2: accepted pc-02-d2, pc-05-d2, pc-09-d2, pc-13-d1, dg-05-d1, dg-06-d1 и, переводом из no_veto, pc-06-d1, pc-16-d1, pn-10-d1, dg-04-d1, dg-09-d1 (11); вето pc-12-d2 (V3/V4: «the day before» — новый temporal contract) и pc-17-d1 (V3: новый факт «час торчу») → pc-12-d3, pc-17-d2. Проход 3: pc-12-d3 accepted (исходный behavioural contract восстановлен); pc-17-d2 accepted с записанной оговоркой V7/V5 (скорее будущий `unnatural_example`, чем veto). **13/13.** Каждое решение — `facilitator_review` у кандидата с причиной; сводка — `review_log`, статус — `acceptance_status`. Принятие живёт в `candidates.json`; корпус не изменён.
4. **Кросс-таб `unnatural_example` × способ авторинга на pilot — exploratory diagnostic**, не тест причинного превосходства метода: items выбраны по флагам, не рандомизированы по способу авторинга.
6. **Carve-out natural-страты — узкий, не общий.** При явно выбранном пути без pre-pilot human naturalness evidence facilitator MAY принять заранее flagged natural-stratum item только при `kind=revision`, только при V9 lexical-only change и с явной записью `accepted_via=facilitator`; это не human evidence и не расширяет правило на semantic/content revisions (authoring guide, правило 6; прецедент pn-10-d1). Не «natural-stratum теперь можно принимать фасилитатором».
5. Cutover work, код не сейчас: `metrics.naturalness_ab build` должен пропускать `kind=replacement` (сейчас build не различает kind — на donor-каталоге он процедурно не запускается); представление retired status и связи «новый original ← retired item» (в `rf.pilot-item.v2` поля нет); ручная сверка принятых donor-кандидатов с `candidates.json` при сборке v0.1.

**Статус: naturalness-authoring CLOSED · 13/13 donor candidates accepted · v0.1 ACCEPTED / SEALED 2026-09-08 (contract A–I closed) · web cutover EXECUTED 2026-09-08 и DEPLOYED (ce9f365) · issuance J: eligibility lifecycle починен 2026-09-09 (внешняя `rf.annotator-eligibility.v1`, sealed шаблон не трогается, ссылка печатается один раз); remaining: установить eligibility двух реальных разметчиков, изготовить две записи, скопировать на хост, рестарт сервиса · human naturalness evidence: none.** Сборка — отдельная работа с отдельным «го» по [pilot-v0.1-cutover-contract](../pilot-v0.1-cutover-contract.md): пять развилок закрыты 2026-09-08 (retirement в manifest, fresh ids, design intent facilitator-only, dogfood sidecar, exact accepted→built equality как gate), контракт A–J, build ≠ web cutover; три пункта ещё открыты и названы там (правило нумерации ids, `accepted_via` для replacement без parent, `origin` для carried_over). «Собрать как очевидно» не разрешено.

## Источники

- USR — Mehri & Eskenazi, ACL 2020: https://aclanthology.org/2020.acl-main.64/ ✅
- DynaEval — Zhang et al., ACL 2021: https://aclanthology.org/2021.acl-long.441/ ✅
- DSTC11 Track 4 overview (multilingual = en/es/zh): https://arxiv.org/abs/2306.12794 ✅
- Grounded Minimal Edits — Wu, Zheng, Mao, Huang, EMNLP 2021: https://aclanthology.org/2021.emnlp-main.183/ ✅
- Binoculars (ICML 2024): https://github.com/ahans30/Binoculars ✅ · MULTITuDE (11 языков, есть ru): https://arxiv.org/abs/2310.13606 ✅
- Why Synthetic Isn't Real Yet (contact-center diagnostic framework, 17 метрик / 4 измерения): https://arxiv.org/abs/2508.18210 ✅
- Feel the Difference? Real vs LLM-generated CBT sessions (RealCBT): https://arxiv.org/abs/2508.20764 ✅
- Evaluating LLM-Generated Versus Human-Authored Responses in Role-Play Dialogues — INLG 2025: https://aclanthology.org/2025.inlg-main.2/ (arXiv 2509.17694) ✅
- Inverse Turing Bench: https://arxiv.org/abs/2606.21844 — ✅ существует; ❌ как подтверждение тезиса «судьи предпочитают GPT-подобные диалоги после перемешивания реплик»
- Toloka Persona Chat Rus: https://www.kaggle.com/datasets/valentinbiryukov/toloka-persona-chat-rus ⚠️ (справочник регистра, не задача)

Внутренние: `docs/annotation-protocol-v0.md` §5–6 · `data/pilot/v0/form/dogfood-v6-items.yaml` · `src/annotation-web/src/Feedback.hs` · commits `07b5106` (правило про example texts), `bdda6c2` (dg-04).
