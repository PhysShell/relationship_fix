"""Модель стоимости группы ключей: S + сумма стоимостей ключей. PoC.

НЕ ПОДКЛЮЧЕНА К ПЛАНИРОВЩИКУ. Её дело — выяснить, способна ли такая
модель вообще воспроизвести калибровку, до того как планировщик начнёт на
неё опираться. Подключение — отдельное решение.

Зачем она нужна. Планировщик сейчас рассогласован сам с собой:
`groups_needed` выбирает число групп по модели Амдала
`T_full * (s + (1 - s) / g)`, а `units_for` назначает каждой группе вес
`T_full * len(keys) / 72`. Второе теряет повторяемую долю `s` и считает все
ключи равными, хотя калибровка показала разницу в 2.69 раза. Поставь
сейчас `UNDIVIDED_SHARE = 0.038` — и планировщик перестанет падать, но
пропустит план для худшей руки 64000 с худшей группой 2.03 ч по его
оценке и 3.15 ч по измерению, а самую тяжёлую группу сочтёт самой лёгкой.

Модель здесь: `T(G) = S + sum(cost(k) for k in G)`, где `S` повторяется в
каждой группе. Стоимость ключа известна только по ПЕРВОЙ координате —
только она и измерена. Внутри блока ключи считаются равными; это
допущение, а не замер, и любая раскладка, выровненная по неизмеренной
координате, несёт риск, которого эта модель не видит.
"""

from __future__ import annotations

from .scheduler import KEYS, key_slices

#: Модель не участвует в планировании. Подключение — отдельное решение.
NOT_WIRED_INTO_THE_PLANNER = True

#: Внутри блока первой координаты ключи считаются равными: так измерено.
UNIFORM_WITHIN_FIRST_COORDINATE_IS_ASSUMED = True

#: ДОПУСК СВЕРКИ НА ОТЛОЖЕННЫХ ДАННЫХ, объявлен до прогона сверки.
#:
#: 5% на время группы и на сумму по варианту. Почему столько: на порядок
#: меньше запаса до бюджета у решений, ради которых модель и нужна (у
#: худшей группы при выбранном числе групп он порядка 10–14%), и выше
#: правдоподобного шума однократного замера на общей виртуалке.
#:
#: ОГОВОРКА О СЛЕПОТЕ: невязки на отложенных половинах частично уже
#: видны через оценки s_A и s_B из прошлого разбора, так что проверка не
#: слепая. Допуск объявлен от величины решения, а не подогнан под невязку.
HELDOUT_TOLERANCE = 0.05


class ModelRefused(Exception):
    """Модель не идентифицируема или не воспроизводит наблюдение."""


def _tiers(keys) -> list:
    return sorted({k[0] for k in keys})


def fit(record: dict) -> dict:
    """S и стоимость ключа по блокам — из C1 и четвертей варианта g=4.

    Пять неизвестных (S и четыре блока) на пять наблюдений: подгонка
    ТОЧНАЯ, степеней свободы ноль. Поэтому воспроизведение C4 и W4 здесь
    ничего не доказывает — оно следует из подгонки. Проверкой служит
    только вариант g=2, в подгонку не вошедший.
    """
    variants = {v["groups"]: v for v in record["variants"]}
    if 1 not in variants or 4 not in variants:
        raise ModelRefused("для подгонки нужны варианты 1 и 4")
    c1 = variants[1]["C_g_sum_wall"]
    quarters = variants[4]["groups_detail"]
    tiers = []
    for row in quarters:
        t = _tiers(tuple(k) for k in row["keys"])
        if len(t) != 1:
            raise ModelRefused(
                f"четверть смешивает блоки {t}: стоимость блока не "
                f"идентифицируема")
        tiers.append(t[0])
    if len(set(tiers)) != len(tiers):
        raise ModelRefused(f"блоки повторяются: {tiers}")
    total = sum(r["wall_seconds"] for r in quarters)
    undivided = (total - c1) / (len(quarters) - 1)
    per_key = {}
    for tier, row in zip(tiers, quarters):
        per_key[tier] = (row["wall_seconds"] - undivided) / row["key_count"]
        if per_key[tier] <= 0:
            raise ModelRefused(f"блок {tier}: неположительная стоимость ключа")
    return {"undivided": undivided, "per_key": per_key, "fitted_on": [1, 4]}


def group_seconds(model: dict, keys) -> float:
    return model["undivided"] + sum(model["per_key"][k[0]] for k in keys)


def scaled(model: dict, factor: float) -> dict:
    """Перенос на другой просмотр. ЛИНЕЙНОСТЬ ПО ПРОСМОТРУ — ДОПУЩЕНИЕ."""
    return {"undivided": model["undivided"] * factor,
            "per_key": {t: v * factor for t, v in model["per_key"].items()},
            "fitted_on": model["fitted_on"], "scaled_by": factor}


def check_heldout(model: dict, record: dict, groups: int = 2,
                  tolerance: float = HELDOUT_TOLERANCE) -> dict:
    """Предсказать вариант, НЕ вошедший в подгонку, и сверить с замером."""
    variants = {v["groups"]: v for v in record["variants"]}
    if groups in model["fitted_on"]:
        raise ModelRefused(f"вариант {groups} входил в подгонку: это не проверка")
    rows = variants[groups]["groups_detail"]
    out = {"groups": groups, "tolerance": tolerance, "rows": []}
    for row in rows:
        keys = [tuple(k) for k in row["keys"]]
        pred = group_seconds(model, keys)
        obs = row["wall_seconds"]
        out["rows"].append({"observed": obs, "predicted": round(pred, 1),
                            "relative_error": round(pred / obs - 1.0, 5)})
    pc = sum(r["predicted"] for r in out["rows"])
    oc = variants[groups]["C_g_sum_wall"]
    pw = max(r["predicted"] for r in out["rows"])
    ow = variants[groups]["W_g_max_wall"]
    out["C"] = {"observed": oc, "predicted": round(pc, 1),
                "relative_error": round(pc / oc - 1.0, 5)}
    out["W"] = {"observed": ow, "predicted": round(pw, 1),
                "relative_error": round(pw / ow - 1.0, 5)}
    obs_ratio = max(r["wall_seconds"] for r in rows) / min(
        r["wall_seconds"] for r in rows)
    pred_ratio = pw / min(r["predicted"] for r in out["rows"])
    out["imbalance"] = {"observed": round(obs_ratio, 4),
                        "predicted": round(pred_ratio, 4)}
    errors = ([abs(r["relative_error"]) for r in out["rows"]]
              + [abs(out["C"]["relative_error"]),
                 abs(out["W"]["relative_error"])])
    out["worst_relative_error"] = round(max(errors), 5)
    out["passed"] = max(errors) <= tolerance
    return out


def worst_contiguous(model: dict, groups: int) -> float:
    """Худшая группа при СМЕЖНОЙ раскладке планировщика."""
    return max(group_seconds(model, s) for s in key_slices(groups))


def balanced_partition(model: dict, groups: int) -> list[list]:
    """Настоящее разбиение на целые ключи: LPT по стоимости ключа.

    Не идеальная граница `S + total / g`, а раскладка, которую можно
    исполнить. Ключи неделимы, поэтому идеальная граница — лишь оценка
    снизу, и прошлый вывод «около 6» опирался именно на неё.
    """
    bins = [[] for _ in range(groups)]
    loads = [model["undivided"]] * groups
    for key in sorted(KEYS, key=lambda k: (-model["per_key"][k[0]], KEYS.index(k))):
        i = min(range(groups), key=lambda j: (loads[j], j))
        bins[i].append(key)
        loads[i] += model["per_key"][key[0]]
    return bins


#: LPT ВЫРОВНЕН ПО НЕИЗМЕРЕННОЙ ОСИ. Внутри блока ключи по модели равны,
#: и LPT раскладывает их по кругу в каноническом порядке с периодом
#: 6 = 3 горизонта x 2 значения maximise. При g=6 каждая группа получает
#: ровно одну клетку (horizon, maximise): по модели баланс идеален, а по
#: горизонту — наихудший из возможных. Использовать для планирования нельзя.
LPT_ALIGNS_WITH_UNMEASURED_AXES = True


def factorial_partition(groups: int) -> list[list]:
    """Разбиение, сбалансированное по ВСЕМ координатам ключа сразу.

    Внутри блока первой координаты 18 ключей = 3 days x 3 horizon x 2
    maximise. Ключ идёт в группу `(2h + x + 2d + t) mod 6` (h, x, d —
    индексы horizon, maximise, days; t — индекс блока). Тогда при g=6
    каждая группа получает по 3 ключа из каждого блока — по модели это
    та же стоимость, что у LPT, — и при этом по 4 каждого горизонта,
    по 4 каждого days и по 6 каждого значения maximise.

    Стоимость по модели от этого не меняется: внутри блока ключи равны.
    Меняется устойчивость к ТОМУ, ЧЕГО МОДЕЛЬ НЕ ВИДИТ: аддитивный вклад
    неизмеренных координат делится между группами поровну.
    """
    if groups != 6:
        raise ModelRefused(
            f"факториальная раскладка построена для g=6, дано {groups}: для "
            f"других g она не выводится этим правилом")
    firsts = sorted({k[0] for k in KEYS})
    days = sorted({k[1] for k in KEYS})
    horizons = sorted({k[2] for k in KEYS})
    bins = [[] for _ in range(groups)]
    for key in KEYS:
        t = firsts.index(key[0])
        d, h, x = days.index(key[1]), horizons.index(key[2]), int(key[3])
        bins[(2 * h + x + 2 * d + t) % groups].append(key)
    return bins


def coordinate_balance(bins) -> dict:
    """Сколько раз каждое значение каждой координаты попало в каждую группу."""
    out = {}
    for axis in range(4):
        values = sorted({k[axis] for k in KEYS}, key=repr)
        out[axis] = [[sum(1 for k in b if k[axis] == v) for v in values]
                     for b in bins]
    return out


def worst_balanced(model: dict, groups: int) -> float:
    return max(group_seconds(model, b) for b in balanced_partition(model, groups))


def minimum_groups(model: dict, budget: float, how) -> int | None:
    """Наименьшее число групп, при котором худшая влезает в бюджет."""
    for g in range(1, len(KEYS) + 1):
        if how(model, g) <= budget:
            return g
    return None
