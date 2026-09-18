"""Положили эффект рукой — вернул ли его анализ?

Пайплайн целиком, ни одной строкой замороженного экстрактора не шевеля:

    TrueEffect  ->  generate_arm  ->  extract (FROZEN)  ->  estimands  ->  contrast

Здесь есть ровно одна вещь, которой не будет ни в одном настоящем
эксперименте: известный ответ. Поэтому и вердиктов здесь на один больше.

    В настоящем эксперименте потолок честности — три исхода:
        signal / practically negligible / INCONCLUSIVE.
    На симуляции добавляется четвёртый, MISMATCH: доверительный интервал
    контраста НЕ накрывает то, что мы положили. В поле такой исход недоступен
    в принципе — не с чем сравнивать. Это и есть единственная причина, по
    которой собственный генератор важнее любого правдоподобного чужого лога:
    чужой лог умеет опровергнуть падение, но не умеет опровергнуть смещение.

Два режима спаривания рук — это два разных вопроса, и путать их дорого:

    paired=True    пара i в обеих руках имеет одни параметры и один поток шума.
                   Отвечает: «возвращает ли анализ положенное?» Дисперсия
                   контраста здесь искусственно занижена — для мощности она
                   ЛОЖЬ, и функция мощности этого режима не принимает.
    paired=False   руки независимы, как при настоящей рандомизации. Только
                   отсюда берутся SD контраста и мощность.

`planted` — не параметр генератора. `latency_log_shift = +0.2` не измеряется в
секундах и не равен сдвигу ни одного эстиманда. Истина на уровне эстиманда
считается отдельно: большой референсной симуляцией обеих рук. У неё своя
монте-карловская погрешность, и она входит в сравнение, а не замалчивается.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from extractor import estimands as es
from extractor.extract import extract
from extractor.model import Mode, PeriodAggregate

from .interval import half_width, student_t_quantile
from .process import DAY, PARTICIPANT, Population, TrueEffect, generate_arm

#: Имена короче, чем у функций, потому что попадают в таблицы вердиктов.
ESTIMANDS: dict[str, Callable[[Sequence[PeriodAggregate], float], es.Estimate]] = {
    "mean_burden": es.mean_burden,
    "mean_incidence": es.mean_incidence,
    "person_period_rmtr": es.person_period_weighted_rmtr,
    "opportunity_rmtr": es.opportunity_weighted_rmtr,
}


# --------------------------------------------------------------------------
# Прогон одной руки через ЗАМОРОЖЕННЫЙ экстрактор
# --------------------------------------------------------------------------

def run_arm(
    seed: int,
    population: Population,
    effect: TrueEffect,
    *,
    dyads: int,
    days: float,
    label: str = "",
) -> list[PeriodAggregate]:
    """Трассы -> `PeriodAggregate`, по одному person-period на пару.

    `Mode.PRODUCTION`, а не QUALIFICATION: симуляция должна ехать по той же
    дороге, что и поле. Под PRODUCTION пер-возможностная трасса не просто
    прячется — она не строится, и если бы восстановление зависело от неё, мы бы
    узнали об этом здесь, а не на живых людях.
    """
    window = days * DAY
    out = []
    for index, trace in enumerate(generate_arm(
        seed, population, effect, dyads=dyads, days=days, label=label,
    )):
        result = extract(
            trace,
            participant=PARTICIPANT,
            period_id=f"{label or '-'}{index:05d}",
            period_start=0.0,
            period_end=window,
            mode=Mode.PRODUCTION,
        )
        out.append(result.aggregate)
    return out


# --------------------------------------------------------------------------
# Повторы: значение эстиманда и его разброс
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Replicates:
    """Значения одной величины по независимым повторам.

    `undefined` — повторы, где эстиманд не существует (все ячейки с N = 0).
    Он считается отдельно и НЕ подменяется нулём: «не определено» и «ноль» —
    разные вещи, и первое, подставленное вторым, тянет среднее вниз ровно там,
    где эффект и должен был бы его тянуть.
    """

    estimand: str
    horizon_hours: float
    values: tuple[float, ...]
    undefined: int

    @property
    def n(self) -> int:
        return len(self.values)

    @property
    def mean(self) -> float | None:
        return statistics.fmean(self.values) if self.values else None

    @property
    def sd(self) -> float | None:
        return statistics.stdev(self.values) if self.n >= 2 else None

    @property
    def se(self) -> float | None:
        sd = self.sd
        return sd / math.sqrt(self.n) if sd is not None else None


def _replicate_values(
    arms: Sequence[Sequence[PeriodAggregate]],
    estimand: str,
    horizon_hours: float,
) -> Replicates:
    fn = ESTIMANDS[estimand]
    values, undefined = [], 0
    for aggregates in arms:
        value = fn(aggregates, horizon_hours).value
        if value is None:
            undefined += 1
        else:
            values.append(float(value))
    return Replicates(estimand, horizon_hours, tuple(values), undefined)


def levels(
    population: Population,
    effect: TrueEffect,
    *,
    dyads: int,
    days: float,
    replicates: int,
    base_seed: int,
    horizon_hours: float,
    label: str = "ref",
) -> dict[str, Replicates]:
    """Абсолютные значения эстимандов в ОДНОЙ руке — для отчёта, не для вердикта.

    Вердикт строится на контрасте, а не на разности двух независимо посчитанных
    уровней: разность двух шумных средних наследует оба шума целиком, и на ней
    эталон выходит менее точным, чем измерение, которое он должен судить.
    Ровно это и случилось при первом прогоне — эталон из 600 пар оказался вдвое
    шире спаренного контраста из 40.
    """
    arms = [
        run_arm(base_seed + r, population, effect, dyads=dyads, days=days, label=label)
        for r in range(replicates)
    ]
    return {name: _replicate_values(arms, name, horizon_hours) for name in ESTIMANDS}


# --------------------------------------------------------------------------
# Контраст рук
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Contrast:
    """Разность рук по повторам: точка, разброс и сколько повторов выпало."""

    estimand: str
    horizon_hours: float
    differences: tuple[float, ...]
    undefined: int
    paired: bool

    @property
    def n(self) -> int:
        return len(self.differences)

    @property
    def mean(self) -> float | None:
        return statistics.fmean(self.differences) if self.differences else None

    @property
    def sd(self) -> float | None:
        return statistics.stdev(self.differences) if self.n >= 2 else None

    @property
    def se(self) -> float | None:
        sd = self.sd
        return sd / math.sqrt(self.n) if sd is not None else None


def contrast(
    population: Population,
    treatment: TrueEffect,
    control: TrueEffect = TrueEffect(),
    *,
    dyads: int,
    days: float,
    replicates: int,
    base_seed: int,
    horizon_hours: float,
    paired: bool,
) -> dict[str, Contrast]:
    """Контраст treatment - control по `replicates` независимым повторам.

    При `paired=True` обе руки получают один `label`, то есть пара i в них —
    одна и та же пара с одним и тем же шумом. При нулевом эффекте руки тогда
    совпадают побитово и каждая разность равна ровно нулю; это не курьёз, а
    самая дешёвая проверка того, что спаривание действительно спаривает.
    """
    left = "" if paired else "T"
    right = "" if paired else "C"
    out: dict[str, Contrast] = {}
    per_estimand: dict[str, list[float]] = {name: [] for name in ESTIMANDS}
    undefined: dict[str, int] = {name: 0 for name in ESTIMANDS}
    for r in range(replicates):
        seed = base_seed + r
        treated = run_arm(seed, population, treatment, dyads=dyads, days=days, label=left)
        untreated = run_arm(seed, population, control, dyads=dyads, days=days, label=right)
        for name, fn in ESTIMANDS.items():
            a = fn(treated, horizon_hours).value
            b = fn(untreated, horizon_hours).value
            if a is None or b is None:
                undefined[name] += 1
            else:
                per_estimand[name].append(float(a) - float(b))
    for name in ESTIMANDS:
        out[name] = Contrast(
            estimand=name,
            horizon_hours=horizon_hours,
            differences=tuple(per_estimand[name]),
            undefined=undefined[name],
            paired=paired,
        )
    return out


def planted_truth(
    population: Population,
    treatment: TrueEffect,
    control: TrueEffect = TrueEffect(),
    *,
    dyads: int,
    days: float,
    replicates: int,
    base_seed: int,
    horizon_hours: float,
) -> dict[str, Contrast]:
    """Истина НА УРОВНЕ ЭСТИМАНДА: тот же контраст, но при большом N.

    Отдельное имя, потому что роль другая. `contrast` — это измерение, которое
    судят; `planted_truth` — то, чем судят. Арифметика одна и та же, и это не
    недосмотр: эталон обязан считаться ровно тем кодом, что и измерение, иначе
    расхождение будет сообщать о разнице реализаций, а не о смещении.

    Всегда спаренный. Спаривание не сдвигает матожидание контраста, оно только
    убирает межпарную гетерогенность из его дисперсии, а она здесь доминирует.
    `base_seed` берут ЗАВЕДОМО другой, чем у измерения: эталон, посчитанный на
    тех же парах, что и пилот, согласуется с ним по построению и потому не
    проверяет ничего.
    """
    return contrast(
        population, treatment, control,
        dyads=dyads, days=days, replicates=replicates,
        base_seed=base_seed, horizon_hours=horizon_hours, paired=True,
    )


# --------------------------------------------------------------------------
# Вердикт: чистая функция, никакой симуляции внутри
# --------------------------------------------------------------------------

class Verdict(Enum):
    #: интервал исключает ноль И накрывает положенное
    RECOVERED = "recovered"
    #: интервал целиком внутри [-delta, +delta]: практически нулевой, как и клали
    ABSENT = "absent"
    #: интервал НЕ накрывает положенное — в поле такой исход недоступен
    MISMATCH = "mismatch"
    #: ни ноль не исключён, ни в delta не поместились
    INCONCLUSIVE = "inconclusive"
    #: эстиманда не существует
    NOT_ESTIMATED = "not_estimated"


def classify(
    *,
    observed: float | None,
    planted: float | None,
    half_width: float,
    agreement_half_width: float,
    delta: float,
) -> Verdict:
    """Пять скаляров -> вердикт. Симуляции здесь нет намеренно.

    `half_width` — полуширина интервала самого контраста (z * se): отвечает на
    вопрос «отличается ли от нуля». `agreement_half_width` — та же полуширина,
    но с добавленной монте-карловской ошибкой референса: отвечает на вопрос
    «то ли это, что клали». Второй всегда шире первого, и подменять его первым
    значит объявлять MISMATCH там, где неточен наш собственный эталон.

    Порядок проверок не переставляется. MISMATCH идёт ПЕРВЫМ: интервал, который
    исключает ноль, но не накрывает истину, — это не находка, это найденное не
    то. Объявить его RECOVERED потому, что знак совпал, — ровно та ошибка,
    ради поимки которой вся симуляция и существует.

    Оговорка, которая обязана звучать вслух: при 95% один MISMATCH из двадцати
    честных прогонов — это сам доверительный интервал, а не дефект. Одиночный
    MISMATCH — повод перезапустить с другим seed и увеличенным референсом, и
    только воспроизведённый называется дефектом.
    """
    if observed is None or planted is None:
        return Verdict.NOT_ESTIMATED
    if abs(observed - planted) > agreement_half_width:
        return Verdict.MISMATCH
    if abs(observed) > half_width:
        return Verdict.RECOVERED
    if abs(observed) + half_width <= delta:
        return Verdict.ABSENT
    return Verdict.INCONCLUSIVE


@dataclass(frozen=True, slots=True)
class RecoveryCheck:
    estimand: str
    horizon_hours: float
    planted: float | None
    planted_se: float | None
    observed: float | None
    observed_se: float | None
    delta: float
    confidence: float
    replicates: int
    undefined: int
    #: эффективные степени свободы сравнения с эталоном (Уэлч — Саттертуэйт)
    agreement_df: float
    verdict: Verdict

    @property
    def ci(self) -> tuple[float, float] | None:
        if self.observed is None or self.observed_se is None:
            return None
        half = half_width(self.observed_se, self.replicates, confidence=self.confidence)
        return (self.observed - half, self.observed + half)


def _welch_df(se_a: float, df_a: float, se_b: float, df_b: float) -> float:
    """Степени свободы разности двух средних с оценёнными и НЕ равными SD.

    Брать здесь df одной из сторон — значит объявить, что вторая известна
    точно. Эталон считается по своим повторам и точно не известен.
    """
    num = (se_a ** 2 + se_b ** 2) ** 2
    den = se_a ** 4 / df_a + se_b ** 4 / df_b
    return num / den if den > 0 else min(df_a, df_b)


def check_recovery(
    observed: Contrast,
    planted: Contrast,
    *,
    delta: float,
    confidence: float = 0.95,
) -> RecoveryCheck:
    """Собирает вердикт из измеренного контраста и эталонного.

    Меньше двух пригодных повторов — отказ, а не вердикт с нулевой шириной
    интервала: нулевая ширина превращает любое отклонение в MISMATCH и любое
    совпадение в RECOVERED, то есть выдаёт уверенность там, где её неоткуда
    взять.

    Квантиль — Стьюдента, не нормальный, и это не педантизм: SD контраста здесь
    оценивается по тем же немногим повторам, и нормальный квантиль давал
    MISMATCH втрое чаще номинала. Мерится это `coverage_probe`, а не
    предполагается.
    """
    for role, side in (("observed", observed), ("planted", planted)):
        if side.n < 2:
            raise ValueError(
                f"{side.estimand}: {role} has {side.n} usable replicate(s) "
                f"({side.undefined} undefined) — an interval needs at least 2"
            )
    if observed.estimand != planted.estimand or observed.horizon_hours != planted.horizon_hours:
        raise ValueError(
            f"comparing {observed.estimand}@{observed.horizon_hours} with "
            f"{planted.estimand}@{planted.horizon_hours}"
        )
    half = half_width(observed.se, observed.n, confidence=confidence)
    agreement_df = _welch_df(observed.se, observed.n - 1, planted.se, planted.n - 1)
    agreement = (student_t_quantile(0.5 + confidence / 2.0, agreement_df)
                 * math.hypot(observed.se, planted.se))
    return RecoveryCheck(
        estimand=observed.estimand,
        horizon_hours=observed.horizon_hours,
        planted=planted.mean,
        planted_se=planted.se,
        observed=observed.mean,
        observed_se=observed.se,
        delta=delta,
        confidence=confidence,
        replicates=observed.n,
        undefined=observed.undefined,
        agreement_df=agreement_df,
        verdict=classify(
            observed=observed.mean,
            planted=planted.mean,
            half_width=half,
            agreement_half_width=agreement,
            delta=delta,
        ),
    )


# --------------------------------------------------------------------------
# Покрытие: инструмент меряет собственную частоту ошибок, а не постулирует её
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Coverage:
    """Сколько раз из скольких эталон НЕ попал в интервал измерения.

    Номинал — `1 - confidence`. Существенное превышение означает, что
    недокрывает ИНСТРУМЕНТ, и тогда MISMATCH перестаёт быть уликой против
    пайплайна: обвинение надо снимать с подсудимого и предъявлять интервалу.
    """

    estimand: str
    trials: int
    mismatches: int
    nominal: float

    @property
    def rate(self) -> float:
        return self.mismatches / self.trials if self.trials else 0.0

    @property
    def within_nominal(self) -> bool:
        """Точный биномиальный верхний хвост на уровне 0.01, без нормальных приближений."""
        n, k, p = self.trials, self.mismatches, self.nominal
        tail = sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))
        return tail > 0.01


def coverage_probe(
    population: Population,
    treatment: TrueEffect,
    planted: dict[str, Contrast],
    *,
    dyads: int,
    days: float,
    replicates: int,
    trials: int,
    base_seed: int,
    horizon_hours: float,
    delta: float,
    confidence: float = 0.95,
) -> dict[str, Coverage]:
    """`trials` независимых «пилотов» против одного эталона — доля MISMATCH.

    Эталон один и тот же намеренно: проверяется интервал измерения, а не
    устойчивость эталона. `base_seed` у каждого испытания свой и заведомо
    далёкий от эталонного.
    """
    counts = {name: 0 for name in ESTIMANDS}
    for t in range(trials):
        observed = contrast(
            population, treatment, dyads=dyads, days=days, replicates=replicates,
            base_seed=base_seed + t * 1_000, horizon_hours=horizon_hours, paired=True,
        )
        for name in ESTIMANDS:
            check = check_recovery(observed[name], planted[name],
                                   delta=delta, confidence=confidence)
            counts[name] += check.verdict is Verdict.MISMATCH
    return {
        name: Coverage(name, trials, counts[name], 1.0 - confidence)
        for name in ESTIMANDS
    }
