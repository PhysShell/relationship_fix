/-
  PROOFS — перечисление эффектов корзины НИЧЕГО НЕ ТЕРЯЕТ.

  Это половина локальной точности, нужная для SOUNDNESS: эффект любой
  реальной перестановки присутствует в `bucketEffects`. Конструктивная
  половина (каждый перечисленный эффект материализуется) здесь не
  доказывается и soundness не держит.
-/
import RelationshipFix.Proofs.Blocks

namespace RelationshipFix

/-- Однородный партнёрский список: один блок, состояние «открыто». -/
theorem allPartner_scan : ∀ (l : List Actor), l ≠ [] →
    (∀ a ∈ l, a = Actor.partner) → ∀ carried,
      countFrom carried l = (if carried then 0 else 1) ∧ stateAfter carried l = true := by
  intro l
  induction l with
  | nil => intro h; exact absurd rfl h
  | cons a as ih =>
      intro _ hall carried
      have ha : a = Actor.partner := hall a (by simp)
      subst ha
      cases as with
      | nil => cases carried <;> simp [countFrom, stateAfter]
      | cons b bs =>
          have hrest := ih (by simp) (fun c hc => hall c (by simp [hc])) true
          cases carried <;> simp [countFrom, stateAfter] at hrest ⊢ <;> omega

/-- Однородный участнический список: возможностей нет, состояние «закрыто». -/
theorem allParticipant_scan : ∀ (l : List Actor), l ≠ [] →
    (∀ a ∈ l, a = Actor.participant) → ∀ carried,
      countFrom carried l = 0 ∧ stateAfter carried l = false := by
  intro l
  induction l with
  | nil => intro h; exact absurd rfl h
  | cons a as ih =>
      intro _ hall carried
      have ha : a = Actor.participant := hall a (by simp)
      subst ha
      cases as with
      | nil => simp [countFrom, stateAfter]
      | cons b bs =>
          have hrest := ih (by simp) (fun c hc => hall c (by simp [hc])) false
          simp [countFrom, stateAfter] at hrest ⊢
          exact hrest


/-- КЛЮЧЕВАЯ СОВМЕСТИМОСТЬ: перечисление `patterns` содержит любую тройку,
    удовлетворяющую ограничению чередования и границам по числу сообщений.

    Если эта лемма не пройдёт, это будет содержательный сигнал о расхождении
    `patterns` и семантики, а не обычная канцелярия. -/
theorem mem_patterns (p q pb qb : Nat) (first : Bool)
    (h1 : 1 ≤ pb) (h2 : pb ≤ p) (h3 : 1 ≤ qb) (h4 : qb ≤ q)
    (halt : if first = true then (pb = qb ∨ pb = qb + 1)
            else (qb = pb ∨ qb = pb + 1)) :
    (first, pb, qb) ∈ patterns p q := by
  have hpb : pb ∈ List.range' 1 p := by
    rw [List.mem_range']
    exact ⟨pb - 1, by omega, by omega⟩
  have hqb : qb ∈ List.range' 1 q := by
    rw [List.mem_range']
    exact ⟨qb - 1, by omega, by omega⟩
  simp only [patterns, List.mem_flatMap]
  refine ⟨pb, hpb, qb, hqb, ?_⟩
  cases first with
  | true =>
      rcases halt with heq | heq
      · simp [heq]
      · simp [heq]
  | false =>
      rcases halt with heq | heq
      · simp [heq]
      · -- `pb = qb + 1` здесь ложно, но simp этого сам не видит
        simp only [heq]
        rw [if_neg (by omega)]
        simp

end RelationshipFix
