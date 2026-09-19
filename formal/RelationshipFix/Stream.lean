/-
  Формальная модель НАБЛЮДЕНИЯ — и только его.

  Здесь нет ни CSV, ни pandas, ни 520 диад, ни кэшей. Ядро отвечает на один
  вопрос: что именно грубый наблюдатель знает о порядке событий, и что из
  этого следует. Всё остальное охраняется обычными тестами.
-/

namespace RelationshipFix

/-- Актёр диады. Их ровно два, и это не упрощение, а условие задачи: движок
    не является общим решателем частичных порядков. -/
inductive Actor where
  | participant : Actor
  | partner : Actor
  deriving DecidableEq, Repr

/-- Что видит грубый наблюдатель: упорядоченный список КОРЗИН, где каждая
    корзина — неупорядоченный набор актёров.

    Порядок МЕЖДУ корзинами известен. Порядок ВНУТРИ корзины — нет. На этом
    различии стоит вся машинерия, и здесь оно становится определением, а не
    комментарием. -/
abbrev Observation := List (List Actor)

/-- Латентная история, совместимая с наблюдением: по корзинам в их порядке,
    внутри каждой — какая-нибудь перестановка её содержимого.

    Это и есть множество допустимых линеаризаций. Заметьте, чего в нём НЕТ:
    никакой вероятностной модели. Источник не сообщал, что `ABBA` столь же
    вероятно, как `AABB`, поэтому и модель этого не утверждает. -/
inductive Admissible : Observation → List Actor → Prop where
  | nil : Admissible [] []
  | cons {b l bs rest} :
      b.Perm l → Admissible bs rest → Admissible (b :: bs) (l ++ rest)

/-- Полная развёртка наблюдения — одна конкретная допустимая история. -/
theorem admissible_flatten (o : Observation) : Admissible o o.flatten := by
  induction o with
  | nil => exact Admissible.nil
  | cons b bs ih =>
      simpa [List.flatten] using Admissible.cons (List.Perm.refl b) ih

/-- Допустимая история — перестановка развёртки. Ничего не теряется и не
    добавляется: огрубление стирает порядок, но не события. -/
theorem admissible_perm (o : Observation) (l : List Actor)
    (h : Admissible o l) : o.flatten.Perm l := by
  induction h with
  | nil => exact List.Perm.refl []
  | cons hb _ ih => exact (hb.append ih)

/-- Наблюдение из двух частей расщепляет любую допустимую историю на две. -/
theorem admissible_split (a b : Observation) (l : List Actor)
    (h : Admissible (a ++ b) l) :
    ∃ l₁ l₂, l = l₁ ++ l₂ ∧ Admissible a l₁ ∧ Admissible b l₂ := by
  induction a generalizing l with
  | nil => exact ⟨[], l, rfl, Admissible.nil, h⟩
  | cons x xs ih =>
      cases h with
      | cons hx hrest =>
          rename_i lx rest
          obtain ⟨l₁, l₂, rfl, h₁, h₂⟩ := ih rest hrest
          exact ⟨lx ++ l₁, l₂, by simp [List.append_assoc],
                 Admissible.cons hx h₁, h₂⟩

/-- Обратное склеивание. -/
theorem admissible_append (a b : Observation) (l₁ l₂ : List Actor)
    (h₁ : Admissible a l₁) (h₂ : Admissible b l₂) :
    Admissible (a ++ b) (l₁ ++ l₂) := by
  induction h₁ with
  | nil => simpa using h₂
  | cons hx _ ih => simpa [List.append_assoc] using Admissible.cons hx ih

end RelationshipFix
