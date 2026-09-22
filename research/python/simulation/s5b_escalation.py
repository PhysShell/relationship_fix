"""Слой эскалации этапа 1: вложенная лестница по ACTIVE-амендменту (ред. 4).

ЧТО ЭТОТ МОДУЛЬ ДОБАВЛЯЕТ К ВОССТАНОВЛЕННОМУ RUNNER'У. `s5b_stage1` считает
ровно один уровень `M` и про точность НЕ утверждает ничего — таким он и
задумывался, пока амендмента не было. Теперь амендмент active, и здесь
появляется то, чего там сознательно не было:

    tau = min{ M из (4000, 16000, 64000) : r_M <= z · 0.1 · GATE_MARGIN · δ }
    tau = inf  ->  MC_PRECISION_INSUFFICIENT  ->  NOT_EVALUATED_MC_PRECISION

ЭСТИМАНД НЕ МЕНЯЕТСЯ. Точки — те же корни обобщённой инверсии, что считал
runner; `roots_from` обязан воспроизводить `arm_endpoints` до последнего
знака, и это проверяется золотым дайджестом, снятым ДО рефакторинга.

ВЛОЖЕННОСТЬ — СТРОГИЙ ПРЕФИКС. Сид периода есть `f"{tag}:{i}"`, функция
ТОЛЬКО научных координат и индекса. Поэтому `accumulate(tag, 0, 16000)` и
`accumulate(tag, 0, 4000)` + `accumulate(tag, 4000, 16000)` дают побитово
одно и то же, а shard, worker, порядок исполнения и их количество в поток
не входят. Это же свойство и делает возможным шардинг диапазонами.

ДВЕ ЯЧЕЙКИ `H = 300` НЕ ПРОПУСКАЮТСЯ. Futility-правила в `2224eb8` нет, а
пилотный прогноз им не является: прогноз остаётся в провенансе как
`MC_PRECISION_PREDICTED_INSUFFICIENT` и НИКОГДА не управляет ходом
вычисления. Лестница исполняется честно до `64000`, и если точность не
достигнута — это предусмотренный исход, а не отсутствие исхода.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from coarsening.bounded import (achievable_frontier, generalized_inverse,
                                hull_of, to_bins)
from coarsening.inversion import Piece, acceptance_set, convex_hull_interval
from coarsening.paired import Stream
from simulation import s5b_precision as PR
from simulation import s5b_prereg as P
from simulation.experiment import REGIMES
from simulation.process import DyadParameters, generate_dyad

DAY = 86400.0

#: КАНОНИЧЕСКИЙ порядок ключей. Нужен, чтобы деление на группы было
#: детерминированным, а не зависело от обхода словаря. `delta` снаружи
#: намеренно: группа из смежных ключей тогда покрывает целые разрешения, и
#: `to_bins` не считается для чужих.
KEYS: tuple[tuple, ...] = tuple(
    (delta, days, horizon, maximise)
    for delta in P.ACQUISITION_RESOLUTIONS_SECONDS
    for days in P.OBSERVATION_DAYS
    for horizon in P.HORIZONS_SECONDS
    for maximise in (False, True))

#: КЛЮЧИ РАЗДЕЛИМЫ ВЫЧИСЛИТЕЛЬНО, А НЕ СТАТИСТИЧЕСКИ, и формулировка здесь
#: существенна. Требуется лишь то, что конец ключа `K` считается без
#: состояния, выведенного из другого ключа. СТАТИСТИЧЕСКОЙ независимости
#: между ключами нет и не требуется: они считаются по ОДНИМ И ТЕМ ЖЕ
#: диадам и вполне могут быть зависимы. Клеточный бюджет ошибки устроен
#: через союзную границу, которой зависимость безразлична, поэтому
#: подменять «можно считать порознь» на «независимы как случайные
#: величины» нельзя — это разные утверждения, и второе здесь не доказано и
#: не нужно.
KEYS_ARE_COMPUTATIONALLY_SEPARABLE_NOT_INDEPENDENT = True

#: Горизонты, пропускаемые по прогнозу. ПУСТО, и это решение, а не недосмотр.
SKIPPED_HORIZONS: tuple[float, ...] = ()

#: Прогноз — провенанс, не управление. Константа объявлена, чтобы её можно
#: было диверсировать: ниже по файлу `PREDICTED_INSUFFICIENT` не встречается
#: ни в одной ветке, и тест это проверяет разбором исходника.
PREDICTED_NEVER_DRIVES_CONTROL_FLOW = True

# ---------------------------------------------------------------------------
# ЗАВЕРШЕНИЕ СПЕЦИФИКАЦИИ: какая рука есть K (post-freeze, не догадка)
# ---------------------------------------------------------------------------
#
# Baseline определил МАТЕМАТИЧЕСКИЙ ОБЪЕКТ `[λ⁻_T − λ⁺_K, λ⁺_T − λ⁻_K]`, но не
# отображение «сетка -> руки». Отображение ВОССТАНОВЛЕНО из уже замороженной
# семантики, а не придумано:
#
#   1. `experiment.REGIMES["R0"]` — null: воздействие не меняет ничего;
#      для любого non-null режима контрольная пара получает `TrueEffect()`,
#      то есть ровно R0.
#   2. Контраст prereg записан как Y(C,T) − Y(C,K) при ОБЩЕМ C: c-реактивность
#      есть свойство популяции и присутствует в обеих руках.
#   3. В сетке этапа 1 отдельной оси control НЕТ: тринадцать строк — это R0
#      один раз плюс R1..R4 на три множителя. Единственный объект сетки,
#      соответствующий K, — R0 той же базовой популяции и той же точки C.
#
# Строка НЕ делает вид, что существовала всегда: это post-freeze completion,
# и оформлено оно отдельно.
CONTROL_ARM_WAS_UNSPECIFIED_IN_BASELINE = True
CONTROL_ARM_MAPPING = (
    "T = (rate, C, Ri, magnitude);  K = (rate, C, R0, 1.0). Совпадают: "
    "разрешение сбора, H, δ, длина окна, базовая популяция и точка "
    "c-реактивности. Для строки R0 T и K — одна и та же рука")


def control_arm_for(rate: float, c_rate: float, regime: str,
                    magnitude: float) -> tuple[float, float, str, float]:
    """Координаты контрольной руки K для данной T. Меняется ТОЛЬКО режим.

    Перескочить между ставками или точками c-реактивности нельзя: это были
    бы разные популяции, и разность перестала бы быть контрастом лечения.
    R0 отображается сам в себя — контраст тогда строится из одной пары
    границ и в общем случае НЕ равен [0, 0], потому что структурная ширина
    идентификации никуда не девается.
    """
    del regime, magnitude                      # K не зависит ни от того, ни от другого
    return (rate, c_rate, "R0", 1.0)


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Один конец одной ячейки на одном просмотре."""

    key: tuple                 # (delta, days, horizon, maximise)
    delta_fraction: float
    point: float
    low: float
    high: float
    radius: float
    status: PR.PrecisionStatus
    look: int | None


# ---------------------------------------------------------------------------
# R4: ИСПРАВЛЕНИЕ СЕМАНТИКИ, НЕ ОПТИМИЗАЦИЯ
# ---------------------------------------------------------------------------
#
# `s5b_stage1.effect` возвращает для R4 пару `(0.20, 0.87)`, то есть делает
# R4 ОБЫЧНОЙ ОДНОРОДНОЙ рукой. Замороженный `experiment.REGIMES["R4"]`
# говорит иное:
#
#     lambda rng: TrueEffect(latency_log_shift=2*LATENCY_SHIFT
#                            if rng.random() < 0.5 else 0.0)
#     mean_latency_shift = LATENCY_SHIFT,  heterogeneous = True
#
# То есть монетка НА ПАРУ: половина получает `0.8`, половина `0.0`, среднее
# `0.4`. Канала incidence у R4 НЕТ ВООБЩЕ — приписанный `ratio = 0.87`
# взялся ниоткуда. Похоже, «половина получает вдвое больше» было прочитано
# как «в среднем половина от R3»: ошибка и в структуре, и в числах.
#
# ПОЧЕМУ ИСПРАВЛЯЕТСЯ РЕАЛИЗАЦИЯ, А НЕ PREREG. Prereg здесь достаточно
# явен: «для R4 множитель применяется к БАЗОВОМУ эффекту ДО расщепления на
# половины, чтобы заявленная структура гетерогенности сохранилась». Менять
# нечего — расходится код.
#
# ИСТОЧНИК ИСТИНЫ — САМ `REGIMES`, А НЕ ПЕРЕПИСАННЫЕ ЧИСЛА. Транскрипция
# констант руками и породила это расхождение один раз; повторять приём,
# который уже подвёл, было бы странно.
R4_SEMANTICS_MISMATCH = (
    "s5b_stage1.effect даёт R4 = (0.20, 0.87) — однородная рука с половинным "
    "сдвигом и несуществующим каналом incidence. experiment.REGIMES['R4'] "
    "задаёт гетерогенность 50/50: половина периодов получает 2*LATENCY_SHIFT, "
    "половина ноль, при среднем LATENCY_SHIFT и ratio = 1.0. Исправляется "
    "РЕАЛИЗАЦИЯ; prereg не трогается")

#: Поток розыгрыша эффекта ОТДЕЛЁН от потока сообщений. Тип периода обязан
#: зависеть только от (tag, i) — иначе шард, порядок или размер куска
#: меняли бы, какая половина пар считается пролеченной, и гетерогенность
#: стала бы функцией расписания.
#:
#: ЭТО COMPLETION CHOICE, А НЕ СЛЕДСТВИЕ. `REGIMES["R4"]` задаёт монетку и
#: требует `rng`, но КАКОЙ именно поток её крутит, заморожено не было.
#: Схема `f"{tag}:effect:{i}"` выбрана здесь и здесь же объявлена: она даёт
#: независимый детерминированный подпоток, не зависящий от расписания. Из
#: исходного `REGIMES` она не вытекает, и изображать неизбежностью её не
#: нужно.
EFFECT_SUBSTREAM = "effect"
EFFECT_SUBSTREAM_IS_A_COMPLETION_CHOICE = True


def regime_effect(tag: str, index: int, regime: str,
                  magnitude: float) -> tuple[float, float]:
    """`(сдвиг, отношение)` ДЛЯ ОДНОГО ПЕРИОДА. Для R0-R3 не зависит от `i`.

    Множитель применяется к базовому эффекту; для R4 это тождественно
    «умножить базу и потом расщепить», потому что `2·(m·L) = m·(2·L)` —
    и это проверяется тестом, а не объявляется.
    """
    stream = random.Random(f"{tag}:{EFFECT_SUBSTREAM}:{index}")
    base = REGIMES[regime].effect(stream)
    return (base.latency_log_shift * magnitude,
            base.opportunity_rate_ratio ** magnitude)


def _params(rate: float, shift: float, ratio: float, c_rate: float,
            c_shift: float) -> DyadParameters:
    return DyadParameters(
        opportunity_rate_per_day=rate * ratio * c_rate,
        timestamp_resolution_seconds=1.0,
        latency_log_mean=DyadParameters().latency_log_mean + shift + c_shift)


def accumulate(tag: str, start: int, stop: int, *, rate: float,
               c_rate: float, c_shift: float, shift: float | None = None,
               ratio: float | None = None, regime: str | None = None,
               magnitude: float = 1.0, wanted=None,
               store: dict | None = None) -> dict[tuple, list]:
    """Периоды `start..stop-1` в общий склад. Дописывает, не пересоздаёт.

    Эффект задаётся ЛИБО парой `(shift, ratio)` — однородная рука, как
    считал восстановленный runner, — ЛИБО `regime`/`magnitude`, и тогда он
    разыгрывается ПОКАЗАТЕЛЬНО ПО ПЕРИОДАМ из отдельного потока. Для
    R0-R3 оба пути дают одно и то же; для R4 — намеренно разное.

    Порядок ключей и порядок периодов внутри ключа определяются ТОЛЬКО
    индексом `i`, поэтому склад, собранный по кускам, побитово совпадает со
    складом, собранным целиком.
    """
    if (regime is None) == (shift is None):
        raise ValueError("задать нужно РОВНО одно: regime или (shift, ratio)")
    if regime is None:
        def effect_for(_index, shift=shift, ratio=ratio):
            return shift, ratio
    else:
        def effect_for(index, regime=regime, magnitude=magnitude):
            return regime_effect(tag, index, regime, magnitude)

    wanted = None if wanted is None else frozenset(wanted)
    deltas = (P.ACQUISITION_RESOLUTIONS_SECONDS if wanted is None
              else tuple(d for d in P.ACQUISITION_RESOLUTIONS_SECONDS
                         if any(k[0] == d for k in wanted)))
    store = {} if store is None else store
    for index in range(start, stop):
        period_shift, period_ratio = effect_for(index)
        params = _params(rate, period_shift, period_ratio, c_rate, c_shift)
        messages = generate_dyad(random.Random(f"{tag}:{index}"), params,
                                 days=P.LONGEST_DURATION_DAYS)
        if not messages:
            continue
        stream = Stream(tuple(m.local_time for m in messages),
                        tuple(0 if m.actor == "partner" else 1 for m in messages),
                        tuple(m.message_id for m in messages))
        for delta in deltas:
            full = to_bins(stream, 1, delta=delta)
            for days in P.OBSERVATION_DAYS:
                window = days * DAY
                prefix = [b for b in full if b.start < window]
                if not prefix:
                    continue
                for horizon in P.HORIZONS_SECONDS:
                    cut = P.initiation_cutoff(window, horizon)
                    kw = dict(horizon=horizon, window_end=window, delta=delta,
                              time_layer=False, initiation_end=cut)
                    for maximise in (False, True):
                        if wanted is not None and (
                                delta, days, horizon, maximise) not in wanted:
                            continue
                        hull = hull_of(
                            achievable_frontier(prefix, maximise=maximise, **kw),
                            upper=maximise)
                        store.setdefault(
                            (delta, days, horizon, maximise), []).append(
                                tuple(Piece(float(n), b) for n, b in hull))
    return store


def roots_from(store: dict[tuple, list]) -> dict[tuple, float]:
    """Точки — ровно те же корни, что считал восстановленный runner."""
    out: dict[tuple, float] = {}
    for key, pieces in store.items():
        maximise = key[3]
        picked = max if maximise else min
        horizon = key[2]

        def total(lam: float, pieces=pieces, picked=picked) -> float:
            return sum(picked(p.b - lam * p.n for p in q) for q in pieces)

        if total(0.0) <= 0.0:
            out[key] = 0.0
            continue
        bracket = generalized_inverse(total, 0.0, horizon + 1e-9, tolerance=1e-4)
        out[key] = bracket.high if maximise else bracket.low
    return out


def endpoints_from(store: dict[tuple, list], *, look: int,
                   z: float = PR.Z_PER_COMPARISON
                   ) -> dict[tuple, Endpoint]:
    """Все концы склада на просмотре `look`, по одному на долю δ.

    δ есть доля ГОРИЗОНТА, поэтому один ключ порождает столько концов,
    сколько объявлено долей: цель по точности у них разная.
    """
    roots = roots_from(store)
    out: dict[tuple, Endpoint] = {}
    for key, pieces in store.items():
        horizon, maximise = key[2], key[3]
        components = acceptance_set(pieces, z=z, lo=0.0, hi=horizon,
                                    maximise=maximise)
        span = convex_hull_interval(components)
        low, high = span if span else (0.0, horizon)
        point = roots[key]
        radius = PR.radius(components, point)
        for fraction in P.DELTA_FRACTIONS_OF_HORIZON:
            delta = fraction * horizon
            precise = PR.is_precise(radius, delta, z=z)
            out[(key, fraction)] = Endpoint(
                key=key, delta_fraction=fraction, point=point,
                low=low, high=high, radius=radius,
                status=(PR.PrecisionStatus.ACHIEVED if precise
                        else PR.PrecisionStatus.INSUFFICIENT),
                look=look if precise else None)
    return out


def run_arm(tag: str, *, rate: float, c_rate: float, c_shift: float,
            shift: float | None = None, ratio: float | None = None,
            regime: str | None = None, magnitude: float = 1.0,
            ladder=PR.LOOKS,
            z: float = PR.Z_PER_COMPARISON) -> dict[tuple, Endpoint]:
    """Честная лестница. Останавливается, когда ВСЕ концы руки точны.

    Периоды общие для всех концов, поэтому рука идёт до максимума из их
    требований. Ни один горизонт не пропускается — см. `SKIPPED_HORIZONS`.
    """
    store: dict[tuple, list] = {}
    settled: dict[tuple, Endpoint] = {}
    drawn = 0
    for size in ladder:
        store = accumulate(tag, drawn, size, rate=rate, shift=shift,
                           ratio=ratio, regime=regime, magnitude=magnitude,
                           c_rate=c_rate, c_shift=c_shift, store=store)
        drawn = size
        current = endpoints_from(store, look=size, z=z)
        for name, endpoint in current.items():
            if name in settled:
                continue
            if endpoint.status is PR.PrecisionStatus.ACHIEVED:
                settled[name] = endpoint
        if len(settled) == len(current):
            break
    for name, endpoint in current.items():
        settled.setdefault(name, endpoint)
    return settled


# ---------------------------------------------------------------------------
# PROVENANCE: прогноз живёт ТОЛЬКО здесь и ни на что не влияет
# ---------------------------------------------------------------------------

def predicted_note(tag: str, key: tuple, fraction: float) -> str:
    """Диагностическая пометка пилота. Вердиктом не является.

    Возвращает строку для провенанса. Ни одна ветка управления её не
    читает: лестница исполняется независимо от того, что предсказал пилот.
    """
    return (f"{tag}|{key}|{fraction}: "
            f"{PR.PrecisionStatus.PREDICTED_INSUFFICIENT.value}")


def cell_is_evaluable(statuses) -> bool:
    """Ячейка оценима, только когда ТОЧНЫ ВСЕ ЧЕТЫРЕ конца.

    Четыре — это λ⁻ и λ⁺ у treated и control. Ни три, ни пять: длина
    проверяется отдельно, потому что `all([])` истинно, а пустая ячейка
    вердикта не заслуживает.
    """
    statuses = list(statuses)
    return (len(statuses) == 4
            and all(s is PR.PrecisionStatus.ACHIEVED for s in statuses))


def cell_status(statuses):
    """`None`, если ячейка оценима; иначе статус ПОВЕРХНОСТИ."""
    if cell_is_evaluable(statuses):
        return None
    return PR.NOT_EVALUATED_MC_PRECISION


# ---------------------------------------------------------------------------
# КОНТРАСТ ЯЧЕЙКИ
# ---------------------------------------------------------------------------
#
# СОВМЕСТНОСТЬ УЖЕ КУПЛЕНА, отдельного пробела здесь нет. Чтобы разность
# множеств была корректна, четыре исходных обязаны быть корректны
# ОДНОВРЕМЕННО; поконцевой гарантии для этого мало. Редакция 4 строит
# каждое множество на `1 − α/12`, где `12 = 4 конца × 3 просмотра`, откуда
#
#     на конец   P(tau < inf, промах) <= 3·α/12 = α/4
#     на ячейку  P(F_cell)            <= 4·α/4  = α
#
# по союзной границе, которой независимость безразлична. Это в точности
# B-13 амендмента, и он не только выведен, но и ИЗМЕРЕН: сценарий
# `cell_four_endpoints` мерил ровно клеточное событие (185/24000 = 0.0077
# при δ = 36, гейт принят).
SIMULTANEOUS_COVERAGE_INVARIANT = (
    "B-13: каждое множество строится на 1 − α/12 (4 конца x 3 просмотра), "
    "поэтому на конец P(ложная сертификация) <= α/4, а союзная граница по "
    "четырём концам даёт P(F_cell) <= α. Независимость не требуется")

#: КАЖДЫЙ КОНЕЦ БЕРЁТСЯ НА СВОЁМ `tau`. Если T сошёлся на 16000, а K лишь
#: на 64000, T остаётся на 16000: `A_16000(T)` и ЕСТЬ результат процедуры
#: для T. Подменить его на `A_64000(T)` значит вернуть множество, которого
#: процедура не возвращала и чьё покрытие не квалифицировано.
EACH_ENDPOINT_AT_ITS_OWN_TAU = True


def cell_contrast(treated_low: Endpoint, treated_high: Endpoint,
                  control_low: Endpoint, control_high: Endpoint
                  ) -> tuple[float, float]:
    """`[inf A(λ⁻_T) − sup A(λ⁺_K),  sup A(λ⁺_T) − inf A(λ⁻_K)]`.

    Берутся ОБОЛОЧКИ множеств принятия: несвязное множество сужать до
    компоненты нельзя, а оболочка только расширяет, поэтому покрытие не
    падает. Каждый конец — на своём `tau`.

    Отказ, если ячейка не оценима: контраст из неточного конца — это число
    без гарантии, и выглядит оно ровно как число с гарантией.
    """
    four = (treated_low, treated_high, control_low, control_high)
    if not cell_is_evaluable([e.status for e in four]):
        raise ValueError(PR.NOT_EVALUATED_MC_PRECISION)
    for endpoint, want in zip(four, (False, True, False, True)):
        if endpoint.key[3] is not want:
            raise ValueError(f"направление конца не то: {endpoint.key}")
    return (treated_low.low - control_high.high,
            treated_high.high - control_low.low)
