/-
  TRUSTED SPEC — идентифицированное множество и включение.
-/
import RelationshipFix.TrustedSpec.Opportunities

namespace RelationshipFix

/-- `IdentifiedN o n` — «значение n совместимо с наблюдением o».

    Это sharp identified set: все значения, достижимые ХОТЬ НА ОДНОЙ
    допустимой истории. Не доверительный интервал, не оценка, не монетка. -/
def IdentifiedN (o : Observation) (n : Nat) : Prop :=
  ∃ l, Admissible o l ∧ NTopological l = n

/-- Включение множеств значений. Своё, а не из Mathlib: ядро собирается из
    одного тулчейна, и тащить гигабайты ради значка `⊆` незачем. -/
def SubsetOf (P Q : Nat → Prop) : Prop := ∀ n, P n → Q n

@[inherit_doc] infix:50 " ⊑ " => SubsetOf

end RelationshipFix
