/-
  TRUSTED SPEC — РЕФЕРЕНСНАЯ СЕМАНТИКА DP, границы которого мы хотим
  сертифицировать.

  ЗАЧЕМ ЭТОТ ФАЙЛ ПОЯВИЛСЯ. Прежняя замороженная цель звучала так:

      SoundSharpBoundsExist := ∃ lo hi, DPSound lo hi ∧ DPSharp lo hi

  и это НЕ soundness нашего DP. Утверждение говорит лишь, что КАКИЕ-ТО
  корректные и резкие функции существуют — в нём не фигурирует ни алгоритм,
  ни его переходы, ни вычисляемые им границы. Доказать его можно абстрактно
  (например, взять сам минимум и максимум по допустимым историям), получить
  зелёного судью и оставить production-DP полностью за кадром. Ровно тот
  класс катастрофы, ради которого строилась стеклянная витрина: сигнализация
  оказалась поставлена не на ту дверь.

  Поэтому теорема обязана НАЗЫВАТЬ границы. Ниже — семантика, которую и
  сертифицируем.

  Она РЕФЕРЕНСНАЯ, а не быстрая: хранятся ВСЕ достижимые пары (N, состояние),
  без отсечения по состоянию. Python отсекает, оставляя лучшее на состояние;
  что это отсечение не теряет экстремумов — отдельное утверждение, и оно
  относится к мосту, а не к этому файлу.
-/
import RelationshipFix.TrustedSpec.Opportunities

namespace RelationshipFix

/-- Границы для `N`. -/
structure Bounds where
  lo : Nat
  hi : Nat
  deriving Repr, DecidableEq

/-- Сжатые шаблоны чередования внутри корзины: (первым партнёр?, блоков
    партнёра, блоков участника). Перестановки одного актёра топологию не
    двигают, поэтому существенны только блоки, и их `O(min p q)`. -/
def patterns (p q : Nat) : List (Bool × Nat × Nat) :=
  (List.range' 1 p).flatMap fun pb =>
    (List.range' 1 q).flatMap fun qb =>
      if pb = qb + 1 then [(true, pb, qb)]
      else if qb = pb + 1 then [(false, pb, qb)]
      else if pb = qb then [(true, pb, qb), (false, pb, qb)]
      else []

/-- Эффект одной корзины: сколько возможностей она открывает и остаётся ли
    серия партнёра открытой на выходе.

    Выбор есть только в СМЕШАННОЙ корзине. Корзина с одним актёром ничего не
    решает: порядок в ней неизвестен, но и неважен. -/
def bucketEffects (b : List Actor) (carried : Bool) : List (Nat × Bool) :=
  let p := b.countP (fun a => decide (a = Actor.partner))
  let q := b.countP (fun a => decide (a = Actor.participant))
  if q = 0 then
    if p = 0 then [(0, carried)]
    else [(if carried then 0 else 1, true)]
  else if p = 0 then [(0, false)]
  else (patterns p q).map fun t =>
    ((if t.1 && carried then t.2.1 - 1 else t.2.1),
     (if t.1 then t.2.1 = t.2.2 + 1 else t.2.1 = t.2.2))

/-- Шаг DP по одной корзине. -/
def dpStep (acc : List (Nat × Bool)) (b : List Actor) : List (Nat × Bool) :=
  acc.flatMap fun s => (bucketEffects b s.2).map fun e => (s.1 + e.1, e.2)

/-- Все достижимые пары (накопленное `N`, открыта ли серия). -/
def dpReachable (o : Observation) : List (Nat × Bool) :=
  o.foldl dpStep [(0, false)]

/-- Границы, которые выдаёт DP. ИМЕННО ОНИ подлежат сертификации.

    ВНИМАНИЕ К СЛОВУ. Это SHARP IDENTIFIED BOUNDS, а не «идентифицированное
    множество равно `[lo, hi]`». Достижимость ОБОИХ КОНЦОВ не влечёт
    достижимости каждого целого между ними: это отдельное утверждение
    (`Spec.IdentifiedSetIsContiguous`), и оно НЕ доказано. Для нынешнего
    вывода «STRICT N ниже любой совместимой величины» достаточно резкой
    нижней границы, поэтому чулан не открывается. -/
def dpBounds (o : Observation) : Bounds :=
  let ns := (dpReachable o).map Prod.fst
  { lo := ns.foldl min (ns.headD 0), hi := ns.foldl max 0 }

-- --------------------------------------------------------------------------
-- Сканирование истории с булевым состоянием — язык промежуточных лемм.
-- --------------------------------------------------------------------------

/-- Состояние после просмотра списка: открыта ли серия партнёра.
    Для диады важно только это, а не сам предыдущий актёр. -/
def stateAfter (carried : Bool) : List Actor → Bool
  | [] => carried
  | a :: as => stateAfter (decide (a = Actor.partner)) as

/-- Сколько возможностей открывает список, если серия уже несёт состояние
    `carried`. Та же величина, что `opps`, но с булевым состоянием. -/
def countFrom (carried : Bool) : List Actor → Nat
  | [] => 0
  | a :: as =>
      (if a = Actor.partner ∧ carried = false then 1 else 0)
        + countFrom (decide (a = Actor.partner)) as

end RelationshipFix
