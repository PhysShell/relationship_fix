/- Печать доверенной базы для сертификата. Проверка живёт в FinalCheck. -/
import RelationshipFix.Verification.Challenge
import RelationshipFix.Verification.Solution

#print axioms RelationshipFix.Solution.coarsening_preserves_fine_orders
#print axioms RelationshipFix.Solution.n_identified_set_monotone
#print axioms RelationshipFix.Solution.bounded_collapses_on_total_order
#print axioms RelationshipFix.Solution.identified_nonempty
#print axioms RelationshipFix.Solution.n_identified_set_collapses
#print axioms RelationshipFix.Challenge.dp_bounds_sound
#print axioms RelationshipFix.Challenge.dp_bounds_sharp
#print axioms RelationshipFix.Challenge.sharp_bounds_exist_abstract
#print axioms RelationshipFix.Challenge.bucket_effect_exact
#print axioms RelationshipFix.Challenge.bucket_effect_complete
#print axioms RelationshipFix.Challenge.bucket_effect_realizable
#print axioms RelationshipFix.Challenge.history_to_reachable
#print axioms RelationshipFix.Challenge.reachable_to_history
#print axioms RelationshipFix.Challenge.identified_set_is_contiguous
