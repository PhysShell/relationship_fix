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
    ("локализация излома с дальней стороны", "coarsening/bounded.py",
     "    return abs(lam - (lo if below else hi))",
     "    return abs(lam - (hi if below else lo))",
     ["tests.test_s5b_prereg"]),
    ("сэндвич снова объявлен первичным", "simulation/s5b_prereg.py",
     'SANDWICH_ROLE = "diagnostic cross-check"',
     'SANDWICH_ROLE = "primary"',
     ["tests.test_s5b_prereg"]),
    ("полное множество -> компонента вокруг корня", "coarsening/inversion.py",
     "    found.sort()",
     "    found.sort()\n"
     "    if len(found) > 1:\n"
     "        root = sum(p.b for q in periods for p in q) / max(1e-9, sum(\n"
     "            p.n for q in periods for p in q))\n"
     "        inside = [c for c in found if c[0] <= root <= c[1]]\n"
     "        found = inside or found[:1]",
     ["tests.test_inversion"]),
    ("вырожденная дисперсия отвергается", "coarsening/inversion.py",
     "        if s_nn == 0.0 and s_bb == 0.0 and ZERO_VARIANCE_IS_ACCEPTED:\n"
     "            found.append((left, right))          # разброса нет: принимаем\n"
     "            continue",
     "        if s_nn == 0.0 and s_bb == 0.0:\n            continue",
     ["tests.test_inversion"]),
    ("оболочка заменена первой компонентой", "coarsening/inversion.py",
     "    return components[0][0], components[-1][1]",
     "    return components[0][0], components[0][1]",
     ["tests.test_inversion"]),
    ("корни округляются ВНУТРЬ", "coarsening/inversion.py",
     "    eps = OUTWARD_EPS * max(1.0, abs(lo), abs(hi), span)\n"
     "    return lo - eps, hi + eps",
     "    eps = OUTWARD_EPS * max(1.0, abs(lo), abs(hi), span)\n"
     "    return lo + eps, hi - eps",
     ["tests.test_inversion"]),
    ("двойной корень теряется", "coarsening/inversion.py",
     "    if disc < -DISCRIMINANT_TOLERANCE * scale:\n        return None",
     "    if disc < 0.0:\n        return None",
     ["tests.test_inversion"]),
    ("неустойчивая формула корней", "coarsening/inversion.py",
     "    q = -0.5 * (b + math.copysign(root, b))\n"
     "    first, second = q / a, (c / q if q != 0.0 else q / a)",
     "    first, second = (-b - root) / (2.0 * a), (-b + root) / (2.0 * a)",
     ["tests.test_inversion"]),
    ("радиус берёт компоненту вокруг корня", "simulation/s5b_precision.py",
     "    low = min(a for a, _ in components)\n"
     "    high = max(b for _, b in components)",
     "    around = [c for c in components if c[0] <= point <= c[1]] or components\n"
     "    low = min(a for a, _ in around)\n"
     "    high = max(b for _, b in around)",
     ["tests.test_s5b_prereg"]),
    ("поправка на просмотры и концы снята", "simulation/s5b_precision.py",
     "ALPHA_PER_COMPARISON = ALPHA / COMPARISONS",
     "ALPHA_PER_COMPARISON = ALPHA",
     ["tests.test_s5b_prereg"]),
    ("измерение концов выброшено из множественности", "simulation/s5b_precision.py",
     "COMPARISONS = ENDPOINTS_PER_CELL * len(LOOKS)",
     "COMPARISONS = len(LOOKS)",
     ["tests.test_s5b_prereg"]),
    ("лестница обрезана до одного просмотра", "simulation/s5b_precision.py",
     "    while current <= MEASUREMENT_MC_MAX_PERIODS_PER_ARM:",
     "    while current <= MEASUREMENT_MC_START_PERIODS_PER_ARM:",
     ["tests.test_s5b_prereg"]),
    ("статус точности слит с вердиктом", "simulation/s5b_precision.py",
     'NOT_EVALUATED_MC_PRECISION = "NOT_EVALUATED_MC_PRECISION"',
     'NOT_EVALUATED_MC_PRECISION = "MEASUREMENT_AMBIGUOUS"',
     ["tests.test_s5b_prereg"]),
    ("быстрый путь квалификации теряет ковариацию", "tools/s5b_qualify.py",
     "        b = -2 * count * seg.mean_b * seg.mean_n + 2 * scale * seg.s_bn",
     "        b = -2 * count * seg.mean_b * seg.mean_n",
     ["tests.test_s5b_qualify"]),
    ("корень квалификации берётся правым концом сегмента", "tools/s5b_qualify.py",
     "        if seg.mean_b - seg.right * seg.mean_n <= 0.0:\n"
     "            return seg.mean_b / seg.mean_n",
     "        if seg.mean_b - seg.right * seg.mean_n <= 0.0:\n"
     "            return seg.right",
     ["tests.test_s5b_qualify"]),
    ("сценарий Филлера возвращён к масштабу golden", "tools/s5b_qualify.py",
     "FIELLER_CATALOGUE = ((Piece(10_000.0, 12_479_520.0),), (Piece(1.0, 720.0),))",
     "FIELLER_CATALOGUE = ((Piece(100.0, 131_520.0),), (Piece(1.0, 720.0),))",
     ["tests.test_s5b_qualify"]),
    ("семейная поправка суиты одолжена у семи сценариев", "tools/s5b_qualify.py",
     "SUITE_Z = NormalDist().inv_cdf(1.0 - SIMULTANEOUS_ALPHA / STATEMENTS)",
     "SUITE_Z = NormalDist().inv_cdf(1.0 - SIMULTANEOUS_ALPHA / 7)",
     ["tests.test_s5b_qualify"]),
    ("реплик снова 4000, мощности не хватает", "tools/s5b_qualify.py",
     "REPLICATES = 24_000", "REPLICATES = 4_000",
     ["tests.test_s5b_qualify"]),
    ("пол приравнен номиналу, запаса нет", "tools/s5b_qualify.py",
     "FLOOR_RATIO = ((1.0 - COVERAGE_ACCEPTANCE_FLOOR) / (1.0 - CONFIDENCE_LEVEL))",
     "FLOOR_RATIO = 1.0",
     ["tests.test_s5b_qualify"]),
    ("ячейке хватает ОДНОГО точного конца", "tools/s5b_qualify.py",
     "    return len(certified) == 4 and all(certified)",
     "    return len(certified) == 4 and any(certified)",
     ["tests.test_s5b_qualify"]),
    ("в гейт возвращён промах БЕЗ сертификата", "tools/s5b_qualify.py",
     "            tally.false_cert += certified and not covered",
     "            tally.false_cert += not covered",
     ["tests.test_s5b_qualify"]),
    ("гейтящий поток seed'ов возвращён тестам", "tools/s5b_qualify.py",
     'QUALIFICATION_NAMESPACE = "r4-qualification"',
     'QUALIFICATION_NAMESPACE = "r4-test"',
     ["tests.test_s5b_qualify"]),
    ("namespace снова получил умолчание", "tools/s5b_qualify.py",
     "def replicate(scenario: Scenario, index: int, tallies=None, *,\n"
     "              namespace: str, ladder=PR.LOOKS, deltas=DELTAS,",
     "def replicate(scenario: Scenario, index: int, tallies=None, *,\n"
     "              namespace: str = QUALIFICATION_NAMESPACE,\n"
     "              ladder=PR.LOOKS, deltas=DELTAS,",
     ["tests.test_s5b_qualify"]),
    ("филлер, доходящий до сертификата, обезврежен", "tools/s5b_qualify.py",
     "FIELLER_CERTIFYING_CATALOGUE = ((Piece(10_000.0, 12_000_499.5),),\n"
     "                                (Piece(1.0, 1_199.5),))",
     "FIELLER_CERTIFYING_CATALOGUE = ((Piece(10_000.0, 12_479_520.0),),\n"
     "                                (Piece(1.0, 720.0),))",
     ["tests.test_s5b_qualify"]),
    ("цель по точности взята самой мягкой delta", "tools/s5b_qualify.py",
     "DELTA = 36.0", "DELTA = 360.0",
     ["tests.test_s5b_qualify"]),
    ("H = 300 снова пропускается по прогнозу", "simulation/s5b_escalation.py",
     "SKIPPED_HORIZONS: tuple[float, ...] = ()",
     "SKIPPED_HORIZONS: tuple[float, ...] = (300.0,)",
     ["tests.test_s5b_escalation"]),
    ("ячейке хватает одного точного конца из четырёх",
     "simulation/s5b_escalation.py",
     "    return (len(statuses) == 4\n"
     "            and all(s is PR.PrecisionStatus.ACHIEVED for s in statuses))",
     "    return (len(statuses) == 4\n"
     "            and any(s is PR.PrecisionStatus.ACHIEVED for s in statuses))",
     ["tests.test_s5b_escalation"]),
    ("вложенность сломана смещением куска", "simulation/s5b_escalation.py",
     '        messages = generate_dyad(random.Random(f"{tag}:{index}"), params,',
     '        messages = generate_dyad(random.Random(f"{tag}:{index - start}"), params,',
     ["tests.test_s5b_escalation"]),
    ("прогноз пущен в управление", "simulation/s5b_escalation.py",
     "PREDICTED_NEVER_DRIVES_CONTROL_FLOW = True",
     "PREDICTED_NEVER_DRIVES_CONTROL_FLOW = False",
     ["tests.test_s5b_escalation"]),
    ("слияние перестало быть fail-closed", "simulation/s5b_shard.py",
     '        raise MergeRefused(f"не хватает юнитов: {missing}")',
     '        pass',
     ["tests.test_s5b_shard"]),
    ("ранний взгляд разрешён вместе с ранним счётом",
     "simulation/s5b_shard.py",
     "        if unit.arm != arm or unit.stop > look:\n            continue",
     "        if unit.arm != arm:\n            continue",
     ["tests.test_s5b_shard"]),
    ("жадная раскладка заменена нарезкой", "simulation/s5b_shard.py",
     "        target = min(range(shards), key=lambda i: (load[i], i))",
     "        target = len(ordered) % shards",
     ["tests.test_s5b_shard"]),
    ("юнит снова пересекает ступень лестницы", "simulation/s5b_shard.py",
     "            for start, stop in _split(previous, look, rate):",
     "            for start, stop in _split(previous, look + 1, rate):",
     ["tests.test_s5b_shard"]),
    ("имя задания зависит от раскладки", "simulation/s5b_shard.py",
     '        raw = f"{self.arm}|{self.start}|{self.stop}"',
     '        raw = f"{self.arm}|{self.start}|{self.stop}|{self.weight}"',
     ["tests.test_s5b_shard"]),
    ("R4 снова однороден по legacy-числам", "simulation/s5b_escalation.py",
     "    base = REGIMES[regime].effect(stream)",
     "    from simulation.s5b_stage1 import effect as _legacy\n"
     "    from simulation.process import TrueEffect\n"
     "    _s, _r = _legacy(regime, 1.0)\n"
     "    base = TrueEffect(latency_log_shift=_s, opportunity_rate_ratio=_r)",
     ["tests.test_s5b_escalation"]),
    ("поток эффекта слит с потоком сообщений",
     "simulation/s5b_escalation.py",
     '    stream = random.Random(f"{tag}:{EFFECT_SUBSTREAM}:{index}")',
     '    stream = random.Random(f"{tag}:{index}")',
     ["tests.test_s5b_escalation"]),
    ("эффект разыгран один раз на руку", "simulation/s5b_escalation.py",
     "        period_shift, period_ratio = effect_for(index)",
     "        period_shift, period_ratio = effect_for(start)",
     ["tests.test_s5b_escalation"]),
    ("контрольная рука взята не нулевым режимом",
     "simulation/s5b_escalation.py",
     '    return (rate, c_rate, "R0", 1.0)',
     '    return (rate, c_rate, "R1", 1.0)',
     ["tests.test_s5b_escalation"]),
    ("контрольная рука перескочила точку c-реактивности",
     "simulation/s5b_escalation.py",
     '    del regime, magnitude                      # K не зависит ни от того, ни от другого\n'
     '    return (rate, c_rate, "R0", 1.0)',
     '    del regime, magnitude                      # K не зависит ни от того, ни от другого\n'
     '    return (rate, 1.00, "R0", 1.0)',
     ["tests.test_s5b_escalation"]),
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
