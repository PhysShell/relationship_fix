/-
  Возможности: определение, от которого зависит N.

  Возможность открывается на ПЕРВОМ сообщении партнёрской серии. Серия из
  трёх подряд сообщений партнёра — одна возможность, а не три. Это то же
  определение, что в замороженном экстракторе, записанное так, чтобы про него
  можно было доказывать теоремы, а не только прогонять примеры.
-/
import RelationshipFix.Stream

namespace RelationshipFix

/-- Число возможностей участника: сколько раз начиналась серия партнёра.
    `prev` — предыдущий актёр, `none` в начале потока. -/
def opps : Option Actor → List Actor → Nat
  | _, [] => 0
  | prev, a :: as =>
      (if a = Actor.partner ∧ prev ≠ some Actor.partner then 1 else 0)
        + opps (some a) as

/-- Корзина ОДНОРОДНА, если все её элементы совпадают. Такая корзина порядка
    не скрывает: переставлять в ней нечего. -/
def Uniform (b : List Actor) : Prop := ∀ x ∈ b, ∀ y ∈ b, x = y

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

/-- ТЕОРЕМА 3 (схлопывание). Если ни одна корзина не скрывает порядка, то
    допустимая история РОВНО ОДНА — развёртка наблюдения.

    Именно это отличает BOUNDED от второго определения метрики: там, где
    неоднозначности нет, он обязан деградировать в обычный экстрактор. -/
theorem bounded_collapses_on_total_order :
    ∀ (o : Observation), (∀ b ∈ o, Uniform b) →
      ∀ l, Admissible o l → l = o.flatten := by
  intro o
  induction o with
  | nil =>
      intro _ l h
      cases h
      rfl
  | cons b bs ih =>
      intro hu l h
      cases h with
      | cons hp hrest =>
          rename_i lb rest
          have hb : lb = b := perm_eq_of_uniform hp (hu b (by simp))
          have hr : rest = bs.flatten :=
            ih (fun x hx => hu x (by simp [hx])) rest hrest
          rw [hb, hr, List.flatten_cons]

end RelationshipFix
