"""S4-Q1c ЗАКРЫТ. Машинный артефакт результата: что, на чём и когда.

Заведён затем, чтобы результат нельзя было «примерно вспомнить». Здесь
цифры, дайджесты входов и выходов, и — главное — ЯВНЫЙ ЗАПРЕТ продолжать
улучшать эту часть.
"""

from __future__ import annotations

STATUS = "CLOSED"
CLOSED_AT_COMMIT = "292cea0"
PREREG = "docs/research/q1c-coarsening-operator-prereg.md"
REPORT = "docs/research/tiepolicy-bounded.md"

#: ВХОД. Корпус не вендорится; сверяется дайджестами.
CORPUS_ARCHIVE_MD5 = "dd3dce055158e70a891e8db49dd2678f"
CENSUS_SHA256_16 = "14eee76ab80554d5f047dd9553cc75c7"
#: ВЫХОД, по одной строке на (диаду, горизонт).
ROWS_SHA256_16 = "cfad9c4f18df98289b8663994169869d"
LOG_SHA256_16 = "84d3f6f28d046468915b5d262d21a883"

DYADS_ADMITTED = 520
DYADS_ANALYSED = 517
HORIZONS_MINUTES = (5, 60, 1440)

#: ГЛАВНОЕ. Точечная оценка STRICT несовместима с наблюдениями.
STRICT_N_OUTSIDE_SHARP_SET = 0.981
STRICT_N_BELOW = 513
STRICT_N_ABOVE = 0
STRICT_RMTR_OUTSIDE_ENVELOPE = {5: 0.369, 60: 0.876, 1440: 0.777}
STRICT_RMTR_ABOVE = {5: 190, 60: 451, 1440: 398}
STRICT_RMTR_BELOW = {5: 0, 60: 0, 1440: 2}

#: Границы информативны: не «минутные данные бесполезны», а «ограничивают с
#: точностью до фактора около двух».
N_RELATIVE_WIDTH_MEDIAN = 0.53
RMTR_MULTIPLICATIVE_WIDTH_MEDIAN = {5: 3.00, 60: 2.28, 1440: 2.26}

#: Кто раздувает интервал, и вердикт по ОБЪЯВЛЕННОМУ ЗАРАНЕЕ порогу 0.5.
ORDER_SHARE_MEDIAN = {5: 0.64, 60: 0.84, 1440: 0.96}
SHARP_TIME_LAYER = "NOT_WORTH_BUILDING"

#: Сертификат измельчения на живых данных.
REFINEMENT_N_HELD, REFINEMENT_N_BROKEN = 174, 0
REFINEMENT_ENVELOPE_HELD, REFINEMENT_ENVELOPE_BROKEN = 174, 0

#: Плотностный градиент — то, что завершает Q1c содержательно.
STRICT_OUTSIDE_BY_DENSITY_QUARTILE = {
    5: (0.155, 0.225, 0.372, 0.715),
    60: (0.698, 0.876, 0.946, 0.969),
    1440: (0.636, 0.682, 0.829, 0.946),
}

#: ПОЧЕМУ ТЕОРЕМА ПРО N ЗДЕСЬ ПРИМЕНИМА. Прогон берёт
#: `window = last + horizon`, поэтому любая корзина начинается не позже
#: последнего события и eligible ВСЕ — на обеих шкалах. Следовательно
#: `N_eligible = NTopological`, и доказанная монотонность действует без
#: оговорки. Не везение, а свойство строки в `tools/bounded_q1c.py`.
ELIGIBILITY_IS_STABLE_HERE = True

#: НЕ УЛУЧШАТЬ. Preregistered stop-rule уже один раз спас проект от
#: превращения в диссертацию о минутах; второй раз он должен сработать без
#: напоминаний. Резкий временной слой не строится — решение принимается уже
#: широкой оболочкой, и сужение не изменит ни одного вывода.
DO_NOT_REOPEN = (
    "sharper temporal bounds",
    "a seventh corpus",
    "re-running with different horizons to see what happens",
)
