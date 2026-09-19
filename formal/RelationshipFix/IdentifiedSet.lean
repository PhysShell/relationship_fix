/-
  Идентифицированное множество для N — и его монотонность по огрублению.

  Это тот самый объект, который в документации называется sharp identified
  set: все значения, совместимые ХОТЬ С ОДНОЙ допустимой историей. Не
  доверительный интервал, не оценка, не результат монетки.
-/
import RelationshipFix.Coarsening
import RelationshipFix.Opportunities

namespace RelationshipFix

/-- `IdentifiedN o n` — «значение n совместимо с наблюдением o». -/
def IdentifiedN (o : Observation) (n : Nat) : Prop :=
  ∃ l, Admissible o l ∧ opps none l = n

/-- Множество никогда не пусто: развёртка наблюдения — всегда допустимая
    история. Отсутствие ответа не становится ответом. -/
theorem identified_nonempty (o : Observation) :
    IdentifiedN o (opps none o.flatten) :=
  ⟨o.flatten, admissible_flatten o, rfl⟩

/-- ТЕОРЕМА 2. Идентифицированное множество N ТОЛЬКО РАСШИРЯЕТСЯ при
    огрублении:

        I_N(Δ₁) ⊆ I_N(Δ₂)

    N зависит ИСКЛЮЧИТЕЛЬНО от допустимой топологии порядка. Никакого
    временного бюджета, никакого `min(Δ, c·H)`, никаких секунд: они в это
    утверждение не входят и не могут его сломать. Поэтому нарушение здесь
    есть баг в огрублении, сборке корзин или DP — и ничто иное. -/
theorem n_identified_set_monotone :
    ∀ (blocks : List Observation) (n : Nat),
      IdentifiedN blocks.flatten n → IdentifiedN (coarsen blocks) n := by
  rintro blocks n ⟨l, hl, hn⟩
  exact ⟨l, coarsening_preserves_fine_orders blocks l hl, hn⟩

/-- Включение множеств значений. Своё, а не из Mathlib: ядро собирается из
    одного тулчейна, и тащить несколько гигабайт ради значка `⊆` незачем. -/
def SubsetOf (P Q : Nat → Prop) : Prop := ∀ n, P n → Q n

@[inherit_doc] infix:50 " ⊑ " => SubsetOf

/-- Та же теорема в виде включения множеств, как она записана в документации:

        I_N(1s) ⊑ I_N(60s) -/
theorem n_identified_subset (blocks : List Observation) :
    IdentifiedN blocks.flatten ⊑ IdentifiedN (coarsen blocks) :=
  fun n hn => n_identified_set_monotone blocks n hn

/-- Схлопывание на уровне множества: где порядка не скрыто, множество —
    одноточечное, и точка совпадает с обычным экстрактором. -/
theorem n_identified_set_collapses (o : Observation) (h : ∀ b ∈ o, Uniform b) :
    ∀ n, IdentifiedN o n ↔ n = opps none o.flatten := by
  intro n
  constructor
  · rintro ⟨l, hl, rfl⟩
    rw [bounded_collapses_on_total_order o h l hl]
  · rintro rfl
    exact identified_nonempty o

end RelationshipFix
