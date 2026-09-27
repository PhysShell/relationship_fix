"""Production-shaped пилот ступени 64000: самый тяжёлый блок, настоящий просмотр.

Зачем. Моделью стоимость 64000 больше не выводится: A-F2a подтвердил
агрегатную форму, но разброс внутри блока остался нерешённым. Для
планировщика важен не он, а МАКСИМУМ фактического времени группы — и его
проще измерить, чем смоделировать. Пилот исполняет ровно те юниты,
которые исполнит полная ступень при смежной раскладке g групп, но только
для блока δ = 60, самого дорогого по всем прежним замерам.

Юниты строятся той же `key_slices`, что у планировщика, и исполняются тем
же `cli run`: `task_id` совпадает с будущим явным планом g = 12 (или 24),
научный результат пишется в формате ступеней.

Разрешены РОВНО два размера: 12 и 24 (запасной). Больше исследований
стоимости этим модулем не заказывается.

Гейт: каждый юнит блока укладывается в `cost.SHARD_BUDGET_HOURS` (2.5 ч)
по времени счёта; падение, таймаут или неверный научный результат — FAIL.
"""

from __future__ import annotations

from simulation import s5b_shard as S

from . import cost, resume
from .identity import ACHIEVED, ArtifactRefused, KNOWN_STATUSES
from .scheduler import FRACTIONS, KEYS, arms, key_slices

PILOT_LOOK = 64000
ALLOWED_GROUPS = (12, 24)
PILOT_ARM = "r96.0:c1.25:R0:m1.0"
PILOT_BLOCK = 60.0

#: Модуль не планирует ступени и планировщиком не импортируется.
NOT_WIRED_INTO_THE_PLANNER = True


class PilotRefused(Exception):
    """Пилот не собирается: состав не тот, что объявлен."""


def units(arm: str, look: int, groups: int, block: float) -> tuple:
    """Юниты блока `block` при смежной раскладке `groups` групп.

    Порядок KEYS на честном слове не принимается: каждая группа блока
    обязана содержать ТОЛЬКО этот δ, группы не пересекаются и вместе
    покрывают блок ровно целиком.
    """
    if look != PILOT_LOOK:
        raise PilotRefused(f"пилот только на ступени {PILOT_LOOK}, дано {look}")
    if groups not in ALLOWED_GROUPS:
        raise PilotRefused(f"g = {groups} не разрешён; только {ALLOWED_GROUPS}")
    if arm not in arms():
        raise PilotRefused(f"рука {arm} не из замороженной сетки")
    whole = tuple(k for k in KEYS if k[0] == block)
    if not whole:
        raise PilotRefused(f"блока δ = {block} в сетке нет")
    slices = key_slices(groups)
    size = len(KEYS) // groups
    if len(KEYS) % groups or len(slices) != groups:
        raise PilotRefused(f"72 ключа не режутся на {groups} равных групп")
    touching = [tuple(s) for s in slices if any(k[0] == block for k in s)]
    for s in touching:
        if len(s) != size:
            raise PilotRefused(f"группа блока из {len(s)} ключей, ожидалось {size}")
        others = sorted({k[0] for k in s} - {block})
        if others:
            raise PilotRefused(f"группа блока δ = {block} содержит и δ {others}")
    flat = [k for s in touching for k in s]
    if len(flat) != len(set(flat)):
        raise PilotRefused("группы блока пересекаются")
    if set(flat) != set(whole):
        raise PilotRefused(
            f"группы покрывают {len(set(flat))} ключей блока из {len(whole)}")
    if len(touching) != len(whole) // size:
        raise PilotRefused(f"групп блока {len(touching)}, ожидалось "
                           f"{len(whole) // size}")
    return tuple(S.Unit(arm=arm, look=look, keys=s, weight=0.0) for s in touching)


def manifest(pilot_units, *, groups: int, block: float) -> dict:
    """Манифест в формате ступени: один юнит — один шард."""
    rows = [{"task_id": u.task_id, "arm": u.arm, "look": u.look, "shard": i,
             "keys": [list(k) for k in u.keys]}
            for i, u in enumerate(pilot_units)]
    return {"look": pilot_units[0].look, "shards": len(rows), "units": rows,
            "pilot": {"groups": groups, "block": block, "arm": pilot_units[0].arm,
                      "budget_hours": cost.SHARD_BUDGET_HOURS}}


def judge(parts, *, look: int, science_sha: str) -> dict:
    """Вердикт пилота. Любой изъян — FAIL с причиной, а не молчание."""
    budget = cost.SHARD_BUDGET_HOURS * 3600.0
    out = {"look": look, "budget_hours": cost.SHARD_BUDGET_HOURS,
           "status": None, "reasons": [], "units": []}
    reasons = out["reasons"]
    try:
        plan = resume.load_manifest(parts)
    except resume.ResumeRefused as exc:
        reasons.append(f"манифеста нет: {exc}")
        out["status"] = "FAIL"
        return out
    meta = plan.get("pilot") or {}
    out["groups"], out["block"], out["arm"] = (meta.get("groups"),
                                               meta.get("block"), meta.get("arm"))
    try:
        expected = {u.task_id for u in units(meta.get("arm"), look,
                                             meta.get("groups"), meta.get("block"))}
    except PilotRefused as exc:
        reasons.append(f"манифест не пилотный: {exc}")
        expected = set()
    declared = resume.declared_units(plan)
    if expected and set(declared) != expected:
        reasons.append("манифест объявляет не те юниты, что даёт раскладка")
    try:
        got = resume.completed(parts, look=look, science_sha=science_sha)
    except (resume.ResumeRefused, ArtifactRefused) as exc:
        reasons.append(f"научный результат не принят: {exc}")
        got = {}
    for tid in sorted(set(declared) - set(got)):
        reasons.append(f"{tid}: результата нет — падение или таймаут")
    for tid in sorted(got):
        payload = got[tid]
        keys = [tuple(k) for k in payload["keys"]]
        ids = [(tuple(e["key"]), e["fraction"]) for e in payload["endpoints"]]
        want = {(k, f) for k in keys for f in FRACTIONS}
        if len(ids) != len(set(ids)) or set(ids) != want:
            reasons.append(f"{tid}: концы не те — {len(ids)} при ожидаемых "
                           f"{len(want)}")
        for e in payload["endpoints"]:
            if e["status"] not in KNOWN_STATUSES:
                reasons.append(f"{tid}: статус {e['status']!r} не из известных")
                break
            if (e["look"] == look) != (e["status"] == ACHIEVED) or \
                    e["look"] not in (look, None):
                reasons.append(f"{tid}: просмотр {e['look']!r} при статусе "
                               f"{e['status']}")
                break
        seconds = payload.get("seconds")
        row = {"task_id": tid, "keys": payload["keys"], "seconds": seconds,
               "hours": None if seconds is None else round(seconds / 3600.0, 3),
               "peak_rss_mb": payload.get("peak_rss_mb"),
               "achieved": sum(e["status"] == ACHIEVED
                               for e in payload["endpoints"]),
               "endpoints": len(payload["endpoints"])}
        out["units"].append(row)
        if seconds is None:
            reasons.append(f"{tid}: время счёта не записано")
        elif seconds > budget:
            reasons.append(f"{tid}: {seconds / 3600.0:.2f} ч > "
                           f"{cost.SHARD_BUDGET_HOURS} ч")
    hours = [r["hours"] for r in out["units"] if r["hours"] is not None]
    out["worst_hours"] = max(hours) if hours else None
    out["status"] = "PASS" if not reasons and got else "FAIL"
    return out
