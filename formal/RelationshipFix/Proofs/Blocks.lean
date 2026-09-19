/-
  PROOFS — блочная структура двухакторного списка.

  Здесь лежит вся настоящая трудность локальной точности корзины:
  `bucketEffects` перечисляет эффекты через ЧИСЛО БЛОКОВ, а допустимые
  истории — через перестановки. Чтобы связать одно с другим, нужны факты о
  том, как блоки устроены: их число, чередование и последний актёр.

  Вынесено отдельным файлом намеренно: если расхождение есть, оно найдётся
  здесь, а не на четырёхсотой строке доказательства про весь DP.
-/
import RelationshipFix.Proofs.Scan

namespace RelationshipFix

/-- Число максимальных блоков актёра `x`. Для `x = partner` это ровно
    `opps`, то есть число возможностей. -/
def blocksOf (x : Actor) : Option Actor → List Actor → Nat
  | _, [] => 0
  | prev, a :: as => (if a = x ∧ prev ≠ some x then 1 else 0) + blocksOf x (some a) as

/-- Партнёрские блоки — это и есть возможности. -/
theorem blocksOf_partner (prev : Option Actor) :
    ∀ l, blocksOf Actor.partner prev l = opps prev l := by
  intro l
  induction l generalizing prev with
  | nil => rfl
  | cons a as ih => simp [blocksOf, opps, ih]

/-- Как влияет предыдущий актёр: ровно на один блок и только если список
    начинается с того же актёра. Записано БЕЗ вычитания — на `Nat` оно
    приносит больше горя, чем пользы. -/
theorem blocksOf_prev (x a : Actor) :
    ∀ as, blocksOf x none as
        = blocksOf x (some a) as + (if as.head? = some x ∧ a = x then 1 else 0) := by
  intro as
  cases as with
  | nil => simp [blocksOf]
  | cons c cs =>
      by_cases hc : c = x
      · by_cases ha : a = x
        · simp [blocksOf, hc, ha]; omega
        · simp [blocksOf, hc, ha]
      · simp [blocksOf, hc]

/-- Первый актёр списка. -/
abbrev firstOf (l : List Actor) : Option Actor := l.head?

/-- Состояние после непустого списка определяется последним актёром. -/
theorem stateAfter_eq_last (c : Bool) :
    ∀ (l : List Actor) (h : l ≠ []), stateAfter c l = decide (l.getLast h = Actor.partner) := by
  intro l
  induction l generalizing c with
  | nil => intro h; exact absurd rfl h
  | cons a as ih =>
      intro _
      cases as with
      | nil => simp [stateAfter]; rfl
      | cons b bs =>
          have : (a :: b :: bs).getLast (by simp) = (b :: bs).getLast (by simp) := by
            simp [List.getLast_cons]
          simp only [stateAfter, this]
          exact ih (decide (a = Actor.partner)) (by simp)

end RelationshipFix
