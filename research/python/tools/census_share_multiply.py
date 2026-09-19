"""S4 probe: перепись разрешения меток по всему архиву Share and Multiply.

    python -m tools.census_share_multiply /path/to/json_files.zip [census.tsv]

Корпус не вендорится (CC BY 4.0 распространение допускает, но соглашение
проекта — держать чужие данные вне репозитория), поэтому путь передаётся.

ЭТО ГЕЙТ, А НЕ АНАЛИЗ. Скрипт отвечает ровно на вопросы допуска — какое
разрешение у каждого чата, сколько в нём актёров, где его края — и НЕ считает
ни плотность, ни слияние серий. Разделение не косметическое: посчитать ответ
на Q1c в том же проходе, что и решение «допускать ли корпус», значит смотреть
на ответ, решая, засчитывать ли вопрос.

Классификатор импортируется из `acquisition.share_multiply_rules`, где он
объявлен ДО первого счёта. Менять его, глядя на эту таблицу, запрещено: на
NetHealth вердикт по выборке в 2 819 строк уже пришлось переворачивать.

`data.pkl` из той же записи НЕ читается никогда — unpickling исполняет
произвольный код из скачанного по сети файла. Здесь читается только JSON.
"""

from __future__ import annotations

import collections
import json
import sys
import zipfile
from pathlib import Path

from acquisition.share_multiply_rules import (
    ARCHIVE_MD5, DYADIC_USER_COUNT, Q1C_MINIMUM_DYADS, Resolution,
    classify_resolution,
)

COLUMNS = ("name", "declared_users", "declared_n", "measured_n", "resolution",
           "first_ms", "last_ms", "receive_ms", "measured_users", "type10")

SECONDS_OR_FINER = (Resolution.SECONDS, Resolution.MILLISECONDS)


def census(archive: Path):
    """По строке на чат. Ничего не агрегирует — агрегация ниже и отдельно."""
    with zipfile.ZipFile(archive) as bundle:
        for name in sorted(n for n in bundle.namelist()
                           if n.lower().endswith(".json")):
            chat = json.loads(bundle.read(name))
            messages = chat.get("messages") or {}
            # `messages` — СЛОВАРЬ со строковыми ключами-индексами, а не
            # список: наивная итерация дала бы строки "0", "1", ... и тихо
            # построила бы мусор вместо падения
            entries = list(messages.values()) if isinstance(messages, dict) else list(messages)
            dates = [m["date"] for m in entries if isinstance(m, dict) and "date" in m]
            yield {
                "name": name,
                "declared_users": chat.get("user_count"),
                "declared_n": chat.get("message_count"),
                "measured_n": len(dates),
                "resolution": classify_resolution(dates).value,
                "first_ms": chat.get("date_first_message"),
                "last_ms": chat.get("date_last_message"),
                "receive_ms": chat.get("date_receive"),
                # диадичность берётся ОТСЮДА, а не из `user_count`: у 26 чатов
                # объявленная двойка расходится с числом фактических актёров
                "measured_users": len({m.get("user") for m in entries
                                       if isinstance(m, dict)}),
                "type10": sum(1 for m in entries
                              if isinstance(m, dict) and m.get("message_type") == 10),
            }


def report(rows: list[dict]) -> str:
    out = [f"SHARE AND MULTIPLY — census of {len(rows)} chats",
           f"  expected md5 of the archive: {ARCHIVE_MD5}"]

    counts = collections.Counter(r["resolution"] for r in rows)
    out.append("  resolution over all chats:")
    for value, n in counts.most_common():
        out.append(f"    {value:<14} {n:>6}  {100 * n / len(rows):5.2f}%")

    dyads = [r for r in rows if r["measured_users"] == DYADIC_USER_COUNT]
    target = [r for r in dyads if r["resolution"] in {x.value for x in SECONDS_OR_FINER}]
    out.append(f"  dyadic by MEASURED actors: {len(dyads)}")
    mismatched = sum(1 for r in rows
                     if r["declared_users"] == DYADIC_USER_COUNT
                     and r["measured_users"] != DYADIC_USER_COUNT)
    out.append(f"    of which `user_count` said 2 and actors disagreed: {mismatched}")
    out.append(f"  Q1c target subset (dyadic AND seconds-or-finer): {len(target)} "
               f"chats, {sum(r['measured_n'] for r in target):,} messages")
    out.append(f"    declared-before-counting threshold: {Q1C_MINIMUM_DYADS} — "
               f"{'CLEARED' if len(target) >= Q1C_MINIMUM_DYADS else 'NOT CLEARED'}")

    # правый край наблюдаемости. Отрицательная разность невозможна физически и
    # выдаёт неизвестный часовой сдвиг меток сообщений
    gaps = [(r["receive_ms"] - r["last_ms"]) / 3.6e6 for r in rows
            if r["receive_ms"] is not None and r["last_ms"] is not None]
    impossible = [g for g in gaps if g < 0]
    out.append(f"  date_receive present: {len(gaps)} of {len(rows)}")
    out.append(f"    impossible (receive BEFORE last message): {len(impossible)}"
               f"  worst {min(gaps):.1f} h — unknown per-chat timezone offset")

    # подпись потолка экспорта: обрезается НАЧАЛО длинного чата
    capped = sum(1 for r in rows if 39_900 <= r["measured_n"] <= 40_100)
    capped_target = sum(1 for r in target if 39_900 <= r["measured_n"] <= 40_100)
    out.append(f"  export-cap signature (~40 000 entries): {capped} corpus-wide, "
               f"{capped_target} inside the Q1c subset")

    # авторское `message_count` = записи минус тип 10; расхождения стоит видеть
    off = sum(1 for r in rows
              if r["declared_n"] is not None
              and r["measured_n"] - r["type10"] != int(r["declared_n"]))
    out.append(f"  chats where message_count != entries - type10: {off}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    archive = Path(argv[1])
    rows = list(census(archive))
    if len(argv) == 3:
        with open(argv[2], "w", encoding="utf-8") as handle:
            handle.write("\t".join(COLUMNS) + "\n")
            for row in rows:
                handle.write("\t".join(str(row[c]) for c in COLUMNS) + "\n")
    print(report(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
