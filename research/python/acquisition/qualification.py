"""Instrumentation qualification: the seam ledger and the exit gate.

The acquisition ledger asked what the SOURCE guarantees. This asks what the
WIRING between our own components guarantees — a different and duller question,
which is precisely why the corpse is usually found here.

Same discipline as before: data, not prose, so a verdict cannot drift; and a
gate that names its criteria rather than being declared green because the suite
is green.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SeamVerdict(Enum):
    QUALIFIED = "QUALIFIED"
    OPEN = "OPEN"                # not yet demonstrated
    NOT_APPLICABLE = "N/A"       # no such seam in this slice; NOT a pass


@dataclass(frozen=True, slots=True)
class Seam:
    """One junction, and what would go wrong if it leaked."""

    key: str
    claim: str
    evidence: str                # the test that demonstrates it
    verdict: SeamVerdict
    failure_mode: str            # what the world looks like when this seam lies


SEAMS = (
    Seam("acquisition.trigger",
         "Приём запускается только по протокольному окну и провенансу, а не по "
         "наличию файла.",
         "FailureInjectionTests.test_missing_producer_provenance · "
         "test_consent_not_recorded",
         SeamVerdict.QUALIFIED,
         "Файл без объявленного продюсера измеряется по семантике, которой у него "
         "может не быть; согласие оказывается формальностью."),
    Seam("window.provenance",
         "Окно приходит из протокола и хранится отдельно от содержимого; из файла "
         "оно не выводится никогда.",
         "HappyPathTests.test_the_protocol_window_travels_unchanged · "
         "SeamContractTests.test_the_window_length_is_end_minus_start",
         SeamVerdict.QUALIFIED,
         "Окно берётся из первого и последнего сообщения — и burden сравнивается "
         "между руками по разным календарям."),
    Seam("window.overlap",
         "Несовпадение окна и экспорта — отказ, а не период, в котором человек "
         "молчал.",
         "FailureInjectionTests.test_window_outside_the_export · "
         "SeamContractTests.test_a_message_exactly_at_the_window_*",
         SeamVerdict.QUALIFIED,
         "N = 0 от промаха по календарю неотличим от N = 0 от молчания."),
    Seam("identity.participant",
         "Участник обязан присутствовать в экспорте.",
         "FailureInjectionTests.test_the_participant_is_not_in_the_export",
         SeamVerdict.QUALIFIED,
         "Извлечение проходит успешно и сообщает о человеке, который ничего не "
         "делал: неверный ответ в одежде верного."),
    Seam("provenance.survival",
         "Версия продюсера, платформа и согласие доезжают до внешнего слоя.",
         "HappyPathTests.test_provenance_survives_the_whole_path",
         SeamVerdict.QUALIFIED,
         "Агрегат без версии — незаявленная семантика; сравнивать такие периоды "
         "между собой нельзя, а выглядят они одинаково."),
    Seam("refusal.fail_closed",
         "REFUSED остаётся REFUSED через всю цепочку и никогда не превращается "
         "в измерение.",
         "FailureInjectionTests.test_no_failure_path_ever_produces_an_empty_"
         "measurement · OutwardShapeTests.test_a_refusal_carrying_numbers_cannot_"
         "be_constructed",
         SeamVerdict.QUALIFIED,
         "`except Exception: return []` — и у участника сегодня просто ноль "
         "возможностей."),
    Seam("privacy.boundary",
         "Наружу уходит ровно allowlist; ни текст, ни имена, ни пути к медиа, "
         "ни id чата не выживают — включая пути отказа, логи и трассировки.",
         "PrivacyBoundaryTests (маркеры в фикстуре, grep по результату, "
         "сериализации, логам и стеку)",
         SeamVerdict.QUALIFIED,
         "Содержимое утекает там, где его меньше всего ищут: в сообщении "
         "исключения, которое кто-то залогировал."),
    Seam("diagnostics.visibility",
         "Счётчики ties, флаги покрытия и вердикты доезжают наружу и не "
         "схлопываются в ноль.",
         "HappyPathTests.test_tie_counters_reach_the_outside · "
         "test_a_cross_actor_tie_is_visible_end_to_end · "
         "test_the_source_cannot_report_deletions_and_says_so",
         SeamVerdict.QUALIFIED,
         "Неоднозначность выглядит как её отсутствие — та же ошибка, что "
         "ловится в этом проекте с первого дня."),
    Seam("determinism",
         "Один артефакт + одни метаданные = один и тот же научный payload, "
         "байт в байт; инструментальных меток в нём нет вовсе.",
         "DeterminismTests",
         SeamVerdict.QUALIFIED,
         "Два прогона расходятся, и разница выглядит как эффект."),
    Seam("freeze.integrity",
         "Инструментовка не редактирует замороженный движок.",
         "tests/test_freeze.py — sha256 всех модулей `extractor/*.py`",
         SeamVerdict.QUALIFIED,
         "Заморозка становится наклейкой: каждая неудобная проверка чинится "
         "в движке, а не в проводке."),
    Seam("reactivity.surface",
         "Всё, что приём требует от человека, перечислено и оценено.",
         "REACTIVITY_SURFACE ниже",
         SeamVerdict.QUALIFIED,
         "«Пассивное измерение» требует семи экранов каждый вечер и пассивно "
         "примерно как пожарная сирена."),
)


@dataclass(frozen=True, slots=True)
class Touchpoint:
    """Something the measurement path asks of the person."""

    key: str
    what: str
    per_period: bool             # repeated every period, or once at enrolment
    passive: bool                # true only if the person does nothing at all
    note: str


#: Named rather than hidden, because this is the honest finding of the stage.
REACTIVITY_SURFACE = (
    Touchpoint("manual_export",
               "Человек сам экспортирует чат из Telegram Desktop и передаёт файл.",
               per_period=True, passive=False,
               note="САМОЕ КРУПНОЕ вмешательство, и оно встроено в acquisition path "
                    "по конструкции. Ручной экспорт — это осознанное действие «сейчас "
                    "меня измеряют», повторяемое каждый период. Называть такой путь "
                    "passive measurement нельзя; в prereg он обязан стоять рядом с "
                    "обсуждением реактивности, а не в разделе про технику."),
    Touchpoint("consent_record",
               "Согласие фиксируется до первого приёма.",
               per_period=False, passive=False,
               note="Разовое и обязательное. Влияет на осведомлённость о наблюдении — "
                    "это и есть предмет H1, а не помеха ему."),
    Touchpoint("provenance_capture",
               "Версия клиента и платформа сообщаются в момент приёма.",
               per_period=True, passive=False,
               note="Мелкое, но не нулевое: ещё один момент, когда человек вспоминает "
                    "о наблюдении. Автоматизируемо, если приложение читает версию само."),
    Touchpoint("refusal_followup",
               "Отказ приёма требует повторного действия человека.",
               per_period=False, passive=False,
               note="Частота отказов = частота напоминаний о наблюдении. Ещё одна "
                    "причина мерить долю отказов, а не только их наличие."),
)


@dataclass(frozen=True, slots=True)
class ExitGate:
    """The stage closes on named criteria, never on «E2E зелёный»."""

    criteria: tuple[str, ...]

    def open_seams(self) -> tuple[Seam, ...]:
        return tuple(s for s in SEAMS if s.verdict is not SeamVerdict.QUALIFIED)

    @property
    def passed(self) -> bool:
        return not self.open_seams()

    def summary(self) -> str:
        return (f"{len(SEAMS)} seams, {len(self.open_seams())} open; "
                f"reactivity surface: {sum(1 for t in REACTIVITY_SURFACE if not t.passive)} "
                f"of {len(REACTIVITY_SURFACE)} touchpoints are NOT passive")


GATE = ExitGate(criteria=(
    "happy path", "failure paths", "provenance", "window handling",
    "refusals fail closed", "privacy export", "determinism", "tie visibility",
    "reactivity surface documented", "no change to the frozen extractor",
))
