/-
  SOLUTION — ОТВЕТ. Связывает доказанные теоремы с замороженными
  формулировками.

  Не импортирует `Challenge`: сверку делает судья, а не решение.
  Незакрытые вопросы здесь просто ОТСУТСТВУЮТ — `StatementIntegrity`
  перечислит их как открытые.
-/
import RelationshipFix.Proofs

namespace RelationshipFix.Solution

theorem coarsening_preserves_fine_orders : Spec.CoarseningPreservesFineOrders :=
  RelationshipFix.coarsening_preserves_fine_orders

theorem n_identified_set_monotone : Spec.NIdentifiedSetMonotone :=
  RelationshipFix.n_identified_set_monotone

theorem bounded_collapses_on_total_order : Spec.BoundedCollapsesOnTotalOrder :=
  RelationshipFix.bounded_collapses_on_total_order

theorem identified_nonempty : Spec.IdentifiedNonempty :=
  RelationshipFix.identified_nonempty

theorem n_identified_set_collapses : Spec.NIdentifiedSetCollapses :=
  RelationshipFix.n_identified_set_collapses

end RelationshipFix.Solution
