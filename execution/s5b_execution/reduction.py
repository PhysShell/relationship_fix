"""Сведение концов и сборка ячеек. Научные функции только ЗОВУТСЯ.

Семантика здесь не изобретается: замороженный `s5b_escalation` уже
объявляет `EACH_ENDPOINT_AT_ITS_OWN_TAU = True` и прямо предупреждает,
что подменять `A_16000(T)` на `A_64000(T)` нельзя. Не хватало только
проводки — её и делает этот модуль.
"""

from __future__ import annotations

from simulation import s5b_escalation as E
from simulation import s5b_precision as PRC
from simulation import s5b_stage1 as legacy

from .identity import ACHIEVED, EndpointId
from .scheduler import FRACTIONS, KEYS, arms

#: Замороженное слияние зовётся на КАЖДОЙ ступени, а не только на 64000.
#:
#: На 4000 и 16000 у руки одна группа ключей, и слияние тривиально. Но
#: путь, который впервые исполняется в бою, — ровно тот, что сегодня
#: уронил прогон: `merge` был единственным шагом воркфлоу, который до того
#: не отрабатывал ни разу. Звать его с первой ступени дешевле, чем узнать
#: о его состоянии на 64000.
FROZEN_MERGE_RUNS_AT_EVERY_LOOK = True


def rehydrate(record: dict) -> E.Endpoint:
    """Запись артефакта обратно в замороженный `Endpoint`."""
    return E.Endpoint(
        key=tuple(record["key"]), delta_fraction=record["fraction"],
        point=record["point"], low=record["low"], high=record["high"],
        radius=record["radius"],
        status=PRC.PrecisionStatus(record["status"]), look=record["look"])


def results_of(payload: dict) -> dict:
    """`{(ключ, доля): Endpoint}` одного part-файла."""
    return {(tuple(r["key"]), r["fraction"]): rehydrate(r)
            for r in payload["endpoints"]}


def merge_arm(arm: str, look: int, payloads, expected, unit_of) -> dict:
    """Концы руки через ЗАМОРОЖЕННЫЙ `s5b_shard.merge`.

    Своей логики слияния здесь нет и не будет: у замороженной семь путей
    отказа, и переписать их «поближе к делу» означало бы завести вторую
    науку рядом с первой.
    """
    from simulation import s5b_shard as S
    parts = [(unit_of[p["task_id"]], results_of(p))
             for p in payloads if p["arm"] == arm and p["look"] == look]
    return S.merge(arm, look, parts, expected=expected)


def cells_from(final: dict[EndpointId, dict]):
    """Ячейки из сведённых концов: каждый на СВОЁМ `tau`.

    Ячейка — пара (рука T, её контроль K) при общих `(ставка, C)`, один
    ключ без `maximise` и одна доля δ. Четыре конца: T и K, каждый в
    вариантах `maximise` False/True.
    """
    out = []
    for rate in E.P.OPPORTUNITY_RATE_GRID:
        for c_rate, _c_shift in E.P.C_REACTIVITY_POINTS:
            control = legacy.arm_tag(rate, c_rate, "R0", 1.0)
            for regime, magnitude in legacy.REGIMES:
                if regime == "R0":
                    continue
                treated = legacy.arm_tag(rate, c_rate, regime, magnitude)
                for delta, days, horizon in _key_prefixes():
                    for fraction in FRACTIONS:
                        quad = _quad(final, treated, control,
                                     delta, days, horizon, fraction)
                        if quad is None:
                            continue
                        out.append(_cell(treated, control, delta, days,
                                         horizon, fraction, quad))
    return out


def _key_prefixes():
    seen = []
    for key in KEYS:
        prefix = (key[0], key[1], key[2])
        if prefix not in seen:
            seen.append(prefix)
    return tuple(seen)


def _quad(final, treated, control, delta, days, horizon, fraction):
    low_key = (delta, days, horizon, False)
    high_key = (delta, days, horizon, True)
    try:
        return (final[EndpointId(treated, low_key, fraction)],
                final[EndpointId(treated, high_key, fraction)],
                final[EndpointId(control, low_key, fraction)],
                final[EndpointId(control, high_key, fraction)])
    except KeyError:
        return None


def _cell(treated, control, delta, days, horizon, fraction, quad):
    statuses = [PRC.PrecisionStatus(r["status"]) for r in quad]
    row = {"treated": treated, "control": control, "key": [delta, days, horizon],
           "fraction": fraction,
           "taus": [r["look"] for r in quad],
           "evaluable": E.cell_is_evaluable(statuses)}
    if row["evaluable"]:
        ends = [rehydrate(r) for r in quad]
        row["contrast"] = list(E.cell_contrast(*ends))
    else:
        row["contrast"] = None
        row["status"] = PRC.NOT_EVALUATED_MC_PRECISION
    return row
