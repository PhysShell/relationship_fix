/-
  Аудит доверенной базы. Не документация, а исполняемая проверка.

  `#print axioms` печатает ВСЁ, на что опирается доказательство. Если там
  появится `sorryAx`, значит теорема не доказана, а объявлена — и скрипт
  `scripts/audit.sh` на этом падает.

  Три стандартные аксиомы (`propext`, `Classical.choice`, `Quot.sound`)
  допустимы: это обычная классическая логика, а не дыра в рассуждении.
-/
import RelationshipFix

open RelationshipFix

#print axioms coarsening_preserves_fine_orders
#print axioms n_identified_set_monotone
#print axioms n_identified_subset
#print axioms bounded_collapses_on_total_order
#print axioms n_identified_set_collapses
#print axioms identified_nonempty
#print axioms admissible_flatten
#print axioms admissible_perm
#print axioms admissible_split
#print axioms admissible_append
#print axioms perm_eq_of_uniform
#print axioms coarse_key_factors
#print axioms same_fine_key_same_coarse_key
