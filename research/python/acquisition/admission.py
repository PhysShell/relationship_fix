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


class Access(Enum):
    """Как файл достаётся. НЕ говорит ничего о том, что с ним разрешено делать."""

    PUBLIC = "PUBLIC"
    ON_REQUEST = "ON_REQUEST"
    RESTRICTED = "RESTRICTED"


def corpus_admission(corpus: str, *, extra: tuple[AdmissionCheck, ...] = ()) -> Admission:
    """Стандартный набор вопросов к любому внешнему корпусу.

    Один набор на все корпуса намеренно: вопрос «а что на самом деле в файле»
    не зависит от того, насколько симпатичной выглядит аннотация.
    """
    return Admission(corpus, (
        AdmissionCheck(
            "licence.terms",
            "Какая лицензия/DUA у файлов и разрешает ли она это использование?",
            "«Скачивается» не значит «разрешено». CollegeMsg скачивается и "
            "лицензии не имеет вовсе.",
            blocking=True),
        AdmissionCheck(
            "licence.redistribution",
            "Можно ли вендорить файлы, или корпус остаётся вне репозитория по пути?",
            "MaiChat уже не вендорится из-за share-alike; повторить легко.",
            blocking=True),
        AdmissionCheck(
            "schema.fields",
            "Какие поля ФАКТИЧЕСКИ присутствуют в файлах?",
            "Разведка по аннотациям уже расходилась с первичным источником.",
            blocking=True),
        AdmissionCheck(
            "schema.text_present",
            "Содержат ли файлы текст сообщений?",
            "«Текст не собирался» слишком удобно для нашей privacy story, "
            "чтобы принимать это без доказательства.",
            blocking=True),
        AdmissionCheck(
            "schema.text_discarded",
            "Если текст есть — отрезан ли он на входе адаптера, не доходя ни "
            "до одного типа?",
            "Обещание отрезать текст исполняется здесь или не исполняется вовсе.",
            blocking=True),
        AdmissionCheck(
            "time.resolution",
            "Каково фактическое разрешение меток времени?",
            "От него напрямую зависит вся Q3: доля cross-actor ties и цена STRICT.",
            blocking=True),
        AdmissionCheck(
            "time.semantics",
            "Что метка ОЗНАЧАЕТ: отправку устройством, приём сервером, биллинг?",
            "Server-receive и часы отправителя — разные величины под одним именем.",
            blocking=True),
        AdmissionCheck(
            "scale.counts",
            "Сколько на самом деле диад, сообщений и какие календарные промежутки?",
            "Заменяет числа из аннотаций измеренными.",
            blocking=True),
        AdmissionCheck(
            "coverage.target_dyad_filtering",
            "Вырезаны ли из данных контакты ВНЕ изучаемого множества, и является "
            "ли это пропуском для оставшейся диады?",
            "Отвечается обычно ДА и ДА-не-является: для процесса конкретной пары "
            "A-B сообщения A с кем-то третьим в процесс не входят по определению. "
            "Ровно так же target chat в Telegram не включает переписку с мамой и "
            "сантехником, и окно диады от этого не становится дырявым. Путать эти "
            "две вещи — значит отказывать корпусу за то, что он корпус.",
            blocking=True),
        AdmissionCheck(
            "coverage.capture_window",
            "Наблюдались ли сообщения ИМЕННО ЭТОЙ пары весь заявленный период, "
            "на обоих устройствах?",
            "Вот это и есть настоящий вопрос покрытия: поздний вход, ранний "
            "выход, устройство, появившееся в середине окна. Без него incidence "
            "считается по номинальному периоду для всех, и отсутствие данных "
            "становится тишиной.",
            blocking=True),
        AdmissionCheck(
            "identity.dyad",
            "Устойчивы ли анонимизированные идентификаторы внутри и между файлами?",
            "Без устойчивого идентификатора person-period не собирается.",
            blocking=True),
        AdmissionCheck(
            "events.non_message",
            "Как отличить обычные сообщения от системных/служебных событий?",
            "Системное событие, принятое за сообщение, изобретает возможности "
            "и портит N — ту самую величину, ради которой S4 и затевается.",
            blocking=True),
        AdmissionCheck(
            "direction.sender_receiver",
            "Есть ли направление, и который из двух столбцов — отправитель?",
            "Вся топология строится на смене актёра. Перепутанное направление "
            "не падает — оно молча меняет каждую возможность местами.",
            blocking=True),
        AdmissionCheck(
            "ethics.scope",
            "Нет ли в условиях запрета на тот анализ, который объявлен в prereg?",
            "Узнать об этом после публикации результата — поздно.",
            blocking=False),
    ) + extra)


#: Все проверки начинаются с UNKNOWN. Ни одна не «проходит по умолчанию»
#: потому, что файл наконец приехал и его хочется посмотреть.
#:
#: `access` и `data_license` — РАЗНЫЕ поля, и это не педантизм: CollegeMsg
#: публичен и лицензии не имеет, SMS-A лежит в supplementary и лицензии тоже
#: пока не имеет.
CORPORA: dict[str, tuple[Access, str, Admission]] = {
    "CNS": (Access.PUBLIC, "MIT (проверено через Figshare API, запись 7267433)",
            corpus_admission("Copenhagen Networks Study — sms.csv (S4-primary)")),
    "SMS-A": (Access.PUBLIC, "NEEDS_VERIFICATION",
              corpus_admission("SMS-A, Wu et al. supplementary (S4-secondary)")),
    "CollegeMsg": (Access.PUBLIC, "NEEDS_VERIFICATION (SNAP лицензии не указывает)",
                   corpus_admission("CollegeMsg, SNAP (S4-sensitivity)")),
    "MessagingMatters": (Access.RESTRICTED, "Apache-2.0 у supplement, файлы restricted",
                         corpus_admission("Messaging Matters (DEFERRED)")),
}

#: Оставлено ради существующих ссылок; корпус отложен, не удалён.
MESSAGING_MATTERS = CORPORA["MessagingMatters"][2]
