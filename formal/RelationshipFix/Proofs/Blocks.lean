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


/-- Состояние после НЕПУСТОГО списка от входного бита не зависит. -/
theorem stateAfter_indep (c c' : Bool) (l : List Actor) (h : l ≠ []) :
    stateAfter c l = stateAfter c' l := by
  rw [stateAfter_eq_last c l h, stateAfter_eq_last c' l h]

/-- Актёров ровно два. Тривиально, но Lean требует сказать это вслух. -/
theorem actor_cases (a : Actor) : a = Actor.partner ∨ a = Actor.participant := by
  cases a
  · exact Or.inr rfl
  · exact Or.inl rfl

/-- ЧЕТЫРЁХКЛЕТОЧНАЯ КЛАССИФИКАЦИЯ ЧЕРЕДОВАНИЯ — ОДНИМ УРАВНЕНИЕМ.

    Вместо четырёх веток

        P,P -> pb = qb + 1      P,Q -> pb = qb
        Q,P -> pb = qb          Q,Q -> qb = pb + 1

    доказывается одно равенство, которое покрывает все четыре:

        pb + 1 = qb + [первый партнёр] + [последний партнёр]

    Проверьте по клеткам — сходится везде. Выигрыш не косметический: иначе
    ветку «оканчивается участником» пришлось бы вытаскивать через отрицание,
    арифметику `Nat` и факт «актёров всего два», и три строки школьной
    математики превратились бы в небольшой административный округ. -/
theorem block_balance : ∀ (l : List Actor), l ≠ [] →
    blocksOf Actor.partner none l + 1
      = blocksOf Actor.participant none l
        + (if l.head? = some Actor.partner then 1 else 0)
        + (if stateAfter false l then 1 else 0) := by
  intro l
  induction l with
  | nil => intro h; exact absurd rfl h
  | cons a as ih =>
      intro _
      cases as with
      | nil => cases a <;> simp [blocksOf, stateAfter]
      | cons b bs =>
          have hne : (b :: bs) ≠ [] := by simp
          have hIH := ih hne
          -- начальный бит съедается ПЕРВЫМ же элементом, поэтому обе стороны
          -- сворачиваются в одно и то же; `stateAfter_indep` тут не нужен
          have hlast : stateAfter false (a :: b :: bs) = stateAfter false (b :: bs) := by
            simp only [stateAfter]
          rw [hlast]
          have hp := blocksOf_prev Actor.partner a (b :: bs)
          have hq := blocksOf_prev Actor.participant a (b :: bs)
          have hhead : (b :: bs).head? = some b := rfl
          rw [hhead] at hp hq
          rcases actor_cases a with ha | ha <;> rcases actor_cases b with hb | hb <;>
            subst ha <;> subst hb <;>
              simp only [blocksOf, List.head?, reduceCtorEq, and_true,
                         and_false, ite_true, ite_false, ne_eq, not_false_eq_true,
                         Option.some.injEq] at hp hq hIH ⊢ <;>
            omega


/-- Входной бит снимает ровно один блок, и только если список начинается с
    партнёра. Записано без вычитания. -/
theorem countFrom_carried : ∀ (l : List Actor),
    countFrom false l
      = countFrom true l + (if l.head? = some Actor.partner then 1 else 0) := by
  intro l
  cases l with
  | nil => simp [countFrom]
  | cons a as => cases a <;> simp [countFrom, List.head?] <;> omega

/-- Блоков актёра не больше, чем его сообщений: в каждом блоке хотя бы одно. -/
theorem blocksOf_le_countP (x : Actor) : ∀ (prev : Option Actor) (l : List Actor),
    blocksOf x prev l ≤ l.countP (fun a => decide (a = x)) := by
  intro prev l
  induction l generalizing prev with
  | nil => simp [blocksOf]
  | cons a as ih =>
      have hrest := ih (some a)
      have hcons : (a :: as).countP (fun c => decide (c = x))
          = (if a = x then 1 else 0) + as.countP (fun c => decide (c = x)) := by
        by_cases ha : a = x <;> simp [List.countP_cons, ha] <;> omega
      by_cases ha : a = x
      · subst ha
        have hrest' := ih (some a)
        by_cases hprev : prev = some a <;>
          simp [blocksOf, hprev, hcons] at hrest' ⊢ <;> omega
      · simp [blocksOf, ha, hcons] at hrest ⊢ <;> omega

/-- И обратно: если сообщения актёра есть, есть и хотя бы один его блок. -/
theorem blocksOf_pos (x : Actor) : ∀ (l : List Actor),
    0 < l.countP (fun a => decide (a = x)) → 0 < blocksOf x none l := by
  intro l
  induction l with
  | nil => simp
  | cons a as ih =>
      intro hpos
      by_cases ha : a = x
      · simp [blocksOf, ha]; omega
      · -- голова не наша, значит блок начнётся дальше; считаем от `some a`
        have step : blocksOf x none (a :: as) = blocksOf x (some a) as := by
          simp [blocksOf, ha]
        have hprev : blocksOf x none as = blocksOf x (some a) as := by
          have := blocksOf_prev x a as
          simp [ha] at this
          omega
        rw [step, ← hprev]
        -- теперь индукция по хвосту
        have hcount : 0 < as.countP (fun c => decide (c = x)) := by
          have heq : (a :: as).countP (fun c => decide (c = x))
              = as.countP (fun c => decide (c = x)) := by
            simp [List.countP_cons, ha]
          omega
        exact ih hcount

end RelationshipFix
