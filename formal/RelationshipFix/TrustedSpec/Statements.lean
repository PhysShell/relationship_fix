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
import RelationshipFix.TrustedSpec.ReferenceDP

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

/-- СЛАБАЯ, АБСТРАКТНАЯ ЛЕММА. Переименована после разбора, и имя теперь
    говорит правду.

    Прежде она называлась `SoundSharpBoundsExist` и числилась следующей
    целью «DP soundness». Это было НЕВЕРНО: здесь не фигурирует ни алгоритм,
    ни его переходы, ни вычисляемые им границы. Утверждение выполняется
    тривиально — возьмите сам минимум и максимум по допустимым историям, — и
    доказав его, можно получить зелёного судью, оставив production-DP
    полностью за кадром.

    То есть сигнализация была поставлена не на ту дверь. Оставлено как
    абстрактная лемма о существовании, и НЕ как цель сертификации. -/
def SharpBoundsExistAbstract : Prop := ∃ lo hi, DPSound lo hi ∧ DPSharp lo hi

/-- НАСТОЯЩАЯ ЦЕЛЬ №1: границы, которые выдаёт `dpBounds`, ограничивают
    КАЖДУЮ допустимую историю.

    Теорема НАЗЫВАЕТ алгоритм. Подменить его абстрактным существованием
    больше нельзя.

    ОБЛАСТЬ СУЖЕНА НАМЕРЕННО: утверждение про `NTopological`, а НЕ про
    production `N_eligible`. Календарное отсечение по горизонту здесь не
    формализовано, и заморозить про него теорему значило бы заморозить
    неверный вопрос. Судья с тем же усердием охраняет и неправильную
    формулировку. -/
def DPBoundsSound : Prop :=
  ∀ o l, Admissible o l →
    (dpBounds o).lo ≤ NTopological l ∧ NTopological l ≤ (dpBounds o).hi

/-- НАСТОЯЩАЯ ЦЕЛЬ №2: обе границы ДОСТИГАЮТСЯ — каждая на какой-то одной
    целостной допустимой истории.

    Отделено от soundness намеренно: если резкость сломается, корректность
    останется ценной сама по себе. Общая теорема, если понадобится, будет
    удобством, а не заменой этим двум. -/
def DPBoundsSharp : Prop :=
  ∀ o, (∃ l, Admissible o l ∧ NTopological l = (dpBounds o).lo) ∧
       (∃ l, Admissible o l ∧ NTopological l = (dpBounds o).hi)

/-- НЕ ЦЕЛЬ, но должно быть названо, чтобы не подразумеваться молча.

    `DPBoundsSharp` говорит, что достижимы ОБА КОНЦА. Из этого НЕ следует,
    что достижимо каждое целое между ними. Поэтому в документации пишется
    «sharp identified BOUNDS `[lo, hi]`», а не «identified set = `[lo, hi]`»:
    второе сильнее и не доказано.

    Для нынешнего вывода — «STRICT N ниже ЛЮБОЙ совместимой величины» —
    достаточно резкой нижней границы, поэтому этот чулан не открывается. -/
def IdentifiedSetIsContiguous : Prop :=
  ∀ o n, (dpBounds o).lo ≤ n → n ≤ (dpBounds o).hi → IdentifiedN o n

-- --------------------------------------------------------------------------
-- ПРОМЕЖУТОЧНЫЕ ЦЕЛИ. План доказательства заморожен вместе с целью, чтобы
-- «мы пошли другим путём» было видно, а не подразумевалось.
-- --------------------------------------------------------------------------

/-- ЛОКАЛЬНАЯ ТОЧНОСТЬ ОДНОЙ КОРЗИНЫ — самое трудное место, и оно нарочно
    вынесено в отдельную лемму.

    `bucketEffects` перечисляет эффекты через ЧИСЛО БЛОКОВ, а допустимые
    истории — через перестановки. Утверждается, что это одно и то же
    множество эффектов. Если лемма не пройдёт, расхождение найдётся
    максимально локально, а не на четырёхсотой строке доказательства про
    весь DP. -/
def BucketEffectExact : Prop :=
  ∀ (b : List Actor) (carried : Bool) (e : Nat × Bool),
    e ∈ bucketEffects b carried ↔
      ∃ l, b.Perm l ∧ countFrom carried l = e.1 ∧ stateAfter carried l = e.2

/-- ПОЛОВИНА, НУЖНАЯ ДЛЯ SOUNDNESS: перечисление НИЧЕГО НЕ ТЕРЯЕТ — эффект
    любой перестановки в нём есть.

    Разделение не косметическое. Корректность границ требует только этой
    половины: чтобы ни одна реальная история не выпала из рассмотрения.
    Резкость требует второй. Доказав первую, мы уже получаем работающий
    вывод, даже если вторая застрянет. -/
def BucketEffectComplete : Prop :=
  ∀ (b : List Actor) (carried : Bool) (l : List Actor), b.Perm l →
    (countFrom carried l, stateAfter carried l) ∈ bucketEffects b carried

/-- ПОЛОВИНА, НУЖНАЯ ДЛЯ SHARPNESS: перечисление НИЧЕГО НЕ ВЫДУМЫВАЕТ —
    каждый перечисленный эффект материализуется перестановкой. -/
def BucketEffectRealizable : Prop :=
  ∀ (b : List Actor) (carried : Bool) (e : Nat × Bool),
    e ∈ bucketEffects b carried →
      ∃ l, b.Perm l ∧ countFrom carried l = e.1 ∧ stateAfter carried l = e.2

/-- КАЖДАЯ реальная история присутствует среди достижимых пар DP.
    Отсюда `DPBoundsSound` становится следствием, а не подвигом. -/
def HistoryToReachable : Prop :=
  ∀ o l, Admissible o l → (countFrom false l, stateAfter false l) ∈ dpReachable o

/-- И обратно: КАЖДАЯ достижимая пара материализуется ЦЕЛОСТНОЙ историей.
    Отсюда следует `DPBoundsSharp`. -/
def ReachableToHistory : Prop :=
  ∀ o e, e ∈ dpReachable o →
    ∃ l, Admissible o l ∧ countFrom false l = e.1 ∧ stateAfter false l = e.2

end RelationshipFix.Spec
