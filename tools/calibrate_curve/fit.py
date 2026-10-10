"""The fit of Q-D §7.1 step 4 with the loss of §7.6 (float form)."""

from __future__ import annotations

import math
from collections.abc import Mapping

LOW, HIGH = 150, 4000  # the search interval of `source_scale` (Q-D §7.1, §7.3)
TOLERANCE = 1e-6  # on log c
EPS = 1e-12
GOLDEN = (math.sqrt(5) - 1) / 2

# cells: x -> (weight, weighted score), with y the score in [0, 1] (draw = ½)
Cells = Mapping[int, tuple[float, float]]


def p_float(x: int, c: float) -> float:
    p = 1.0 / (1.0 + 10.0 ** (-x / c))
    return min(max(p, EPS), 1.0 - EPS)


def mean_loss(cells: Cells, c: float) -> float:
    """Mean fractional binary cross-entropy (Q-D §7.6) at scale `c`."""

    total = weight = 0.0
    for x, (n, y) in cells.items():
        p = p_float(x, c)
        total -= y * math.log(p) + (n - y) * math.log(1.0 - p)
        weight += n
    return total / weight


def fit(cells: Cells) -> float:
    """The `c` minimizing the mean loss, by golden-section search on `log c` in [150, 4000]."""

    lo, hi = math.log(LOW), math.log(HIGH)
    a, b = hi - GOLDEN * (hi - lo), lo + GOLDEN * (hi - lo)
    fa, fb = mean_loss(cells, math.exp(a)), mean_loss(cells, math.exp(b))
    while hi - lo > TOLERANCE:
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - GOLDEN * (hi - lo)
            fa = mean_loss(cells, math.exp(a))
        else:
            lo, a, fa = a, b, fb
            b = lo + GOLDEN * (hi - lo)
            fb = mean_loss(cells, math.exp(b))
    return math.exp((lo + hi) / 2)


def rounded(c: float) -> int:
    """Half-even to an integer (Q-D §7.1 step 4); Python's `round` rounds half to even."""

    return round(c)


def inside(scale: int) -> bool:
    """Strictly inside the search interval (Q-D §7.3)."""

    return LOW < scale < HIGH


def merge(*many: Cells) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    for cells in many:
        for x, (n, y) in cells.items():
            m, z = out.get(x, (0.0, 0.0))
            out[x] = (m + n, z + y)
    return out
