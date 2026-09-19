"""Протокол намеренной диверсии: гейт, который никогда не падал, не проверен.

ЗАЧЕМ ОТДЕЛЬНЫЙ ИНСТРУМЕНТ, а не «поправил руками и посмотрел». Потому что
сама процедура оказалась ненадёжной, и поймано это было случайно.

Подмена `SIMULTANEOUS_ALPHA / 7` на `/ 2` НЕ МЕНЯЕТ РАЗМЕР ФАЙЛА, а `cp` при
восстановлении уложился в ту же секунду. Python признаёт `.pyc` свежим по
паре (mtime с точностью до секунды, размер), поэтому после восстановления
исполнялся ПРОТУХШИЙ байт-код — и набор «падал» на уже исправленном коде.

Направление здесь было безобидным: ложное падение. Обратное столь же
возможно — диверсия живёт, а набор зелёный, потому что переиспользован
байт-код ДО неё. То есть протокол, проверяющий гейты, сам нуждался в гейте.
Тот же класс, что протухший `.olean` в `formal/scripts/audit.sh`: там
`Verification` не входил в дефолтный таргет, и `FinalCheck` радостно зеленел
на вчерашних артефактах.

Здесь изоляция структурная: `-B` плюс снос `__pycache__` перед каждым шагом.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _clear_caches() -> None:
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def run_tests(modules: list[str]) -> bool:
    """True, если набор зелёный. Байт-код не читается и не пишется."""
    _clear_caches()
    done = subprocess.run([sys.executable, "-B", "-m", "unittest", *modules],
                          cwd=ROOT, capture_output=True, text=True)
    return done.returncode == 0


def diversion(path: str, old: str, new: str, modules: list[str]) -> bool:
    """Базовое зелёное -> диверсия красная -> восстановление зелёное.

    Любой другой исход — отказ. В частности «диверсия прошла незамеченной»
    означает, что проверяемого гейта не существует, как бы уверенно он ни
    назывался в документации.
    """
    target = ROOT / path
    source = target.read_text()
    if source.count(old) != 1:
        raise SystemExit(f"якорь не уникален в {path}")

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".bak") as backup:
        backup.write(source)
        saved = pathlib.Path(backup.name)
    try:
        if not run_tests(modules):
            raise SystemExit("базовый набор уже красный — диверсия бессмысленна")
        target.write_text(source.replace(old, new))
        if run_tests(modules):
            raise SystemExit(f"ДИВЕРСИЯ ПРОШЛА НЕЗАМЕЧЕННОЙ: {path}: {old!r}")
        target.write_text(saved.read_text())
        if not run_tests(modules):
            raise SystemExit("после восстановления набор красный")
        return True
    finally:
        target.write_text(saved.read_text())
        saved.unlink(missing_ok=True)
        _clear_caches()


#: Диверсии, объявленные вместе с гейтами, которые они проверяют.
DIVERSIONS = (
    ("наружу -> внутрь (границы периода)", "coarsening/bounded.py",
     "        # НАРУЖУ: нижний конец вниз, верхний вверх. Численная ошибка обязана\n"
     "        # РАСШИРЯТЬ идентифицированное множество, а не сужать его\n"
     "        return Interval(solve(False).low, solve(True).high)",
     "        return Interval(solve(False).high, solve(True).low)",
     ["tests.test_bounded"]),
    ("наружу -> внутрь (границы руки)", "coarsening/bounded.py",
     "                                   0.0, horizon + 1e-9, tolerance=tolerance)\n"
     "\n    try:\n        return Interval(solve(False).low, solve(True).high)",
     "                                   0.0, horizon + 1e-9, tolerance=tolerance)\n"
     "\n    try:\n        return Interval(solve(False).high, solve(True).low)",
     ["tests.test_bounded"]),
    ("левый край плато -> правый", "coarsening/bounded.py",
     "        if value(mid) > 0.0:", "        if value(mid) >= 0.0:",
     ["tests.test_bounded"]),
    ("отказ -> молчание", "coarsening/bounded.py",
     '        raise NoCrossing(f"g({hi}) > 0 — искомое значение вне скобки")',
     "        return Bracket(hi, hi)", ["tests.test_bounded"]),
    ("семейная поправка снята", "simulation/s5b_prereg.py",
     "COVERAGE_ALPHA_EACH = SIMULTANEOUS_ALPHA / 7",
     "COVERAGE_ALPHA_EACH = SIMULTANEOUS_ALPHA / 2", ["tests.test_s5b_prereg"]),
    ("реплик снова 1000", "simulation/s5b_prereg.py",
     "COVERAGE_REPLICATES = 4_000", "COVERAGE_REPLICATES = 1_000",
     ["tests.test_s5b_prereg"]),
    ("отсечка инициации игнорируется", "coarsening/bounded.py",
     "    if initiation_end is None:\n        return start + horizon <= window_end\n"
     "    return start < initiation_end",
     "    return start + horizon <= window_end",
     ["tests.test_bounded", "tests.test_s5b_prereg"]),
)


def main() -> int:
    for name, path, old, new, modules in DIVERSIONS:
        diversion(path, old, new, modules)
        print(f"  поймана: {name}")
    print(f"{len(DIVERSIONS)} диверсий, все пойманы")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
