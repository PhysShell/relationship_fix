"""Возобновление прерванного прогона по `task_id`.

Зачем это важнее четырёх спасённых шардов. 23 сентября выяснилось, что
S5b живёт в общей вычислительной квартире: его 41 задание заняли все 20
слотов аккаунта и остановили работу в соседнем репозитории. Прогон
пришлось отменить. Значит останавливать его придётся и впредь — и тогда
возможность сказать «освободите слоты, завтра продолжим с оставшихся
`task_id`» стоит больше, чем любая оптимизация упаковки.

Единица переиспользования — `task_id`, а НЕ номер шарда. Номер шарда есть
решение планировщика: при возобновлении оставшиеся юниты перепаковываются
как угодно, и привязка к старому номеру сделала бы переиспользование
заложником раскладки. `task_id` считается от `(arm, look, keys)` и от
раскладки не зависит — это отдельный гейт науки.

Отказ по умолчанию. Принимается ровно то, что:
    объявлено ИСХОДНЫМ манифестом прогона;
    посчитано на той же ступени;
    посчитано под тем же `SCIENCE_SHA`;
    даёт свой `task_id` из своего же состава;
    сходится по отпечатку СОДЕРЖИМОГО;
    не противоречит другой копии себя.
"""

from __future__ import annotations

import json
import pathlib

from simulation import s5b_shard as S

from .identity import load_unit_payloads, recompute_digest


class ResumeRefused(Exception):
    """Часть прошлого прогона не принята. Сомнительная — не принимается."""


#: Переиспользование привязано к `task_id`, а не к номеру шарда
REUSE_IS_KEYED_BY_TASK_ID_NOT_SHARD = True


def declared_units(manifest: dict) -> dict[str, dict]:
    """Юниты, объявленные манифестом прерванного прогона."""
    out = {}
    for row in manifest["units"]:
        if row["task_id"] in out:
            raise ResumeRefused(f"манифест объявил {row['task_id']} дважды")
        out[row["task_id"]] = row
    return out


def load_manifest(directory) -> dict:
    path = pathlib.Path(directory) / "manifest.json"
    if not path.exists():
        raise ResumeRefused(f"{directory}: нет manifest.json прошлого прогона")
    return json.loads(path.read_text())


def completed(directory, *, look: int, science_sha: str) -> dict[str, dict]:
    """Части прерванного прогона, пригодные к переиспользованию.

    `science_sha` сверяется с ПРОВЕНАНСОМ манифеста: части его не несут, а
    манифест объявляет, под каким научным кодом считался весь прогон.
    Принять часть, посчитанную другой наукой, значило бы склеить два
    разных вычисления и выдать за одно.
    """
    manifest = load_manifest(directory)
    if manifest["look"] != look:
        raise ResumeRefused(
            f"{directory}: манифест на ступень {manifest['look']}, "
            f"возобновляется {look}")
    prov = manifest.get("provenance") or {}
    was = prov.get("science_sha", "")
    if not was:
        raise ResumeRefused(f"{directory}: манифест без science_sha в провенансе")
    if was != science_sha:
        raise ResumeRefused(
            f"{directory}: части посчитаны под SCIENCE_SHA {was}, сейчас "
            f"{science_sha} — это разные вычисления")

    declared = declared_units(manifest)
    out: dict[str, dict] = {}
    for payload in load_unit_payloads(directory):   # отпечаток уже пересчитан
        tid = payload["task_id"]
        if tid not in declared:
            raise ResumeRefused(
                f"{directory}: часть {tid} не объявлена манифестом прогона")
        if payload["look"] != look:
            raise ResumeRefused(
                f"{tid}: посчитан на ступени {payload['look']}, а не {look}")
        row = declared[tid]
        if payload["arm"] != row["arm"] or payload["keys"] != row["keys"]:
            raise ResumeRefused(
                f"{tid}: научные координаты части не совпадают с манифестом")
        rebuilt = S.Unit(arm=payload["arm"], look=payload["look"],
                         keys=tuple(tuple(k) for k in payload["keys"]),
                         weight=0.0)
        if rebuilt.task_id != tid:
            raise ResumeRefused(
                f"{tid}: состав юнита даёт {rebuilt.task_id}")
        if tid in out and recompute_digest(out[tid]) != recompute_digest(payload):
            raise ResumeRefused(f"{tid}: две копии с разным содержимым")
        out[tid] = payload
    return out


def merge_parts(reused: dict[str, dict], fresh: dict[str, dict]) -> dict[str, dict]:
    """Части прошлого прогона плюс посчитанные заново.

    Пересечение — отказ, а не «свежее побеждает»: если юнит посчитан
    дважды, значит план считал его недостающим, хотя он был на месте, и
    молча предпочесть одну копию означало бы скрыть расхождение.
    """
    both = sorted(set(reused) & set(fresh))
    if both:
        raise ResumeRefused(
            f"{len(both)} юнитов посчитаны заново, хотя переиспользованы: "
            f"{both[:3]}")
    out = dict(reused)
    out.update(fresh)
    return out
