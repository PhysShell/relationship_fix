/-
  PROOFS — мост между `opps` (язык спецификации) и `countFrom` (язык DP).

  Для диады состояние сканирования — один бит: открыта ли серия партнёра.
  `opps` носит `Option Actor`, но зависит от него только через этот бит, и
  первое, что стоит доказать, — что носить полный `Option Actor` было
  излишеством.
-/
import RelationshipFix.TrustedSpec

namespace RelationshipFix

/-- `opps` зависит от предыдущего актёра ТОЛЬКО через бит «это был партнёр». -/
theorem opps_eq_countFrom (prev : Option Actor) :
    ∀ l, opps prev l = countFrom (decide (prev = some Actor.partner)) l := by
  intro l
  induction l generalizing prev with
  | nil => rfl
  | cons a as ih =>
      simp only [opps, countFrom]
      congr 1
      · by_cases ha : a = Actor.partner
        · by_cases hp : prev = some Actor.partner <;> simp [ha, hp]
        · simp [ha]
      · have := ih (some a)
        simpa using this

/-- Частный случай, которым и пользуется DP: старт с «серия не открыта». -/
theorem nTopological_eq_countFrom (l : List Actor) :
    NTopological l = countFrom false l := by
  have := opps_eq_countFrom none l
  simpa using this

/-- Счёт складывается по конкатенации, если второй кусок стартует с
    состояния, оставленного первым. Именно это склеивает корзины. -/
theorem countFrom_append (carried : Bool) (l r : List Actor) :
    countFrom carried (l ++ r)
      = countFrom carried l + countFrom (stateAfter carried l) r := by
  induction l generalizing carried with
  | nil => simp [countFrom, stateAfter]
  | cons a as ih =>
      simp only [List.cons_append, countFrom, stateAfter]
      rw [ih]
      omega

/-- И состояние тоже. -/
theorem stateAfter_append (carried : Bool) (l r : List Actor) :
    stateAfter carried (l ++ r) = stateAfter (stateAfter carried l) r := by
  induction l generalizing carried with
  | nil => simp [stateAfter]
  | cons a as ih => simpa [stateAfter] using ih (decide (a = Actor.partner))

end RelationshipFix
