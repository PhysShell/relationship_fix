"""Гейт приёма внешнего корпуса: что обязано быть установлено ДО первого чтения.

Ledger источника спрашивал, что гарантирует ИСТОЧНИК. Instrumentation
qualification — что гарантирует ПРОВОДКА. Это спрашивает третье и самое скучное:
что лежит в присланном файле на самом деле.

Скучное — не значит необязательное. Разведка по аннотациям уже разошлась с
первичным источником (S4 prereg §0.3: «133 чата» против N = 142 в самой
статье), а утверждение «текст не собирался» слишком удобно для нашей privacy
story, чтобы принимать его без доказательства. Поэтому здесь данные, а не
проза, и гейт, который **называет свои критерии** вместо того, чтобы считаться
зелёным, потому что зелёная сборка.

Главное правило — fail-closed: `UNKNOWN` НЕ ПРОХОДИТ. Непроверенная проверка не
отличается от проваленной, и отсутствие не становится свидетельством.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CheckVerdict(Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    #: ещё не выполнено. НЕ проход: непроверенное и проваленное здесь равны
    UNKNOWN = "UNKNOWN"


class AdmissionError(ValueError):
    """Попытка читать корпус, который ещё не допущен."""


@dataclass(frozen=True, slots=True)
class AdmissionCheck:
    """Один вопрос к присланному файлу, и что случится, если на него не ответить."""

    key: str
    question: str
    #: что ломается, если это не установлено. Пустое не допускается: проверка
    #: без последствий отказа — ритуал, а не проверка
    at_stake: str
    blocking: bool
    verdict: CheckVerdict = CheckVerdict.UNKNOWN
    #: что НАБЛЮДАЛИ. Обязательно для PASSED и FAILED: вердикт без наблюдения
    #: — это мнение
    finding: str = ""

    def __post_init__(self):
        if not self.at_stake:
            raise AdmissionError(f"{self.key}: проверка без названной цены отказа")
        if self.verdict is not CheckVerdict.UNKNOWN and not self.finding:
            raise AdmissionError(
                f"{self.key}: вердикт {self.verdict.value} без наблюдения. "
                f"Вердикт без записанного наблюдения — это мнение"
            )
        if self.verdict is CheckVerdict.UNKNOWN and self.finding:
            raise AdmissionError(
                f"{self.key}: наблюдение записано, а вердикт остался UNKNOWN"
            )

    @property
    def clears(self) -> bool:
        return self.verdict is CheckVerdict.PASSED

    def resolved(self, verdict: CheckVerdict, finding: str) -> AdmissionCheck:
        """Ответ на вопрос. Возвращает НОВУЮ проверку: журнал не переписывается."""
        return AdmissionCheck(self.key, self.question, self.at_stake,
                              self.blocking, verdict, finding)


@dataclass(frozen=True, slots=True)
class Admission:
    corpus: str
    checks: tuple[AdmissionCheck, ...]

    def __post_init__(self):
        keys = [c.key for c in self.checks]
        if len(keys) != len(set(keys)):
            raise AdmissionError(f"{self.corpus}: дублирующиеся ключи проверок")

    def check(self, key: str) -> AdmissionCheck:
        for candidate in self.checks:
            if candidate.key == key:
                return candidate
        raise KeyError(key)

    @property
    def blocking_open(self) -> tuple[AdmissionCheck, ...]:
        return tuple(c for c in self.checks if c.blocking and not c.clears)

    @property
    def admitted(self) -> bool:
        """Допущен только когда КАЖДАЯ блокирующая проверка пройдена."""
        return not self.blocking_open

    def resolve(self, key: str, verdict: CheckVerdict, finding: str) -> Admission:
        return Admission(self.corpus, tuple(
            c.resolved(verdict, finding) if c.key == key else c for c in self.checks))

    def render(self) -> str:
        lines = [f"ADMISSION — {self.corpus}",
                 f"  admitted: {self.admitted}"]
        width = max(len(c.key) for c in self.checks)
        for c in self.checks:
            mark = "!" if c.blocking else " "
            lines.append(f"  {mark} {c.key:<{width}}  {c.verdict.value:<8} "
                         f"{c.finding or c.question}")
        if self.blocking_open:
            lines.append("  blocking and unresolved: "
                         + ", ".join(c.key for c in self.blocking_open))
        return "\n".join(lines)


def require_admission(admission: Admission) -> None:
    """Вызывается ПЕРЕД первым чтением корпуса. Не проходит — не читаем.

    Существует затем, чтобы допуск нельзя было «помнить». Гарантия отличается
    от политики тем, что её нельзя забыть исполнить.
    """
    if not admission.admitted:
        raise AdmissionError(
            f"{admission.corpus}: корпус не допущен; не пройдено — "
            + ", ".join(f"{c.key} ({c.verdict.value})" for c in admission.blocking_open)
        )


#: Все проверки начинаются с UNKNOWN. Ни одна не будет «пройдена по умолчанию»
#: потому, что файл наконец приехал и его хочется посмотреть.
MESSAGING_MATTERS = Admission("Messaging Matters (S4)", (
    AdmissionCheck(
        "licence.terms",
        "Какая лицензия/DUA у присланных файлов и разрешает ли она это использование?",
        "Без этого весь S4 — правовой риск, а не результат.",
        blocking=True),
    AdmissionCheck(
        "licence.redistribution",
        "Можно ли вендорить файлы, или корпус остаётся вне репозитория по пути?",
        "MaiChat уже не вендорится из-за share-alike; повторить ошибку легко.",
        blocking=True),
    AdmissionCheck(
        "schema.fields",
        "Какие поля ФАКТИЧЕСКИ присутствуют в файлах?",
        "Разведка по аннотациям уже разошлась с первичным источником (S4 §0.3).",
        blocking=True),
    AdmissionCheck(
        "schema.text_present",
        "Содержат ли файлы текст сообщений?",
        "«Текст не собирался» слишком удобно для нашей privacy story, чтобы "
        "принимать это без доказательства.",
        blocking=True),
    AdmissionCheck(
        "schema.text_discarded",
        "Если текст есть — отрезан ли он на входе адаптера, не доходя ни до "
        "одного типа?",
        "Обещание из письма исполняется здесь или не исполняется вовсе.",
        blocking=True),
    AdmissionCheck(
        "time.resolution",
        "Каково фактическое разрешение меток времени?",
        "От него напрямую зависит вся Q3: доля cross-actor ties и цена STRICT.",
        blocking=True),
    AdmissionCheck(
        "time.semantics",
        "Что метка ОЗНАЧАЕТ: отправку устройством, приём сервером, что-то ещё?",
        "MaiChat — server-receive, Telegram — часы отправителя. Смешать их "
        "значит сравнивать разные величины под одним именем.",
        blocking=True),
    AdmissionCheck(
        "scale.counts",
        "Сколько на самом деле диад, сообщений и какие календарные промежутки?",
        "Заменяет непроверенные 133 / 129 / 2.18M / «3 месяца» измеренными.",
        blocking=True),
    AdmissionCheck(
        "coverage.semantics",
        "Что означает пустой промежуток: не было сообщений или не было данных?",
        "Q1 считает incidence по окну. Пропуск данных, принятый за тишину, "
        "занижает её молча — отсутствие стало бы свидетельством.",
        blocking=True),
    AdmissionCheck(
        "identity.dyad",
        "Устойчивы ли анонимизированные идентификаторы диады и участника внутри "
        "и между файлами?",
        "Без устойчивого идентификатора person-period не собирается.",
        blocking=True),
    AdmissionCheck(
        "events.non_message",
        "Как отличить обычные сообщения от системных/служебных событий?",
        "Системное событие, принятое за сообщение, изобретает возможности и "
        "портит N — ту самую величину, ради которой S4 и затевается.",
        blocking=True),
    AdmissionCheck(
        "ethics.scope",
        "Нет ли в условиях запрета на тот анализ, который мы объявили в prereg?",
        "Узнать об этом после публикации результата — поздно.",
        blocking=False),
))
