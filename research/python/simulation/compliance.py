"""Адверсариальная проверка ITT против per-protocol на ИЗВЕСТНЫХ potential outcomes.

Генератор здесь не участвует вовсе, и это главное. Прошлая попытка крутила
параметры процесса в надежде, что per-protocol наконец испортится, и получила
|t| = 0.70 — то есть доказала только, что избирательность была слишком слабой.
Правильная проверка строит смещение ПО КОНСТРУКЦИИ:

    Y0_i                     исход без воздействия
    tau_i                    индивидуальный эффект
    Y1_i = Y0_i + tau_i      исход при воздействии
        ↓
    случайное назначение Z
        ↓
    комплаенс, ДЕТЕРМИНИРОВАННО связанный с tau_i
    при фиксированной общей доле соблюдения
        ↓
    ITT              оценивает эффект НАЗНАЧЕНИЯ
    per-protocol     оценивает эффект в ОТОБРАННОЙ подгруппе

`tau_i` симметричен вокруг нуля, поэтому истинный средний эффект по популяции
равен нулю во всех трёх режимах. Это и делает проверку чистой: любой знак у
per-protocol порождён исключительно тем, КТО согласился, а не величиной
эффекта.

Две зеркальные конструкции при одинаковой доле соблюдения:

    SELECT_HIGH   соблюдают те, кому воздействие помогает  → PP выше ITT
    SELECT_LOW    соблюдают те, кому оно вредит            → PP ниже ITT
    RANDOM        соблюдают случайные                      → расхождения нет

Зеркальность важнее любого одного знака: она отделяет **избирательность** от
разбавления и от случайной разницы в реализованной доле соблюдения.

Формулировка результата держится узкой. Показывается, что анализ ОТЛИЧАЕТ
эффект назначения от per-protocol оценки, когда соблюдение избирательно связано
с откликом. Не показывается, что «per-protocol всегда смещён» — это было бы
слишком широко.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from enum import Enum

from extractor.model import HorizonAggregate, LengthSummary, PeriodAggregate

from .experiment import PRIMARY, Assignment, analyse
from .interval import student_t_quantile

HORIZON_HOURS = 24.0
WINDOW_SECONDS = 14 * 24 * 3600.0


@dataclass(frozen=True, slots=True)
class PotentialOutcomes:
    """`Y0` и `tau` на участника. Оба известны, потому что мы их положили."""

    baseline: tuple[float, ...]
    effect: tuple[float, ...]

    @property
    def n(self) -> int:
        return len(self.baseline)

    @property
    def ate(self) -> float:
        """Истинный средний эффект по ПОПУЛЯЦИИ, а не по соблюдающим."""
        return statistics.fmean(self.effect)

    def observed(self, treated: bool, index: int) -> float:
        value = self.baseline[index] + (self.effect[index] if treated else 0.0)
        return max(0.0, value)


def draw_potential_outcomes(
    n: int,
    seed: int,
    *,
    baseline_mean: float = 1800.0,
    baseline_sd: float = 600.0,
    effect_mean: float = 0.0,
    effect_sd: float = 900.0,
) -> PotentialOutcomes:
    """`effect_mean = 0` по умолчанию: истинный эффект нулевой, знак у PP берётся
    только из отбора соблюдающих."""
    rng = random.Random(f"{seed}:potential")
    return PotentialOutcomes(
        baseline=tuple(rng.gauss(baseline_mean, baseline_sd) for _ in range(n)),
        effect=tuple(rng.gauss(effect_mean, effect_sd) for _ in range(n)),
    )


class ComplianceRule(Enum):
    RANDOM = "random"
    SELECT_HIGH = "select_high"
    SELECT_LOW = "select_low"


def _compliers(outcomes, assigned, rule, rate, rng) -> set[int]:
    pool = [i for i, z in enumerate(assigned) if z]
    take = round(len(pool) * rate)
    if rule is ComplianceRule.RANDOM:
        return set(rng.sample(pool, take))
    ordered = sorted(pool, key=lambda i: outcomes.effect[i],
                     reverse=rule is ComplianceRule.SELECT_HIGH)
    return set(ordered[:take])


def _cell(value: float) -> PeriodAggregate:
    """Одна возможность, вся тяжесть в ней: `rmtr = burden / N = value`.

    Анализ прогоняется НАСТОЯЩИЙ (`experiment.analyse`), а не переписанный для
    теста: квалифицируется тот код, который поедет в поле.
    """
    return PeriodAggregate(
        participant_id="p", period_id="w",
        horizons=(HorizonAggregate(horizon_hours=HORIZON_HOURS,
                                   opportunities_eligible=1,
                                   sum_min_latency_seconds=value,
                                   replied_within=1),),
        own_messages=LengthSummary(count=0, total_chars=0),
        own_episode_returns=0, cross_actor_tie_groups=0,
        ambiguous_opportunities=0, observation_window_seconds=WINDOW_SECONDS)


def compliance_trial(
    outcomes: PotentialOutcomes,
    seed: int,
    *,
    rule: ComplianceRule,
    compliance_rate: float,
    treated_share: float = 0.5,
) -> tuple[Assignment, list[PeriodAggregate]]:
    rng = random.Random(f"{seed}:{rule.value}:trial")
    assigned = [rng.random() < treated_share for _ in range(outcomes.n)]
    compliers = _compliers(outcomes, assigned, rule, compliance_rate, rng)
    received = [i in compliers for i in range(outcomes.n)]
    cells = [_cell(outcomes.observed(received[i], i)) for i in range(outcomes.n)]
    return Assignment(tuple(assigned), tuple(received)), cells


@dataclass(frozen=True, slots=True)
class ComplianceCheck:
    rule: ComplianceRule
    trials: int
    true_ate: float
    mean_itt: float
    mean_pp: float
    mean_gap: float
    se_gap: float
    mean_compliance: float

    @property
    def t_gap(self) -> float:
        return abs(self.mean_gap) / self.se_gap if self.se_gap > 0 else math.inf

    @property
    def expected_sign(self) -> int:
        return {ComplianceRule.SELECT_HIGH: 1,
                ComplianceRule.SELECT_LOW: -1,
                ComplianceRule.RANDOM: 0}[self.rule]

    @property
    def passes(self) -> bool:
        """Знак, а не величина. Конкретное значение PP не пинуется намеренно —
        оно зависит от параметров конструкции, а проверяется направление."""
        if self.expected_sign == 0:
            return self.t_gap < 3.0
        return self.t_gap > 3.0 and math.copysign(1, self.mean_gap) == self.expected_sign


def run_compliance_check(
    rule: ComplianceRule,
    *,
    participants: int = 400,
    trials: int = 40,
    compliance_rate: float = 0.5,
    base_seed: int = 770_000,
    effect_sd: float = 900.0,
) -> ComplianceCheck:
    itt_values, pp_values, gaps, rates = [], [], [], []
    true_ate = []
    for t in range(trials):
        outcomes = draw_potential_outcomes(participants, base_seed + t,
                                           effect_sd=effect_sd)
        assignment, cells = compliance_trial(outcomes, base_seed + t, rule=rule,
                                             compliance_rate=compliance_rate)
        itt = analyse(assignment, cells, estimand=PRIMARY,
                      horizon_hours=HORIZON_HOURS, delta=0.0)
        pp = analyse(assignment, cells, estimand=PRIMARY,
                     horizon_hours=HORIZON_HOURS, delta=0.0, by_receipt=True)
        if itt.difference is None or pp.difference is None:
            continue
        itt_values.append(itt.difference)
        pp_values.append(pp.difference)
        gaps.append(pp.difference - itt.difference)
        rates.append(assignment.compliance_rate)
        true_ate.append(outcomes.ate)
    return ComplianceCheck(
        rule=rule,
        trials=len(gaps),
        true_ate=statistics.fmean(true_ate),
        mean_itt=statistics.fmean(itt_values),
        mean_pp=statistics.fmean(pp_values),
        mean_gap=statistics.fmean(gaps),
        se_gap=statistics.stdev(gaps) / math.sqrt(len(gaps)),
        mean_compliance=statistics.fmean(rates),
    )
