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


class Admissibility(Enum):
    """Корпус допускается НЕ ЦЕЛИКОМ, а по вопросам.

    NetHealth показал это в чистом виде: 60 миллионов строк и богатейший
    кодбук отвечают почти на всё — кроме единственного вопроса, ради которого
    корпус и открывали. Один булев допуск такое выразить не умеет.
    """

    QUALIFIED = "QUALIFIED"
    #: отвечает, но с названным ущербом
    PARTIAL = "PARTIAL"
    REFUSED = "REFUSED"


@dataclass(frozen=True, slots=True)
class Question:
    """Вопрос и то, от каких проверок он ДЕЙСТВИТЕЛЬНО зависит."""

    key: str
    asks: str
    #: провал любой из них делает вопрос неотвечаемым
    requires: tuple[str, ...]
    #: провал ухудшает ответ, но не отменяет его; ущерб надо назвать
    degraded_by: tuple[str, ...] = ()
    degradation: str = ""

    def __post_init__(self):
        if self.degraded_by and not self.degradation:
            raise AdmissionError(
                f"{self.key}: названы смягчающие проверки, но не назван ущерб"
            )


def admissibility(question: Question, admission: Admission) -> Admissibility:
    """Выводится из вердиктов проверок, а не объявляется вручную."""
    for key in question.requires:
        if not admission.check(key).clears:
            return Admissibility.REFUSED
    for key in question.degraded_by:
        if not admission.check(key).clears:
            return Admissibility.PARTIAL
    return Admissibility.QUALIFIED


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


class Permission(Enum):
    YES = "YES"
    NO = "NO"
    #: условия есть, но ответ на этот вопрос из них не следует однозначно
    UNSETTLED = "UNSETTLED"
    #: условий найти не удалось. НЕ «значит можно»
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class LicenceTerms:
    """Право — это не одна строка «PERMISSIVE», а несколько разных ответов.

    Плоская строка уже подводила: «скачивается» принимали за «разрешено». Но и
    «есть лицензия» недостаточно — CC BY-NC-SA даёт research YES и commercial
    NO одновременно, и для проекта с продуктом это две разные судьбы.
    """

    name: str
    research_use: Permission
    commercial_reuse: Permission
    share_alike: bool
    attribution_required: bool
    evidence: str
    #: дополнительные условия сверх самой лицензии (DUA, terms of use)
    extra_terms: str = ""

    @property
    def known(self) -> bool:
        return self.research_use is not Permission.UNKNOWN

    def render(self) -> str:
        return (f"{self.name} · research={self.research_use.value} · "
                f"commercial={self.commercial_reuse.value} · "
                f"share-alike={'yes' if self.share_alike else 'no'}")


UNKNOWN_LICENCE = LicenceTerms(
    "UNKNOWN", Permission.UNKNOWN, Permission.UNKNOWN, False, False,
    "лицензия не найдена ни в записи, ни на странице проекта")


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
            "licence.derivative_reach",
            "Ограничивает ли эта лицензия ПРОИЗВОДНОЕ от корпуса — то есть "
            "откалиброванный на нём генератор и всё, что из него следует?",
            "ПОПРАВКА к прежней редакции: рассуждение «калибровали на CC BY-NC-SA "
            "→ весь генератор теперь CC BY-NC-SA» слишком примитивно. ShareAlike "
            "относится к АДАПТИРОВАННОМУ лицензируемому материалу, а численные "
            "параметры и статистические выводы не становятся copyright derivative "
            "work автоматически. Настоящий риск обычно в ДРУГОМ: в отдельных "
            "Terms of Use, ограничивающих ЦЕЛЬ использования. Даже если mu = 7.3 "
            "сам по себе не «заражён» лицензией, протащить результат "
            "исследовательского использования в коммерческий product pipeline "
            "при условии «solely for academic purposes» — очень спорно. И "
            "обходной путь «мы посмотрели на корпус, а потом руками подобрали "
            "похожее значение» — тот же information flow, только в усах и плаще.",
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
            "events.duplicate_semantics",
            "Может ли ОДНО реальное событие попасть в файл дважды — например, "
            "если оба участника в когорте и событие записали оба телефона? Если "
            "да, как две записи сводятся в одну?",
            "Самая злая из возможных ошибок здесь. Двойное логирование удваивает "
            "часть сообщений, то есть ровно ПЛОТНОСТЬ — тот самый параметр, ради "
            "которого весь S4 и затеян. Откалибровать на удвоенной плотности "
            "concurrency и торжественно объявить результат — баг настолько "
            "идеальный, что почти заслуживает отдельной статьи.",
            blocking=True),
        AdmissionCheck(
            "identity.resolution_quality",
            "Насколько надёжно сопоставлены личности, и что означают поля "
            "уверенности — вероятность или порядковую шкалу?",
            "Порог отбора по уверенности меняет и выборку, и плотность. Молча "
            "взять чужой порог «>= 0.6, авторы называют это хорошим» значит "
            "принять чужое решение за своё и не заметить этого.",
            blocking=True),
        AdmissionCheck(
            "channel.mixing",
            "Один ли это канал связи, или несколько — и не скоррелированы ли "
            "каналы с платформой?",
            "Смешать SMS и мессенджер, доступный только на одной платформе, "
            "значит впрыснуть platform/channel confounding прямо в плотность. "
            "Групповые события — отдельная топология, а не шумная диада.",
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
#: `access` и `licence` — РАЗНЫЕ поля, и это не педантизм. Ландшафт кандидатов
#: устроен так, что чистая лицензия и богатые данные пока не встретились в
#: одном корпусе ни разу.
CORPORA: dict[str, tuple[Access, LicenceTerms, Admission]] = {
    "CNS": (
        Access.PUBLIC,
        LicenceTerms(
            "MIT", Permission.YES, Permission.YES, False, True,
            "Figshare API, запись 7267433: license.name=MIT; статья CC BY 4.0"),
        corpus_admission("Copenhagen Networks Study — sms.csv (S4-primary)")),
    "CES": (
        Access.PUBLIC,
        LicenceTerms(
            "CC BY-NC-SA 4.0", Permission.YES, Permission.NO, True, True,
            "Kaggle API: licenseNameNullable='CC BY-NC-SA 4.0'; 2 759 192 661 байт",
            extra_terms="Terms of Use датасета: «Users shall utilize the dataset "
                        "SOLELY for academic, research, or educational purposes»; "
                        "запрет реидентификации. ПОПРАВКА к прежней редакции: "
                        "условия НЕ говорят, что агенты связаны договором целиком "
                        "— они требуют, чтобы team members, включая "
                        "agents/subcontractors/partners С ДОСТУПОМ к данным, "
                        "соблюдали те же privacy protections. Практический вывод "
                        "тот же: скормить корпус агентам и внешним сервисам и "
                        "считать, что ничего не произошло, нельзя."),
        corpus_admission("College Experience Study (S4-candidate-2)")),
    "NetHealth": (
        Access.PUBLIC,
        LicenceTerms(
            "CC BY 4.0", Permission.YES, Permission.YES, False, True,
            "Zenodo API, запись 21904040 (12.08.2026): license.id='cc-by-4.0', "
            "access_right='open'. ПРЕЖНЯЯ запись поля Rights не имела — смотреть "
            "надо было свежий релиз, а не первый попавшийся",
            extra_terms="Отдельного DUA в записи нет; ограничений по цели и по "
                        "коммерческому использованию в описании нет. Страница "
                        "проекта на nd.edu недоступна для проверки (403), там "
                        "упоминается форма-уведомление о скачивании — вежливость, "
                        "а не условие, но заполнить её стоит"),
        corpus_admission("NetHealth CommEvents (S4-primary-candidate)")),
    "ShareAndMultiply": (
        Access.PUBLIC,
        LicenceTerms(
            "CC BY 4.0", Permission.YES, Permission.YES, False, True,
            "Figshare API, запись 19785193 v1: license={'value': 1, 'name': "
            "'CC BY 4.0'}. Лицензия стоит НА ЧИТАЕМОМ АРТЕФАКТЕ: файлы той же "
            "записи, md5 архива сверен после скачивания",
            extra_terms="Отдельного DUA нет. Ограничений по цели в записи нет. "
                        "Атрибуция обязательна"),
        corpus_admission(
            "Share and Multiply / WhatsApp Data Set (S4-Q1c-only)",
            extra=(
                AdmissionCheck(
                    "format.deserialisation_safety",
                    "Читаем ли мы формат, который нельзя выполнить — или тот, "
                    "который выполняется при чтении?",
                    "В записи лежит `data.pkl` на 3.7 ГБ, и README прямо "
                    "предлагает `pandas.read_pickle`. Unpickling ИСПОЛНЯЕТ "
                    "произвольный код из файла, скачанного по сети. Разница "
                    "между «прочитать данные» и «запустить чужую программу с "
                    "правами своего процесса» — не стилистическая.",
                    blocking=True),
                AdmissionCheck(
                    "selection.donation_mechanism",
                    "Как чат попал в корпус, и кто решал, попадёт ли он?",
                    "Донация пользовательского экспорта — это выборка, "
                    "собранная добровольцами о себе. Абсолютную величину "
                    "incidence по такой выборке заявлять нельзя. Проверка "
                    "существует затем, чтобы Q1a отказывался ВЫВОДИМО, а не по "
                    "памяти о том, что мы так решили.",
                    blocking=True),
                AdmissionCheck(
                    "time.absolute_offset",
                    "Известен ли АБСОЛЮТНЫЙ момент события — или только его "
                    "положение относительно других событий того же чата?",
                    "Отдельно от `time.semantics` НАМЕРЕННО, по тому же "
                    "уроку, что развёл `coverage.target_dyad_filtering` и "
                    "`coverage.capture_window`: одна проверка не может быть "
                    "пройденной для интервалов и проваленной для времени "
                    "суток. Интервалы сдвиг не чувствуют, night-suppression и "
                    "суточные профили — чувствуют целиком.",
                    blocking=True),
                AdmissionCheck(
                    "subset.q1c_dyadic_seconds",
                    "Существует ли пересечение «ровно два актёра» И "
                    "«разрешение не грубее секунды», и хватает ли его?",
                    "Весь смысл этого корпуса под Q1c держится на этом "
                    "пересечении: на минутной шкале слияние серий уже "
                    "произошло, и измерять его нечем. Пустое пересечение — "
                    "это ОТВЕТ, а не повод смягчить определение «секундного».",
                    blocking=True),
            ))),
    "SMS-A": (
        Access.PUBLIC, UNKNOWN_LICENCE,
        corpus_admission("SMS-A, Wu et al. supplementary")),
    "CollegeMsg": (
        Access.PUBLIC, UNKNOWN_LICENCE,
        corpus_admission("CollegeMsg, SNAP")),
    "StudentLife": (
        Access.PUBLIC, UNKNOWN_LICENCE,
        corpus_admission("StudentLife, Dartmouth")),
    "MessagingMatters": (
        Access.RESTRICTED,
        LicenceTerms(
            "Apache-2.0 (supplement)", Permission.UNSETTLED, Permission.UNSETTLED,
            False, True,
            "Zenodo 19428331: Apache-2.0 у supplement, САМИ ФАЙЛЫ restricted"),
        corpus_admission("Messaging Matters (DEFERRED)")),
    "FriendsFamily": (
        Access.ON_REQUEST, UNKNOWN_LICENCE,
        corpus_admission("Friends & Family (DEFERRED)")),
}

#: Оставлено ради существующих ссылок; корпус отложен, не удалён.
MESSAGING_MATTERS = CORPORA["MessagingMatters"][2]
