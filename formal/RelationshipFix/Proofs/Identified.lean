/-
  PROOFS — идентифицированное множество N.
-/
import RelationshipFix.Proofs.Coarsening
import RelationshipFix.Proofs.Collapse

namespace RelationshipFix

/-- `Spec.IdentifiedNonempty`. -/
theorem identified_nonempty : Spec.IdentifiedNonempty :=
  fun o => ⟨o.flatten, admissible_flatten o, rfl⟩

/-- ТЕОРЕМА 2. `Spec.NIdentifiedSetMonotone`.

    `N` зависит ИСКЛЮЧИТЕЛЬНО от допустимой топологии порядка: никакого
    временного бюджета, никаких секунд. Поэтому нарушение здесь есть баг в
    огрублении, сборке корзин или DP — и ничто иное. -/
theorem n_identified_set_monotone : Spec.NIdentifiedSetMonotone := by
  rintro blocks n ⟨l, hl, hn⟩
  exact ⟨l, coarsening_preserves_fine_orders blocks l hl, hn⟩

/-- `Spec.NIdentifiedSetCollapses`. -/
theorem n_identified_set_collapses : Spec.NIdentifiedSetCollapses := by
  intro o h n
  constructor
  · rintro ⟨l, hl, rfl⟩
    rw [bounded_collapses_on_total_order o h l hl]
  · rintro rfl
    exact identified_nonempty o

end RelationshipFix
