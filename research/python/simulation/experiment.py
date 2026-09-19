"""S5a: прогон эксперимента K0 целиком по замороженному генератору.

Вопрос ровно один: **работает ли наш эксперимент, если мир устроен так, как мы
ему сказали?** Не «устроен ли мир именно так» — генератор заморожен и
некалиброван, откалиброванных параметров 0 из 8.

Поэтому здесь НЕТ и не будет: выбора pilot N, назначения `δ`, оценки
реалистичной мощности, предсказания исхода пилота. Это S5b, и после
S4-closure он PARTIALLY_UNBLOCKED: оператор огрубления и поведение
наблюдателя калибруемы, АБСОЛЮТНАЯ incidence — нет. Список запрещённых после S5 предложений — в prereg §2.

Анализ отделён от симуляции намеренно: проверяется именно АНАЛИЗ, а порождение
данных служит ему стендом. Всё, что анализ знает о мире, приходит к нему через
`PeriodAggregate`, как и в поле.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from extractor.extract import extract
from extractor.model import HorizonAggregate, Mode, PeriodAggregate

from .interval import student_t_quantile
from .process import DAY, PARTICIPANT, Population, TrueEffect, generate_dyad

#: Ячеечные величины: те, у которых есть распределение ПО person-period и к
#: которым поэтому применим двухвыборочный интервал.
#:
#: `opportunity_weighted_rmtr` сюда не входит и не должен: это отношение сумм,
#: у него нет ячеечного распределения. Его роль алгебраическая — точный
#: множитель длительности в разложении `B = N x R`. Роли не сливать.
CELL_VALUES: dict[str, Callable[[HorizonAggregate], float | None]] = {
    "person_period_rmtr": lambda c: c.rmtr_seconds,
    "mean_burden": lambda c: c.reentry_burden_seconds,
    "mean_incidence": lambda c: float(c.opportunities_eligible),
}

#: Первичный инференциальный эстиманд, выбранный РАНЬШЕ и по содержательным
#: причинам: одна единица рандомизации — один голос. S5 этого выбора не делает.
#: ИСТОРИЧЕСКИЙ ПЕРВИЧНЫЙ АНАЛИЗ S5a, и он здесь НЕ МЕНЯЕТСЯ: файл описывает
#: то, что было сделано и квалифицировано. Первичный эстиманд S5b — другой
#: (opportunity-weighted ΣB/ΣN), см. `simulation/s5b_prereg.py` §4.0, и
#: квалификацию он получает отдельно, через S5a-RATIO (§4b). Унаследовать
#: сертификат S5a он НЕ МОЖЕТ.
PRIMARY = "person_period_rmtr"


# --------------------------------------------------------------------------
# Режимы: для идентификации поведения анализа, не ради реализма
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Regime:
    name: str
    description: str
    #: эффект для одной пары; `rng` нужен только гетерогенному режиму
    effect: Callable[[random.Random], TrueEffect]
    #: средний приложенный сдвиг логарифма латентности — для отчёта, не для вывода
    mean_latency_shift: float = 0.0
    heterogeneous: bool = False


LATENCY_SHIFT = 0.4
RATE_RATIO = 0.75


def _null(_: random.Random) -> TrueEffect:
    return TrueEffect()


REGIMES: dict[str, Regime] = {
    "R0": Regime("R0", "null — воздействие не меняет ничего", _null),
    "R1": Regime(
        "R1",
        "latency-only — воздействие приложено ТОЛЬКО к каналу латентности. "
        "Incidence всё равно сдвинется эмерджентно, через слияние серий (S3a)",
        lambda _: TrueEffect(latency_log_shift=LATENCY_SHIFT),
        mean_latency_shift=LATENCY_SHIFT,
    ),
    "R2": Regime(
        "R2",
        "incidence-only — порождение возможностей, латентность не тронута",
        lambda _: TrueEffect(opportunity_rate_ratio=RATE_RATIO),
    ),
    "R3": Regime(
        "R3",
        "mixed — латентность и incidence одновременно",
        lambda _: TrueEffect(latency_log_shift=LATENCY_SHIFT,
                             opportunity_rate_ratio=RATE_RATIO),
        mean_latency_shift=LATENCY_SHIFT,
    ),
    "R4": Regime(
        "R4",
        "heterogeneous — ТОТ ЖЕ средний ITT, но эффект у пар разный: половина "
        "получает вдвое больше, половина не получает ничего",
        lambda rng: TrueEffect(latency_log_shift=2 * LATENCY_SHIFT
                               if rng.random() < 0.5 else 0.0),
        mean_latency_shift=LATENCY_SHIFT,
        heterogeneous=True,
    ),
}


# --------------------------------------------------------------------------
# Рандомизация и комплаенс
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Assignment:
    """Кому что назначено и кто что получил. Различие — это и есть ITT."""

    assigned_treated: tuple[bool, ...]
    received_treated: tuple[bool, ...]

    @property
    def n(self) -> int:
        return len(self.assigned_treated)

    @property
    def compliance_rate(self) -> float:
        assigned = [r for a, r in zip(self.assigned_treated, self.received_treated) if a]
        return sum(assigned) / len(assigned) if assigned else 1.0


def randomise(
    n: int,
    seed: int,
    *,
    treated_share: float = 0.5,
    compliance: float = 1.0,
    selective: bool = False,
    population: Population | None = None,
) -> Assignment:
    """Назначение рук и, отдельно, фактическое получение воздействия.

    `selective=True` делает несоблюдение ЗАВИСИМЫМ от самой пары: реже
    соблюдают те, у кого латентность и так велика. Это не украшение — именно на
    таком несоблюдении per-protocol смещается, а ITT нет, и только так проверка
    ITT что-то проверяет.
    """
    rng = random.Random(f"{seed}:assign")
    assigned = [rng.random() < treated_share for _ in range(n)]
    received = []
    pop = population or Population()
    for index, treat in enumerate(assigned):
        if not treat:
            received.append(False)
            continue
        probability = compliance
        if selective:
            drawn = pop.draw(random.Random(f"{seed}:{index}:params"))
            slow = drawn.latency_log_mean > pop.base.latency_log_mean
            probability = compliance * (0.5 if slow else 1.0)
        received.append(rng.random() < probability)
    return Assignment(tuple(assigned), tuple(received))


# --------------------------------------------------------------------------
# Один прогон эксперимента
# --------------------------------------------------------------------------

def run_trial(
    regime: Regime,
    seed: int,
    *,
    dyads: int,
    days: float,
    population: Population | None = None,
    treated_share: float = 0.5,
    compliance: float = 1.0,
    selective: bool = False,
    missing_share: float = 0.0,
) -> tuple[Assignment, list[PeriodAggregate]]:
    """Каждая пара живёт ОДИН раз, в своей руке. Это эксперимент, не контраст.

    `missing_share` выбрасывает person-period целиком — так выглядит человек,
    не приславший экспорт за период. Выбрасывается СЛУЧАЙНО и независимо от
    руки: зависимое от руки выбывание — отдельный вопрос, и подменять одно
    другим нельзя.
    """
    pop = population or Population()
    assignment = randomise(dyads, seed, treated_share=treated_share,
                           compliance=compliance, selective=selective,
                           population=pop)
    effect_rng = random.Random(f"{seed}:effects")
    drop_rng = random.Random(f"{seed}:missing")
    window = days * DAY
    aggregates: list[PeriodAggregate] = []
    for index, received in enumerate(assignment.received_treated):
        if drop_rng.random() < missing_share:
            aggregates.append(None)          # место сохраняется, данных нет
            continue
        effect = regime.effect(effect_rng) if received else TrueEffect()
        params = effect.apply(pop.draw(random.Random(f"{seed}:{index}:params")))
        trace = generate_dyad(random.Random(f"{seed}:{index}:stream"), params, days=days)
        aggregates.append(extract(trace, participant=PARTICIPANT,
                                  period_id=f"d{index:05d}", period_start=0.0,
                                  period_end=window, mode=Mode.PRODUCTION).aggregate)
    return assignment, aggregates


# --------------------------------------------------------------------------
# Анализ: двухвыборочное сравнение по назначению (ITT)
# --------------------------------------------------------------------------

class Decision(Enum):
    #: интервал ЦЕЛИКОМ вне области эквивалентности
    REACTIVITY_SIGNAL = "reactivity_signal"
    #: интервал ЦЕЛИКОМ внутри [-delta, +delta]
    PRACTICALLY_NEGLIGIBLE = "practically_negligible"
    #: всё остальное, включая «эстиманд не существует»
    INCONCLUSIVE = "inconclusive"


def decide(low: float | None, high: float | None, delta: float) -> Decision:
    """Три исхода, и третий обязателен. Чистая функция, пять чисел.

    Ноль исключается автоматически, когда интервал целиком вне `[-delta, delta]`,
    поэтому отдельной проверки на ноль нет: она была бы слабее.

    Отсутствующий интервал — INCONCLUSIVE, а не «нет эффекта». Отсутствие не
    становится свидетельством.
    """
    if low is None or high is None or delta < 0:
        return Decision.INCONCLUSIVE
    if low > delta or high < -delta:
        return Decision.REACTIVITY_SIGNAL
    if -delta <= low and high <= delta:
        return Decision.PRACTICALLY_NEGLIGIBLE
    return Decision.INCONCLUSIVE


@dataclass(frozen=True, slots=True)
class ArmSummary:
    label: str
    cells_assigned: int
    cells_missing: int
    cells_contributing: int
    cells_zero_incidence: int
    mean: float | None
    sd: float | None


@dataclass(frozen=True, slots=True)
class TrialResult:
    estimand: str
    horizon_hours: float
    treated: ArmSummary
    control: ArmSummary
    difference: float | None
    se: float | None
    df: float | None
    low: float | None
    high: float | None
    delta: float
    decision: Decision
    analysis: str

    @property
    def estimable(self) -> bool:
        return self.difference is not None


def _arm(label, values, assigned, missing, zero) -> ArmSummary:
    return ArmSummary(
        label=label,
        cells_assigned=assigned,
        cells_missing=missing,
        cells_contributing=len(values),
        cells_zero_incidence=zero,
        mean=statistics.fmean(values) if values else None,
        sd=statistics.stdev(values) if len(values) >= 2 else None,
    )


def analyse(
    assignment: Assignment,
    aggregates: Sequence[PeriodAggregate | None],
    *,
    estimand: str = PRIMARY,
    horizon_hours: float = 24.0,
    delta: float,
    confidence: float = 0.95,
    by_receipt: bool = False,
) -> TrialResult:
    """Уэлч по ячейкам, интервал Стьюдента, гейт эквивалентности.

    `by_receipt=False` — ITT, анализ КАК РАНДОМИЗОВАНО. `by_receipt=True` —
    per-protocol, и он здесь существует не как альтернатива, а как то, что
    обязано СМЕСТИТЬСЯ при избирательном несоблюдении. Если не смещается,
    проверка ITT ничего не проверила.
    """
    value_of = CELL_VALUES[estimand]
    groups: dict[bool, list[float]] = {True: [], False: []}
    counts = {True: [0, 0, 0], False: [0, 0, 0]}   # assigned, missing, zero-incidence
    arms = assignment.received_treated if by_receipt else assignment.assigned_treated
    for in_treatment, aggregate in zip(arms, aggregates):
        counts[in_treatment][0] += 1
        if aggregate is None:
            counts[in_treatment][1] += 1
            continue
        cell = aggregate.horizon(horizon_hours)
        if cell.opportunities_eligible == 0:
            counts[in_treatment][2] += 1
        value = value_of(cell)
        if value is not None:
            groups[in_treatment].append(float(value))

    treated = _arm("treated", groups[True], *counts[True])
    control = _arm("control", groups[False], *counts[False])
    difference = se = df = low = high = None
    if (treated.sd is not None and control.sd is not None
            and treated.mean is not None and control.mean is not None):
        n_t, n_c = treated.cells_contributing, control.cells_contributing
        var_t, var_c = treated.sd ** 2 / n_t, control.sd ** 2 / n_c
        difference = treated.mean - control.mean
        se = math.sqrt(var_t + var_c)
        denominator = var_t ** 2 / (n_t - 1) + var_c ** 2 / (n_c - 1)
        df = (var_t + var_c) ** 2 / denominator if denominator > 0 else min(n_t, n_c) - 1
        half = student_t_quantile(0.5 + confidence / 2.0, df) * se
        low, high = difference - half, difference + half

    return TrialResult(
        estimand=estimand,
        horizon_hours=horizon_hours,
        treated=treated,
        control=control,
        difference=difference,
        se=se,
        df=df,
        low=low,
        high=high,
        delta=delta,
        decision=decide(low, high, delta),
        analysis="per-protocol" if by_receipt else "ITT",
    )


# --------------------------------------------------------------------------
# Операционные характеристики: как часто какое решение
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class OperatingCharacteristics:
    regime: str
    estimand: str
    delta: float
    trials: int
    counts: dict[Decision, int] = field(default_factory=dict)
    mean_difference: float | None = None
    mean_half_width: float | None = None

    def share(self, decision: Decision) -> float:
        return self.counts.get(decision, 0) / self.trials if self.trials else 0.0


def operating_characteristics(
    regime: Regime,
    *,
    trials: int,
    dyads: int,
    days: float,
    delta: float,
    estimand: str = PRIMARY,
    horizon_hours: float = 24.0,
    base_seed: int = 500_000,
    **trial_kwargs,
) -> OperatingCharacteristics:
    counts: dict[Decision, int] = {}
    differences, widths = [], []
    for t in range(trials):
        assignment, aggregates = run_trial(regime, base_seed + t, dyads=dyads,
                                           days=days, **trial_kwargs)
        result = analyse(assignment, aggregates, estimand=estimand,
                         horizon_hours=horizon_hours, delta=delta)
        counts[result.decision] = counts.get(result.decision, 0) + 1
        if result.difference is not None:
            differences.append(result.difference)
            widths.append(result.high - result.difference)
    return OperatingCharacteristics(
        regime=regime.name,
        estimand=estimand,
        delta=delta,
        trials=trials,
        counts=counts,
        mean_difference=statistics.fmean(differences) if differences else None,
        mean_half_width=statistics.fmean(widths) if widths else None,
    )
