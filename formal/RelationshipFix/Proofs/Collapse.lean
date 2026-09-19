/-
  PROOFS — схлопывание там, где порядка не скрыто.
-/
import RelationshipFix.Proofs.Structure

namespace RelationshipFix

/-- ТЕОРЕМА 3. `Spec.BoundedCollapsesOnTotalOrder`.

    Именно это отличает BOUNDED от второго определения метрики: где
    неоднозначности нет, он обязан деградировать в обычный экстрактор. -/
theorem bounded_collapses_on_total_order : Spec.BoundedCollapsesOnTotalOrder := by
  intro o
  induction o with
  | nil =>
      intro _ l h
      cases h
      rfl
  | cons b bs ih =>
      intro hu l h
      cases h with
      | cons hp hrest =>
          rename_i lb rest
          have hb : lb = b := perm_eq_of_uniform hp (hu b (by simp))
          have hr : rest = bs.flatten :=
            ih (fun x hx => hu x (by simp [hx])) rest hrest
          rw [hb, hr, List.flatten_cons]

end RelationshipFix
