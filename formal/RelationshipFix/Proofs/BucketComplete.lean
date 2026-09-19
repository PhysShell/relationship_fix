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


/-- Партнёрские блоки — это счёт от «серия не открыта». -/
theorem blocksOf_partner_none (l : List Actor) :
    blocksOf Actor.partner none l = countFrom false l := by
  rw [blocksOf_partner, opps_eq_countFrom]
  simp

/-- Двухакторность: нет участников — значит все партнёры. -/
theorem all_partner_of_no_participant (l : List Actor)
    (h : l.countP (fun a => decide (a = Actor.participant)) = 0) :
    ∀ a ∈ l, a = Actor.partner := by
  intro a ha
  have := (List.countP_eq_zero).1 h a ha
  rcases actor_cases a with h1 | h1
  · exact h1
  · simp [h1] at this

/-- И наоборот. -/
theorem all_participant_of_no_partner (l : List Actor)
    (h : l.countP (fun a => decide (a = Actor.partner)) = 0) :
    ∀ a ∈ l, a = Actor.participant := by
  intro a ha
  have := (List.countP_eq_zero).1 h a ha
  rcases actor_cases a with h1 | h1
  · simp [h1] at this
  · exact h1

/-- Пустой список — единственный без обоих актёров. -/
theorem eq_nil_of_no_actors (l : List Actor)
    (hp : l.countP (fun a => decide (a = Actor.partner)) = 0)
    (hq : l.countP (fun a => decide (a = Actor.participant)) = 0) : l = [] := by
  cases l with
  | nil => rfl
  | cons a as =>
      rcases actor_cases a with h1 | h1
      · simp [List.countP_cons, h1] at hp
      · simp [List.countP_cons, h1] at hq


/-- ПЕРЕЧИСЛЕНИЕ НИЧЕГО НЕ ТЕРЯЕТ: эффект любой перестановки корзины в нём
    есть. Половина локальной точности, нужная для SOUNDNESS. -/
theorem bucket_effect_complete : Spec.BucketEffectComplete := by
  intro b carried l hperm
  have hP : b.countP (fun a => decide (a = Actor.partner))
          = l.countP (fun a => decide (a = Actor.partner)) := hperm.countP_eq _
  have hQ : b.countP (fun a => decide (a = Actor.participant))
          = l.countP (fun a => decide (a = Actor.participant)) := hperm.countP_eq _
  simp only [bucketEffects, hP, hQ]
  by_cases hq : l.countP (fun a => decide (a = Actor.participant)) = 0
  · by_cases hp : l.countP (fun a => decide (a = Actor.partner)) = 0
    · -- корзина пуста
      have : l = [] := eq_nil_of_no_actors l hp hq
      subst this
      simp [hq, hp, countFrom, stateAfter]
    · -- только партнёры
      have hne : l ≠ [] := by
        intro h; subst h; simp at hp
      obtain ⟨hc, hs⟩ := allPartner_scan l hne (all_partner_of_no_participant l hq) carried
      simp [hq, hp, hc, hs]
  · by_cases hp : l.countP (fun a => decide (a = Actor.partner)) = 0
    · -- только участники
      have hne : l ≠ [] := by
        intro h; subst h; simp at hq
      obtain ⟨hc, hs⟩ := allParticipant_scan l hne (all_participant_of_no_partner l hp) carried
      simp [hq, hp, hc, hs]
    · -- СМЕШАННАЯ корзина: работает block_balance и mem_patterns
      have hne : l ≠ [] := by
        intro h; subst h; simp at hp
      -- `set` — тактика Mathlib, которого здесь нет; пишем термы явно
      have hbal := block_balance l hne
      have hpb1 : 1 ≤ blocksOf Actor.partner none l :=
        blocksOf_pos Actor.partner l (by omega)
      have hpb2 : blocksOf Actor.partner none l
          ≤ l.countP (fun a => decide (a = Actor.partner)) :=
        blocksOf_le_countP Actor.partner none l
      have hqb1 : 1 ≤ blocksOf Actor.participant none l :=
        blocksOf_pos Actor.participant l (by omega)
      have hqb2 : blocksOf Actor.participant none l
          ≤ l.countP (fun a => decide (a = Actor.participant)) :=
        blocksOf_le_countP Actor.participant none l
      have hcount : blocksOf Actor.partner none l = countFrom false l :=
        blocksOf_partner_none l
      have hstate : stateAfter carried l = stateAfter false l :=
        stateAfter_indep carried false l hne
      have hcarr := countFrom_carried l
      have halt : if (decide (l.head? = some Actor.partner)) = true then
            (blocksOf Actor.partner none l = blocksOf Actor.participant none l
              ∨ blocksOf Actor.partner none l = blocksOf Actor.participant none l + 1)
          else
            (blocksOf Actor.participant none l = blocksOf Actor.partner none l
              ∨ blocksOf Actor.participant none l = blocksOf Actor.partner none l + 1) := by
        by_cases hf : l.head? = some Actor.partner <;>
          by_cases hl : stateAfter false l = true <;>
            simp [hf, hl] at hbal ⊢ <;> omega
      have hmem := mem_patterns
        (l.countP (fun a => decide (a = Actor.partner)))
        (l.countP (fun a => decide (a = Actor.participant)))
        (blocksOf Actor.partner none l) (blocksOf Actor.participant none l)
        (decide (l.head? = some Actor.partner)) hpb1 hpb2 hqb1 hqb2 halt
      simp only [hq, hp, if_false, List.mem_map]
      refine ⟨(decide (l.head? = some Actor.partner),
               blocksOf Actor.partner none l,
               blocksOf Actor.participant none l), hmem, ?_⟩
      by_cases hf : l.head? = some Actor.partner <;>
        by_cases hl : stateAfter false l = true <;>
          cases carried <;>
            simp [hf, hl, hstate] at hbal hcarr ⊢ <;> omega

end RelationshipFix
