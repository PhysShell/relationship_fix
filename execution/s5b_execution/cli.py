"""Командная оболочка слоя исполнения.

    plan    --look L [--prior D ...]   манифест ступени с учётом реестра
    run     --look L --shard N         посчитать свой мешок замороженным run_unit
    reduce  --look L --prior D ...     свести концы, каждый на своём tau
    pilot   --look 64000 --groups G    манифест пилота: блок δ при раскладке G
    judge   --look 64000 --parts D     вердикт пилота по его частям

Ступень в несколько прогонов (`multirun`):

    plan --multirun [--resume D]       ОДИН полный манифест; продолжение
                                       обязано спланировать тот же
    select --run R [--resume D]        партия прогона целиком и повторы
                                       сверх неё, до потолка матрицы
    progress --parts D --batch F       итог прогона: PARTIAL / COMPLETE /
                                       STOP / KILL; наука не сводится

`reduce` — не «слияние ради полноты». Он строит реестр по ВОСХОДЯЩИМ
ступеням и отдаёт каждый конец на его собственном `tau`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import resource
import sys
import time

from simulation import s5b_prereg as P
from simulation import s5b_shard as S

from . import (calibrate, cost, guard, multirun, provenance, reduction,
               resume, scheduler)
from .identity import NOT_PART_FILES, ArtifactRefused, load_unit_payloads
from .ledger import Ledger

LOOKS = tuple(P.LOOKS) if hasattr(P, "LOOKS") else None


def _ladder():
    from simulation import s5b_precision as PRC
    return tuple(PRC.LOOKS)


def _declared_by(directory, look: int):
    """Юниты, ОБЪЯВЛЕННЫЕ манифестом одного каталога."""
    path = pathlib.Path(directory) / "manifest.json"
    if not path.exists():
        raise SystemExit(f"{directory}: нет manifest.json — объявить нечего")
    manifest = json.loads(path.read_text())
    if manifest["look"] != look:
        raise SystemExit(f"{directory}: манифест на ступень {manifest['look']}, "
                         f"а файлы на {look}")
    return [S.Unit(arm=u["arm"], look=u["look"],
                   keys=tuple(tuple(k) for k in u["keys"]), weight=0.0)
            for u in manifest["units"]]


def _expected_units(directory, look: int, also: str = ""):
    """Юниты, ОБЪЯВЛЕННЫЕ ступенью — а ступень может идти в несколько прогонов.

    Читается манифест, а не приехавшие файлы. Вывести ожидаемое из
    полученного значило бы сделать проверку полноты тавтологией: она бы
    проходила всегда, ровно потому что сравнивает набор сам с собой.

    Прогон-продолжение объявляет ОСТАТОК: `plan --resume` исключает из
    манифеста то, что уже посчитано. Поэтому после возобновления каталог
    сведения законно содержит части, которых в его собственном манифесте
    нет, — и сверка только с ним отвергала полный набор как «лишние
    руки». Проверено запуском: и двухчастная, и трёхчастная цепочка
    падали на сведении, то есть `--resume` не доходил до результата ни
    разу.

    Объявленное ступенью = манифест ЭТОГО прогона плюс манифест цепочки,
    из которой берутся переиспользованные части. С гейтом: продолжение
    обязано объявлять ПОДМНОЖЕСТВО — выдумать юнит, которого ступень не
    объявляла, оно не может.
    """
    mine = _declared_by(directory, look)
    if not also:
        return mine
    prior = _declared_by(also, look)
    by_id = {u.task_id: u for u in prior}
    stray = sorted(u.task_id for u in mine if u.task_id not in by_id)
    if stray:
        raise SystemExit(
            f"{directory}: продолжение объявило юниты, которых нет в "
            f"манифесте цепочки {also}: {stray[:3]}")
    for unit in mine:
        by_id[unit.task_id] = unit
    return sorted(by_id.values(), key=lambda u: u.task_id)


def _verify_arms(directory, payloads, scheduled: set[str]) -> None:
    """Три РАЗНЫХ множества рук, и их нельзя сливать.

        canonical  вся сетка замороженной науки — что вообще существует;
        scheduled  что объявил манифест ЭТОЙ ступени;
        arrived    что реально приехало.

    Требование `arrived == canonical` было верно ровно до тех пор, пока
    лестница считала всю сетку на каждой ступени. После остановки это
    неверно: рука, все концы которой закрылись, законно не планируется
    дальше, и её отсутствие — правильная работа реестра, а не пропажа.

    Проверяется поэтому: `arrived == scheduled` (ничего не потеряно и
    ничего лишнего) и `scheduled` подмножество `canonical` (ничего
    выдуманного). Каноническое множество берётся из ЗАМОРОЖЕННОЙ науки и
    остаётся утверждением, независимым от манифеста.
    """
    canonical = {a["tag"] for a in S.production_arms()}
    stray = sorted(scheduled - canonical)
    if stray:
        raise SystemExit(
            f"{directory}: манифест запланировал руки вне сетки замороженной "
            f"науки: {stray[:3]}")
    arrived = {p["arm"] for p in payloads}
    if arrived != scheduled:
        raise SystemExit(
            f"{directory}: приехавшие руки не совпали с запланированными; "
            f"нет {sorted(scheduled - arrived)[:3]}, лишние "
            f"{sorted(arrived - scheduled)[:3]}")


def _verify_with_frozen_merge(directory, look: int, payloads,
                              also: str = "") -> int:
    """Собрать концы КАЖДОЙ руки замороженным `s5b_shard.merge`.

    Зовётся на ВСЕХ ступенях, а не только там, где рука дробится. На 4000
    и 16000 у руки одна группа ключей и слияние тривиально — но именно
    «тривиальный и потому не исполняемый путь» уронил прогон 35805206374:
    шаг merge был единственным, который до того не отрабатывал ни разу.
    """
    expected = _expected_units(directory, look, also)
    unit_of = {u.task_id: u for u in expected}
    _verify_arms(directory, payloads, {u.arm for u in expected})
    missing = [p["task_id"] for p in payloads if p["task_id"] not in unit_of]
    if missing:
        raise SystemExit(f"{directory}: файлы вне манифеста: {missing}")
    for arm in sorted({u.arm for u in expected}):
        reduction.merge_arm(arm, look, payloads, expected, unit_of)
    return len(expected)


def _prior_state(args) -> tuple[Ledger | None, dict]:
    """Состояние прошлых ступеней: из ЧЕКПОЙНТА либо из сырых частей.

    Чекпойнт предпочтительнее и на 64000 обязателен: сырые части 16000 не
    содержат концов, остановившихся на 4000, поэтому собрать из них
    полный реестр нельзя в принципе.
    """
    if args.checkpoint:
        data = json.loads(pathlib.Path(args.checkpoint).read_text())
        led = Ledger.from_checkpoint(data)
        _anchor_checkpoint(args, data)
        return led, {args.checkpoint: data.get("ledger_digest", "")}
    if args.prior:
        return _ledger_from(args.prior, args.prior_digest)
    return None, {}


def _anchor_checkpoint(args, data: dict) -> None:
    """Чекпойнт привязан к КОНКРЕТНОЙ ступени отпечатком её реестра.

    `from_checkpoint` доказывает лишь, что файл согласован сам с собой.
    Какой именно прогон он описывает, говорит `--prior-digest`: у сырых
    частей это отпечаток частей, у чекпойнта — `ledger_digest`. Совместимый
    чекпойнт другого прогона без этой сверки прошёл бы молча.
    """
    got = data.get("ledger_digest", "")
    if args.prior_digest and got != args.prior_digest:
        raise SystemExit(
            f"{args.checkpoint}: реестр {got}, заявлен {args.prior_digest} — "
            f"приехал не тот прогон")


def _ledger_from(prior_dirs, expected_digest: str = "",
                 also: str = "") -> tuple[Ledger, dict]:
    """Реестр по каталогам ступеней, впитанным ПО ВОЗРАСТАНИЮ.

    `expected_digest` относится к САМОЙ РАННЕЙ ступени набора. `prior_run`
    якорем не является: `task_id` кодирует научные координаты, а не байты
    реализации, поэтому совместимый чужой прогон даст ровно те же имена
    файлов. Отпечаток — единственное, что привязывает вход к конкретному
    вычислению.

    `also` — каталог цепочки возобновления. Относится ТОЛЬКО к последней,
    текущей ступени: у прошлых ступеней свои полные манифесты, и
    расширять их объявленный состав нечем и незачем.
    """
    ledger, inputs, loaded = Ledger(), {}, []
    for directory in prior_dirs:
        payloads = load_unit_payloads(directory)
        looks = {p["look"] for p in payloads}
        if len(looks) != 1:
            raise SystemExit(f"{directory}: смешаны ступени {sorted(looks)}")
        loaded.append((looks.pop(), payloads, directory))
    for index, (look, payloads, directory) in enumerate(
            sorted(loaded, key=lambda t: t[0])):
        last = index == len(loaded) - 1
        _verify_with_frozen_merge(directory, look, payloads,
                                  also if last else "")
        got = provenance.digest_of(payloads)
        if index == 0 and expected_digest and got != expected_digest:
            raise SystemExit(
                f"{directory}: отпечаток входа {got}, заявлен "
                f"{expected_digest} — приехал не тот прогон")
        ledger.absorb(look, payloads)
        inputs[str(directory)] = got
    return ledger, inputs


def _plan_multirun(args, out, checks, ledger, inputs) -> int:
    """План многопрогонной ступени: ОДИН полный манифест на все прогоны.

    Упаковка — наименьшее число заданий в бюджете шарда, без потолка
    матрицы: его держит партия. Продолжение планирует ступень заново из
    тех же входов и обязано получить ТОТ ЖЕ манифест; тогда в каталог
    ложится манифест первого прогона байт в байт, с его провенансом.
    Расхождение — отказ до счёта: ступень, спланированная иначе, уже не
    та ступень, части которой собраны.
    """
    try:
        units = multirun.units(args.look, ledger)
        buckets = multirun.pack(units, cost.SHARD_BUDGET_HOURS * 3600.0)
        multirun.check_jobs(buckets)
    except multirun.MultiRunRefused as exc:
        raise SystemExit(f"ПЛАН НЕ СОБРАН: {exc}")
    rows = []
    for shard, bucket in enumerate(buckets):
        for unit in bucket:
            rows.append({"task_id": unit.task_id, "arm": unit.arm,
                         "look": unit.look, "shard": shard,
                         "keys": [list(k) for k in unit.keys]})
    rows.sort(key=lambda r: r["task_id"])
    manifest = {"look": args.look, "shards": len(buckets), "units": rows,
                "shard_seconds": [round(sum(u.weight for u in b), 1)
                                  for b in buckets]}
    try:
        multirun.check(manifest)
    except multirun.MultiRunRefused as exc:
        raise SystemExit(f"ПЛАН НЕ СОБРАН: {exc}")
    digest = multirun.body_digest(manifest)
    out.mkdir(parents=True, exist_ok=True)
    if args.resume:
        chain = resume.load_manifest(args.resume)
        if multirun.body(chain) != multirun.body(manifest):
            raise SystemExit(
                f"{args.resume}: манифест цепочки {multirun.body_digest(chain)} "
                f"не совпадает с планом этого прогона {digest} — ступень "
                f"спланирована иначе, продолжать её нельзя")
        (out / "manifest.json").write_bytes(
            (pathlib.Path(args.resume) / "manifest.json").read_bytes())
    else:
        record = provenance.collect(inputs=inputs, manifest_digest=digest)
        record["look"] = args.look
        record["prior_run"] = args.prior_run
        record["prior_digest"] = args.prior_digest
        record["preflight"] = checks
        manifest["provenance"] = record
        (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    print(json.dumps({"count": len(buckets), "units": len(rows),
                      "manifest_digest": digest,
                      "continued": bool(args.resume),
                      "preflight": checks,
                      "carried": 0 if ledger is None
                      else ledger.settled_count()}, sort_keys=True))
    return 0


class _Killed(Exception):
    """Научный вход не принят: KILL, а не повтор.

    Повтор положен только заданию, чей результат отсутствует или неполон,
    потому что оно упало. Часть, которая приехала, но не проходит приёмку
    (отпечаток, identity, наука, манифест), — не упавшее задание, а
    испорченный вход: пересчитать его значило бы спрятать порчу.
    """


#: Чем отказывает приёмка части. ValueError — и непарсящийся JSON.
_REFUSALS = (resume.ResumeRefused, ArtifactRefused, ValueError)


def _chain_done(args, manifest: dict) -> set[str]:
    """Выполненные юниты цепочки. Манифест цепочки — тот же, что у прогона."""
    science = os.environ.get("SCIENCE_SHA", "")
    was = (manifest.get("provenance") or {}).get("science_sha", "")
    if was != science:
        raise _Killed(
            f"манифест ступени под SCIENCE_SHA {was!r}, прогон под "
            f"{science!r} — это разные вычисления")
    if not args.resume:
        return set()
    chain = resume.load_manifest(args.resume)
    if multirun.body(chain) != multirun.body(manifest):
        raise _Killed(
            f"{args.resume}: манифест цепочки не тот, что у этого прогона")
    return _accepted(pathlib.Path(args.resume), args.look,
                     "часть прошлого прогона")


def _accepted(parts, look: int, whose: str) -> set[str]:
    """Принятые части каталога. Ни одной — пусто: прогон, где упало всё,
    законен и значит «выполнено ничего». Не принята — KILL."""
    names = [p for p in parts.glob("*.json") if p.name not in NOT_PART_FILES]
    if not names:
        return set()
    try:
        return set(resume.completed(
            parts, look=look, science_sha=os.environ.get("SCIENCE_SHA", "")))
    except _REFUSALS as exc:
        raise _Killed(f"{whose} не принята: {exc}")


def _select(args, out) -> int:
    """Задания этого прогона: его партия целиком и повторы сверх неё."""
    manifest = json.loads(pathlib.Path(args.manifest).read_text())
    if manifest["look"] != args.look:
        raise SystemExit(f"манифест на ступень {manifest['look']}, "
                         f"запрошена {args.look}")
    try:
        done = _chain_done(args, manifest)
    except _Killed as exc:
        raise SystemExit(f"KILL: {exc}")
    try:
        selection = multirun.select(
            manifest, done, run=args.run,
            cap=args.batch_cap or multirun.BATCH_CAP,
            matrix=args.run_matrix or multirun.RUN_MATRIX)
        batch = multirun.batch_manifest(manifest, selection)
    except multirun.MultiRunRefused as exc:
        raise SystemExit(f"ВЫБОР НЕ СДЕЛАН: {exc}")
    batch["provenance"] = provenance.collect(
        inputs={}, manifest_digest=selection["manifest_digest"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "batch.json").write_text(json.dumps(batch, sort_keys=True))
    print(json.dumps({"shards": selection["shards"], "run": selection["run"],
                      "units": len(selection["units"]),
                      "retries": selection["retries"],
                      "nominal": len(selection["nominal"]),
                      "carried": selection["carried"]},
                     sort_keys=True))
    return 0


def _progress(args, out) -> int:
    """Итог прогона. Наука не сводится: только сделано, упало, осталось.

    Незаконченная ступень — PARTIAL и зелёный прогон. Красный — упавшее
    выбранное задание, STOP (восстановительный прогон ступень не закроет
    или не закрыл) и KILL (научный вход не принят).
    """
    if not args.parts or not args.batch:
        raise SystemExit("итогу прогона нужны --parts и --batch")
    parts = pathlib.Path(args.parts)
    manifest = resume.load_manifest(parts)
    if manifest["look"] != args.look:
        raise SystemExit(f"манифест на ступень {manifest['look']}, "
                         f"запрошена {args.look}")
    selection = json.loads(pathlib.Path(args.batch).read_text())["selection"]
    try:
        done = _chain_done(args, manifest)
        arrived = _accepted(parts, args.look, "часть этого прогона")
        report = multirun.progress(manifest, selection, done, arrived)
    except (_Killed, multirun.MultiRunRefused) as exc:
        report = multirun.killed(str(exc), selection["run"])
        report["manifest_digest"] = multirun.body_digest(manifest)
    report["provenance"] = provenance.collect(
        inputs={}, manifest_digest=report["manifest_digest"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "progress.json").write_text(
        json.dumps(report, sort_keys=True, ensure_ascii=False))
    print(json.dumps({k: report.get(k) for k in
                      ("run", "status", "ok", "reason", "selected_units",
                       "arrived_units", "failed_shards", "done_units",
                       "remaining_units")}, sort_keys=True, ensure_ascii=False))
    return 0 if report["ok"] else 1


def _encode(results) -> list:
    return [{"key": list(name[0]), "fraction": name[1],
             "point": e.point, "low": e.low, "high": e.high,
             "radius": e.radius, "status": e.status.value, "look": e.look}
            for name, e in sorted(results.items(), key=repr)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode",
                        choices=("plan", "run", "reduce", "calibrate",
                                 "pilot", "judge", "select", "progress"))
    parser.add_argument("--look", type=int, required=True)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--arm", default="",
                        help="рука для калибровки экономии деления")
    parser.add_argument("--variants", default="1,2,4",
                        help="варианты калибровки через запятую: целое g — "
                             "смежная раскладка, cells6 — зонд по клеткам "
                             "(horizon, maximise)")
    parser.add_argument("--deadline-minutes", type=float, default=0.0,
                        help="сколько минут задания ОСТАЛОСЬ; охранник времени "
                             "не начинает вариант, который не успеет")
    parser.add_argument("--out", default="out")
    parser.add_argument("--prior", action="append", default=[])
    parser.add_argument("--manifest", default="manifest.json")
    parser.add_argument("--prior-digest", default="",
                        help="отпечаток входа: у сырых частей — их digest, у "
                             "чекпойнта — его ledger_digest")
    parser.add_argument("--prior-run", default="")
    parser.add_argument("--repo", default="")
    parser.add_argument("--pin", default="")
    parser.add_argument("--workflow", default="")
    parser.add_argument("--workflow-sha256", default="")
    parser.add_argument("--request-path", default=guard.REQUEST_PATH,
                        help="файл заявки: единственный путь, который вправе "
                             "меняться между якорем и заявкой")
    parser.add_argument("--science", default="")
    parser.add_argument("--resume", default="",
                        help="каталог частей прерванного прогона ЭТОЙ ступени")
    parser.add_argument("--checkpoint", default="",
                        help="чекпойнт реестра предыдущей ступени")
    parser.add_argument("--groups", type=int, default=0,
                        help="пилот: число групп смежной раскладки (12 или 24)")
    parser.add_argument("--block", type=float, default=0.0,
                        help="пилот: первая координата блока, например 60")
    parser.add_argument("--parts", default="",
                        help="пилот: каталог манифеста и частей для вердикта; "
                             "progress: каталог полного манифеста и частей "
                             "этого прогона")
    parser.add_argument("--multirun", action="store_true",
                        help="plan: один полный манифест ступени на все прогоны")
    parser.add_argument("--run", type=int, default=0,
                        help="select: номер прогона ступени, 1 + число прошлых")
    parser.add_argument("--batch-cap", type=int, default=0,
                        help="select: номинальная партия; по умолчанию "
                             "multirun.BATCH_CAP")
    parser.add_argument("--run-matrix", type=int, default=0,
                        help="select: потолок матрицы прогона; по умолчанию "
                             "multirun.RUN_MATRIX")
    parser.add_argument("--batch", default="",
                        help="progress: файл выбора этого прогона")
    args = parser.parse_args(argv)
    out = pathlib.Path(args.out)

    if args.mode == "pilot":
        # ПИЛОТ 64000. Ступень лестницы этим режимом НЕ считается: реестр
        # не трогается, манифест объявляет только юниты одного блока.
        from . import pilot
        checks = {}
        if args.science:
            checks["science_modules"] = guard.assert_science_comes_from(
                args.science)
        try:
            chosen = pilot.units(args.arm, args.look, args.groups, args.block)
        except pilot.PilotRefused as exc:
            raise SystemExit(f"ПИЛОТ НЕ СОБРАН: {exc}")
        manifest = pilot.manifest(chosen, groups=args.groups, block=args.block)
        body = json.dumps(manifest, sort_keys=True)
        record = provenance.collect(
            inputs={},
            manifest_digest=hashlib.sha256(body.encode()).hexdigest()[:16])
        record["look"] = args.look
        record["preflight"] = checks
        manifest["provenance"] = record
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        print(json.dumps({"shards": list(range(manifest["shards"])),
                          "units": [u["task_id"] for u in manifest["units"]],
                          "groups": args.groups, "block": args.block}))
        return 0

    if args.mode == "judge":
        from . import pilot
        if not args.parts:
            raise SystemExit("вердикту нужен --parts")
        verdict = pilot.judge(args.parts, look=args.look,
                              science_sha=os.environ.get("SCIENCE_SHA", ""))
        verdict["provenance"] = {
            "science_sha": os.environ.get("SCIENCE_SHA", ""),
            "execution_sha": os.environ.get("EXECUTION_SHA", ""),
            "request_sha": os.environ.get("REQUEST_SHA", "")}
        out.mkdir(parents=True, exist_ok=True)
        (out / "pilot-verdict.json").write_text(
            json.dumps(verdict, sort_keys=True, ensure_ascii=False))
        print(json.dumps(verdict, sort_keys=True, ensure_ascii=False, indent=1))
        # красный прогон = FAIL: вердикт виден без чтения артефакта
        return 0 if verdict["status"] == "PASS" else 1

    if args.mode == "plan":
        # PREFLIGHT. Порядок не косметический: всё, что может обрушиться
        # дёшево, обязано обрушиться ДО появления дорогой матрицы.
        # Отдельная дымовая проба проверяла бы почти то же самое и
        # добавляла бы ещё один церемониальный труп в историю проекта.
        checks: dict = {}
        if args.workflow and args.workflow_sha256:
            checks["workflow_sha256"] = guard.assert_workflow_matches(
                args.workflow, args.workflow_sha256)
        if args.repo and args.pin:
            head = os.environ.get("REQUEST_SHA", "HEAD")
            guard.assert_object_exists(args.repo, args.pin)
            guard.assert_is_ancestor(args.repo, args.pin, head)
            science = os.environ.get("EXECUTION_SHA", "")
            if science:
                guard.assert_object_exists(args.repo, science)
                guard.assert_pin_descends_from(args.repo, science, args.pin)
            changed = guard.changed_paths(args.repo, args.pin, head)
            guard.assert_request_is_only_a_signal(changed, args.request_path)
            checks["pin"] = args.pin
            checks["changed_since_pin"] = changed
        if args.science:
            checks["science_modules"] = guard.assert_science_comes_from(
                args.science)
        ledger, inputs = _prior_state(args)
        if args.multirun:
            return _plan_multirun(args, out, checks, ledger, inputs)
        done: set[str] = set()
        if args.resume:
            # ЦЕПОЧКА ОБЯЗАНА БЫТЬ ПОЛНОЙ, и проверяется это ДО счёта.
            #
            # Прогон-продолжение объявляет остаток. Если указать на него
            # как на цепочку, работа ещё более раннего прогона не видна:
            # трёхчастная цепочка запланировала 102 юнита вместо 71 и
            # молча пересчитала то, что уже было. Каталог возобновления
            # обязан нести ЧАСТИ ВСЕХ прогонов цепочки и манифест того,
            # который объявил ступень целиком.
            whole = {u.task_id for u in scheduler.units_for(args.look, ledger)}
            declared = {u.task_id for u in _declared_by(args.resume, args.look)}
            short = sorted(whole - declared)
            if short:
                raise SystemExit(
                    f"{args.resume}: манифест цепочки объявляет "
                    f"{len(declared)} юнитов из {len(whole)} — это "
                    f"продолжение, а не начало. Нужен манифест прогона, "
                    f"объявившего ступень целиком; не хватает {short[:3]}")
            got = resume.completed(args.resume, look=args.look,
                                   science_sha=os.environ.get("SCIENCE_SHA", ""))
            done = set(got)
            checks["reused"] = resume.origin(
                args.resume, look=args.look,
                science_sha=os.environ.get("SCIENCE_SHA", ""))
        units = scheduler.units_for(args.look, ledger, skip=done)
        if not units:
            raise SystemExit(
                f"все юниты ступени {args.look} уже посчитаны прошлым "
                f"прогоном: считать нечего, сразу reduce")
        count = scheduler.shards_needed(units)
        buckets = S.assign(units, count)
        scheduler.check_platform(buckets)
        # РАСКЛАДКА ПИШЕТСЯ В МАНИФЕСТ, а не выводится заново в `run`.
        # Пусть план и исполнение расходятся невозможным образом, а не
        # «одинаково считают»: сегодняшний отказ прогона был ровно из
        # расхождения двух мест, которые обязаны были совпасть.
        rows = []
        for shard, bucket in enumerate(buckets):
            for unit in bucket:
                rows.append({"task_id": unit.task_id, "arm": unit.arm,
                             "look": unit.look, "shard": shard,
                             "keys": [list(k) for k in unit.keys]})
        rows.sort(key=lambda r: r["task_id"])
        manifest = {"look": args.look, "shards": count, "units": rows}
        body = json.dumps(manifest, sort_keys=True)
        record = provenance.collect(
            inputs=inputs,
            manifest_digest=hashlib.sha256(body.encode()).hexdigest()[:16])
        record["look"] = args.look
        record["prior_run"] = args.prior_run
        record["prior_digest"] = args.prior_digest
        record["preflight"] = checks
        manifest["provenance"] = record
        # каждая строка манифеста обязана ДАВАТЬ свой task_id
        for row in rows:
            rebuilt = S.Unit(arm=row["arm"], look=row["look"],
                             keys=tuple(tuple(k) for k in row["keys"]),
                             weight=0.0)
            if rebuilt.task_id != row["task_id"]:
                raise SystemExit(f"манифест: {row['task_id']} не выводится "
                                 f"из состава юнита")
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        print(json.dumps({"shards": list(range(count)), "count": count,
                          "units": len(rows),
                          "carried": 0 if ledger is None
                          else ledger.settled_count()}))
        return 0

    if args.mode == "select":
        return _select(args, out)

    if args.mode == "progress":
        return _progress(args, out)

    if args.mode == "run":
        manifest = json.loads(
            pathlib.Path(args.manifest).read_text())
        if manifest["look"] != args.look:
            raise SystemExit(f"манифест на ступень {manifest['look']}, "
                             f"запрошена {args.look}")
        mine = [u for u in manifest["units"] if u["shard"] == args.shard]
        if not mine:
            raise SystemExit(f"в манифесте нет юнитов шарда {args.shard}")
        known = scheduler.arms()
        out.mkdir(parents=True, exist_ok=True)
        for row in mine:
            unit = S.Unit(arm=row["arm"], look=row["look"],
                          keys=tuple(tuple(k) for k in row["keys"]),
                          weight=0.0)
            if unit.task_id != row["task_id"]:
                raise SystemExit(
                    f"манифест объявил {row['task_id']}, а состав юнита даёт "
                    f"{unit.task_id}: происхождение нарушено")
            arm = known[unit.arm]
            started = time.perf_counter()
            results = S.run_unit(unit, rate=arm["rate"], c_rate=arm["c_rate"],
                                 c_shift=arm["c_shift"], regime=arm["regime"],
                                 magnitude=arm["magnitude"])
            payload = {"task_id": unit.task_id, "arm": unit.arm,
                       "look": unit.look,
                       "keys": [list(k) for k in unit.keys],
                       "endpoints": _encode(results)}
            payload["digest"] = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
            payload["seconds"] = round(time.perf_counter() - started, 1)
            payload["peak_rss_mb"] = round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
            (out / f"{unit.task_id}.json").write_text(
                json.dumps(payload, sort_keys=True))
            print(f"{unit.task_id} {unit.arm} {payload['seconds']}s "
                  f"{payload['digest']}", flush=True)
        return 0

    if args.mode == "calibrate":
        # КАЛИБРОВКА ЭКОНОМИИ ДЕЛЕНИЯ. Один раннер, один просмотр, одна рука.
        #
        # Ступень лестницы этим режимом НЕ считается и реестр не трогается:
        # на выходе исполнительный параметр, а не наука. Поэтому нет ни
        # пина заявки, ни сверки отпечатка воркфлоу: закреплять нужно
        # SCIENCE_SHA, потому что от него зависит сравнение делёного с
        # неделёным, и он закреплён checkout'ом.
        if args.science:
            guard.assert_science_comes_from(args.science)
        if not args.arm:
            raise SystemExit("калибровке нужна --arm")
        if args.deadline_minutes <= 0:
            raise SystemExit(
                "калибровке нужен --deadline-minutes: без охранника времени "
                "таймаут задания стал бы суррогатом измерения")
        out.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + args.deadline_minutes * 60.0
        target = out / "calibration.json"
        prov = {
            "science_sha": os.environ.get("SCIENCE_SHA", ""),
            "execution_sha": os.environ.get("EXECUTION_SHA", ""),
            "request_sha": os.environ.get("REQUEST_SHA", ""),
            "runner": os.environ.get("RUNNER_NAME", ""),
            "deadline_minutes": args.deadline_minutes,
        }
        variants = [v.strip() for v in args.variants.split(",") if v.strip()]
        try:
            record = calibrate.run(args.arm, args.look, deadline=deadline,
                                   variants=variants, checkpoint=target,
                                   provenance=prov)
        except calibrate.SplitChangedTheScience as exc:
            # запись промежуточных вариантов уже на диске: ДОПОЛНЯЕТСЯ,
            # а не затирается одной строкой причины
            kept = (json.loads(target.read_text()) if target.exists()
                    else {"provenance": prov})
            kept["correctness"] = "KILL"
            kept["reason"] = str(exc)
            target.write_text(json.dumps(kept, sort_keys=True))
            raise SystemExit(f"КАЛИБРОВКА ОСТАНОВЛЕНА: {exc}")
        # что измерение означает для ступени 64000 — считается здесь же,
        # чтобы вывод не пришлось толковать задним числом
        worst = max(cost.seconds_for(a["effective_rate"], 64_000)
                    for a in S.production_arms())
        budget = cost.SHARD_BUDGET_HOURS * 3600.0
        platform = cost.PLATFORM_CAP_HOURS * 3600.0
        record["worst_unit_64000_hours"] = round(worst / 3600.0, 3)
        record["implications"] = {
            name: {"groups_for_budget": calibrate.groups_for_target(
                       worst, budget, share),
                   "groups_for_platform": calibrate.groups_for_target(
                       worst, platform, share)}
            for name, share in sorted(record.get("shares", {}).items())}
        (out / "calibration.json").write_text(
            json.dumps(record, sort_keys=True))
        print(json.dumps({k: record[k] for k in
                          ("arm", "look", "correctness", "shares",
                           "implications", "incomplete",
                           "worst_unit_64000_hours")}, sort_keys=True))
        for v in record["variants"]:
            print(f"{v['label']:>6s} g={v['groups']} C={v['C_g_sum_wall']:.1f}s "
                  f"W={v['W_g_max_wall']:.1f}s разброс={v['spread_max_over_min']} "
                  f"cpu={v['C_g_sum_cpu']:.1f}s rss={v['rss_high_water_mb']}MB",
                  flush=True)
        return 0

    # reduce
    if args.science:
        guard.assert_science_comes_from(args.science)
    reuse_origin: dict = {}
    if args.resume:
        reused = resume.completed(args.resume, look=args.look,
                                  science_sha=os.environ.get("SCIENCE_SHA", ""))
        fresh = {p["task_id"]: p for p in load_unit_payloads(out)}
        merged = resume.merge_parts(reused, fresh)
        for tid, payload in reused.items():
            (out / f"{tid}.json").write_text(json.dumps(payload, sort_keys=True))
        reuse_origin = resume.origin(
            args.resume, look=args.look,
            science_sha=os.environ.get("SCIENCE_SHA", ""))
        print(f"переиспользовано {len(reused)}, посчитано заново {len(fresh)}, "
              f"всего {len(merged)}")
    if args.checkpoint:
        data = json.loads(pathlib.Path(args.checkpoint).read_text())
        ledger = Ledger.from_checkpoint(data)
        _anchor_checkpoint(args, data)
        payloads = load_unit_payloads(out)
        _verify_with_frozen_merge(out, args.look, payloads, args.resume)
        ledger.absorb(args.look, payloads)
        inputs = {str(out): provenance.digest_of(payloads)}
    else:
        ledger, inputs = _ledger_from(list(args.prior) + [out],
                                      args.prior_digest, args.resume)
    final = ledger.finalise(args.look)
    cells = reduction.cells_from(final)
    evaluable = sum(1 for c in cells if c["evaluable"])
    summary = {
        "look": args.look,
        "looks_absorbed": list(ledger.looks_absorbed),
        "endpoints_seen": ledger.seen_count(),
        "endpoints_settled": ledger.settled_count(),
        "ignored_because_already_settled": ledger.ignored_because_already_settled,
        "ledger_digest": ledger.digest(),
        "cells": len(cells), "cells_evaluable": evaluable,
        "inputs": inputs,
    }
    # Отпечаток ВЫХОДА берётся от НАУЧНОГО результата: ячейки и реестр.
    #
    # Прежде он считался от всей сводки, а та несёт `inputs`, ключами
    # которых служат ПУТИ каталогов. Тот же результат, собранный из другого
    # каталога, давал другой отпечаток — и «частичный + возобновление»
    # расходился с непрерывным прогоном при побайтово одинаковой науке.
    # Отпечаток, меняющийся от переноса каталога, отпечатком результата не
    # является.
    body = json.dumps({"cells": cells,
                       "ledger_digest": summary["ledger_digest"],
                       "endpoints_settled": summary["endpoints_settled"]},
                      sort_keys=True)
    summary["provenance"] = {
        "science_sha": os.environ.get("SCIENCE_SHA", ""),
        "execution_sha": os.environ.get("EXECUTION_SHA", ""),
        "request_sha": os.environ.get("REQUEST_SHA", ""),
        "look": args.look,
        "prior_run": args.prior_run,
        "prior_digest": args.prior_digest,
        "input_digest": provenance.digest_of(
            load_unit_payloads(out)),
        "output_digest": hashlib.sha256(body.encode()).hexdigest()[:16],
        # откуда взялись переиспользованные части. Без этого артефакт
        # утверждал бы, что весь набор посчитан текущим прогоном.
        "reused": reuse_origin,
    }
    (out / "reduced.json").write_text(json.dumps(
        {"summary": summary, "cells": cells}, sort_keys=True))
    # ЧЕКПОЙНТ: без него следующая ступень не восстановит ранние tau
    (out / "checkpoint.json").write_text(json.dumps(
        ledger.to_checkpoint(
            canonical_arms={a["tag"] for a in S.production_arms()},
            provenance=summary["provenance"]), sort_keys=True))
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
