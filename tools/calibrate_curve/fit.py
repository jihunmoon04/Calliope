"""The fits: the monotone band table of QM-D §5, and the logistic of Q-D §7.1 step 4 (float form,
the loss of §7.6) for the baselines of QM-D §6.2."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from calliope.reasoning.grading import COVERED_BELOW, MONOTONE_V1_KNOTS

KNOTS = MONOTONE_V1_KNOTS
CLIP = 1500

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


# -- the monotone band table (QM-D §5) -------------------------------------------------------------

COVERAGE = 400.0  # symmetrized samples a knot's window needs to be estimated (QM-D §5 step 3)
WIDTH = 3  # the window is ±3 bandwidths


@dataclass(frozen=True)
class Monotone:
    """A band's table, or why it has none: `points` is None when a knot below 600 cp is
    unestimated (QM-D §5 step 3: the fit stops before the isotonic step)."""

    points: tuple[int, ...] | None
    interpolated: tuple[int, ...]  # unestimated knots ≥ 600 cp, filled by step 5
    unestimated_below: tuple[int, ...]  # unestimated knots < 600 cp (the band is refused)


def _kernels(multiplier: int) -> list[tuple[int, list[float]]]:
    """Per knot: the first x of its window and the Gaussian weights over the window."""

    out = []
    for i, k in enumerate(KNOTS):
        spacing = KNOTS[i + 1] - k if i + 1 < len(KNOTS) else k - KNOTS[i - 1]
        h = multiplier * spacing
        lo, hi = max(-CLIP, k - WIDTH * h), min(CLIP, k + WIDTH * h)
        out.append((lo, [math.exp(-(((x - k) / h) ** 2) / 2) for x in range(lo, hi + 1)]))
    return out


_KERNELS: dict[int, list[tuple[int, list[float]]]] = {}


def symmetric(cells: Cells) -> tuple[list[float], list[float]]:
    """`n(x)` and `s(x)` on [−1500, 1500]: every sample (x, y) also counts as (−x, 1 − y)."""

    n = [0.0] * (2 * CLIP + 1)
    s = [0.0] * (2 * CLIP + 1)
    for x, (w, y) in cells.items():
        n[CLIP + x] += w
        s[CLIP + x] += y
        n[CLIP - x] += w
        s[CLIP - x] += w - y
    return n, s


def _pav(values: list[float], weights: list[float]) -> list[float]:
    """Weighted pool-adjacent-violators: the non-decreasing least-squares fit."""

    blocks: list[list[float]] = []  # [weighted sum, weight, count]
    for v, w in zip(values, weights, strict=True):
        blocks.append([v * w, w, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            last = blocks.pop()
            for j in range(3):
                blocks[-1][j] += last[j]
    out: list[float] = []
    for total, weight, count in blocks:
        out += [total / weight] * int(count)
    return out


def estimates(cells: Cells, multiplier: int = 1) -> list[tuple[float, float] | None]:
    """QM-D §5 steps 1–3: per knot `(v_i, W_i)`, or None when `W_i < 400` (unestimated)."""

    kernels = _KERNELS.setdefault(multiplier, _kernels(multiplier))
    n, s = symmetric(cells)
    out: list[tuple[float, float] | None] = []
    for lo, weights in kernels:
        start = CLIP + lo
        cover = sum(w * n[start + j] for j, w in enumerate(weights))
        if cover >= COVERAGE:
            out.append((sum(w * s[start + j] for j, w in enumerate(weights)) / cover, cover))
        else:
            out.append(None)
    return out


def monotone(cells: Cells, multiplier: int = 1) -> Monotone:
    """QM-D §5 steps 1–6 on one key's (or shard's) aggregates."""

    estimated: list[tuple[int, float, float]] = []  # (knot index, v, W)
    missing: list[int] = []
    for i, found in enumerate(estimates(cells, multiplier)):
        if found is None:
            missing.append(KNOTS[i])
        else:
            estimated.append((i, *found))
    below = tuple(k for k in missing if k < COVERED_BELOW)
    if below:
        return Monotone(None, (), below)
    fitted = _pav([v for _, v, _ in estimated], [w for _, _, w in estimated])
    values: list[float | None] = [None] * len(KNOTS)
    for (i, _, _), v in zip(estimated, fitted, strict=True):
        values[i] = max(v, 0.5)
    known = [i for i, v in enumerate(values) if v is not None]  # knot 0 is among them
    for i, v in enumerate(values):
        if v is not None:
            continue
        lower = max(j for j in known if j < i)
        upper = min((j for j in known if j > i), default=None)
        vl = values[lower]
        assert vl is not None
        if upper is None:
            values[i] = vl
        else:
            vu = values[upper]
            assert vu is not None
            t = (KNOTS[i] - KNOTS[lower]) / (KNOTS[upper] - KNOTS[lower])
            values[i] = vl + t * (vu - vl)
    points = [1000] + [round(2000 * v) for v in values[1:] if v is not None]
    return Monotone(tuple(points), tuple(missing), ())
