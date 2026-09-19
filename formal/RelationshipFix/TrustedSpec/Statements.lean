/-
  TRUSTED SPEC — ФОРМУЛИРОВКИ. Что именно требуется доказать.

  Этот файл — вопрос, а не ответ. Он отделён от доказательств намеренно:
  главная угроза на нынешней стадии не `sorry` (его ноль), а тихая правка
  определения после того, как доказательство не пошло. Хэш этого файла
  попадает в сертификат; изменить вопрос молча не получится.

  ЗДЕСЬ ЛЕЖАТ И ЕЩЁ НЕ ДОКАЗАННЫЕ ФОРМУЛИРОВКИ. Это не недосмотр, а весь
  смысл: statement замораживается ДО того, как prover нашёл удобную форму.
-/
import RelationshipFix.TrustedSpec.Coarsening
import RelationshipFix.TrustedSpec.IdentifiedSet

namespace RelationshipFix.Spec

open RelationshipFix

/-- Огрубление только СТИРАЕТ ограничения порядка. -/
def CoarseningPreservesFineOrders : Prop :=
  ∀ (blocks : List Observation) (l : List Actor),
    Admissible blocks.flatten l → Admissible (coarsen blocks) l

/-- Идентифицированное множество `N` только расширяется: `I_N(fine) ⊑ I_N(coarse)`. -/
def NIdentifiedSetMonotone : Prop :=
  ∀ (blocks : List Observation),
    IdentifiedN blocks.flatten ⊑ IdentifiedN (coarsen blocks)

/-- Где корзины не скрывают порядка, допустимая история ровно одна. -/
def BoundedCollapsesOnTotalOrder : Prop :=
  ∀ (o : Observation), (∀ b ∈ o, Uniform b) →
    ∀ l, Admissible o l → l = o.flatten

/-- Множество никогда не пусто: отсутствие ответа не становится ответом. -/
def IdentifiedNonempty : Prop :=
  ∀ (o : Observation), IdentifiedN o (NTopological o.flatten)

/-- Там, где порядка не скрыто, множество одноточечно. -/
def NIdentifiedSetCollapses : Prop :=
  ∀ (o : Observation), (∀ b ∈ o, Uniform b) →
    ∀ n, IdentifiedN o n ↔ n = NTopological o.flatten

-- --------------------------------------------------------------------------
-- ЕЩЁ НЕ ДОКАЗАНО. Формулировки заморожены ЗАРАНЕЕ.
-- --------------------------------------------------------------------------

/-- Пара границ КОРРЕКТНА (sound), если она ограничивает КАЖДУЮ допустимую
    историю. Не «почти каждую» и не «ту, которую нашёл DP». -/
def DPSound (lo hi : Observation → Nat) : Prop :=
  ∀ o l, Admissible o l → lo o ≤ NTopological l ∧ NTopological l ≤ hi o

/-- Пара границ РЕЗКАЯ (sharp), если ОБА конца достигаются — каждый на
    какой-то одной целостной допустимой истории.

    Именно «на одной целостной»: минимум одной возможности и минимум другой
    могут требовать взаимоисключающих порядков одной корзины, поэтому
    поопортунитная сумма экстремумов резкой границей не является. -/
def DPSharp (lo hi : Observation → Nat) : Prop :=
  ∀ o, (∃ l, Admissible o l ∧ NTopological l = lo o) ∧
       (∃ l, Admissible o l ∧ NTopological l = hi o)

/-- СЛЕДУЮЩАЯ ЦЕЛЬ: существует корректная и резкая пара границ.

    Формулировка положена сюда ДО начала доказательства — чтобы не вышло
    «неделя в Lean, получилась удобная форма, назовём её soundness».

    ОБЛАСТЬ УЖЕ СУЖЕНА, и это существенно: утверждение про `NTopological`,
    а НЕ про production `N_eligible`. Календарное отсечение по горизонту не
    формализовано, поэтому писать про него теорему сейчас значило бы
    заморозить неверный вопрос. Машины последовательны до оскорбительного:
    comparator с тем же усердием охраняет и неправильную формулировку. -/
def SoundSharpBoundsExist : Prop := ∃ lo hi, DPSound lo hi ∧ DPSharp lo hi

end RelationshipFix.Spec
