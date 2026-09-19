/-
  CHALLENGE — ВОПРОС, а не ответ.

  Здесь `sorry` стоит НАМЕРЕННО и означает не дыру в доказательстве, а дыру
  в ЗАДАНИИ: «вот формула, которую решение обязано доказать». Поэтому файл
  исключён из обычного запрета на `sorry` — и ровно поэтому он НИКОГДА не
  импортируется деревом доказательств.

  Импортирует ТОЛЬКО `TrustedSpec`. Это не педантизм: если бы challenge
  зависел от слоя доказательств, достаточно было бы «слегка улучшить»
  определение — и challenge с solution съехали бы вместе, дружно согласившись
  друг с другом. Охрана, в которой вор сам обновляет фотографию
  разыскиваемого, охраняет плохо.
-/
import RelationshipFix.TrustedSpec

namespace RelationshipFix.Challenge

theorem coarsening_preserves_fine_orders : Spec.CoarseningPreservesFineOrders := sorry

theorem n_identified_set_monotone : Spec.NIdentifiedSetMonotone := sorry

theorem bounded_collapses_on_total_order : Spec.BoundedCollapsesOnTotalOrder := sorry

theorem identified_nonempty : Spec.IdentifiedNonempty := sorry

theorem n_identified_set_collapses : Spec.NIdentifiedSetCollapses := sorry

/-- ОТКРЫТЫЙ ВОПРОС. Формулировка заморожена ДО начала доказательства —
    чтобы не вышло «неделя в Lean, получилась удобная форма, назовём её
    soundness». Решения пока нет, и это видно машине, а не только человеку. -/
theorem sound_sharp_bounds_exist : Spec.SoundSharpBoundsExist := sorry

end RelationshipFix.Challenge
