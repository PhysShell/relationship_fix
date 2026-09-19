/-
  СУДЬЯ. Проверяет не «чисто ли доказательство», а гораздо более неприятный
  вопрос: ДОКАЗЫВАЕТ ЛИ ОНО ТОТ ВОПРОС, который был зафиксирован заранее.

  Главный риск нынешней стадии не `sorry` — его ноль. Риск такой:

      не могу доказать -> слегка «улучшаю» определение -> доказываю -> QED

  Здесь это становится ошибкой сборки. Проверяется:

    1. тип challenge-теоремы СОВПАДАЕТ с типом solution-теоремы;
    2. этот тип есть в точности ЗАМОРОЖЕННАЯ КОНСТАНТА из `TrustedSpec`,
       а не её развёрнутая копия, которая могла бы разойтись;
    3. solution не зависит от `sorryAx` и не выходит за список разрешённых
       аксиом;
    4. challenge, наоборот, ОБЯЗАН зависеть от `sorryAx` — иначе это не
       дыра в задании, а чьё-то доказательство, пролезшее в вопрос.

  Чего здесь НЕТ, и об этом сказано прямо: это НЕ upstream `comparator`.
  Тот дополнительно собирает challenge и solution в РАЗНЫХ окружениях и
  переигрывает доказательство ядром заново. Причины, по которым он здесь не
  запущен, перечислены в `docs/formal-model.md`, и статус там — DEFERRED, а
  не «сделано».
-/
import Lean
import RelationshipFix.Verification.Challenge
import RelationshipFix.Verification.Solution

open Lean Elab Command

namespace RelationshipFix.Verification

/-- Разрешённые аксиомы.
    ДОВЕРЕННАЯ БАЗА ВЫРОСЛА, и это записано, а не замолчано.

    Первые пять теорем (огрубление, монотонность, схлопывание) обходились
    ОДНИМ `propext`. Доказательство корректности границ DP втянуло ещё две —
    `Classical.choice` и `Quot.sound`, — и не из-за экзотики: они приходят из
    обычных библиотечных лемм про `List` и из `omega`.

    Это стандартная классическая тройка, та же, на которой стоит
    формализация Ферма. Охотиться за `Classical.choice` внутри ядра Lean было
    бы днями работы при нулевом эпистемическом выигрыше.

    Но прежнее хвастовство «у нас база меньше, чем у FLT» больше не верно для
    новых теорем, и `FinalCheck` пинит РАЗНЫЕ наборы для старых и новых: рост
    базы должен быть виден построчно, а не усреднён по проекту. -/
def permittedAxioms : List Name := [``propext, ``Classical.choice, ``Quot.sound]

/-- (challenge, solution, замороженная формулировка). -/
def claimed : List (Name × Name × Name) :=
  [(`RelationshipFix.Challenge.coarsening_preserves_fine_orders,
    `RelationshipFix.Solution.coarsening_preserves_fine_orders,
    `RelationshipFix.Spec.CoarseningPreservesFineOrders),
   (`RelationshipFix.Challenge.n_identified_set_monotone,
    `RelationshipFix.Solution.n_identified_set_monotone,
    `RelationshipFix.Spec.NIdentifiedSetMonotone),
   (`RelationshipFix.Challenge.bounded_collapses_on_total_order,
    `RelationshipFix.Solution.bounded_collapses_on_total_order,
    `RelationshipFix.Spec.BoundedCollapsesOnTotalOrder),
   (`RelationshipFix.Challenge.identified_nonempty,
    `RelationshipFix.Solution.identified_nonempty,
    `RelationshipFix.Spec.IdentifiedNonempty),
   (`RelationshipFix.Challenge.n_identified_set_collapses,
    `RelationshipFix.Solution.n_identified_set_collapses,
    `RelationshipFix.Spec.NIdentifiedSetCollapses),
   (`RelationshipFix.Challenge.bucket_effect_complete,
    `RelationshipFix.Solution.bucket_effect_complete,
    `RelationshipFix.Spec.BucketEffectComplete),
   (`RelationshipFix.Challenge.history_to_reachable,
    `RelationshipFix.Solution.history_to_reachable,
    `RelationshipFix.Spec.HistoryToReachable),
   (`RelationshipFix.Challenge.dp_bounds_sound,
    `RelationshipFix.Solution.dp_bounds_sound,
    `RelationshipFix.Spec.DPBoundsSound)]

/-- Вопросы, заданные и пока не закрытые. Их отсутствие в solution — не
    недосмотр, а состояние работ, видимое машине. -/
def openQuestions : List (Name × Name) :=
  [(`RelationshipFix.Challenge.dp_bounds_sharp,
    `RelationshipFix.Spec.DPBoundsSharp),
   (`RelationshipFix.Challenge.sharp_bounds_exist_abstract,
    `RelationshipFix.Spec.SharpBoundsExistAbstract),
   (`RelationshipFix.Challenge.bucket_effect_exact,
    `RelationshipFix.Spec.BucketEffectExact),
   (`RelationshipFix.Challenge.bucket_effect_realizable,
    `RelationshipFix.Spec.BucketEffectRealizable),
   (`RelationshipFix.Challenge.reachable_to_history,
    `RelationshipFix.Spec.ReachableToHistory),
   (`RelationshipFix.Challenge.identified_set_is_contiguous,
    `RelationshipFix.Spec.IdentifiedSetIsContiguous)]

run_cmd do
  let env ← getEnv
  for (chal, sol, spec) in claimed do
    let some ci := env.find? chal | throwError "нет challenge-декларации {chal}"
    let some si := env.find? sol | throwError "нет solution-декларации {sol}"
    unless ci.type == si.type do
      throwError "STATEMENT DRIFT: {chal} и {sol} имеют РАЗНЫЕ типы"
    unless ci.type == mkConst spec do
      throwError "{chal} формулирует не замороженную константу {spec}"
    let solAxioms ← liftCoreM <| collectAxioms sol
    if solAxioms.contains ``sorryAx then
      throwError "{sol} зависит от sorryAx — это объявление, а не доказательство"
    for a in solAxioms do
      unless permittedAxioms.contains a do
        throwError "{sol} использует неразрешённую аксиому {a}"
    let chalAxioms ← liftCoreM <| collectAxioms chal
    unless chalAxioms.contains ``sorryAx do
      throwError "{chal} НЕ является дырой — в вопрос пролезло доказательство"
  for (chal, spec) in openQuestions do
    let some _ := env.find? chal | throwError "нет challenge-декларации {chal}"
    if env.find? (`RelationshipFix.Solution ++ chal.getString!.toName) |>.isSome then
      throwError "{spec} числится открытым, а решение уже есть — обновите списки"
  logInfo s!"statement integrity: {claimed.length} claimed, \
{openQuestions.length} open, axioms limited to {permittedAxioms}"

end RelationshipFix.Verification
