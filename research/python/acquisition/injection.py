"""Failure injection ON A REAL ARTIFACT, rather than eight toy files.

Mutation testing asks whether the tests notice a broken implementation. This
asks the same of the system boundary: take one large plausible input and corrupt
it in one specific way, then check that the corruption produces the expected
outcome at the expected layer. Eight hand-written miniature fixtures prove that
eight hand-written miniature fixtures behave; a corrupted 25 000-message export
proves something about the path.

Not every injection expects a refusal. Two expect a successful run — one with
ambiguity counters raised, one with a planted secret that must not come out the
other end. An injection suite where every answer is "refused" would pass on a
pipeline that refuses everything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from .model import Verdict


@dataclass(frozen=True, slots=True)
class Injection:
    key: str
    describe: str
    #: bytes → bytes. `None` means the corruption is at the harness level
    #: (missing provenance), applied by the caller rather than to the artifact.
    corrupt: Callable[[bytes], bytes] | None
    #: The exact verdict expected, for injections that must be rejected.
    #: `None` means: whatever the UNCORRUPTED artifact produced with this
    #: window, the injected one must still carry measurements. The baseline
    #: verdict belongs to the artifact and the window, not to the injection —
    #: pinning ACCEPTED here would make the suite fail on any fixture whose
    #: coverage heuristic fires, which is a statement about the fixture.
    expected_verdict: Verdict | None
    #: a finding code the result must carry, when the outcome is a refusal
    expected_code: str = ""
    #: for injections that must SUCCEED: text that must not survive the path
    planted_secret: str = ""
    #: the injection must RAISE this exported counter above the baseline
    raises_counter: str = ""


def _reload(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))


def _dump(document: dict) -> bytes:
    return json.dumps(document).encode("utf-8")


def _strip_timestamps(raw: bytes) -> bytes:
    document = _reload(raw)
    for entry in document["messages"]:
        entry.pop("date_unixtime", None)
    return _dump(document)


def _wrong_type(raw: bytes) -> bytes:
    document = _reload(raw)
    document["type"] = "private_group"
    return _dump(document)


def _truncate(raw: bytes) -> bytes:
    return raw[: len(raw) // 3]


def _nan(raw: bytes) -> bytes:
    document = _reload(raw)
    document["messages"][0]["id"] = "__NAN__"
    return _dump(document).replace(b'"__NAN__"', b"NaN")


def _unsupported_structure(raw: bytes) -> bytes:
    document = _reload(raw)
    document["messages"].insert(len(document["messages"]) // 2, 42)
    return _dump(document)


def _cross_actor_tie(raw: bytes) -> bytes:
    """Force two adjacent messages of different actors onto one second.

    The one injection whose expected outcome is a MEASUREMENT: the run
    succeeds, and the ambiguity travels out as counters instead of vanishing.
    """
    document = _reload(raw)
    messages = document["messages"]
    for i in range(len(messages) - 1):
        if messages[i].get("from_id") != messages[i + 1].get("from_id"):
            messages[i + 1]["date_unixtime"] = messages[i]["date_unixtime"]
            break
    return _dump(document)


PLANTED = "INJECTED_SECRET_KEY_552310"


def _extra_sensitive_fields(raw: bytes) -> bytes:
    """An unexpected schema key carrying content. The path must ignore it and,
    above all, must not carry it outward — tomorrow's Telegram version will add
    fields nobody has read yet."""
    document = _reload(raw)
    for entry in document["messages"][:50]:
        entry["secret_future_field"] = PLANTED
    return _dump(document)


INJECTIONS = (
    Injection("missing_date_unixtime", "у всех сообщений снято время",
              _strip_timestamps, Verdict.REFUSED, "no_usable_messages"),
    Injection("wrong_chat_type", "personal_chat подменён на private_group",
              _wrong_type, Verdict.OUT_OF_SCOPE, "not_the_target_chat_type"),
    Injection("truncated_json", "файл обрезан на трети",
              _truncate, Verdict.REFUSED, "invalid_json"),
    Injection("nan_constant", "NaN вместо id — stdlib принимает, JSON нет",
              _nan, Verdict.REFUSED, "invalid_json"),
    Injection("unsupported_structure", "в массив сообщений вставлено число",
              _unsupported_structure, Verdict.REFUSED, "malformed_entry"),
    Injection("missing_producer_provenance", "провенанс продюсера не передан",
              None, Verdict.REFUSED, "missing_producer_provenance"),
    Injection("cross_actor_same_second_tie", "два соседних актёра в одну секунду",
              _cross_actor_tie, None, raises_counter="cross_actor_tie_groups"),
    Injection("extra_sensitive_fields", "неизвестный ключ схемы с содержимым",
              _extra_sensitive_fields, None, planted_secret=PLANTED),
)
