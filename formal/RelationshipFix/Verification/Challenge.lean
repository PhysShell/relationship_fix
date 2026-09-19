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

/-- ОТКРЫТЫЙ ВОПРОС №1. Корректность ИМЕННО ТЕХ границ, которые выдаёт
    `dpBounds`. Формулировка заморожена ДО начала доказательства. -/
theorem dp_bounds_sound : Spec.DPBoundsSound := sorry

/-- ОТКРЫТЫЙ ВОПРОС №2. Резкость. Отдельной теоремой: провал резкости не
    обесценивает корректность. -/
theorem dp_bounds_sharp : Spec.DPBoundsSharp := sorry

/-- Слабая абстрактная лемма. НЕ является целью сертификации: в ней не
    фигурирует ни алгоритм, ни его границы. Оставлена, чтобы разница между
    ней и двумя предыдущими была видна в одном файле. -/
theorem sharp_bounds_exist_abstract : Spec.SharpBoundsExistAbstract := sorry

end RelationshipFix.Challenge
