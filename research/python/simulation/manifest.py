"""Манифест запуска: чтобы таблица через месяц воспроизвелась без везения.

Всякий научный прогон симуляции обязан нести с собой то, что его определяет.
Иначе через месяц остаётся число и вера в то, что тогда всё было хорошо.

Это же закрывает мутационный пробел, оставленный сознательно: посев и
спаривание внутри `coverage_probe` не прибиты к конкретному вызову RNG — вместо
этого требуется, чтобы запуск объявлял свой корень, свою политику спаривания и
свой отпечаток генератора. Прибитый вызов RNG воспроизводит реализацию;
манифест воспроизводит РЕЗУЛЬТАТ, а нужен именно он.

`generator_digest` — sha256 золотой трассы. Он меняется при любой смысловой
правке процесса, и это его работа: манифест со старым отпечатком объявляет, что
числа относились к другому генератору.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import subprocess
from dataclasses import dataclass, field

from .process import DyadParameters, Population, TrueEffect, generate_dyad

#: Параметры золотой трассы. Менять их — значит менять отпечаток, поэтому они
#: живут здесь константами, а не аргументами.
GOLDEN_SEED = "golden"
GOLDEN_DAYS = 9.0

#: ЗАМОРОЗКА СЕМАНТИКИ ГЕНЕРАТОРА до S4 (Messaging Matters).
#:
#: Отпечаток здесь — не справочная величина, а замок. Он меняется при любой
#: смысловой правке процесса, и менять его разрешено ТОЛЬКО вместе с
#: документированной поправкой: расхождение, его класс, что сделано, новый
#: отпечаток. Без этого правила калибровочный корпус за два круга превращается
#: в дрессировочную площадку, а «похоже на людей» — в критерий истины.
#:
#: На момент заморозки откалиброванных параметров: 0 из 8. Ближайшее, что может
#: снять заморозку, — реальные асинхронные многодневные данные, а не ещё один
#: круг подгонки под MaiChat.
FROZEN_DIGEST = "168aef4ea6d8bca4bbadc7f7ae87b2c84847e6588b32e62278a311970624879e"
FROZEN_UNTIL = "S4 — Messaging Matters (async, multi-day corpus)"


def trace_digest(params: DyadParameters = DyadParameters(),
                 *, seed: str = GOLDEN_SEED, days: float = GOLDEN_DAYS) -> str:
    """Отпечаток порождающего процесса, а не отпечаток файла.

    Считается по СГЕНЕРИРОВАННОЙ трассе, поэтому переформатирование кода его не
    трогает, а изменение порядка вытягиваний — трогает. Ровно это и надо: файл
    может меняться сколько угодно, процесс — нет.
    """
    trace = generate_dyad(random.Random(seed), params, days=days)
    blob = json.dumps([[m.message_id, m.actor, m.local_time, m.char_count]
                       for m in trace], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def code_commit() -> str:
    """git sha симуляционного кода, или `unknown` — но не молчание."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if out.returncode != 0:
        return "unknown"
    sha = out.stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                           text=True, timeout=10).stdout.strip()
    return f"{sha}-dirty" if dirty else sha


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Всё, что определяет прогон. Печатается рядом с числами, а не вместо них."""

    purpose: str
    master_seed: int | str
    replicates: int
    dyads: int
    days: float
    horizon_hours: float
    paired: bool
    population: Population
    effect: TrueEffect
    generator_digest: str
    code_commit: str
    #: версия и происхождение внешнего корпуса, когда прогон его касается
    corpus: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def build(cls, purpose: str, **fields) -> RunManifest:
        fields.setdefault("population", Population())
        fields.setdefault("effect", TrueEffect())
        return cls(
            purpose=purpose,
            generator_digest=trace_digest(fields["population"].base),
            code_commit=code_commit(),
            **fields,
        )

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["population"] = dataclasses.asdict(self.population)
        out["effect"] = dataclasses.asdict(self.effect)
        return out

    def render(self) -> str:
        lines = [f"RUN MANIFEST — {self.purpose}"]
        rows = [
            ("generator digest", self.generator_digest),
            ("code commit", self.code_commit),
            ("master seed", self.master_seed),
            ("replicates", self.replicates),
            ("dyads per arm", self.dyads),
            ("days per period", self.days),
            ("horizon (hours)", self.horizon_hours),
            ("pairing policy", "paired" if self.paired else "independent arms"),
            ("corpus", self.corpus or "—"),
        ]
        width = max(len(name) for name, _ in rows)
        lines += [f"  {name:<{width}}  {value}" for name, value in rows]
        base = dataclasses.asdict(self.population.base)
        lines.append("  parameter grid:")
        lines += [f"    {k:<28} {v}" for k, v in sorted(base.items())]
        spread = {k: v for k, v in dataclasses.asdict(self.population).items()
                  if k != "base"}
        lines += [f"    {k:<28} {v}" for k, v in sorted(spread.items())]
        effect = dataclasses.asdict(self.effect)
        lines.append("  planted effect:" if not self.effect.is_null
                     else "  planted effect: none (null)")
        if not self.effect.is_null:
            lines += [f"    {k:<28} {v}" for k, v in sorted(effect.items())]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)
