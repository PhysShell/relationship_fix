"""Генератор событийных трасс переписки с ИЗВЕСТНЫМ порождающим процессом.

Для пассивных метрик текст почти не нужен: нужны момент, актёр, границы серий и
окно. Поэтому здесь не синтезируются диалоги — здесь синтезируется ПРОЦЕСС, и
LLM для этого не требуется. Романтические страдания, к счастью, не являются
runtime-зависимостью.

Главная ценность — не объём, а то, что мы кладём эффект своей рукой:

    true_latency_shift      = +20 с
    true_opportunity_ratio  = 0.85
            ↓
    сгенерированные трассы
            ↓
    ЗАМОРОЖЕННЫЙ экстрактор
            ↓
    estimands
            ↓
    восстановили ли мы то, что положили?

Фиктивный чат от LLM этого не даёт: там никто не знает истинного
data-generating process, и «правдоподобно выглядит» — не проверка.

Никакого текста генератор не производит вовсе. `char_count` — число, а не
строка: длина участвует в одном описательном агрегате и не участвует ни в одной
топологической величине.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace

from extractor.model import RawMessage

HOUR = 3600.0
DAY = 24 * HOUR

PARTNER = "partner"
PARTICIPANT = "participant"


@dataclass(frozen=True, slots=True)
class DyadParameters:
    """Процесс одной пары. Все параметры — про ВРЕМЯ и ОЧЕРЁДНОСТЬ."""

    #: сколько раз в сутки партнёр открывает новую серию
    opportunity_rate_per_day: float = 6.0
    #: длина серии партнёра (геометрическая, среднее = 1/(1-p))
    burst_continue_p: float = 0.35
    #: пауза внутри серии
    within_burst_seconds: float = 45.0
    #: логнормальная латентность ответа участника
    latency_log_mean: float = math.log(600.0)      # медиана 10 минут
    latency_log_sd: float = 1.2
    #: вероятность, что участник не ответит вовсе
    nonresponse_p: float = 0.08
    #: ночное подавление: доля попыток, отбрасываемых в ночные часы
    night_suppression: float = 0.9
    night_start_hour: int = 1
    night_end_hour: int = 8
    #: РАЗРЕШЕНИЕ ЧАСОВ ИСТОЧНИКА. Не косметика и не округление для красоты.
    #: Telegram отдаёт целые секунды, а `TiePolicy.STRICT` выбрасывает каждую
    #: возможность, задевшую cross-actor tie. Генератор с непрерывным временем
    #: не производит таких ties почти никогда — и тогда симуляция отвечает на
    #: вопрос о часах, которых у нас нет, а доля выброшенного и дисперсия
    #: выходят оптимистичными. Квантование идёт floor'ом: он монотонен, поэтому
    #: ответ не может уехать ВПЕРЁД сообщения, на которое отвечает; он может
    #: только совпасть с ним секундой, что и есть моделируемое явление.
    timestamp_resolution_seconds: float = 1.0
    #: принудительный tie сверх естественных — ручка для тестов и для вопроса
    #: «а если источник грубее, чем мы думаем». В норме ноль: естественной
    #: неоднозначности от разрешения часов достаточно и она честнее.
    tie_p: float = 0.0
    mean_chars: float = 40.0


@dataclass(frozen=True, slots=True)
class Population:
    """Гетерогенность между парами: у каждой свои параметры вокруг базовых."""

    base: DyadParameters = DyadParameters()
    #: SD логарифма частоты возможностей между парами
    rate_log_sd: float = 0.45
    #: SD сдвига логарифма латентности между парами
    latency_log_sd_between: float = 0.5
    #: SD доли неответов между парами (усечённая)
    nonresponse_sd: float = 0.04

    def draw(self, rng: random.Random) -> DyadParameters:
        base = self.base
        return replace(
            base,
            opportunity_rate_per_day=base.opportunity_rate_per_day
            * math.exp(rng.gauss(0.0, self.rate_log_sd)),
            latency_log_mean=base.latency_log_mean
            + rng.gauss(0.0, self.latency_log_sd_between),
            nonresponse_p=min(0.6, max(0.0, base.nonresponse_p
                                       + rng.gauss(0.0, self.nonresponse_sd))),
        )


@dataclass(frozen=True, slots=True)
class TrueEffect:
    """То, что кладём рукой. Ноль по всем полям = нулевой эффект.

    Разделено на три канала намеренно: мы уже установили, что воздействие может
    двигать И частоту возможностей, И длительность, И вероятность молчания, и
    что эти три величины — не одно и то же (`reentry_burden_H` = incidence x
    duration плюс ковариация).
    """

    #: множитель частоты возможностей: 0.85 = на 15% реже
    opportunity_rate_ratio: float = 1.0
    #: сдвиг ЛОГАРИФМА латентности: +0.1 ≈ на 10% дольше
    latency_log_shift: float = 0.0
    #: аддитивный сдвиг вероятности неответа
    nonresponse_shift: float = 0.0

    @property
    def is_null(self) -> bool:
        return (self.opportunity_rate_ratio == 1.0
                and self.latency_log_shift == 0.0
                and self.nonresponse_shift == 0.0)

    def apply(self, params: DyadParameters) -> DyadParameters:
        return replace(
            params,
            opportunity_rate_per_day=params.opportunity_rate_per_day
            * self.opportunity_rate_ratio,
            latency_log_mean=params.latency_log_mean + self.latency_log_shift,
            nonresponse_p=min(0.95, max(0.0, params.nonresponse_p + self.nonresponse_shift)),
        )


def _is_night(at: float, params: DyadParameters) -> bool:
    """Окно ночи, включая левую границу и исключая правую.

    Вырожденный случай `start == end` означает ОТСУТСТВИЕ ночи, и это
    приходится сказать явно: без этой ветки он попадал в перенос через полночь,
    где `hour >= start or hour < end` истинно всегда, и ночью становились сутки
    целиком. Человек, написавший `night_start_hour = night_end_hour = 0` в
    смысле «ночи нет», получил бы подавление 90% всего потока и ни одной
    ошибки.
    """
    start, end = params.night_start_hour, params.night_end_hour
    if start == end:
        return False
    hour = (at % DAY) / HOUR
    return start <= hour < end if start < end else (hour >= start or hour < end)


def generate_dyad(
    rng: random.Random,
    params: DyadParameters,
    *,
    days: float,
    start: float = 0.0,
) -> list[RawMessage]:
    """Одна пара за `days` суток. Возвращает поток `RawMessage` без текста.

    Порождающий процесс ровно тот, который наша топология и описывает: партнёр
    открывает серию, участник либо возвращается, либо нет, следующая возможность
    наступает после этого. Ничего про «отношения» здесь нет и быть не должно.
    """
    messages: list[RawMessage] = []
    now = start
    end = start + days * DAY
    counter = 0
    mean_gap = DAY / max(params.opportunity_rate_per_day, 1e-6)

    resolution = params.timestamp_resolution_seconds

    def push(actor: str, at: float) -> None:
        nonlocal counter
        counter += 1
        stamped = math.floor(at / resolution) * resolution if resolution > 0 else at
        messages.append(RawMessage(
            message_id=f"{counter:09d}",
            actor=actor,
            local_time=stamped,
            utc_offset_minutes=0,
            char_count=max(1, int(rng.expovariate(1.0 / params.mean_chars))),
            device_id="sim",
            deleted=False,
            synced_at=None,
        ))

    while now < end:
        now += rng.expovariate(1.0 / mean_gap)
        if now >= end:
            break
        if _is_night(now, params) and rng.random() < params.night_suppression:
            continue

        # серия партнёра
        opened = now
        push(PARTNER, opened)
        last = opened
        while rng.random() < params.burst_continue_p:
            last += rng.expovariate(1.0 / params.within_burst_seconds)
            push(PARTNER, last)

        if rng.random() < params.nonresponse_p:
            now = last                     # участник не вернулся
            continue

        latency = rng.lognormvariate(params.latency_log_mean, params.latency_log_sd)
        reply_at = opened + latency
        if rng.random() < params.tie_p:
            reply_at = last                # cross-actor tie: та же секунда
        if reply_at >= end:
            now = last
            continue
        push(PARTICIPANT, reply_at)
        now = reply_at

    return messages


def generate_arm(
    seed: int,
    population: Population,
    effect: TrueEffect,
    *,
    dyads: int,
    days: float,
    label: str = "",
) -> list[list[RawMessage]]:
    """Рука эксперимента: `dyads` пар, каждой свои параметры плюс общий эффект.

    Два генератора на пару, а не один общий на руку, и оба засеяны СТРОКОЙ:

        f"{seed}:{label}:{index}:params"   гетерогенность
        f"{seed}:{label}:{index}:stream"   шум событий

    Строковый seed в `random.Random` идёт через sha512, а не через `hash()`,
    поэтому не зависит от `PYTHONHASHSEED`. Один общий rng на руку так не умеет:
    стоит эффекту изменить число вытянутых чисел у пары 0, и у пары 1 расходится
    всё, хотя эффект к ней применён тот же.

    `label` управляет спариванием рук и это не косметика, а выбор вопроса:

        label одинаковый   пара i в обеих руках получает ОДНИ параметры и один
                           поток шума. Контраст тогда изолирует эффект от
                           выборочного шума — этим проверяют, восстанавливает ли
                           анализ положенное. При нулевом эффекте руки совпадают
                           побитово, и контраст обязан быть ровно нулём.
        label разный       пары независимы, как в настоящей рандомизации. Только
                           так можно мерить дисперсию контраста и мощность;
                           спаренная дисперсия занижена и для мощности лжёт.
    """
    arm: list[list[RawMessage]] = []
    for index in range(dyads):
        params = effect.apply(population.draw(random.Random(f"{seed}:{label}:{index}:params")))
        arm.append(generate_dyad(
            random.Random(f"{seed}:{label}:{index}:stream"), params, days=days,
        ))
    return arm
