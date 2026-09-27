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


#: Деревья, откуда приходят модули. Слой исполнения лежит ВНЕ
#: `research/python`, и пока он не был перечислен здесь, контракт
#: «исполнён именно текущий исходник» на него не распространялся:
#: уцелевший `.pyc` под `execution/` читался бы молча. Дыра найдена
#: рассуждением о контракте, а не падением.
CACHE_ROOTS = (ROOT, ROOT.parent.parent / "execution")


def _clear_caches() -> None:
    for root in CACHE_ROOTS:
        if not root.exists():
            raise SystemExit(f"дерево модулей {root} не найдено")
        for cache in root.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)


def _live_harness_pids() -> list[int]:
    """PID'ы процессов, ДЕЙСТВИТЕЛЬНО исполняющих этот harness.

    Не `pgrep -f`: он ищет подстроку во всей командной строке и потому
    находит собственную оболочку — её `bash -c '... tools/diversion.py ...'`
    содержит имя файла целиком. Первая версия стража отказывала при каждом
    запуске именно поэтому.

    Не родословная: при запуске через `( ... & )` процесс переподчиняется
    init РАНЬШЕ, чем страж успевает посмотреть предков, и оболочка
    перестаёт быть предком. Вторая версия из-за этого отвергала сама себя.

    Здесь разбирается `argv`: у настоящего процесса harness'а ОТДЕЛЬНЫЙ
    аргумент оканчивается на `diversion.py`, а `argv[0]` — интерпретатор.
    Без второго условия флаг получает обёртка `timeout`, у которой такой
    аргумент тоже есть. Все три ошибки найдены запуском, не рассуждением.
    """
    mine = os.getpid()
    out = []
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == mine:
            continue
        try:
            argv = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue                       # процесс ушёл, пока читали
        if not argv or not argv[0]:
            continue
        if b"python" not in argv[0].rsplit(b"/", 1)[-1]:
            continue
        if any(a.endswith(b"diversion.py") for a in argv[1:] if a):
            out.append(pid)
    return sorted(out)


def _refuse_if_another_run_is_live() -> None:
    """Два harness'а одновременно портят и восстанавливают одни файлы.

    23 сентября это произошло: забытый прогон с `timeout 1800` пережил
    уведомление о завершении своей задачи, и полчаса показаний были про
    гонку, а не про код — «после восстановления набор красный» и счётчик
    якорей, менявшийся между тремя проверками подряд.

    Уведомление сообщает о завершении ОБОЛОЧКИ, а не порождённого ею
    процесса. Поэтому проверяется процесс.
    """
    others = _live_harness_pids()
    if others:
        raise SystemExit(
            f"уже идёт прогон диверсий: {others}. Два harness'а правят одни "
            f"файлы навстречу друг другу, и показания становятся про гонку, "
            f"а не про код. Дождитесь или снимите тот процесс.")


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
    ("юнит отдаёт чужие ключи безнаказанно", "simulation/s5b_shard.py",
     '            if name[0] not in unit.keys:\n'
     '                raise MergeRefused(f"юнит прислал чужой ключ: {name[0]!r}")',
     "            pass",
     ["tests.test_s5b_shard"]),
    ("неполное покрытие ключей проходит", "simulation/s5b_shard.py",
     "    if seen != set(E.KEYS):",
     "    if False:",
     ["tests.test_s5b_shard"]),
    ("жадная раскладка заменена нарезкой", "simulation/s5b_shard.py",
     "        target = min(range(shards), key=lambda i: (load[i], i))",
     "        target = len(ordered) % shards",
     ["tests.test_s5b_shard"]),
    ("тяжёлая рука больше не дробится по ключам",
     "simulation/s5b_shard.py",
     "    for groups in range(1, len(E.KEYS) + 1):",
     "    for groups in range(1, 2):",
     ["tests.test_s5b_shard"]),
    ("число шардов снова оценивается формулой", "simulation/s5b_shard.py",
     "    for count in range(start, GITHUB_MATRIX_MAX_JOBS + 1):\n"
     "        try:\n"
     "            check_platform_limits(assign(units, count))\n"
     "        except PlanRefused:\n"
     "            continue\n"
     "        return count",
     "    return start",
     ["tests.test_s5b_shard"]),
    ("имя задания зависит от раскладки", "simulation/s5b_shard.py",
     '        raw = f"{self.arm}|{self.look}|" + ";".join(repr(k) for k in self.keys)',
     '        raw = f"{self.arm}|{self.look}|{self.weight}|" + ";".join(repr(k) for k in self.keys)',
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
    ("контраст берёт внутренние края вместо внешних",
     "simulation/s5b_escalation.py",
     "    return (treated_low.low - control_high.high,\n"
     "            treated_high.high - control_low.low)",
     "    return (treated_low.high - control_high.low,\n"
     "            treated_high.low - control_low.high)",
     ["tests.test_s5b_escalation"]),
    ("ранний tau подменяется поздним просмотром",
     "../../execution/s5b_execution/ledger.py",
     "        if identity in self._settled:\n"
     "            # УЖЕ ОСТАНОВИЛСЯ. Свежая копия не заменяет ничего.\n"
     "            self.ignored_because_already_settled += 1\n"
     "            return\n",
     "        if identity in self._settled:\n"
     "            self.ignored_because_already_settled += 1\n",
     ["tests.test_s5b_execution"]),
    ("ступени впитываются в любом порядке",
     "../../execution/s5b_execution/ledger.py",
     "        if self._absorbed and look <= self._absorbed[-1]:\n"
     "            raise LedgerRefused(",
     "        if False:\n"
     "            raise LedgerRefused(",
     ["tests.test_s5b_execution"]),
    ("огибающая стоимости заменена средним",
     "../../execution/s5b_execution/cost.py",
     "    at_fit = max(a + b * max(rate, 0.0) for a, b in RUNNER_FITS)",
     "    at_fit = (sum(a + b * max(rate, 0.0) for a, b in RUNNER_FITS)\n"
     "              / len(RUNNER_FITS))",
     ["tests.test_s5b_execution"]),
    ("неизмеренная экономия деления ключей подставлена константой",
     "../../execution/s5b_execution/cost.py",
     "UNDIVIDED_SHARE: float | None = None",
     "UNDIVIDED_SHARE: float | None = 0.05",
     ["tests.test_s5b_execution"]),
    ("бюджет шарда возвращён к пробитому",
     "../../execution/s5b_execution/cost.py",
     "SHARD_BUDGET_HOURS = 2.5",
     "SHARD_BUDGET_HOURS = 4.0",
     ["tests.test_s5b_execution"]),
    ("полнота набора выводится из приехавшего, а не из манифеста",
     "../../execution/s5b_execution/cli.py",
     "    expected = _expected_units(directory, look, also)\n"
     "    unit_of = {u.task_id: u for u in expected}",
     "    expected = [S.Unit(arm=p[\"arm\"], look=p[\"look\"],\n"
     "                      keys=tuple(tuple(k) for k in p[\"keys\"]),\n"
     "                      weight=0.0) for p in payloads]\n"
     "    unit_of = {u.task_id: u for u in expected}",
     ["tests.test_s5b_execution"]),
    ("отпечаток части не пересчитывается из содержимого",
     "../../execution/s5b_execution/identity.py",
     "        got = recompute_digest(payload)\n"
     "        if got != payload[\"digest\"]:",
     "        got = payload[\"digest\"]\n"
     "        if got != payload[\"digest\"]:",
     ["tests.test_s5b_execution"]),
    ("родство якоря и заявки не доказывается",
     "../../execution/s5b_execution/guard.py",
     "    if done.returncode != 0:\n"
     "        raise BoundaryViolated(\n"
     "            f\"якорь {pin} не является предком заявки {head}\")",
     "    if False:\n"
     "        raise BoundaryViolated(\n"
     "            f\"якорь {pin} не является предком заявки {head}\")",
     ["tests.test_s5b_execution"]),
    ("пустой diff принимается за отсутствие посторонних правок",
     "../../execution/s5b_execution/guard.py",
     "    if paths != [REQUEST_PATH]:",
     "    if paths not in ([REQUEST_PATH], []):",
     ["tests.test_s5b_execution"]),
    ("проверяются только две вершины научного графа",
     "../../execution/s5b_execution/guard.py",
     'SCIENCE_NAMESPACES = ("simulation", "coarsening")',
     'SCIENCE_NAMESPACES = ("simulation",)',
     ["tests.test_s5b_execution"]),
    ("отпечаток воркфлоу не сверяется",
     "../../execution/s5b_execution/guard.py",
     "    if got != expected:\n"
     "        raise BoundaryViolated(\n"
     "            f\"воркфлоу {path}: отпечаток {got}, заявлен {expected} — \"",
     "    if False:\n"
     "        raise BoundaryViolated(\n"
     "            f\"воркфлоу {path}: отпечаток {got}, заявлен {expected} — \"",
     ["tests.test_s5b_execution"]),
    ("граница импортов науки не проверяется",
     "../../execution/s5b_execution/guard.py",
     "        if not where.is_relative_to(root):",
     "        if False:",
     ["tests.test_s5b_execution"]),
    ("после пина разрешено менять что угодно",
     "../../execution/s5b_execution/guard.py",
     "    paths = sorted(paths)\n"
     "    if paths != [REQUEST_PATH]:",
     "    paths = sorted(paths)\n"
     "    if False:",
     ["tests.test_s5b_execution"]),
    ("отпечаток входа не сверяется",
     "../../execution/s5b_execution/cli.py",
     "        if index == 0 and expected_digest and got != expected_digest:",
     "        if False:",
     ["tests.test_s5b_execution"]),
    ("история заявки обрезана — diff пин..заявка немой",
     "../../.github/workflows/s5b-stage1.yml",
     "          # нужна история, иначе diff пин..заявка не построить\n"
     "          fetch-depth: 0\n",
     "",
     ["tests.test_s5b_workflows"]),
    ("многострочный run: снова плоский скаляр",
     "../../.github/workflows/s5b-stage1.yml",
     "        run: |\n"
     "          python3 -B -c \"import sys; sys.path[:0] = \\\n",
     "        run: python3 -B -c \"import sys; sys.path[:0] = \\\n",
     ["tests.test_s5b_workflows"]),
    ("воркфлоу зовёт флаг, которого у CLI нет",
     "../../.github/workflows/s5b-stage1.yml",
     "            --manifest plan/manifest.json \\\n",
     "            --plan plan/manifest.json \\\n",
     ["tests.test_s5b_workflows"]),
    ("вычисляющее задание берёт код с коммита-заявки",
     "../../.github/workflows/s5b-stage1.yml",
     "    steps:\n"
     "      - uses: actions/checkout@v7\n"
     "        with:\n"
     "          ref: ${{ env.SCIENCE_SHA }}\n"
     "          path: science\n"
     "      - uses: actions/checkout@v7\n"
     "        with:\n"
     "          ref: ${{ env.EXECUTION_SHA }}\n"
     "          path: exec\n"
     "      - uses: actions/setup-python@v7\n"
     "        with:\n"
     "          python-version: '3.11'\n"
     "      - uses: actions/download-artifact@v8\n"
     "        with:\n"
     "          name: s5b-manifest-",
     "    steps:\n"
     "      - uses: actions/checkout@v7\n"
     "        with:\n"
     "          ref: ${{ github.sha }}\n"
     "          path: science\n"
     "      - uses: actions/checkout@v7\n"
     "        with:\n"
     "          ref: ${{ env.EXECUTION_SHA }}\n"
     "          path: exec\n"
     "      - uses: actions/setup-python@v7\n"
     "        with:\n"
     "          python-version: '3.11'\n"
     "      - uses: actions/download-artifact@v8\n"
     "        with:\n"
     "          name: s5b-manifest-",
     ["tests.test_s5b_workflows"]),
    ("ранний tau теряется при обороте через чекпойнт",
     "../../execution/s5b_execution/ledger.py",
     '                tau=row["tau"], payload=dict(row["payload"]))',
     '                tau=max(data["looks_absorbed"]),\n'
     '                payload=dict(row["payload"]))',
     ["tests.test_s5b_execution"]),
    ("чекпойнт принимается без сверки отпечатка",
     "../../execution/s5b_execution/ledger.py",
     '        got = out.digest()\n        if got != data["ledger_digest"]:',
     '        got = out.digest()\n        if False:',
     ["tests.test_s5b_execution"]),
    ("переиспользуется часть чужого SCIENCE_SHA",
     "../../execution/s5b_execution/resume.py",
     "    if was != science_sha:", "    if False:",
     ["tests.test_s5b_execution"]),
    ("юнит, посчитанный дважды, молча принимается",
     "../../execution/s5b_execution/resume.py",
     "    both = sorted(set(reused) & set(fresh))", "    both = []",
     ["tests.test_s5b_execution"]),
    ("матрица снова забирает столько слотов, сколько найдёт",
     "../../.github/workflows/s5b-stage1.yml",
     "      max-parallel: 6\n", "",
     ["tests.test_s5b_workflows"]),
    ("предел параллелизма разошёлся с планировщиком",
     "../../execution/s5b_execution/cost.py",
     "MAX_PARALLEL = 6", "MAX_PARALLEL = 20",
     ["tests.test_s5b_workflows"]),
    ("запланированная рука вне замороженной сетки проходит",
     "../../execution/s5b_execution/cli.py",
     "    stray = sorted(scheduled - canonical)", "    stray = []",
     ["tests.test_s5b_execution"]),
    ("руки сверяются с приехавшим вместо замороженной сетки",
     "../../execution/s5b_execution/cli.py",
     '    canonical = {a["tag"] for a in S.production_arms()}',
     '    canonical = {p["arm"] for p in payloads}',
     ["tests.test_s5b_execution"]),
    ("происхождение переиспользованных частей не записывается",
     "../../execution/s5b_execution/cli.py",
     '        "reused": reuse_origin,\n', "",
     ["tests.test_s5b_execution"]),
    ("научные координаты части не сверяются с манифестом",
     "../../execution/s5b_execution/resume.py",
     '        if payload["arm"] != row["arm"] or payload["keys"] != row["keys"]:',
     "        if False:",
     ["tests.test_s5b_execution"]),
    ("цепочка возобновления снова сводится к одному прогону",
     "../../execution/s5b_execution/cli.py",
     "    mine = _declared_by(directory, look)\n    if not also:\n"
     "        return mine",
     "    mine = _declared_by(directory, look)\n    if True:\n"
     "        return mine",
     ["tests.test_s5b_execution"]),
    ("продолжение может объявить юнит вне цепочки",
     "../../execution/s5b_execution/cli.py",
     "    stray = sorted(u.task_id for u in mine if u.task_id not in by_id)\n",
     "    stray = []\n",
     ["tests.test_s5b_execution"]),
    ("обрезанная цепочка принимается планом",
     "../../execution/s5b_execution/cli.py",
     "            short = sorted(whole - declared)\n",
     "            short = []\n",
     ["tests.test_s5b_execution"]),
    ("третий прогон цепочки скачивается с условием первого",
     "../../.github/workflows/s5b-stage1.yml",
     "      - if: ${{ needs.plan.outputs.resume_run_3 != '' }}\n",
     "      - if: ${{ needs.plan.outputs.resume_run != '' }}\n",
     ["tests.test_s5b_workflows"]),
    ("манифест цепочки берётся у продолжения",
     "../../.github/workflows/s5b-stage1.yml",
     "      # манифест — ТОЛЬКО от первого прогона цепочки\n"
     "      - if: ${{ needs.plan.outputs.resume_run != '' }}\n"
     "        uses: actions/download-artifact@v8\n"
     "        with:\n"
     "          path: resumed\n"
     "          name: s5b-manifest-${{ needs.plan.outputs.look }}\n"
     "          run-id: ${{ needs.plan.outputs.resume_run }}\n",
     "      # манифест — ТОЛЬКО от первого прогона цепочки\n"
     "      - if: ${{ needs.plan.outputs.resume_run_2 != '' }}\n"
     "        uses: actions/download-artifact@v8\n"
     "        with:\n"
     "          path: resumed\n"
     "          name: s5b-manifest-${{ needs.plan.outputs.look }}\n"
     "          run-id: ${{ needs.plan.outputs.resume_run_2 }}\n",
     ["tests.test_s5b_workflows"]),
    ("потолок цепочки снят",
     "../../.github/workflows/s5b-stage1.yml",
     '          if [ "$#" -gt 3 ]; then\n',
     '          if [ "$#" -gt 99 ]; then\n',
     ["tests.test_s5b_workflows"]),
    ("калибровка режет ключи своей копией, а не раскладкой планировщика",
     "../../execution/s5b_execution/calibrate.py",
     "    return str(groups), key_slices(groups)",
     "    return str(groups), ((KEYS,) if groups == 1 else tuple(\n"
     "        KEYS[i::groups] for i in range(groups)))",
     ["tests.test_s5b_calibration"]),
    ("сверка делёного с неделёным не смотрит на значения",
     "../../execution/s5b_execution/calibrate.py",
     "    differing = [name for name in sorted(set(baseline) & set(merged), key=repr)\n"
     "                 if _as_tuple(baseline[name]) != _as_tuple(merged[name])]",
     "    differing = []",
     ["tests.test_s5b_calibration"]),
    ("доли вариантов усредняются в одно удобное число",
     "../../execution/s5b_execution/calibrate.py",
     '        out[f"s_{g}"] = round((total / base - 1.0) / (g - 1), 6)',
     '        out["s"] = round((total / base - 1.0) / (g - 1), 6)',
     ["tests.test_s5b_calibration"]),
    ("охранник времени не мешает начать невлезающий вариант",
     "../../execution/s5b_execution/calibrate.py",
     "        if 1 in totals and left < need:",
     "        if False:",
     ["tests.test_s5b_calibration"]),
    ("разрез ключей теряет хвост",
     "../../execution/s5b_execution/scheduler.py",
     "    return tuple(KEYS[i:i + size] for i in range(0, len(KEYS), size))",
     "    return tuple(KEYS[i:i + size] for i in range(0, len(KEYS) - 1, size))",
     ["tests.test_s5b_calibration", "tests.test_s5b_execution"]),
    ("охранник времени калибровки съедает весь потолок задания",
     "../../.github/workflows/s5b-split-calibration.yml",
     '  GUARD_MINUTES: "330"',
     '  GUARD_MINUTES: "350"',
     ["tests.test_s5b_workflows"]),
    ("калибровку пускают на дорогую ступень",
     "../../.github/workflows/s5b-split-calibration.yml",
     '          if [ "$LOOK" != "4000" ]; then\n',
     '          if [ "$LOOK" = "0" ]; then\n',
     ["tests.test_s5b_workflows"]),
    ("воркфлоу закреплён на слое, где нужного кода ещё нет",
     "../../.github/workflows/s5b-split-calibration.yml",
     '  EXECUTION_SHA: "2f36713ab66ac91d50b64a96dd7e8054c23ac9f4"',
     '  EXECUTION_SHA: "068e13ffc8e4505c54ee25c8362a9e991462fcbc"',
     ["tests.test_s5b_workflows"]),
    ("вариант из подгонки принимается как проверка",
     "../../execution/s5b_execution/keycost.py",
     '    if groups in model["fitted_on"]:',
     "    if False:",
     ["tests.test_s5b_keycost"]),
    ("проверка модели смотрит только на сумму, а не на группы",
     "../../execution/s5b_execution/keycost.py",
     '    errors = ([abs(r["relative_error"]) for r in out["rows"]]\n'
     '              + [abs(out["C"]["relative_error"]),\n'
     '                 abs(out["W"]["relative_error"])])',
     '    errors = [abs(out["C"]["relative_error"])]',
     ["tests.test_s5b_keycost"]),
    ("допуск проверки модели распущен",
     "../../execution/s5b_execution/keycost.py",
     "HELDOUT_TOLERANCE = 0.05",
     "HELDOUT_TOLERANCE = 0.5",
     ["tests.test_s5b_keycost"]),
    ("факториальная раскладка забыла про days",
     "../../execution/s5b_execution/keycost.py",
     "        bins[(2 * h + x + 2 * d + t) % groups].append(key)",
     "        bins[(2 * h + x + t) % groups].append(key)",
     ["tests.test_s5b_keycost"]),
    ("PoC модели стоимости тихо подключён к планировщику",
     "../../execution/s5b_execution/cli.py",
     "from .ledger import Ledger\n",
     "from .ledger import Ledger\nfrom . import keycost  # noqa: F401\n",
     ["tests.test_s5b_keycost"]),
    ("CI снова берёт мелкий клон без закреплённых коммитов",
     "../../.github/workflows/annotation-web.yml",
     "          fetch-depth: 0\n",
     "          fetch-depth: 1\n",
     ["tests.test_s5b_workflows"]),
    ("охранник снова считает худший случай s = 1",
     "../../execution/s5b_execution/calibrate.py",
     "GUARD_SHARE_UNKNOWN = 0.25",
     "GUARD_SHARE_UNKNOWN = 1.0",
     ["tests.test_s5b_calibration"]),
    ("зонд смешивает maximise внутри клетки",
     "../../execution/s5b_execution/calibrate.py",
     "        cells.setdefault((key[2], key[3]), []).append(key)",
     "        cells.setdefault((key[2],), []).append(key)",
     ["tests.test_s5b_calibration"]),
    ("промежуточная запись варианта не пишется",
     "../../execution/s5b_execution/calibrate.py",
     "        pathlib.Path(path).write_text(json.dumps(record, sort_keys=True))",
     "        pass",
     ["tests.test_s5b_calibration"]),
    ("Gate A сравнивает абсолютные секунды вместо профиля",
     "../../execution/s5b_execution/keycost.py",
     '    base = model["per_key"][1.0]',
     "    base = 1.0",
     ["tests.test_s5b_keycost"]),
    ("неравная клетка не убивает равномерность",
     "../../execution/s5b_execution/keycost.py",
     "    elif spread > CELLS_EFFECT_SPREAD:",
     "    elif False:",
     ["tests.test_s5b_keycost"]),
    ("расхождение s внутри прогона выкинуто из вердикта Gate A",
     "../../execution/s5b_execution/keycost.py",
     '                                    "s_within_run", "s_across_runs",\n',
     '                                    "s_across_runs",\n',
     ["tests.test_s5b_keycost"]),
    ("A-F1: отложенные factorial6/cells6 выкинуты из вердикта",
     "../../execution/s5b_execution/threelevel.py",
     '    elif max(abs(c["F6_C_error"]), abs(c["F6_W_error"]),\n'
     '             abs(c["C6_C_error"])) > HELDOUT_TOLERANCE:\n',
     "    elif False:\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: накладные снова изображают стоимость ключей",
     "../../execution/s5b_execution/threelevel.py",
     '    overhead = est["A"] + sum(est["B"].values())\n',
     "    overhead = 0.0\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: отрицательная B зажата в ноль",
     "../../execution/s5b_execution/threelevel.py",
     '    b = {d: m[f"P_d{d:g}"]["total"] - m["P2"]["total"] for d in DELTAS}\n',
     '    b = {d: max(0.0, m[f"P_d{d:g}"]["total"] - m["P2"]["total"])\n'
     "         for d in DELTAS}\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: потолок шума снят",
     "../../execution/s5b_execution/threelevel.py",
     '    if n["group_relative"] > NOISE_CEILING:\n',
     "    if False:\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: охранник бюджета начинает то, что не влезет",
     "../../execution/s5b_execution/threelevel.py",
     "        if elapsed + need > budget:\n",
     "        if False:\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: перерасход бюджета не делает прогон неполным",
     "../../execution/s5b_execution/threelevel.py",
     "        if clock() - start > budget:\n",
     "        if False:\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: локальный gate тихо подключён к планировщику",
     "../../execution/s5b_execution/cli.py",
     "from .ledger import Ledger\n",
     "from .ledger import Ledger\nfrom . import threelevel  # noqa: F401\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: P_dδ не делит свой блок",
     "../../execution/s5b_execution/threelevel.py",
     "        half = len(own) // 2\n",
     "        half = len(own)\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: наука не сверяется с замороженной",
     "../../execution/s5b_execution/threelevel.py",
     "    if changed:\n",
     "    if False:\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: пропавший повтор не делает прогон неполным",
     "../../execution/s5b_execution/threelevel.py",
     '    complete = (not record.get("incomplete")\n'
     "                and all(len(by.get(lbl, ())) == REPEATS for lbl in labels))\n",
     '    complete = not record.get("incomplete")\n',
     ["tests.test_s5b_threelevel"]),
    ("A-F1: неравные клетки не убивают равномерность",
     "../../execution/s5b_execution/threelevel.py",
     '    elif c["uniformity_status"] == "KILL_UNIFORM_WITHIN_BLOCK":\n',
     "    elif False:\n",
     ["tests.test_s5b_threelevel"]),
    ("A-F1: потолок шума поднят после замера",
     "../../execution/s5b_execution/threelevel.py",
     "NOISE_CEILING = 0.02\n",
     "NOISE_CEILING = 0.12\n",
     ["tests.test_s5b_threelevel"]),
    ('A-F2a: ΣB снова из отложенного Q6',
     "../../execution/s5b_execution/af2a.py",
     '    sb = (totals["F6"] - totals["P1"] - 5 * a) / 5\n',
     '    sb = totals["Q6"] - totals["P1"] - 5 * a\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: отрицательная ΣB зажата в ноль',
     "../../execution/s5b_execution/af2a.py",
     '    sb = (totals["F6"] - totals["P1"] - 5 * a) / 5\n',
     '    sb = max(0.0, (totals["F6"] - totals["P1"] - 5 * a) / 5)\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: отложенные выкинуты из вердикта',
     "../../execution/s5b_execution/af2a.py",
     '    if max(abs(e) for e in c["heldout_errors"].values()) > HELDOUT_TOLERANCE:\n',
     '    if False:\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: контроль шума равномерности снят',
     "../../execution/s5b_execution/af2a.py",
     '    if out["factorial_spread"] > UNIFORM_CONTROL_SPREAD:\n',
     '    if False:\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: остаток <= 0 не останавливает зонд',
     "../../execution/s5b_execution/af2a.py",
     '    if min(rf + rc) <= 0:\n',
     '    if False:\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: KILL равномерности не выносится',
     "../../execution/s5b_execution/af2a.py",
     '    if u["uniformity_status"] == "KILL_UNIFORM_WITHIN_BLOCK":\n',
     '    if False:\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: шаг 0 не проверяет шум',
     "../../execution/s5b_execution/af2a.py",
     '    if _spread(totals) > NOISE_SPREAD:\n',
     '    if False:\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: шаг 0 не проверяет окно просмотра',
     "../../execution/s5b_execution/af2a.py",
     '    if not lo <= sum(totals) / len(totals) <= hi:\n',
     '    if False:\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: исполнитель идёт дальше шумного шага 0',
     "../../execution/s5b_execution/af2a.py",
     '    if gate is not None:\n        record["stopped_at_step0"] = gate\n',
     '    if False:\n        record["stopped_at_step0"] = gate\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: порядок раундов снова простой сдвиг',
     "../../execution/s5b_execution/af2a.py",
     'ROUND_POSITIONS = ((0, 1, 2, 3, 4, 5), (2, 3, 4, 5, 0, 1), (5, 3, 1, 0, 4, 2))\n',
     'ROUND_POSITIONS = ((0, 1, 2, 3, 4, 5), (2, 3, 4, 5, 0, 1), (4, 5, 0, 1, 2, 3))\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: кольцо H4 разорвано',
     "../../execution/s5b_execution/af2a.py",
     '    return tuple(b[j][:half] + b[j - 1][half:] for j in range(len(b)))\n',
     '    return tuple(b[j][:half] + b[j][half:] for j in range(len(b)))\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: охранник бюджета начинает то, что не влезет',
     "../../execution/s5b_execution/af2a.py",
     '        if elapsed + need > budget:\n',
     '        if False:\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: перерасход бюджета не делает прогон неполным',
     "../../execution/s5b_execution/af2a.py",
     '        if clock() - start > budget:\n',
     '        if False:\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: наука не сверяется с замороженной',
     "../../execution/s5b_execution/af2a.py",
     '    if changed:\n',
     '    if False:\n',
     ["tests.test_s5b_af2a"]),
    ('A-F2a: локальный gate тихо подключён к планировщику',
     "../../execution/s5b_execution/cli.py",
     'from .ledger import Ledger\n',
     'from .ledger import Ledger\nfrom . import af2a  # noqa: F401\n',
     ["tests.test_s5b_af2a"]),
    ("отсечка инициации игнорируется", "coarsening/bounded.py",
     "    if initiation_end is None:\n        return start + horizon <= window_end\n"
     "    return start < initiation_end",
     "    return start + horizon <= window_end",
     ["tests.test_bounded", "tests.test_s5b_prereg"]),
)


def main() -> int:
    _refuse_if_another_run_is_live()
    self_test()
    print("  самопроверка: внесённая правка видна, откат виден")
    for name, path, old, new, modules in DIVERSIONS:
        diversion(path, old, new, modules)
        print(f"  поймана: {name}")
    print(f"{len(DIVERSIONS)} диверсий, все пойманы")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
