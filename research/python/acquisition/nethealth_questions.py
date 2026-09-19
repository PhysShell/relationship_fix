"""Что именно NetHealth имеет право отвечать — по вопросам, а не целиком.

Разбиение выводится из вердиктов проверок (`admissibility`), а не объявляется
руками. Поэтому если завтра `coverage.capture_window` закроется, Q1 поднимется
сам, а пока он закрыт — не поднимется никаким энтузиазмом.

Корпус ЗАМОРОЖЕН в этом качестве: попытки выжать из него incidence прекращены.
Дальше началась бы знакомая алхимия «сложили два соседних признака и получили
observability».
"""

from __future__ import annotations

from .admission import Question, Admissibility, admissibility
from .nethealth_admission import admission

#: Проверки, от которых зависит любой разговор о событиях вообще.
_BASE = ("licence.terms", "licence.derivative_reach", "schema.fields",
         "schema.text_present", "time.semantics", "identity.dyad",
         "direction.sender_receiver", "events.non_message",
         "events.duplicate_semantics", "identity.resolution_quality")

QUESTIONS: tuple[Question, ...] = (
    Question(
        "tie_pressure_SM",
        "Какова доля cross-actor ties и цена `TiePolicy.STRICT` на родной "
        "секундной шкале канала SM?",
        requires=_BASE + ("time.resolution", "channel.mixing"),
    ),
    Question(
        "duplicate_mechanics",
        "Как устроено двойное логирование одного события и чем оно опасно?",
        requires=_BASE,
    ),
    Question(
        "channel_platform_structure",
        "Как каналы связаны с платформой и путём сбора?",
        requires=_BASE + ("time.resolution", "channel.mixing"),
    ),
    Question(
        "run_topology",
        "Как устроены серии сообщений и возвраты внутри НАБЛЮДЁННОГО потока?",
        requires=_BASE,
        degraded_by=("coverage.capture_window",),
        degradation=(
            "Неизвестная terminal acquisition режет ПРАВЫЙ хвост: последняя "
            "серия и последний ответ могут не попасть в выгрузку. Для "
            "топологии это меньшее зло, чем для incidence, но не ноль — "
            "поэтому PARTIAL, а не QUALIFIED."),
    ),
    Question(
        "completed_reply_latency",
        "Как распределена латентность ЗАВЕРШЁННЫХ возвратов?",
        requires=_BASE,
        degraded_by=("coverage.capture_window",),
        degradation=(
            "Тот же правый хвост: возврат, случившийся после последней "
            "выгрузки, выглядит как незавершённый. Смещение направлено в одну "
            "сторону — в сторону более коротких наблюдённых латентностей."),
    ),
    Question(
        "incidence_per_day",
        "Сколько возможностей в сутки? Сколько `N` на person-period?",
        requires=_BASE + ("coverage.capture_window",),
    ),
    Question(
        "nonresponse_fraction",
        "Какова доля неотвеченных возможностей?",
        requires=_BASE + ("coverage.capture_window",),
    ),
    Question(
        "fixed_window_burden",
        "Каков `reentry_burden_H` на фиксированном окне?",
        requires=_BASE + ("coverage.capture_window",),
    ),
)


def verdicts() -> dict[str, Admissibility]:
    state = admission()
    return {q.key: admissibility(q, state) for q in QUESTIONS}


def render() -> str:
    state = admission()
    lines = ["NETHEALTH — admissibility by question (frozen)"]
    for group in (Admissibility.QUALIFIED, Admissibility.PARTIAL,
                  Admissibility.REFUSED):
        members = [q for q in QUESTIONS if admissibility(q, state) is group]
        if not members:
            continue
        lines.append(f"  {group.value}:")
        for q in members:
            lines.append(f"    {q.key}")
            if q.degradation:
                lines.append(f"      ! {q.degradation.splitlines()[0][:70]}")
    return "\n".join(lines)
