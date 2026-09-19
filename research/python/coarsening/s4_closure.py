"""S4-CLOSURE — решение, а не эксперимент.

Записывает, ЧТО ИМЕННО S4 изменил в допустимом дизайне измерения. Заведён
ради одной конкретной опасности: через месяц S5b начнёт ссылаться на S4 как
на «мы наконец откалибровали incidence». S4 этого не сделал — и именно этого
он не сделал громче всего.

Файл машинный намеренно. Проза в `docs/research/s4-closure-decision-record.md`
объясняет, а тесты следят, чтобы объяснение не разошлось с решением.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(Enum):
    """Каким СПОСОБОМ утверждение держится. Не «насколько мы уверены»."""

    PROVED_IN_LEAN = "PROVED_IN_LEAN"
    TESTED_AGAINST_ORACLE = "TESTED_AGAINST_ORACLE"
    EMPIRICAL = "EMPIRICAL"
    ASSUMPTION = "ASSUMPTION"
    NOT_CLAIMED = "NOT_CLAIMED"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True, slots=True)
class Claim:
    key: str
    says: str
    #: цепочка, на которой утверждение стоит — по звеньям, а не одним словом
    chain: tuple[Status, ...]
    #: что эта цепочка РАЗРЕШАЕТ сказать, дословно
    licenses: str

    @property
    def strongest(self) -> Status:
        order = [Status.PROVED_IN_LEAN, Status.TESTED_AGAINST_ORACLE,
                 Status.EMPIRICAL, Status.ASSUMPTION, Status.NOT_CLAIMED,
                 Status.DEFERRED]
        return min(self.chain, key=order.index)

    @property
    def weakest(self) -> Status:
        order = [Status.PROVED_IN_LEAN, Status.TESTED_AGAINST_ORACLE,
                 Status.EMPIRICAL, Status.ASSUMPTION, Status.NOT_CLAIMED,
                 Status.DEFERRED]
        return max(self.chain, key=order.index)


#: ДВА ВЫВОДА S4 — И У НИХ РАЗНЫЙ ЭПИСТЕМИЧЕСКИЙ СТАТУС.
#:
#: Их постоянно хочется произнести одним предложением. Нельзя: цепочка под
#: `N` заметно прочнее цепочки под `RMTR`, и разница не в силе эффекта, а в
#: том, чем каждое звено держится.
CLAIMS: tuple[Claim, ...] = (
    Claim(
        "strict_n_incompatible",
        "Оценка STRICT по N несовместима НИ С ОДНОЙ допустимой хронологией.",
        (Status.EMPIRICAL, Status.PROVED_IN_LEAN),
        "Эмпирически STRICT_N < lo на 513 диадах из 517 (выше верхней границы "
        "— ноль). Формально `lo ≤ N` для любой допустимой истории доказано в "
        "Lean (`DPBoundsSound`). Отсюда `STRICT_N < N` — для КАЖДОЙ "
        "хронологии, совместимой с наблюдением. Это самая прочная цепочка "
        "проекта: измерение плюс теорема, а не измерение плюс интуиция."),
    Claim(
        "strict_rmtr_outside_envelope",
        "Оценка STRICT по RMTR лежит вне валидной внешней оболочки.",
        (Status.EMPIRICAL, Status.TESTED_AGAINST_ORACLE, Status.ASSUMPTION),
        "Эмпирически снаружи у 87.6% диад при H = 60 мин (всегда СВЕРХУ). Но "
        "soundness временного слоя держится на переборном оракуле и на "
        "объявленных допущениях, а НЕ на доказательстве. Поэтому вывод "
        "формулируется на ступень осторожнее: «снаружи заведомо слишком "
        "широкой оболочки, следовательно тем более вне резкого множества "
        "внутри неё» — при условии, что оболочка действительно внешняя."),
)


#: РЕШЕНИЯ, вступающие в силу с этого момента.
DECISIONS: dict[str, str] = {
    "S4_Q1c": "CLOSED",
    "strict_on_coarse_timestamps":
        "НЕ ЯВЛЯЕТСЯ допустимым primary analysis для этой метрики. Не "
        "«шумный», не «консервативный» — он считает другой функционал, и его "
        "значение может не принадлежать множеству совместимых величин.",
    "tie_policy_for_coarse_data":
        "BOUNDED. ORDER_AMBIGUOUS — НОРМАЛЬНЫЙ ИСХОД, а не повод выбрать "
        "удобный tie-break. Равномерный случайный порядок внутри корзины "
        "вводит вероятностную модель, которой источник не давал.",
    "sharper_time_layer": "NOT_WORTH_BUILDING (порог объявлен до прогона)",
    "Q1a_absolute_incidence": "DOCUMENTED_LIMITATION — не измерено",
    "n_eligible_boundary_semantics":
        "DEFERRED до появления настоящих fixed person-period окон. Сейчас это "
        "красивый краевой случай; тогда станет частью эстиманда.",
}


#: ЧТО S4 РАЗРЕШИЛ КАЛИБРОВАТЬ.
CALIBRATABLE: tuple[str, ...] = (
    "локальная временная структура потока",
    "слияние серий под оператором C_60",
    "связь неоднозначности с локальной плотностью",
    "ширина идентификации, создаваемая неопределённостью порядка",
    "поведение грубого наблюдателя",
)

#: ЧЕГО НЕ РАЗРЕШИЛ. Список существует затем, чтобы на него можно было
#: показать пальцем, когда в S5b появится соблазн.
NOT_CALIBRATABLE: tuple[str, ...] = (
    "абсолютные opportunities в сутки",
    "истинная доля неответов в популяции с полным покрытием",
    "incidence бремени на фиксированном окне",
)

#: ПРЕДЛОЖЕНИЯ, ЗАПРЕЩЁННЫЕ В S5B. Дословно, чтобы узнавались.
FORBIDDEN_IN_S5B: tuple[str, ...] = (
    "S4 откалибровал incidence",
    "мы знаем типичную плотность переписки",
    "opportunity_rate_per_day взят из данных",
    "средняя из WhatsApp и NetHealth",
    "STRICT даёт консервативную оценку",
)

#: S5b РАЗБЛОКИРОВАН ЧАСТИЧНО. Прежний статус BLOCKED_ON_S4 снимается только
#: с того, что S4 действительно установил.
S5B_STATUS = "PARTIALLY_UNBLOCKED"
S5B_UNBLOCKED = ("оператор огрубления", "поведение наблюдателя",
                 "ширина идентификации как функция локальной плотности")
S5B_STILL_BLOCKED = ("абсолютная incidence как вход дизайна",
                     "единственное число pilot N без оси чувствительности")

#: opportunity_rate_per_day остаётся ОСЬЮ СЕТКИ ЧУВСТВИТЕЛЬНОСТИ, а не
#: входным числом. Никакого среднего, добытого плоскогубцами из двух чужих
#: корпусов и объявленного человеческой природой.
OPPORTUNITY_RATE_IS_A_SENSITIVITY_AXIS = True

#: МОРОЗИЛКА. Каждый пункт — с причиной, по которой он туда попал.
FREEZER: dict[str, str] = {
    "DPBoundsSharp": "вывод сильнее не делает; достижимость проверена оракулом",
    "IdentifiedSetIsContiguous": "ни один вывод от непрерывности не зависит",
    "temporal_layer_lean_proof": "сначала оценить размер задачи, потом решать",
    "fractional_optimization_proof": "оракул покрывает, причины спешить нет",
    "upstream_comparator": "несовместимая инфраструктура; локальный судья на месте",
    "nanoda": "закрывает риск №999 при открытых рисках №1-3",
    "sharper_time_solver": "объявленный заранее порог сказал NOT_WORTH_BUILDING",
    "seventh_corpus": "stop-rule сработал; правило до первого неудобного "
                      "результата — не preregistration",
}


def licenses(key: str) -> str:
    for claim in CLAIMS:
        if claim.key == key:
            return claim.licenses
    raise KeyError(key)
