/-
  PROOFS — свёртка DP в структурную рекурсию.

  `dpReachable` определён через `foldl`, потому что так же устроен цикл в
  Python. Для индукции это неудобно: аккумулятор несёт накопленное `N`.
  Поэтому доказывается равенство с обычной рекурсией по корзинам — и
  дальше работаем с ней.

  Это ЛЕММА, а не правка спецификации. Вопрос остался тем же.
-/
import RelationshipFix.Proofs.Scan

namespace RelationshipFix

/-- Те же достижимые пары, но рекурсией слева направо. -/
def dpFrom (carried : Bool) : Observation → List (Nat × Bool)
  | [] => [(0, carried)]
  | b :: bs => (bucketEffects b carried).flatMap fun e =>
      (dpFrom e.2 bs).map fun r => (e.1 + r.1, r.2)

/-- Свёртка с произвольным аккумулятором раскрывается через `dpFrom`. -/
theorem foldl_dpStep (o : Observation) :
    ∀ acc : List (Nat × Bool),
      o.foldl dpStep acc
        = acc.flatMap fun s => (dpFrom s.2 o).map fun r => (s.1 + r.1, r.2) := by
  induction o with
  | nil =>
      intro acc
      simp [dpFrom]
  | cons b bs ih =>
      intro acc
      simp only [List.foldl_cons, ih, dpStep, dpFrom]
      simp [List.flatMap_assoc, List.map_flatMap, List.flatMap_map,
            List.map_map, Function.comp_def, Nat.add_assoc]

/-- То, ради чего лемма: спецификационный `dpReachable` и есть `dpFrom`. -/
theorem dpReachable_eq (o : Observation) : dpReachable o = dpFrom false o := by
  simp [dpReachable, foldl_dpStep o [(0, false)]]

end RelationshipFix
