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

/-- Разрешённые аксиомы. Ровно одна: `propext`. Ни `Classical.choice`, ни
    `Quot.sound` ядру не понадобились, и расширять список молча нельзя. -/
def permittedAxioms : List Name := [``propext]

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
    `RelationshipFix.Spec.NIdentifiedSetCollapses)]

/-- Вопросы, заданные и пока не закрытые. Их отсутствие в solution — не
    недосмотр, а состояние работ, видимое машине. -/
def openQuestions : List (Name × Name) :=
  [(`RelationshipFix.Challenge.dp_bounds_sound,
    `RelationshipFix.Spec.DPBoundsSound),
   (`RelationshipFix.Challenge.dp_bounds_sharp,
    `RelationshipFix.Spec.DPBoundsSharp),
   (`RelationshipFix.Challenge.sharp_bounds_exist_abstract,
    `RelationshipFix.Spec.SharpBoundsExistAbstract)]

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
