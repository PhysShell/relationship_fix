"""Адаптер Share and Multiply: один чат JSON -> поток диады.

Корпус не вендорится; путь передаётся. Читается ТОЛЬКО `json_files.zip` —
`data.pkl` из той же записи не читается никогда, см.
`acquisition.share_multiply_rules.PICKLE_IS_NOT_READ`.

Правила чтения объявлены до счёта в `share_multiply_rules`, и адаптер их
исполняет, а не переизобретает: `messages` — словарь, а не список; тип 10
исключается; актёр берётся из `user`; текста нет и брать нечего.
"""

from __future__ import annotations

import hashlib
import json
import zipfile

from acquisition.share_multiply_rules import (
    EXCLUDE_MESSAGE_TYPE, MESSAGES_ARE_A_DICT_KEYED_BY_STRING_INDEX,
)
from coarsening.paired import Stream, order


class NotADyad(ValueError):
    """Актёров не два. Получатель выводим только в диаде."""


def tie_key(index: str, salt: bytes) -> str:
    """Произвольный, но детерминированный ключ разрыва равенства меток.

    НАМЕРЕННО НЕ ФАЙЛОВЫЙ ПОРЯДОК. Ключ вида '000001' воспроизвёл бы истинный
    порядок внутри корзины и подарил грубому наблюдателю знание, которого у
    него нет, — цена огрубления вышла бы нулевой по построению (prereg §3).
    `salt` меняет розыгрыш: по нему и меряется, насколько ответ зависит от
    произвольного выбора.
    """
    return hashlib.blake2b(salt + index.encode(), digest_size=8).hexdigest()


def adapt(chat: dict, *, salt: bytes = b"") -> Stream:
    messages = chat.get("messages") or {}
    assert MESSAGES_ARE_A_DICT_KEYED_BY_STRING_INDEX
    items = messages.items() if isinstance(messages, dict) else enumerate(messages)
    stamps, actors, keys = [], [], []
    for index, message in items:
        if message.get("message_type") == EXCLUDE_MESSAGE_TYPE:
            continue
        stamps.append(message["date"] / 1000.0)      # epoch ms -> seconds
        actors.append(message["user"])
        keys.append(tie_key(str(index), salt))
    distinct = sorted(set(actors))
    if len(distinct) != 2:
        raise NotADyad(f"actors: {len(distinct)}")
    seat = {actor: number for number, actor in enumerate(distinct)}
    return order(stamps, [seat[a] for a in actors], keys)


def chats(archive: str, names):
    """Ленивая выдача: 9.5 млн сообщений целиком в память не кладём."""
    with zipfile.ZipFile(archive) as bundle:
        for name in names:
            yield name, json.loads(bundle.read(name))
