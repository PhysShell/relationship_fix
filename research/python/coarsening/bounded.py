"""`TiePolicy.BOUNDED`: точная partial identification для двухакторных потоков.

ЗАЧЕМ. Измерение показало, что `STRICT` на минутной шкале не теряет
наблюдения, а МЕНЯЕТ ЭСТИМАНД. Пусть A = возможность задета неоднозначной
группой меток, I = 1 − A, T = латентность возврата. Хотели

    E[min(T, H) | eligible]

а STRICT даёт

    E[min(T, H) | eligible, I = 1]

и секундная рука показывает, что I и T зависимы жёстко: выброшенные возвраты
имеют медиану 1 минуту, оставленные — 6. Для будущего эксперимента с
вмешательством хуже ещё на порядок: если prompting двигает плотность, он
двигает и вероятность попасть в неоднозначную группу,

    Z -> плотность -> ambiguity -> включение в анализ

то есть включение становится ПОСТ-ТРИТМЕНТ переменной, и рандомизация анализ
уже не спасает. Это родственник найденной раньше проблемы с
treatment-dependent N, только пришедший через measurement process.

ЧТО ЗДЕСЬ ЕСТЬ И ЧЕГО НЕТ. Общий partial-order движок не строится: он
упирается в перебор linear extensions и факториальную сложность. Но у нас
ровно два актёра и корзины, у которых ПОРЯДОК МЕЖДУ корзинами известен, а
неизвестен только порядок внутри. Это подарок, и он даёт точный
специализированный DP.

    НЕТ probabilistic ordering — источник не давал вероятностной модели, и
    придумывать, что AABB и ABBA равновероятны, не на чем;
    НЕТ learned tie model;
    НЕТ generic DAG framework.

ДВА СЛОЯ НЕОПРЕДЕЛЁННОСТИ, и они разделены намеренно:

    ORDER   какие серии и возможности вообще возможны;
    TIME    какие латентности возможны при каждой допустимой топологии,
            потому что метка «12:34» означает интервал [12:34:00, 12:35:00).

`time_layer=False` даёт слой порядка отдельно — и именно он обязан
схлопываться в обычный экстрактор, когда хронология однозначна.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .paired import Stream
from .prereg import OBSERVED_RESOLUTION_SECONDS, coarsen

#: Порядок ВНУТРИ корзины неизвестен; порядок МЕЖДУ корзинами известен.
#: На этом и стоит весь DP.
WITHIN_BIN_ORDER_IS_FREE = True

#: Перестановки одного и того же актёра нас не касаются: AAABB и AABAB
#: сжимаются в разные шаблоны, а AAABB и AAABB — в один. Существенным
#: является только СЖАТЫЙ ШАБЛОН ЧЕРЕДОВАНИЯ, и его вариантов кратно меньше,
#: чем перестановок сообщений.
ONLY_COMPRESSED_PATTERNS_MATTER = True


@dataclass(frozen=True, slots=True)
class Bin:
    """Корзина: начало и сколько сообщений каждого актёра в ней лежит."""

    start: float
    partner: int
    participant: int

    @property
    def size(self) -> int:
        return self.partner + self.participant


def to_bins(stream: Stream, participant: int, *,
            delta: float = OBSERVED_RESOLUTION_SECONDS,
            phase: float = 0.0) -> list[Bin]:
    """Поток -> корзины. Сообщения внутри корзины теряют порядок, и это суть."""
    counts: dict[float, list[int]] = {}
    for stamp, actor in zip(stream.stamps, stream.actors):
        key = coarsen(stamp, delta, phase)
        row = counts.setdefault(key, [0, 0])
        row[1 if actor == participant else 0] += 1
    return [Bin(start, row[0], row[1]) for start, row in sorted(counts.items())]


def patterns(partner: int, participant: int):
    """Сжатые шаблоны чередования: (первым идёт партнёр?, блоков P, блоков Q).

    Для `partner = a`, `participant = b` допустимы все чередования с
    `1 <= p <= a`, `1 <= q <= b` и `|p - q| <= 1`. Вариантов O(min(a, b)),
    а не `(a + b)! / (a! b!)`.
    """
    out = []
    for p in range(1, partner + 1):
        for q in range(1, participant + 1):
            if p == q + 1:
                out.append((True, p, q))
            elif q == p + 1:
                out.append((False, p, q))
            elif p == q:
                out.append((True, p, q))
                out.append((False, p, q))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Move:
    """Один переход DP: что прибавилось к N и к B, и чем кончилась корзина."""

    opened: int
    #: закрытие перенесённой возможности: (начало её корзины) или None
    closed_carried: bool
    #: сколько возможностей открылось И закрылось внутри этой корзины
    closed_inside: int
    #: None, либо начало корзины, где осталась открытая серия
    state: float | None


#: Состояние «серия осталась открытой с прежней корзины» переносится как есть.
CARRY = "carry"


def moves(bucket: Bin, carried: bool) -> list[Move]:
    """Все допустимые исходы корзины при заданном входящем состоянии.

    Выбор есть только в СМЕШАННОЙ корзине. Корзина с одним актёром ничего не
    решает: там порядок неизвестен, но и неважен — перестановки одного актёра
    топологию не двигают.
    """
    if bucket.participant == 0:                      # только партнёр
        if carried:
            return [Move(0, False, 0, CARRY)]        # серия продолжается
        return [Move(1, False, 0, bucket.start)]     # серия открывается
    if bucket.partner == 0:                          # только участник
        return [Move(0, carried, 0, None)]
    out = []
    for first_is_partner, p, q in patterns(bucket.partner, bucket.participant):
        if first_is_partner:
            opened = p - 1 if carried else p
            closed_carried = carried
            closed_inside = q - 1 if carried else q
            state = bucket.start if p == q + 1 else None
        else:
            opened = p
            closed_carried = carried
            closed_inside = min(p, q - 1)
            state = None if q == p + 1 else bucket.start
        out.append(Move(opened, closed_carried, closed_inside, state))
    return out


def opens_here(start: float, *, horizon: float, window_end: float,
               initiation_end: float | None) -> bool:
    """Может ли В ЭТОЙ корзине ОТКРЫТЬСЯ засчитываемая возможность.

    ДВЕ РАЗНЫЕ ГРАНИЦЫ, и смешивать их нельзя — найдено третьим враждебным
    чтением. `window_end` — конец НАБЛЮДЕНИЯ: до него корзины остаются в
    данных и закрывают ранее открытые возможности. `initiation_end` — конец
    ОБЛАСТИ ИНИЦИАЦИИ: после него новые открытия не засчитываются.

    Просто обрезать корзины по отсечке НЕЛЬЗЯ. Возможность может открыться до
    отсечки, а ответ прийти после неё; выбросив поздние корзины, мы превратим
    завершённую возможность в цензурированную и припишем ей полный горизонт.
    Ошибка тихая и ровно в ту сторону, которая красивее выглядит.

    `initiation_end` — ИСКЛЮЧАЮЩАЯ верхняя граница на начало корзины. Она
    скалярна потому, что область инициации — префикс по времени; на этом же
    свойстве стоит теорема N_min = 0 => N_max = 0.

    None означает историческое правило (`start + H <= window_end`), при
    котором конец наблюдения и отсечка совпадают. Так считался Q1c, и его
    запечатанный результат обязан воспроизводиться байт в байт.
    """
    if initiation_end is None:
        return start + horizon <= window_end
    return start < initiation_end


def contribution(move: Move, bucket: Bin, opened_at: float | None, *,
                 delta: float, horizon: float, window_end: float,
                 time_layer: bool,
                 initiation_end: float | None = None) -> tuple[int, float, float]:
    """(сколько eligible возможностей открылось, вклад в B_lo, вклад в B_hi).

    Eligibility считается по НАЧАЛУ КОРЗИНЫ — той же метке, которую видит
    обычный экстрактор, и одинаково в обеих границах. Истинное время открытия
    гуляет внутри корзины, поэтому у возможностей ровно на краю окна правило
    могло бы дрогнуть; это объявлено, а не замолчано.
    """
    def opens(at: float) -> bool:
        return opens_here(at, horizon=horizon, window_end=window_end,
                          initiation_end=initiation_end)

    here_eligible = opens(bucket.start)
    n_add = move.opened if here_eligible else 0
    low = high = 0.0

    if move.closed_carried and opened_at is not None:
        if opens(opened_at):
            gap = bucket.start - opened_at
            if time_layer:
                low += min(max(0.0, gap - delta), horizon)
                high += min(gap + delta, horizon)
            else:
                low += min(gap, horizon)
                high += min(gap, horizon)

    if move.closed_inside and here_eligible:
        if time_layer:
            # спаны закрытых внутри корзины возможностей НЕ ПЕРЕСЕКАЮТСЯ,
            # поэтому их сумма ограничена шириной корзины. Складывать по
            # min(delta, H) на каждую значило бы выдать за верхнюю границу
            # то, что ни в одном допустимом порядке не достижимо
            high += min(delta, move.closed_inside * horizon)
        # low = 0: внутри корзины возврат может быть мгновенным

    return n_add, low, high


@dataclass(frozen=True, slots=True)
class Interval:
    low: float
    high: float

    @property
    def width(self) -> float:
        return self.high - self.low

    def __contains__(self, other) -> bool:
        return self.low <= other.low and other.high <= self.high


#: Кэш допустимых ходов по ФОРМЕ корзины. Форм мало (корзины крошечные), а
#: проходов DP много: дробная оптимизация зовёт его десятки раз. Собирается
#: из `moves`, чтобы быстрый путь не разошёлся с читаемым определением.
_MOVE_TABLE: dict[tuple[int, int, bool], tuple] = {}

#: как кодируется исход корзины: 0 — серия закрыта, 1 — открыта ЗДЕСЬ,
#: 2 — перенесена с прежней корзины без изменений
_CLOSED, _HERE, _CARRY = 0, 1, 2


def _table(partner: int, participant: int, carried: bool) -> tuple:
    key = (partner, participant, carried)
    cached = _MOVE_TABLE.get(key)
    if cached is None:
        rows = []
        for move in moves(Bin(0.0, partner, participant), carried):
            if move.state is None:
                kind = _CLOSED
            elif move.state == CARRY:
                kind = _CARRY
            else:
                kind = _HERE
            rows.append((move.opened, move.closed_carried,
                         move.closed_inside, kind))
        cached = tuple(rows)
        _MOVE_TABLE[key] = cached
    return cached


def _optimise(bins: list[Bin], *, delta: float, horizon: float,
              window_end: float, time_layer: bool, lam: float,
              maximise: bool, require_any: bool,
              initiation_end: float | None = None) -> float | None:
    """min/max по допустимым порядкам величины (B − λ·N). Shortest path по DAG.

    B и N складываются по переходам, поэтому `B − λN` тоже складывается, и
    экстремум берётся ОДНИМ целостным порядком. Это и есть та ловушка,
    которую нельзя обойти поопортунитно: минимум одной возможности и минимум
    другой могут требовать взаимоисключающих порядков одной корзины.
    """
    def opens(at: float) -> bool:
        return opens_here(at, horizon=horizon, window_end=window_end,
                          initiation_end=initiation_end)

    frontier: dict[tuple[float | None, bool], float] = {(None, False): 0.0}
    for bucket in bins:
        start = bucket.start
        here_eligible = opens(start)
        nxt: dict[tuple[float | None, bool], float] = {}
        for (state, seen), value in frontier.items():
            carried = state is not None
            carried_eligible = carried and opens(state)
            if carried_eligible:
                gap = start - state
                if time_layer:
                    cross = (min(gap + delta, horizon) if maximise
                             else min(max(0.0, gap - delta), horizon))
                else:
                    cross = min(gap, horizon)
            else:
                cross = 0.0
            for opened, closes_carried, inside, kind in _table(
                    bucket.partner, bucket.participant, carried):
                n_add = opened if here_eligible else 0
                gain = -lam * n_add
                if closes_carried and carried:
                    gain += cross
                if inside and here_eligible and maximise and time_layer:
                    gain += min(delta, inside * horizon)
                target = state if kind == _CARRY else (
                    start if kind == _HERE else None)
                key = (target, seen or n_add > 0)
                candidate = value + gain
                previous = nxt.get(key)
                if previous is None or (candidate > previous if maximise
                                        else candidate < previous):
                    nxt[key] = candidate
        frontier = nxt
    better = max if maximise else min
    best = None
    for (state, seen), value in frontier.items():
        if require_any and not seen:
            continue
        total = value
        if state is not None and opens(state):
            total += horizon                    # возврата не было: вносит H
        if best is None or better(best, total) == total:
            best = total
    return best


def count_bounds(bins: list[Bin], *, horizon: float, window_end: float,
                 initiation_end: float | None = None) -> Interval:
    """Границы для N. Отдельно, потому что N — самостоятельная величина."""
    return Interval(float(_count(bins, horizon, window_end, False, initiation_end)),
                    float(_count(bins, horizon, window_end, True, initiation_end)))


def _count(bins: list[Bin], horizon: float, window_end: float,
           maximise: bool, initiation_end: float | None = None) -> int:
    """Чистый экстремум N: тот же DP с нулевым вкладом в B."""
    better = max if maximise else min
    frontier: dict[float | None, int] = {None: 0}
    for bucket in bins:
        nxt: dict[float | None, int] = {}
        eligible = opens_here(bucket.start, horizon=horizon,
                              window_end=window_end,
                              initiation_end=initiation_end)
        for state, value in frontier.items():
            for move in moves(bucket, state is not None):
                target = state if move.state == CARRY else move.state
                candidate = value + (move.opened if eligible else 0)
                if target not in nxt or better(nxt[target], candidate) == candidate:
                    nxt[target] = candidate
        frontier = nxt
    return better(frontier.values())


def burden_bounds(bins: list[Bin], *, horizon: float, window_end: float,
                  delta: float = OBSERVED_RESOLUTION_SECONDS,
                  time_layer: bool = True,
                  initiation_end: float | None = None) -> Interval:
    low = _optimise(bins, delta=delta, horizon=horizon, window_end=window_end,
                    time_layer=time_layer, lam=0.0, maximise=False,
                    require_any=False, initiation_end=initiation_end)
    high = _optimise(bins, delta=delta, horizon=horizon, window_end=window_end,
                     time_layer=time_layer, lam=0.0, maximise=True,
                     require_any=False, initiation_end=initiation_end)
    return Interval(low or 0.0, high or 0.0)


#: Точность поиска λ в дробной оптимизации, в секундах.
#: Двадцатая секунды на величине, которая меряется в минутах, — запас с
#: избытком; это численный допуск поиска, а не научный параметр.
RATIO_TOLERANCE_SECONDS = 5e-2


class NoCrossing(ValueError):
    """g не пересекает ноль внутри скобки, или обратилась в None/NaN.

    ЯВНЫЙ ОТКАЗ вместо героического поиска корня, которого нет. Люди и так
    умеют находить смысл там, где его нет; помогать в этом библиотечной
    функции не обязательно.
    """


@dataclass(frozen=True, slots=True)
class Bracket:
    """low <= λ* <= high, и `width` — гарантированная односторонняя ошибка.

    ПОЧЕМУ НЕ ЧИСЛО. Математически λ* = inf{λ : g(λ) <= 0} от бюджета
    итераций не зависит. ЧИСЛЕННО — зависит, какую сторону скобки вернуть, и
    это не вопрос шестой цифры: конец руки входит в

        [λ⁻T − λ⁺K,  λ⁺T − λ⁻K]

    и выбор не той стороны СУЖАЕТ идентифицированное множество. Компьютер
    ради красивого округления выбросит допустимые значения — а выбрасывать
    допустимые значения это ровно то, чего частичная идентификация не делает
    по определению.

    Поэтому возвращается скобка, а сторону выбирает вызывающий: нижний конец
    руки берётся ВНИЗ, верхний ВВЕРХ. Наружу, всегда наружу.
    """

    low: float
    high: float

    @property
    def width(self) -> float:
        return self.high - self.low


def generalized_inverse(g, lo: float, hi: float, *,
                        tolerance: float | None = None,
                        iterations: int = 60) -> Bracket:
    """Скобка вокруг inf{ λ ∈ [lo, hi] : g(λ) <= 0 }. Чистая функция от `g`.

    В комментариях когда-то стояло «g не возрастает, значит корень
    единственный». Это НЕВЕРНО: из монотонности следует только существование
    точки смены знака. Функция может иметь ПЛАТО

        g > 0 при λ < a,   g = 0 на [a, b],   g < 0 при λ > b

    и тогда «корень» перестаёт быть определением. Обобщённо-обратная при
    плато даёт ЛЕВЫЙ край `a`, и уникальность определению больше не нужна;
    она остаётся отдельным проверяемым свойством (`dinkelbach_slope_bound`).

    Инвариант: g(low) > 0 и g(high) <= 0 на каждом шаге, поэтому искомое
    значение лежит в (low, high]. Ширина доводится до `tolerance`.

    Отказы ЯВНЫЕ: `NoCrossing`, если g(hi) > 0 (скобка мала), если g(lo) уже
    <= 0 при lo, не равном левой границе области, или если g вернула
    None/NaN/inf.
    """
    # РАЗРЕШАЕТСЯ ПРИ ВЫЗОВЕ, а не при определении. Аргумент по умолчанию
    # вычисляется один раз при импорте, поэтому `tolerance=RATIO_TOLERANCE`
    # в сигнатуре делал точность НЕПОДМЕНЯЕМОЙ — и тест, сравнивавший
    # «грубый» прогон с «высокоточным», сравнивал грубый сам с собой.
    # Ровно тот класс пустого теста, против которого он и писался.
    if tolerance is None:
        tolerance = RATIO_TOLERANCE_SECONDS

    def value(at: float) -> float:
        got = g(at)
        if got is None or not math.isfinite(got):
            raise NoCrossing(f"g({at}) = {got}")
        return got

    if value(lo) <= 0.0:
        return Bracket(lo, lo)          # λ* <= lo: скобка вырождена, но верна
    if value(hi) > 0.0:
        raise NoCrossing(f"g({hi}) > 0 — искомое значение вне скобки")

    low, high = lo, hi
    for _ in range(iterations):
        if high - low < tolerance:
            break
        mid = (low + high) / 2.0
        if value(mid) > 0.0:
            low = mid
        else:
            high = mid
    return Bracket(low, high)


def dinkelbach_slope_bound(periods: list[list[Bin]], *, horizon: float,
                           window_end: float,
                           initiation_end: float | None = None) -> int:
    """Сколько НЕПУСТЫХ периодов в руке — то же, что верхняя оценка наклона.

    ДОСТАТОЧНОЕ УСЛОВИЕ СТРОГОГО УБЫВАНИЯ, названное явно вместо ссылки на
    монотонность. Каждое `min_h (B_h − λN_h)` — минимум аффинных функций с
    наклонами `−N_h`. По теореме `N_min = 0 => N_max = 0` непустой период
    имеет `N >= 1` при КАЖДОЙ допустимой истории, значит его наклон `<= −1`.
    Сумма по руке убывает с наклоном не более `−(число непустых периодов)`.
    
    Отсюда: пока результат этой функции положителен, плато невозможно и
    обобщённо-обратная совпадает с единственным корнем. Ноль означает, что
    эстиманда нет вовсе.
    
    То есть уникальность корня куплена ровно той теоремой, которая закрыла
    претензию про плавающий знаменатель. Одно предусловие держит оба ответа,
    и сломается оно тоже сразу для обоих.
    """
    return sum(1 for bins in periods
               if _count(bins, horizon, window_end, True, initiation_end) > 0)


def ratio_bounds(bins: list[Bin], *, horizon: float, window_end: float,
                 delta: float = OBSERVED_RESOLUTION_SECONDS,
                 time_layer: bool = True,
                 initiation_end: float | None = None,
                 tolerance: float | None = None) -> Interval | None:
    """Границы для R = B / N через дробную оптимизацию.

    ЧТО ИМЕННО ВОЗВРАЩАЕТСЯ, и слово тут выбрано не для красоты. По ПОРЯДКУ
    оптимизация точная, по ВРЕМЕНИ — внешняя оболочка (латентности берутся из
    интервалов корзин с внутрикорзинным бюджетом, но без полной совместной
    оптимизации положений). Поэтому при `time_layer=True` это
    VALID OUTER IDENTIFICATION ENVELOPE, а не sharp bounds.

    Разница работает НА УСИЛЕНИЕ вывода: точка снаружи заведомо слишком
    широкой оболочки тем более лежит вне неизвестного резкого множества
    внутри неё. И ослабляет только обратное утверждение — «точка внутри»
    ничего не доказывает.

    При `time_layer=False` остаётся чистый слой порядка, и вот он резкий.


    НЕЛЬЗЯ писать `R_min = B_min / N_max` и звать это границами: `B_min` и
    `N_max` достигаются, вообще говоря, на РАЗНЫХ допустимых порядках, и
    получившаяся оболочка не резкая, а иногда и не валидная как утверждение
    о достижимости.

    Правильно — искать λ, при котором экстремум `B − λN` обращается в ноль:
    тогда λ и есть экстремум отношения, достигаемый одним целостным порядком.
    Это стандартный приём (Dinkelbach), и он избавляет от хранения всего
    зоопарка достижимых пар (N, B).
    """
    if _count(bins, horizon, window_end, True, initiation_end) == 0:
        return None                      # эстиманда нет: N = 0 при любом порядке

    counts = count_bounds(bins, horizon=horizon, window_end=window_end,
                          initiation_end=initiation_end)
    burden = burden_bounds(bins, horizon=horizon, window_end=window_end,
                           delta=delta, time_layer=time_layer,
                           initiation_end=initiation_end)
    # НАИВНАЯ оболочка B_lo/N_hi .. B_hi/N_lo не годится как ОТВЕТ — её
    # концы достигаются на разных порядках. Но как СКОБКА ПОИСКА она
    # безупречна: искомый экстремум отношения лежит внутри неё, и старт с
    # [0, H] просто тратил бы итерации
    lo_bracket = burden.low / counts.high if counts.high else 0.0
    hi_bracket = burden.high / counts.low if counts.low else horizon

    def solve(maximise: bool) -> Bracket:
        # f(λ) = extremum(B − λN) не возрастает по λ; искомый конец — её
        # ОБОБЩЁННО-ОБРАТНАЯ, а не «корень»: см. `generalized_inverse`
        return generalized_inverse(
            lambda lam: _optimise(bins, delta=delta, horizon=horizon,
                                  window_end=window_end, time_layer=time_layer,
                                  lam=lam, maximise=maximise, require_any=True,
                                  initiation_end=initiation_end),
            max(0.0, lo_bracket), min(horizon, hi_bracket) + 1e-9,
            tolerance=tolerance)

    try:
        # НАРУЖУ: нижний конец вниз, верхний вверх. Численная ошибка обязана
        # РАСШИРЯТЬ идентифицированное множество, а не сужать его
        return Interval(solve(False).low, solve(True).high)
    except NoCrossing:
        return None


# ---------------------------------------------------------------------------
# Решение. Неидентифицированность — не то же, что статистическая неясность.
# ---------------------------------------------------------------------------

class Identified(Enum):
    """Что удалось УСТАНОВИТЬ, а не что получилось посчитать."""

    REACTIVITY_SIGNAL = "reactivity_signal"
    PRACTICALLY_NEGLIGIBLE = "practically_negligible"
    #: интервал идентификации пересекает границу решения. Это НЕ шум выборки и
    #: увеличением N не лечится: источник просто не различает нужные порядки
    ORDER_AMBIGUOUS = "order_ambiguous"
    #: эстиманда нет вовсе
    UNDEFINED = "undefined"


def identified(interval: Interval | None, delta: float) -> Identified:
    """Три состояния плюс «эстиманда нет». Чистая функция.

    Интерфейс между неопределённостью ИЗМЕРЕНИЯ и уже построенным гейтом
    решения. Если минутный источник даёт [−4 мин, +37 мин], правильный ответ
    не «поищем модель поумнее», а «источник недостаточно идентифицирует нужный
    causal endpoint». И тогда всё: источник не годится для этой задачи.
    """
    if interval is None or delta < 0 or math.isnan(interval.low) \
            or math.isnan(interval.high):
        return Identified.UNDEFINED
    if interval.low > delta or interval.high < -delta:
        return Identified.REACTIVITY_SIGNAL
    if -delta <= interval.low and interval.high <= delta:
        return Identified.PRACTICALLY_NEGLIGIBLE
    return Identified.ORDER_AMBIGUOUS


# ---------------------------------------------------------------------------
# ОПРЕДЕЛЁННОСТЬ ЭСТИМАНДА. Найдено враждебным чтением prereg S5b.
# ---------------------------------------------------------------------------

class Definedness(Enum):
    """Существует ли `R = B/N` на этой person-period — и при ВСЕХ ли историях.

    ПОЧЕМУ ЭТО ОТДЕЛЬНАЯ ВЕЛИЧИНА, а не деталь реализации. `ratio_bounds`
    возвращает `None` только когда `N = 0` при ЛЮБОМ допустимом порядке. Во
    всех остальных случаях он зовёт `_optimise(require_any=True)`, то есть
    оптимизирует по историям С ХОТЯ БЫ ОДНОЙ возможностью. Значит при

        count_bounds = [0, 3]

    возвращённый интервал — это интервал УСЛОВНО НА `N > 0`, а само событие
    `N > 0` латентно: часть допустимых историй его не даёт.

    Последствие тихое и дорогое. Если такие ячейки складывать в среднее по
    руке, то множество слагаемых само зависит от ненаблюдаемой хронологии, и

        [mean L_i, mean U_i]

    перестаёт быть резкой границей среднего: она выведена для ФИКСИРОВАННОГО
    знаменателя. Интервал, условный на событии, которое само неоднозначно,
    складывать с безусловными нельзя.

    Три случая, а не два — и третий не является неоднозначностью:
    """

    #: N > 0 при любом допустимом порядке. Слагаемое безусловное.
    DEFINED = "defined"
    #: N = 0 при любом допустимом порядке. Эстиманда нет НИ ПРИ КАКОЙ истории,
    #: поэтому ячейка выбывает ДЕТЕРМИНИРОВАННО и знаменатель остаётся
    #: фиксированным. Это не неоднозначность, а пустой период.
    UNDEFINED_EVERYWHERE = "undefined_everywhere"
    #: N = 0 при одних порядках и N > 0 при других. Вот это — неоднозначность
    #: САМОЙ ОБЛАСТИ ОПРЕДЕЛЕНИЯ, и она не лечится ни числом диад, ни более
    #: умным интервалом при фиксированном знаменателе.
    AMBIGUOUS = "definedness_ambiguous"


def definedness(counts: Interval) -> Definedness:
    """`count_bounds` -> статус определённости. Чистая функция."""
    if counts.high <= 0.0:
        return Definedness.UNDEFINED_EVERYWHERE
    if counts.low > 0.0:
        return Definedness.DEFINED
    return Definedness.AMBIGUOUS


def arm_ratio_bounds(periods: list[list[Bin]], *, horizon: float,
                     window_end: float, delta: float = OBSERVED_RESOLUTION_SECONDS,
                     time_layer: bool = True,
                     initiation_end: float | None = None,
                 tolerance: float | None = None) -> Interval | None:
    """Границы для ΣB / ΣN по ВСЕЙ руке. Найдено враждебным чтением S5b.

    ЗАЧЕМ ОТДЕЛЬНАЯ ФУНКЦИЯ, если есть `ratio_bounds` на период. Потому что
    для функционала «отношение сумм» поячеечные интервалы складывать НЕЛЬЗЯ:

        [ Σ B_lo / Σ N_hi ,  Σ B_hi / Σ N_lo ]     НЕ границы

    это ровно ловушка `B_min / N_max`, поднятая этажом выше: концы достигаются
    на РАЗНЫХ допустимых порядках, и получившаяся оболочка не резкая. Среднее
    поячеечных концов не годится тем более — оно вообще про другой функционал
    (person-period-weighted), а не про этот.

    ПРАВИЛЬНО — тот же Динкельбах, но по всей руке сразу: искать λ, при котором
    экстремум `ΣB − λΣN` обращается в ноль. И здесь везение структурное:
    периоды независимы, ограничений между ними нет, а целевая функция
    аддитивна, поэтому

        min по совместным порядкам Σ_i (B_i − λ N_i)  =  Σ_i min_i (B_i − λ N_i)

    то есть совместная оптимизация РАСПАДАЕТСЯ на уже имеющийся поячеечный DP.
    Стоимость линейна по числу периодов, а не экспоненциальна.

    Почему этот функционал вообще стал первичным — см. prereg S5b §4:
    person-period-weighted RMTR условен на `N > 0`, а это post-treatment
    событие. Здесь пустые периоды вносят 0 и в числитель, и в знаменатель, и
    никакого знаменателя на уровне периода просто нет.

    По ПОРЯДКУ точно; по ВРЕМЕНИ — внешняя оболочка, как и у `ratio_bounds`.
    """
    if not periods:
        return None
    if sum(_count(bins, horizon, window_end, True, initiation_end)
           for bins in periods) == 0:
        return None                      # эстиманда нет: ΣN = 0 при любом порядке

    def total(lam: float, maximise: bool) -> float:
        return sum(_optimise(bins, delta=delta, horizon=horizon,
                             window_end=window_end, time_layer=time_layer,
                             lam=lam, maximise=maximise, require_any=False,
                             initiation_end=initiation_end) or 0.0
                   for bins in periods)

    def solve(maximise: bool) -> Bracket:
        return generalized_inverse(lambda lam: total(lam, maximise),
                                   0.0, horizon + 1e-9, tolerance=tolerance)

    try:
        return Interval(solve(False).low, solve(True).high)
    except NoCrossing:
        return None


#: Шаг зондирования односторонних наклонов. Зажат с двух сторон: СВЕРХУ —
#: минимальным расстоянием между изломами (они лежат в точках ΔB/ΔN, поэтому
#: два различных отстоят не менее чем на 1/N_max²), СНИЗУ — ошибкой округления
#: разностного отношения при G порядка 10⁷…10⁹. 1e-5 с лежит между ними с
#: запасом в обе стороны, и устойчивость по шагу проверяется тестом.
SLOPE_PROBE_STEP_SECONDS = 1e-5


def one_sided_slopes(g, lam: float, *,
                     step: float = SLOPE_PROBE_STEP_SECONDS) -> tuple[int, int]:
    """(наклон слева, наклон справа) в точке `lam`, ЦЕЛЫМИ.

    ψ(λ) = extremum по историям (B − λN) — кусочно-линейная функция с
    наклонами −N, поэтому наклон ВСЕГДА ЦЕЛЫЙ, и округление здесь не
    приближение, а снятие шума разностного отношения.
    """
    left = round((g(lam) - g(lam - step)) / step)
    right = round((g(lam + step) - g(lam)) / step)
    return left, right


def is_regular_at(g, lam: float, *,
                  step: float = SLOPE_PROBE_STEP_SECONDS) -> bool:
    """Совпадают ли односторонние производные в `lam`.

    ЗАЧЕМ ЭТО НУЖНО, и найдено это пятым враждебным чтением. Теорема об
    огибающей даёт ψ'(λ) = −N_h* ТОЛЬКО когда активная история единственна.
    При ничьей между историями с РАЗНЫМИ N у ψ излом:

        ∂ψ(λ) = [−N_max, −N_min]

    и равенство d/dλ E[ψ] = −E[N*] из огибающей УЖЕ НЕ СЛЕДУЕТ — нужен мост
    через матожидание. Доказанное «N >= 1» даёт «наклон никогда не ноль», но
    НЕ даёт «слева равно справа». Это разные утверждения, и второе несущее:
    после отказа от бутстрапа производная стала балкой всего инференса.

    Случай достижим, а не гипотетичен: у корзины (partner=2, participant=2)
    минимальное отношение равно нулю сразу для нескольких историй с разными
    N, и в λ0 = 0 наклоны −1 и −2. То есть λ⁻ упирается в границу области
    значений И сидит в изломе одновременно — Wald там не просто неточен.
    """
    left, right = one_sided_slopes(g, lam, step=step)
    return left == right


#: Допуск проверки аффинности. НЕ произвольная малая константа: настоящий
#: излом меняет наклон не меньше чем на 1 (наклоны целые, −N), поэтому провис
#: относительно хорды на отрезке ширины w не меньше w/4, когда излом в
#: середине. Порог ставится на шесть порядков ниже этой величины — то есть
#: далеко и от нуля, и от шума плавающей точки, а не «подобран, чтобы
#: проходило».
AFFINE_SAG_FRACTION = 1e-6


def _is_affine_on(g, a: float, b: float) -> bool:
    """Аффинна ли `g` на [a, b]. Точно для кусочно-линейной вогнутой `g`.

    ψ(λ) = min по историям (B − λN) — минимум аффинных функций, значит
    ВОГНУТА. Для вогнутой функции ψ(середина) >= полусумма концов, причём
    равенство РАВНОСИЛЬНО аффинности на отрезке. Одно вычисление вместо
    сканирования сеткой, и без риска перешагнуть излом.
    """
    mid = (a + b) / 2.0
    left, right, centre = g(a), g(b), g(mid)
    chord = (left + right) / 2.0
    # минимальный провис настоящего излома: (b − a)/4 при скачке наклона 1
    floor_sag = (b - a) / 4.0
    return abs(centre - chord) <= AFFINE_SAG_FRACTION * max(floor_sag, 1e-12)


def nearest_breakpoint(g, lam: float, radius: float, *,
                       iterations: int = 60) -> float | None:
    """Расстояние до ближайшего излома `g` в пределах `radius`, или None.

    ЗАЧЕМ ИМЕННО ЭТО, а не односторонние производные в точке. Найдено шестым
    враждебным чтением, и ошибка была структурной.

    Прежний гейт сравнивал односторонние наклоны ВЫБОРОЧНОГО критерия в
    ВЫБОРОЧНОМ корне. Но если излом есть у ПОПУЛЯЦИОННОГО g в λ0, выборочный
    корень отстоит от него на O(n^{-1/2}) и почти наверное лежит ВНУТРИ
    линейного куска — гейт рапортует REGULAR. Хуже: с ростом n он слепнет
    СИЛЬНЕЕ, потому что λ̂ → λ0, но событие «λ̂ = λ0 точно» имеет вероятность
    около нуля.

    Замерено на построенной смеси 50/50 с популяционным разрывом 0.5:
    гейт сказал REGULAR в 60/60 при n = 25 и в 59/60 при n = 1600.

    Правильный объект — РАССТОЯНИЕ ДО ИЗЛОМА, а не производная в точке. Если
    ближайший излом дальше, чем неопределённость самого λ0, то g линейна в
    окрестности корня, и это сильнее, чем равенство односторонних наклонов.
    """
    if _is_affine_on(g, lam - radius, lam + radius):
        return None
    # ВАЖНЫЙ КРАЙ: излом РОВНО в `lam`. Каждая половина тогда аффинна по
    # отдельности, и проверка только половин его пропускает — первая
    # редакция этой функции так и делала.
    below = _is_affine_on(g, lam - radius, lam)
    above = _is_affine_on(g, lam, lam + radius)
    if below and above:
        return 0.0

    # Ищем ПЕРВЫЙ излом, двигаясь от `lam` наружу. Предикат берётся от
    # ФИКСИРОВАННОГО начала: иначе подвижный конец, попав ровно на излом,
    # уходит дальше (следующий отрезок уже аффинен) и уводит ответ на
    # границу радиуса. Этот путь набором не исполнялся, и баг нашёлся
    # вручную; теперь на него есть тест.
    if below:                      # излом справа от lam
        lo, hi = lam, lam + radius
        affine = lambda x: _is_affine_on(g, lam, x)
    else:                          # излом слева
        lo, hi = lam - radius, lam
        affine = lambda x: _is_affine_on(g, x, lam)

    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        near_is_affine = affine(mid)
        if below:
            lo, hi = (mid, hi) if near_is_affine else (lo, mid)
        else:
            lo, hi = (lo, mid) if near_is_affine else (mid, hi)
        if hi - lo < 1e-9 * max(1.0, abs(lam)):
            break
    return abs(lam - (lo if below else hi))


def count_near_breakpoints(periods: list[list[Bin]], lam: float, radius: float, *,
                           delta: float = OBSERVED_RESOLUTION_SECONDS,
                           horizon: float, window_end: float,
                           time_layer: bool = True,
                           initiation_end: float | None = None,
                           maximise: bool = False) -> tuple[int, float | None]:
    """(сколько периодов имеют излом ближе `radius` к `lam`, минимум расстояния).

    СЕРТИФИКАТ РЕГУЛЯРНОСТИ ПОПУЛЯЦИОННОГО КРИТЕРИЯ. Если НИ ОДИН период не
    имеет излома в окрестности корня, то g = E[ψ] ЛИНЕЙНА в этой окрестности,
    а значит дифференцируема — утверждение сильнее, чем равенство
    односторонних наклонов в точке, и, в отличие от него, не слепнет от того,
    что оценка корня не попадает в излом ровно.
    """
    nearest: float | None = None
    hits = 0
    for bins in periods:
        def psi(at: float, bins=bins) -> float:
            return _optimise(bins, delta=delta, horizon=horizon,
                             window_end=window_end, time_layer=time_layer,
                             lam=at, maximise=maximise, require_any=False,
                             initiation_end=initiation_end) or 0.0

        distance = nearest_breakpoint(psi, lam, radius)
        if distance is not None:
            hits += 1
            nearest = distance if nearest is None else min(nearest, distance)
    return hits, nearest


def achievable_frontier(bins: list[Bin], *, horizon: float, window_end: float,
                        delta: float = OBSERVED_RESOLUTION_SECONDS,
                        time_layer: bool = True,
                        initiation_end: float | None = None,
                        maximise: bool = False) -> dict[int, float]:
    """N -> минимальное достижимое B. Тот же DP, но с N в состоянии.

    ТРЕБУЕМАЯ МАШИНЕРИЯ ИНВЕРСИИ ТЕСТА, объявленная в prereg S5b §4. Смысл:

        ψ(λ) = min по историям (B − λN) = min по N (Bmin(N) − λN)

    то есть ψ — ОПОРНАЯ ФУНКЦИЯ множества достижимых пар. Посчитав фронт один
    раз, дальше каждое λ стоит O(|фронт|), а не целый DP. Именно это делает
    исполнимым исследование покрытия: 7.2 часа вместо 305 суток.

    Считается для НАПРАВЛЕНИЯ МИНИМУМА, потому что ψ — минимум; вклады
    берутся ровно те же, что в `_optimise(maximise=False)`.
    """
    def opens(at: float) -> bool:
        return opens_here(at, horizon=horizon, window_end=window_end,
                          initiation_end=initiation_end)

    # (состояние переноса, N) -> минимальное B
    frontier: dict[tuple[float | None, int], float] = {(None, 0): 0.0}
    for bucket in bins:
        start = bucket.start
        here_eligible = opens(start)
        nxt: dict[tuple[float | None, int], float] = {}
        for (state, count), value in frontier.items():
            carried = state is not None
            if carried and opens(state):
                gap = start - state
                if time_layer:
                    cross = (min(gap + delta, horizon) if maximise
                             else min(max(0.0, gap - delta), horizon))
                else:
                    cross = min(gap, horizon)
            else:
                cross = 0.0
            for opened, closes_carried, inside, kind in _table(
                    bucket.partner, bucket.participant, carried):
                added = opened if here_eligible else 0
                gain = cross if (closes_carried and carried) else 0.0
                if inside and here_eligible and maximise and time_layer:
                    gain += min(delta, inside * horizon)
                target = state if kind == _CARRY else (
                    start if kind == _HERE else None)
                key = (target, count + added)
                candidate = value + gain
                known = nxt.get(key)
                if known is None or (candidate > known if maximise
                                     else candidate < known):
                    nxt[key] = candidate
        frontier = nxt

    out: dict[int, float] = {}
    for (state, count), value in frontier.items():
        total = value
        if state is not None and opens(state):
            total += horizon                # возврата не было: вносит H
        known = out.get(count)
        if known is None or (total > known if maximise else total < known):
            out[count] = total
    return out


def hull_of(frontier: dict[int, float], *, upper: bool = False
            ) -> tuple[tuple[int, float], ...]:
    """Оболочка точек (N, B): нижняя для минимума, верхняя для максимума."""
    if not upper:
        return lower_hull(frontier)
    flipped = lower_hull({n: -b for n, b in frontier.items()})
    return tuple((n, -b) for n, b in flipped)


def lower_hull(frontier: dict[int, float]) -> tuple[tuple[int, float], ...]:
    """Нижняя выпуклая оболочка точек (N, B). Только её вершины участвуют в ψ.

    Точка над оболочкой не минимизирует B − λN НИ ПРИ КАКОМ λ, поэтому хранить
    её незачем. Оболочка строится по возрастанию N обычным обходом Эндрю.
    """
    points = sorted(frontier.items())
    hull: list[tuple[int, float]] = []
    for point in points:
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            x3, y3 = point
            # выбрасываем среднюю точку, если она не ниже хорды
            if (y2 - y1) * (x3 - x1) >= (y3 - y1) * (x2 - x1):
                hull.pop()
            else:
                break
        hull.append(point)
    return tuple(hull)
