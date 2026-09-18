"""DONOR-0: что можно взять готовым, и что оно молча утверждает за нас.

Экономия здесь реальная — парсинг, format-dirt, фикстуры, UX, differential
oracle. Но estimands и `SourceSemantics` остаются своими: мы уже знаем, сколько
скрытой дряни живёт в словах вроде `response_time`.

Главный вопрос к каждому донору — не «работает ли он», а:

    какие утверждения о данных этот парсер делает за нас,
    и какой provenance он теряет по дороге?

Это и отделяет нормальный reuse от импорта чужих багов через `pip install`.

Лицензии проверены по файлу `LICENSE` в репозитории, а не по бейджу и не по
пересказу. На лицензиях этот проект уже обжигался: `NC` и `ND` вычеркнули два
корпуса из четырёх ещё до того, как схема начала иметь значение.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

PERMISSIVE = frozenset({"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC"})


class Disposition(Enum):
    ADOPT = "ADOPT"        # код реально входит к нам
    WRAP = "WRAP"          # остаётся отдельной зависимостью за границей
    ORACLE = "ORACLE"      # только differential testing, в продукт не входит
    FIXTURE = "FIXTURE"    # берём тестовый материал, не код
    UX = "UX"              # нужно решение интерфейса, код не нужен
    REJECT = "REJECT"

    @property
    def needs_permissive_license(self) -> bool:
        """ORACLE, FIXTURE и UX не линкуются в наш продукт. ADOPT и WRAP — да."""
        return self in (Disposition.ADOPT, Disposition.WRAP)


class LicenseError(ValueError):
    """Попытка взять код на условиях, которых у нас нет."""


@dataclass(frozen=True, slots=True)
class Donor:
    name: str
    url: str
    #: SPDX по прочитанному файлу. "NONE" означает отсутствие лицензии, то есть
    #: all rights reserved — это НЕ «наверное можно».
    license_spdx: str
    license_evidence: str
    disposition: tuple[Disposition, ...]
    input_formats: str
    #: что теряется при проходе через этого донора
    provenance_lost: str
    #: что он утверждает о данных, не спрашивая нас
    semantics_assumed: str
    #: True, если он выдаёт данные в форме ЧУЖОЙ платформы
    emits_foreign_shape: bool
    note: str

    def __post_init__(self):
        if not self.license_evidence:
            raise LicenseError(f"{self.name}: лицензия без доказательства")
        for disposition in self.disposition:
            if disposition.needs_permissive_license and self.license_spdx not in PERMISSIVE:
                raise LicenseError(
                    f"{self.name}: {disposition.value} требует пермиссивной лицензии, "
                    f"а там {self.license_spdx}"
                )
        if not self.provenance_lost or not self.semantics_assumed:
            raise LicenseError(
                f"{self.name}: донор без ответа на «что теряется» и «что утверждается» "
                f"не рассматривается — это и есть вопрос, ради которого делается review"
            )


DONORS = (
    Donor(
        name="KnugiHK/WhatsApp-Chat-Exporter",
        url="https://github.com/KnugiHK/WhatsApp-Chat-Exporter",
        license_spdx="MIT",
        license_evidence="LICENSE @main — «MIT License Copyright (c) 2021-2026 Knugi»",
        disposition=(Disposition.WRAP,),
        input_formats="Android/iOS WhatsApp DB, crypt12/14/15 → HTML и JSON",
        provenance_lost="Платформа и версия WhatsApp, версия самого экспортёра, метод "
                        "приёма (какой backup, когда снят, чем расшифрован) — ничего из "
                        "этого в выходном JSON не записано. Тот же класс дефекта, что у "
                        "Telegram Desktop, который не пишет свою версию.",
        semantics_assumed="Что поля БД WhatsApp ложатся в telegram-образную схему с тем "
                          "же смыслом. НЕ ПРОВЕРЕНО: `--tg` существует (`__main__.py:150`, "
                          "`telegram_json_format`), но что именно он кладёт в `date_unixtime` "
                          "и `id` — первое, что обязан квалифицировать WRAP-трек.",
        emits_foreign_shape=True,
        note="Богатый источник для WhatsApp — куда богаче официального .txt с минутами и "
             "без id. Отдельный acquisition-трек, не расширение телеграмного.",
    ),
    Donor(
        name="mtmxo/whatsapp-chat-analyzer",
        url="https://github.com/mtmxo/whatsapp-chat-analyzer",
        license_spdx="MIT",
        license_evidence="LICENSE @main — «MIT License Copyright (c) 2026 marco cerbella»",
        disposition=(Disposition.ADOPT, Disposition.WRAP),
        input_formats="WhatsApp .txt: iOS и Android, DD/MM и MM/DD, 2- и 4-значные годы, "
                      "multiline, BOM; типы TEXT/MEDIA/SYSTEM/DELETED. Stdlib-only, py3.10+",
        provenance_lost="`message_id` не теряется — его в формате НЕТ вовсе. Актёр — "
                        "отображаемое ИМЯ (`sender: str | None`), а не стабильный id, то есть "
                        "ровно то, что наш ledger запрещает использовать как актёра у "
                        "Telegram. Разрешение времени — минута.",
        semantics_assumed="Что определённый детектором формат даты — правильный. Детектор "
                          "это ВЫВОД, а не чтение: `03/04` разбирается как DD/MM или MM/DD "
                          "по эвристике, и ошибка здесь не шумит, а молча сдвигает сообщения "
                          "на месяцы. В нашем ledger это PARTIAL с объявленным поведением "
                          "при неоднозначности, а не QUALIFIED.",
        emits_foreign_shape=False,
        note="Останавливаемся на середине их конвейера: их детектор и типизированный "
             "Message → наш SourceSemantics-адаптер. Не переписывать regex №47 самим: "
             "из «нам нужно всего несколько строк» и вырастают iOS, AM/PM, RTL-маркеры, "
             "локали и четыре месяца ненависти к символу «[».",
    ),
    Donor(
        name="joweich/chat-miner",
        url="https://github.com/joweich/chat-miner",
        license_spdx="MIT",
        license_evidence="LICENSE @main — «MIT License Copyright (c) 2021 Jonas Weich»",
        disposition=(Disposition.ORACLE,),
        input_formats="WhatsApp, Telegram JSON, Signal, Facebook Messenger, Instagram",
        provenance_lost="Всё приводится к DataFrame, а вместе с этим уходит ровно то, на "
                        "чём держатся наши выводы: позиция в источнике, сырая идентичность, "
                        "evidence порядка, неоднозначность, происхождение покрытия.",
        semantics_assumed="Что пять платформ сводимы к одной таблице. Для аналитики — "
                          "разумно; для нас это и есть спорное утверждение.",
        emits_foreign_shape=False,
        note="Независимый свидетель, не канонический нормализатор. Расхождение трёх "
             "парсеров на одной строке — вот там и начинается полезная работа.",
    ),
    Donor(
        name="emylfy/TelAnalysis",
        url="https://github.com/emylfy/TelAnalysis",
        license_spdx="MIT",
        license_evidence="LICENSE @main — «MIT License Copyright (c) 2026 emylfy»",
        disposition=(Disposition.FIXTURE, Disposition.UX, Disposition.ORACLE),
        input_formats="Telegram Desktop JSON/HTML, локально, без загрузки наружу",
        provenance_lost="Как fixture-донор — ничего: мы берём файлы, не код. Как oracle — "
                        "их response latency считается по их определению, не по нашему, и "
                        "совпадение чисел ничего не подтвердит, пока определения не сверены.",
        semantics_assumed="Ничего о РЕАЛЬНОМ Telegram: демо синтетические, "
                          "`tools/gen_demo_data.py` с фиксированным seed. Поэтому они "
                          "НЕ evidence для семантики источника — только stress/E2E материал.",
        emits_foreign_shape=False,
        note="`personal_demo.json` ~18k сообщений 1-on-1 и `group_demo.json` ~70k. Первый — "
             "почти идеальный крупный E2E-вход целевого ТИПА, которого в публичном доступе "
             "мы не нашли ни разу. Плюс готовый local-upload UX как prior art.",
    ),
    Donor(
        name="Radhium/WhatsApp-Chat-Analyzer",
        url="https://github.com/Radhium/WhatsApp-Chat-Analyzer",
        license_spdx="NONE",
        license_evidence="LICENSE отсутствует на main И на master; в package.json поля "
                         "license нет. Проверено curl'ом по обеим веткам.",
        disposition=(Disposition.UX,),
        input_formats="browser-local WhatsApp .txt, response times / streaks / silences",
        provenance_lost="Неприменимо: код не берём.",
        semantics_assumed="Их операционализация response time — часть competing-metric "
                          "корпуса, а не источник. Именно ради таких сравнений он и нужен.",
        emits_foreign_shape=False,
        note="ПОПРАВКА к предварительному раскладу: без лицензии это all rights reserved, "
             "а не «наверное можно». Код — REJECT при любом желании. Берём только идеи "
             "интерфейса и операционализации, которые авторским правом не защищены; "
             "ни строки не копируем.",
    ),
    Donor(
        name="xiaotianxt/tg",
        url="https://github.com/xiaotianxt/tg",
        license_spdx="MIT",
        license_evidence="LICENSE @main — «MIT License Copyright (c) 2026 xiaotianxt»; "
                         "Cargo.toml: version 2.2.1, license = \"MIT\"",
        disposition=(Disposition.ORACLE,),
        input_formats="локальная `db_storage` Telegram Desktop через SQLCipher, read-only, "
                      "`query_only`, включая закоммиченный WAL; экспорт txt/csv/json",
        provenance_lost="Ничего — как oracle мы берём его ВЫВОД, не код. Но сам он читает "
                        "иной срез реальности, чем официальный экспорт, и это не потеря, "
                        "а второй независимый взгляд.",
        semantics_assumed="Что локальная база = история. README это прямо опровергает: "
                          "«не восстанавливает сообщения, которых уже нет в локальной базе». "
                          "Официальный экспорт тянет историю С СЕРВЕРА (прослежено по "
                          "`messages.getHistory` в экспортёре), локальная база — кэш клиента "
                          "с неизвестными правилами вытеснения.",
        emits_foreign_shape=False,
        note="ORACLE только для разработчика на его собственном аккаунте, macOS/Linux. "
             "Ценность именно в расхождении: сравнение `tg` и официального экспорта на одном "
             "чате измеряет ПОЛНОТУ экспорта — то, о чём `coverage.completeness` сегодня "
             "UNAVAILABLE. Участникам этот путь не предлагается, см. LOCAL-0 §3.",
    ),
    Donor(
        name="lucasrodes/whatstk",
        url="https://github.com/lucasrodes/whatstk",
        license_spdx="GPL-3.0",
        license_evidence="LICENSE @master — «GNU GENERAL PUBLIC LICENSE Version 3»",
        disposition=(Disposition.ORACLE,),
        input_formats="WhatsApp parser/DataFrame toolkit, зрелый",
        provenance_lost="Как у любого DataFrame-нормализатора: позиция, идентичность, "
                        "evidence порядка.",
        semantics_assumed="Свои правила разбора и сессий, не наши.",
        emits_foreign_shape=False,
        note="Copyleft: линковать нельзя, иначе вместо отношений мы начнём изучать GPL. "
             "Как oracle — запускается отдельным процессом над фикстурой, результаты "
             "сравниваются; это не производное произведение.",
    ),
)


def adoptable() -> tuple[Donor, ...]:
    return tuple(d for d in DONORS
                 if any(x.needs_permissive_license for x in d.disposition))


def foreign_shape_donors() -> tuple[Donor, ...]:
    """Доноры, выдающие данные в форме чужой платформы.

    Ловушка, которую через полгода кто-нибудь непременно устроит: увидит
    одинаковые ключи JSON и объединит два адаптера, потому что утка крякает как
    утка. Форма данных telegram-подобна — семантика источника не Telegram.

    Такой вход обязан иметь СВОЮ идентичность источника и свою квалификацию:

        source:      WHATSAPP_DB_VIA_WHATSAPP_CHAT_EXPORTER
        provenance:  WhatsApp platform/version · exporter version · acquisition method
    """
    return tuple(d for d in DONORS if d.emits_foreign_shape)
