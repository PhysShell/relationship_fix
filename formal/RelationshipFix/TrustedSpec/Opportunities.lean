/-
  TRUSTED SPEC — что такое возможность и однородная корзина.
-/
import RelationshipFix.TrustedSpec.Observation

namespace RelationshipFix

/-- Число возможностей участника: сколько раз начиналась серия партнёра.
    Серия из трёх подряд сообщений партнёра — ОДНА возможность, а не три.

    ВАЖНОЕ ОГРАНИЧЕНИЕ ОБЛАСТИ. Это ТОПОЛОГИЧЕСКОЕ `N`. Оно НЕ равно
    production `N_eligible`: календарное отсечение по горизонту
    (`opened_at + H ≤ period_end`) здесь не формализовано вовсе. Любая
    теорема отсюда говорит про топологию, и распространять её на
    production-величину нельзя, пока граница eligibility не формализована. -/
def opps : Option Actor → List Actor → Nat
  | _, [] => 0
  | prev, a :: as =>
      (if a = Actor.partner ∧ prev ≠ some Actor.partner then 1 else 0)
        + opps (some a) as

/-- То же под именем, которое нельзя перепутать с production-величиной. -/
abbrev NTopological (l : List Actor) : Nat := opps none l

/-- Корзина ОДНОРОДНА, если все её элементы совпадают. Такая корзина порядка
    не скрывает: переставлять в ней нечего. -/
def Uniform (b : List Actor) : Prop := ∀ x ∈ b, ∀ y ∈ b, x = y

end RelationshipFix
