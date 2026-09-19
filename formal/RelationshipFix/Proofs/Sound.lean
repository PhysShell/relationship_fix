/-
  PROOFS — КОРРЕКТНОСТЬ ГРАНИЦ DP.

  Финишная прямая: из локальной полноты корзины индукцией по допустимости
  получается, что каждая реальная история присутствует среди достижимых пар,
  а оттуда границы следуют обычными фактами про foldl min/max.
-/
import RelationshipFix.Proofs.BucketComplete
import RelationshipFix.Proofs.Reachable

namespace RelationshipFix

/-- Обобщение по входному состоянию — иначе индукция не проходит. -/
theorem history_mem_dpFrom : ∀ (o : Observation) (carried : Bool) (l : List Actor),
    Admissible o l → (countFrom carried l, stateAfter carried l) ∈ dpFrom carried o := by
  intro o
  induction o with
  | nil =>
      intro carried l h
      cases h
      simp [dpFrom, countFrom, stateAfter]
  | cons b bs ih =>
      intro carried l h
      cases h with
      | cons hperm hrest =>
          rename_i l₁ rest
          have hbucket := bucket_effect_complete b carried l₁ hperm
          have hIH := ih (stateAfter carried l₁) rest hrest
          simp only [dpFrom, List.mem_flatMap, List.mem_map]
          refine ⟨(countFrom carried l₁, stateAfter carried l₁), hbucket,
                  (countFrom (stateAfter carried l₁) rest,
                   stateAfter (stateAfter carried l₁) rest), hIH, ?_⟩
          simp [countFrom_append, stateAfter_append]

/-- `Spec.HistoryToReachable`. -/
theorem history_to_reachable : Spec.HistoryToReachable := by
  intro o l h
  rw [dpReachable_eq]
  exact history_mem_dpFrom o false l h

-- --------------------------------------------------------------------------
-- Скучные факты про foldl min/max. Один раз — и больше этой дряни не видеть.
-- --------------------------------------------------------------------------

theorem foldl_min_le_init : ∀ (ns : List Nat) (x : Nat), ns.foldl min x ≤ x := by
  intro ns
  induction ns with
  | nil => intro x; simp
  | cons a as ih =>
      intro x
      have := ih (min x a)
      simp only [List.foldl_cons]
      omega

theorem init_le_foldl_max : ∀ (ns : List Nat) (x : Nat), x ≤ ns.foldl max x := by
  intro ns
  induction ns with
  | nil => intro x; simp
  | cons a as ih =>
      intro x
      have := ih (max x a)
      simp only [List.foldl_cons]
      omega

theorem foldl_min_le_mem : ∀ (ns : List Nat) (x n : Nat), n ∈ ns → ns.foldl min x ≤ n := by
  intro ns
  induction ns with
  | nil => intro _ _ h; simp at h
  | cons a as ih =>
      intro x n h
      simp only [List.foldl_cons]
      rcases List.mem_cons.1 h with rfl | hmem
      · have := foldl_min_le_init as (min x n)
        omega
      · exact ih (min x a) n hmem

theorem mem_le_foldl_max : ∀ (ns : List Nat) (x n : Nat), n ∈ ns → n ≤ ns.foldl max x := by
  intro ns
  induction ns with
  | nil => intro _ _ h; simp at h
  | cons a as ih =>
      intro x n h
      simp only [List.foldl_cons]
      rcases List.mem_cons.1 h with rfl | hmem
      · have := init_le_foldl_max as (max x n)
        omega
      · exact ih (max x a) n hmem

/-- `Spec.DPBoundsSound` — ГРАНИЦЫ, КОТОРЫЕ ВЫДАЁТ DP, ограничивают КАЖДУЮ
    допустимую историю.

    Именно это делает практический вывод законным: если оценка STRICT ниже
    `lo`, она ниже `N` ЛЮБОЙ хронологии, совместимой с наблюдением. -/
theorem dp_bounds_sound : Spec.DPBoundsSound := by
  intro o l h
  have hmem := history_to_reachable o l h
  have hn : countFrom false l ∈ (dpReachable o).map Prod.fst :=
    List.mem_map.2 ⟨_, hmem, rfl⟩
  rw [nTopological_eq_countFrom]
  constructor
  · exact foldl_min_le_mem _ _ _ hn
  · exact mem_le_foldl_max _ _ _ hn

end RelationshipFix
