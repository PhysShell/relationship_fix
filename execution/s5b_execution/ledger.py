"""Реестр: у КАЖДОГО конца свой самый ранний просмотр остановки.

Зачем он вообще нужен. Замороженный `run_unit` накапливает префикс
`0..look` и зовёт `endpoints_from(store, look=look)` — это ОДНА оценка на
ОДНОМ `M`. Последовательную процедуру `τ = min{M : r_M <= порог}`
реализует `s5b_precision.run_nested`, и производственный путь её не зовёт
вовсе. Значит на следующей ступени конец, уже остановившийся на 4000,
будет переоценён заново и вернёт свой `A_M` при большем `M`.

Взять это новое значение — значит подменить `A_τ` на `A_M`, а защита
именно `A_τ` и есть центральная часть ревизии 4.

Надеяться, что «позже всё равно получится не хуже», нельзя: в геометрии
Филлера множество приёма бывает несвязным и неограниченным, радиус по `M`
убывать НЕ ОБЯЗАН. Конец, достигший точности на 4000, на 16000 может её
потерять. Ранний `τ` из позднего просмотра не восстанавливается в
принципе — его нужно ХРАНИТЬ.

Поэтому правило одно и без исключений:

    первый ACHIEVED фиксируется навсегда вместе со своим payload;
    все последующие копии того же конца ИГНОРИРУЮТСЯ;
    не достигший точности до последней ступени — INSUFFICIENT.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .identity import (ACHIEVED, INSUFFICIENT, KNOWN_STATUSES, EndpointId,
                       endpoint_ids)


class LedgerRefused(Exception):
    """Реестр отказал. Молча принять сомнительный вход он не вправе."""


@dataclass(frozen=True, slots=True)
class Settled:
    """Конец, остановившийся на `tau`, с ЗАМОРОЖЕННЫМ значением того
    просмотра. `payload` — запись артефакта как есть, без пересчёта."""

    tau: int
    payload: dict


class Ledger:
    """Состояние по концам между ступенями лестницы.

    Не потокобезопасен и не обязан быть: слияние идёт одним заданием.
    """

    def __init__(self) -> None:
        self._settled: dict[EndpointId, Settled] = {}
        self._seen: set[EndpointId] = set()
        self._absorbed: list[int] = []
        self.ignored_because_already_settled = 0

    # -- чтение -----------------------------------------------------------

    @property
    def looks_absorbed(self) -> tuple[int, ...]:
        return tuple(self._absorbed)

    def is_settled(self, identity: EndpointId) -> bool:
        return identity in self._settled

    def tau_of(self, identity: EndpointId) -> int | None:
        found = self._settled.get(identity)
        return None if found is None else found.tau

    def settled_count(self) -> int:
        return len(self._settled)

    def seen_count(self) -> int:
        return len(self._seen)

    # -- запись -----------------------------------------------------------

    def absorb(self, look: int, payloads) -> None:
        """Впитать результаты одной ступени. Порядок ступеней ВОСХОДЯЩИЙ.

        Порядок здесь не косметика. Впитать 16000 раньше 4000 значило бы
        зафиксировать `tau = 16000` у конца, который на самом деле
        остановился раньше, а потом честно проигнорировать настоящий
        ранний результат. `τ` перестал бы быть минимумом. Поэтому
        нарушение порядка — отказ, а не сортировка на лету.
        """
        if self._absorbed and look <= self._absorbed[-1]:
            raise LedgerRefused(
                f"ступени впитываются по возрастанию: {look} после "
                f"{self._absorbed[-1]}")
        for payload in payloads:
            if payload["look"] != look:
                raise LedgerRefused(
                    f"{payload['task_id']}: юнит посчитан на "
                    f"{payload['look']}, впитывается как {look}")
            for identity, record in endpoint_ids(payload):
                self._absorb_one(look, identity, record)
        self._absorbed.append(look)

    def _absorb_one(self, look: int, identity: EndpointId,
                    record: dict) -> None:
        status = record["status"]
        if status not in KNOWN_STATUSES:
            raise LedgerRefused(f"неизвестный статус {status!r}")
        if status == ACHIEVED and record["look"] != look:
            raise LedgerRefused(
                f"конец объявлен точным на {record['look']}, а приехал со "
                f"ступени {look}: происхождение нарушено")
        if status == INSUFFICIENT and record["look"] is not None:
            raise LedgerRefused(
                f"неточный конец несёт просмотр {record['look']!r}")
        self._seen.add(identity)
        if identity in self._settled:
            # УЖЕ ОСТАНОВИЛСЯ. Свежая копия не заменяет ничего.
            self.ignored_because_already_settled += 1
            return
        if status == ACHIEVED:
            self._settled[identity] = Settled(tau=look, payload=dict(record))

    # -- расписание -------------------------------------------------------

    def unit_is_needed(self, arm: str, keys, fractions) -> bool:
        """Юнит идёт на следующую ступень, если внутри остался ХОТЬ ОДИН
        незакрывшийся конец.

        Пересчёт уже закрывшегося конца науку не портит — он просто стоит
        процессорного времени. Портит её подмена значения, и от неё
        защищает `absorb`, а не это расписание.
        """
        for key in keys:
            for fraction in fractions:
                if EndpointId(arm, tuple(key), fraction) not in self._settled:
                    return True
        return False

    # -- итог -------------------------------------------------------------

    def finalise(self, last_look: int) -> dict[EndpointId, dict]:
        """Итоговая карта концов: каждый на СВОЁМ `τ`.

        Не достигший точности ни на одной ступени получает
        `MC_PRECISION_INSUFFICIENT` и `look = None` — это отказ вердикта,
        а не вердикт.
        """
        if not self._absorbed:
            raise LedgerRefused("реестр пуст: сводить нечего")
        if self._absorbed[-1] != last_look:
            raise LedgerRefused(
                f"последняя впитанная ступень {self._absorbed[-1]}, "
                f"а итог требуют на {last_look}")
        out: dict[EndpointId, dict] = {}
        for identity in self._seen:
            found = self._settled.get(identity)
            if found is not None:
                out[identity] = dict(found.payload)
            else:
                out[identity] = {"key": list(identity.key),
                                 "fraction": identity.fraction,
                                 "status": INSUFFICIENT, "look": None}
        return out

    def digest(self) -> str:
        """Устойчивый отпечаток состояния. От порядка чтения не зависит."""
        rows = sorted(
            (json.dumps(i.as_json(), sort_keys=True), s.tau,
             json.dumps(s.payload, sort_keys=True))
            for i, s in self._settled.items())
        return hashlib.sha256(
            json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
