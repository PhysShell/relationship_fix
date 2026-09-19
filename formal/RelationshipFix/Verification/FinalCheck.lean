/-
  FINAL CHECK — доверенная база ПРИБИТА К ИСХОДНИКУ.

  Разница с обычным аудитом существенна и стоит десяти строк:

      grep по исходникам      ловит НАПИСАННЫЙ `sorry`
      #print axioms + shell   ловит ТРАНЗИТИВНЫЙ `sorryAx`
      #guard_msgs             ловит ЛЮБОЕ изменение доверенной базы

  Если завтра теорема начнёт зависеть от `Classical.choice`, от
  `Quot.sound` или от чьей-нибудь свежей `axiom miracle`, спрятанной за
  пятью леммами, — первые два слоя скажут «всё прекрасно, sorryAx нет», а
  этот файл покраснеет.

  Строки не сочинены вручную, а один раз сняты с Lean 4.34.0 и
  зафиксированы. Тулчейн запинен, поэтому хрупкость текстового сообщения
  здесь работает на пользу: апгрейд Lean заставит перепроверить сертификат
  явно, а не молча.
-/
import RelationshipFix.Verification.Challenge
import RelationshipFix.Verification.Solution
import RelationshipFix.Verification.StatementIntegrity

/-- info: 'RelationshipFix.Solution.coarsening_preserves_fine_orders' depends on axioms: [propext] -/
#guard_msgs in
#print axioms RelationshipFix.Solution.coarsening_preserves_fine_orders

/-- info: 'RelationshipFix.Solution.n_identified_set_monotone' depends on axioms: [propext] -/
#guard_msgs in
#print axioms RelationshipFix.Solution.n_identified_set_monotone

/-- info: 'RelationshipFix.Solution.bounded_collapses_on_total_order' depends on axioms: [propext] -/
#guard_msgs in
#print axioms RelationshipFix.Solution.bounded_collapses_on_total_order

/-- info: 'RelationshipFix.Solution.identified_nonempty' does not depend on any axioms -/
#guard_msgs in
#print axioms RelationshipFix.Solution.identified_nonempty

/-- info: 'RelationshipFix.Solution.n_identified_set_collapses' depends on axioms: [propext] -/
#guard_msgs in
#print axioms RelationshipFix.Solution.n_identified_set_collapses

/-
  А это — проверка в ДРУГУЮ сторону, и она не менее важна. Открытый вопрос
  обязан оставаться дырой. В тот день, когда любая из строк ниже перестанет
  зависеть от `sorryAx`, она покраснеет — и это будет ровно то место, где
  теорему надо переносить из Challenge в Solution, а не тихо радоваться
  зелёной сборке.
-/
/-- info: 'RelationshipFix.Challenge.dp_bounds_sound' depends on axioms: [sorryAx] -/
#guard_msgs in
#print axioms RelationshipFix.Challenge.dp_bounds_sound

/-- info: 'RelationshipFix.Challenge.dp_bounds_sharp' depends on axioms: [sorryAx] -/
#guard_msgs in
#print axioms RelationshipFix.Challenge.dp_bounds_sharp

/-- info: 'RelationshipFix.Challenge.sharp_bounds_exist_abstract' depends on axioms: [sorryAx] -/
#guard_msgs in
#print axioms RelationshipFix.Challenge.sharp_bounds_exist_abstract
