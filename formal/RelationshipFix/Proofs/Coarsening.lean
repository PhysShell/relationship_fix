/-
  PROOFS — огрубление только стирает ограничения порядка.
-/
import RelationshipFix.Proofs.Structure

namespace RelationshipFix

/-- ТЕОРЕМА 1. `Spec.CoarseningPreservesFineOrders`. -/
theorem coarsening_preserves_fine_orders : Spec.CoarseningPreservesFineOrders := by
  intro blocks
  induction blocks with
  | nil =>
      intro l h
      cases h
      exact Admissible.nil
  | cons blk rest ih =>
      intro l h
      rw [List.flatten_cons] at h
      obtain ⟨l₁, l₂, rfl, h₁, h₂⟩ := admissible_split blk rest.flatten l h
      exact Admissible.cons (admissible_perm blk l₁ h₁) (ih l₂ h₂)

/-- Арифметический мост: если Δ₁ делит Δ₂, то грубый ключ есть ФУНКЦИЯ от
    мелкого. Отсюда и следует, что грубая корзина — объединение подряд идущих
    мелких. Что сборка корзин в Python реализует именно это — утверждение о
    реализации, и оно проверяется property-тестом, а не здесь. -/
theorem coarse_key_factors (fine coarse t : Nat) (hpos : 0 < fine)
    (hdvd : fine ∣ coarse) :
    t / coarse = (t / fine) / (coarse / fine) := by
  obtain ⟨k, rfl⟩ := hdvd
  rw [Nat.mul_div_cancel_left k hpos, Nat.div_div_eq_div_mul]

/-- У событий с одинаковым мелким ключом одинаковый грубый. -/
theorem same_fine_key_same_coarse_key (fine coarse a b : Nat) (hpos : 0 < fine)
    (hdvd : fine ∣ coarse) (h : a / fine = b / fine) :
    a / coarse = b / coarse := by
  rw [coarse_key_factors fine coarse a hpos hdvd,
      coarse_key_factors fine coarse b hpos hdvd, h]

end RelationshipFix
