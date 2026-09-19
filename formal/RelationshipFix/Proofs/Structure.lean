/-
  PROOFS — структурные леммы о допустимости. Слой, который меняется ЧАСТО.
-/
import RelationshipFix.TrustedSpec

namespace RelationshipFix

/-- Полная развёртка наблюдения — одна конкретная допустимая история. -/
theorem admissible_flatten (o : Observation) : Admissible o o.flatten := by
  induction o with
  | nil => exact Admissible.nil
  | cons b bs ih =>
      simpa [List.flatten] using Admissible.cons (List.Perm.refl b) ih

/-- Допустимая история — перестановка развёртки. Огрубление стирает порядок,
    но не события. -/
theorem admissible_perm (o : Observation) (l : List Actor)
    (h : Admissible o l) : o.flatten.Perm l := by
  induction h with
  | nil => exact List.Perm.refl []
  | cons hb _ ih => exact (hb.append ih)

/-- Наблюдение из двух частей расщепляет любую допустимую историю на две. -/
theorem admissible_split (a b : Observation) (l : List Actor)
    (h : Admissible (a ++ b) l) :
    ∃ l₁ l₂, l = l₁ ++ l₂ ∧ Admissible a l₁ ∧ Admissible b l₂ := by
  induction a generalizing l with
  | nil => exact ⟨[], l, rfl, Admissible.nil, h⟩
  | cons x xs ih =>
      cases h with
      | cons hx hrest =>
          rename_i lx rest
          obtain ⟨l₁, l₂, rfl, h₁, h₂⟩ := ih rest hrest
          exact ⟨lx ++ l₁, l₂, by simp [List.append_assoc],
                 Admissible.cons hx h₁, h₂⟩

/-- Обратное склеивание. -/
theorem admissible_append (a b : Observation) (l₁ l₂ : List Actor)
    (h₁ : Admissible a l₁) (h₂ : Admissible b l₂) :
    Admissible (a ++ b) (l₁ ++ l₂) := by
  induction h₁ with
  | nil => simpa using h₂
  | cons hx _ ih => simpa [List.append_assoc] using Admissible.cons hx ih

/-- Перестановка однородного списка равна ему самому. -/
theorem perm_eq_of_uniform {b l : List Actor} (hp : b.Perm l) (hu : Uniform b) :
    l = b := by
  cases b with
  | nil => simpa using hp.symm.eq_nil
  | cons x xs =>
      have hb : (x :: xs) = List.replicate (x :: xs).length x := by
        rw [List.eq_replicate_iff]
        exact ⟨rfl, fun y hy => hu y hy x (by simp)⟩
      have hl : l = List.replicate l.length x := by
        rw [List.eq_replicate_iff]
        refine ⟨rfl, fun y hy => ?_⟩
        exact hu y (hp.mem_iff.mpr hy) x (by simp)
      rw [hl, hb, hp.length_eq]

end RelationshipFix
