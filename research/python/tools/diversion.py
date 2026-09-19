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

import os
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
    """True, если набор зелёный, и исполнен ИМЕННО текущий исходник.

    `-B` сам по себе НЕ КОНТРАКТ: он запрещает ЗАПИСЬ байт-кода, а чтение
    уже существующего `.pyc` не запрещает. Поэтому три меры разом:

        снос всех __pycache__ перед запуском
        -B, чтобы прогон не оставил новых
        PYTHONPYCACHEPREFIX в пустой временный каталог, так что даже
        уцелевший где-то кэш не лежит на пути

    Третья и есть контракт: путь кэша ФИЗИЧЕСКИ пуст, а не «вероятно
    неактуален».
    """
    _clear_caches()
    with tempfile.TemporaryDirectory() as fresh:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=fresh,
                   PYTHONDONTWRITEBYTECODE="1")
        done = subprocess.run([sys.executable, "-B", "-m", "unittest", *modules],
                              cwd=ROOT, capture_output=True, text=True, env=env)
    return done.returncode == 0


#: САМОПРОВЕРКА ПЕРЕД ДИВЕРСИЯМИ. Прежде чем ловить гейты, harness обязан
#: доказать, что исполняет тот файл, который только что испортил. Иначе
#: «диверсия поймана» может означать «прочитан вчерашний байт-код», а
#: «не поймана» — ровно то же самое.
SENTINEL = "__diversion_self_test__"


def self_test() -> None:
    """Вносит метку в исходник и требует, чтобы её увидел ОТДЕЛЬНЫЙ процесс."""
    target = ROOT / "simulation" / "s5b_prereg.py"
    source = target.read_text()
    probe = [sys.executable, "-B", "-c",
             f"from simulation import s5b_prereg as m; "
             f"raise SystemExit(0 if hasattr(m, {SENTINEL!r}) else 1)"]

    def sees_sentinel() -> bool:
        _clear_caches()
        with tempfile.TemporaryDirectory() as fresh:
            env = dict(os.environ, PYTHONPYCACHEPREFIX=fresh,
                       PYTHONDONTWRITEBYTECODE="1")
            return subprocess.run(probe, cwd=ROOT, capture_output=True,
                                  env=env).returncode == 0

    try:
        if sees_sentinel():
            raise SystemExit("метка видна ДО внесения — самопроверка сломана")
        target.write_text(source + f"\n{SENTINEL} = True\n")
        if not sees_sentinel():
            raise SystemExit("ВНЕСЁННАЯ ПРАВКА НЕ ВИДНА: harness исполняет не тот "
                             "исходник — все результаты диверсий ничего не значат")
    finally:
        target.write_text(source)
        _clear_caches()
    if sees_sentinel():
        raise SystemExit("метка видна ПОСЛЕ отката — откат не работает")


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
    ("детектор изломов ослеплён", "coarsening/bounded.py",
     "    left = round((g(lam) - g(lam - step)) / step)\n"
     "    right = round((g(lam + step) - g(lam)) / step)\n    return left, right",
     "    left = round((g(lam) - g(lam - step)) / step)\n    return left, left",
     ["tests.test_s5b_prereg"]),
    ("излом РОВНО в корне пропускается", "coarsening/bounded.py",
     "    if below and above:\n        return 0.0",
     "    if below and above:\n        return None",
     ["tests.test_s5b_prereg"]),
    ("ноль наблюдений = ноль риска", "simulation/s5b_prereg.py",
     "    bound = wilson_upper(near_breakpoints, periods) * largest_jump",
     "    bound = (near_breakpoints / periods) * largest_jump",
     ["tests.test_s5b_prereg"]),
    ("граничный гейт снят", "simulation/s5b_prereg.py",
     "    margin = REGULARITY_RADIUS_SE_MULTIPLE * standard_error\n"
     "    return margin < root < horizon - margin",
     "    return 0.0 <= root <= horizon",
     ["tests.test_s5b_prereg"]),
    ("отсечка инициации игнорируется", "coarsening/bounded.py",
     "    if initiation_end is None:\n        return start + horizon <= window_end\n"
     "    return start < initiation_end",
     "    return start + horizon <= window_end",
     ["tests.test_bounded", "tests.test_s5b_prereg"]),
)


def main() -> int:
    self_test()
    print("  самопроверка: внесённая правка видна, откат виден")
    for name, path, old, new, modules in DIVERSIONS:
        diversion(path, old, new, modules)
        print(f"  поймана: {name}")
    print(f"{len(DIVERSIONS)} диверсий, все пойманы")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
