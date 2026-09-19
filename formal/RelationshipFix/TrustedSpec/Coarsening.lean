/-
  TRUSTED SPEC — что такое огрубление.
-/
import RelationshipFix.TrustedSpec.Observation

namespace RelationshipFix

/-- Огрубление СКЛЕИВАЕТ ПОДРЯД ИДУЩИЕ корзины: каждая грубая корзина есть
    развёртка блока мелких.

    Определение абстрактное намеренно. Существенно ровно одно: грубая корзина
    есть объединение подряд идущих мелких. Что реальная сборка корзин
    (`to_bins`) действительно такова — утверждение о РЕАЛИЗАЦИИ, и оно
    проверяется property-тестом на Python, а не здесь. -/
def coarsen (blocks : List Observation) : Observation := blocks.map List.flatten

end RelationshipFix
