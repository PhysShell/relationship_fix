# Research hypotheses

Здесь фиксируются предположения, которые **могут оказаться ложными**. Они не являются invariants и не должны проникать в продукт как факт до соответствующего evaluation gate.

## H1 — Persona simulation: recovery vs attachment

**Гипотеза:** ограниченная персонализированная симуляция может уменьшать urge-to-contact реального ex и помогать rehearsal/closure лучше, чем generic assistant, не создавая более сильной зависимости от агента.

**Фальсификация:** если style/state-matched simulator повышает agent attachment, rumination или usage trajectory без клинически/поведенчески значимого улучшения recovery outcomes, simulator mode не оправдан.

Кандидат-дизайн: A generic assistant / B style-matched stateless / C style+state+boundaries; primary — изменение urge-to-contact/rumination, secondary — validated agent-attachment measure + usage distribution. Simulator включается только после safety/compliance gate.

## H2 — Personalized deliberate practice > generic psychoeducation

**Гипотеза:** Replay на собственных реальных эпизодах даёт больший перенос коммуникативного навыка на новые ситуации, чем generic relationship education.

**Риск:** RCT-база deliberate practice в найденной литературе относится прежде всего к подготовке терапевтов; перенос на обычных партнёров не доказан.

**Тест:** generic arm vs personalized Replay; outcome — blinded evaluation на unseen scenarios, а не self-report «было полезно» сразу после тренировки.

## H3 — Trajectory metrics имеют construct validity на real dyads

**Гипотеза:** representation взаимодействия как sequence/trajectory добавляет полезную информацию сверх bag-of-labels / sentiment timeline.

**Риск:** State Space Grid representation полезна как язык описания, но отдельные flexibility/attractor metrics не имеют автоматической predictive/construct validity для нашей задачи.

**Тест:** E0 на synthetic проверяет только recovery planted trajectory; E1 на real conversations + blind annotation решает вопрос construct validity. Synthetic success не считается подтверждением H3.

## H4 — Auditable evidence loop даёт добавочную продуктовую ценность

**Гипотеза:** active counterevidence search + calibrated abstention + source provenance + human correction создают заметно более полезный и доверенный анализ, чем сильный evidence-first prompt поверх frontier LLM.

**Тест:** blind A/B/C baseline из [evaluation contract](evaluation-contract.md), затем one-shot willingness-to-pay за полный Microscope report + Replay.

**Фальсификация:** если C едва отличается от strong prompt baseline или пользователи не платят после реально показанной ценности, собственный engine/сложный pipeline требует пересмотра.

## H5 — Ex-archive test bench переносится на living couples

**Гипотеза:** ontology и retrieval, отлаженные на retrospective/ex архивах, сохраняют приемлемую precision на живых, включая довольные и неконфликтные пары.

**Риск:** selection bias ex-data оптимизирует систему под conflict, criticism, withdrawal и rupture и превращает обычную playful/healthy коммуникацию в патологию.

**Тест:** Living Couple Sanity Set (5–10 действующих пар) до основного Stage 5 + synthetic non-conflict scenarios: normality, affection, playful insults, healthy disagreement, successful repair, accepted boundary, support offered/declined without conflict.

## Текущий критерий направления

Microscope-first остаётся test bench, а не доказанной бизнес-моделью. Existing-couples surface становится основным кандидатом на recurring value только после того, как H3–H5 проходят соответствующие E1/E2 gates.
