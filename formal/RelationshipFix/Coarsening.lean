/-
  Огрубление часов: что оно делает с МНОЖЕСТВОМ допустимых историй.

  Главная теорема проекта в одну строку: огрубление только СТИРАЕТ
  ограничения порядка. Всё остальное — следствия.
-/
import RelationshipFix.Stream

namespace RelationshipFix

/-- Огрубление СКЛЕИВАЕТ ПОДРЯД ИДУЩИЕ корзины. `blocks` — группировка:
    каждая грубая корзина есть развёртка блока мелких.

    Определение абстрактное намеренно. Оно не зависит ни от того, что часы
    измеряются в секундах, ни от того, что Δ делится нацело: существенно
    ровно одно — грубая корзина есть объединение подряд идущих мелких.
    Арифметическая часть («минутные ключи суть функция от секундных»)
    доказана ниже отдельно. -/
def coarsen (blocks : List Observation) : Observation := blocks.map List.flatten

/-- ТЕОРЕМА 1. Огрубление сохраняет все допустимые мелкие порядки.

        Orders(s, Δ₁) ⊆ Orders(C(s), Δ₂)

    Это тот самый инвариант, про который в документации сказано «если упал,
    значит баг, никаких философских объяснений». Теперь он не в документации. -/
theorem coarsening_preserves_fine_orders :
    ∀ (blocks : List Observation) (l : List Actor),
      Admissible blocks.flatten l → Admissible (coarsen blocks) l := by
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

/-- Арифметический мост: если Δ₁ делит Δ₂, то ГРУБЫЙ КЛЮЧ ЕСТЬ ФУНКЦИЯ ОТ
    МЕЛКОГО. Отсюда и следует, что грубая корзина — объединение подряд идущих
    мелких: события с одним мелким ключом обязаны иметь один грубый.

    Это ровно та часть, ради которой стоило считать честно: «минутная корзина
    есть объединение секундных» звучит очевидно, но опирается на то, что
    целочисленное деление ассоциативно именно так. -/
theorem coarse_key_factors (fine coarse t : Nat) (hpos : 0 < fine)
    (hdvd : fine ∣ coarse) :
    t / coarse = (t / fine) / (coarse / fine) := by
  obtain ⟨k, rfl⟩ := hdvd
  rw [Nat.mul_div_cancel_left k hpos, Nat.div_div_eq_div_mul]

/-- И следствие, которым пользуется сборка корзин: у событий с одинаковым
    мелким ключом одинаковый грубый. -/
theorem same_fine_key_same_coarse_key (fine coarse a b : Nat) (hpos : 0 < fine)
    (hdvd : fine ∣ coarse) (h : a / fine = b / fine) :
    a / coarse = b / coarse := by
  rw [coarse_key_factors fine coarse a hpos hdvd,
      coarse_key_factors fine coarse b hpos hdvd, h]

end RelationshipFix
