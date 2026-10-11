"""Band selection in the training month (QM-D §6.1) and the validation gates on the next month
(QM-D §6.2), with the deployed loss (QM-D §6.3, Q-D §7.6)."""

from __future__ import annotations

import math
import random
from array import array
from dataclasses import dataclass, field

from calliope.reasoning import curve_points, table_points
from calliope.reasoning.grading import MAX_SHARD_DEVIATION, MIN_POSITIONS, MONOTONE_V1_KNOTS
from tools.calibrate_curve.data import SHARDS, BandSums, Key, Training, Validation
from tools.calibrate_curve.fit import CLIP, fit, inside, merge, monotone, rounded

DEFAULT_SCALE = 1000
CLAMP = 1 / 4000  # half a unit of 1/2000 (Q-D §7.6)
RESAMPLES = 1000
SEED = 20261010
RELIABILITY_MIN = 2000
RELIABILITY_TOLERANCE = 0.03
WEIGHT_FLAG = 10  # gate 4: units of 1/2000 (QM-D §6.2)
ERASED_FLAG = 0.005  # the plateau report's flag (QM-D §5)

Cells = dict[int, tuple[float, float]]
Row = tuple[float, float, float, float, float, float, float]  # L0, L½, L1, B0, B½, B1, p


def _cells(raw: dict[int, list[int]]) -> Cells:
    return {x: (float(n), hp / 2) for x, (n, hp) in raw.items()}


def points_of(points: tuple[int, ...]) -> list[int]:
    """`table_points` on the source knots for every x in [−1500, 1500]."""

    knots = tuple(zip(MONOTONE_V1_KNOTS, points, strict=True))
    return [table_points(x, knots) for x in range(-CLIP, CLIP + 1)]


def logistic_of(scale: int) -> list[int]:
    return [curve_points(x, scale) for x in range(-CLIP, CLIP + 1)]


def rows(values: list[int]) -> list[Row]:
    """The deployed losses per x (QM-D §6.3): `p = E / 2000`, clamped for L, unclamped for B."""

    out = []
    for v in values:
        p = v / 2000
        q = min(max(p, CLAMP), 1 - CLAMP)
        l0, l1 = -math.log(1 - q), -math.log(q)
        out.append((l0, (l0 + l1) / 2, l1, p * p, (p - 0.5) ** 2, (1 - p) ** 2, p))
    return out


def deviation(a: list[int], b: list[int], cells: Cells) -> float:
    """The position-weighted mean |E_a − E_b| over a key's samples (QM-D §6.1)."""

    total = weight = 0.0
    for x, (n, _) in cells.items():
        total += n * abs(a[x + CLIP] - b[x + CLIP])
        weight += n
    return total / weight


# -- QM-D §6.1: selection in the training month ------------------------------------------------


@dataclass
class BandFit:
    key: Key
    positions: int
    logistic: int  # (d): the band's logistic c on the training month
    fittable: bool  # ≥ 100 000 positions and c strictly inside the search interval
    points: tuple[int, ...] | None = None
    interpolated: tuple[int, ...] = ()
    shard_deviation: float | None = None
    cross: dict = field(default_factory=dict)  # cross-fitted log losses and reliability
    weighted_deviation: float | None = None  # gate 4; None when the weighted fit is unestimable
    weighted_unestimated: tuple[int, ...] = ()  # knots below 600 cp the game weights do not cover
    sensitivity: tuple[int, ...] | None = None  # the table at 2 × bandwidth (report only)
    reasons: list[str] = field(default_factory=list)  # why §6.1 left the band out

    @property
    def kept(self) -> bool:
        return not self.reasons


def _cross(training: Training, key: Key, fit_: BandFit) -> None:
    """Five held-out shards: each scored by the table and the logistic fitted on the other four."""

    shards = [_cells(s) for s in training.shards[key]]
    totals = [0.0, 0.0, 0.0]  # log loss: table, default, band logistic
    n = 0.0
    bins = [[0.0, 0.0, 0.0] for _ in range(10)]
    default = rows(logistic_of(DEFAULT_SCALE))
    for k in range(SHARDS):
        train = merge(*(shards[j] for j in range(SHARDS) if j != k))
        table = monotone(train)
        if table.points is None:
            fit_.reasons.append(f"cross-fit {k}: knots {list(table.unestimated_below)} unestimated")
            return
        curves = (rows(points_of(table.points)), default, rows(logistic_of(rounded(fit(train)))))
        for x, (m, y) in shards[k].items():
            for c, curve in enumerate(curves):
                row = curve[x + CLIP]
                totals[c] += y * row[2] + (m - y) * row[0]
            p = curves[0][x + CLIP][6]
            b = bins[min(9, int(p * 10))]
            b[0] += m
            b[1] += p * m
            b[2] += y
            n += m
    table_loss, default_loss, logistic_loss = (t / n for t in totals)
    failing = [
        i
        for i, (m, sp, sy) in enumerate(bins)
        if m >= RELIABILITY_MIN and abs(sy / m - sp / m) > RELIABILITY_TOLERANCE
    ]
    fit_.cross = {
        "log_loss": {"table": table_loss, "default": default_loss, "logistic": logistic_loss},
        "reliability": [
            {"n": int(m), "p": sp / m, "y": sy / m} if m else {"n": 0} for m, sp, sy in bins
        ],
        "failing_bins": failing,
    }
    if table_loss > default_loss:
        fit_.reasons.append(f"cross-fitted log loss {table_loss:.6f} > c=1000's {default_loss:.6f}")
    if table_loss > logistic_loss:
        fit_.reasons.append(
            f"cross-fitted log loss {table_loss:.6f} > band logistic's {logistic_loss:.6f}"
        )
    if failing:
        fit_.reasons.append(f"cross-fitted reliability fails in bins {failing}")


def select(training: Training) -> dict[Key, BandFit]:
    """QM-D §6.1 on every (time class, band) of the training month."""

    out: dict[Key, BandFit] = {}
    for key in sorted(training.cells):
        cells = _cells(training.cells[key])
        positions = int(sum(n for n, _ in cells.values()))
        c = rounded(fit(cells))
        fit_ = BandFit(key, positions, c, positions >= MIN_POSITIONS and inside(c))
        out[key] = fit_
        if positions < MIN_POSITIONS:
            fit_.reasons.append(f"positions {positions} < {MIN_POSITIONS}")
            continue
        table = monotone(cells)
        if table.points is None:
            fit_.reasons.append(f"knots {list(table.unestimated_below)} unestimated")
            continue
        fit_.points, fit_.interpolated = table.points, table.interpolated
        band = points_of(table.points)
        worst = 0.0
        for k, raw in enumerate(training.shards[key]):
            shard = monotone(_cells(raw))
            if shard.points is None:
                fit_.reasons.append(f"shard {k}: knots {list(shard.unestimated_below)} unestimated")
                break
            worst = max(worst, deviation(points_of(shard.points), band, cells))
        else:
            fit_.shard_deviation = worst
            if worst > MAX_SHARD_DEVIATION:
                fit_.reasons.append(f"shard deviation {worst:.2f} > {MAX_SHARD_DEVIATION}")
        weighted = monotone({x: (w, y) for x, (w, y) in training.weighted[key].items()})
        if weighted.points is not None:
            fit_.weighted_deviation = deviation(points_of(weighted.points), band, cells)
        else:
            fit_.weighted_unestimated = weighted.unestimated_below
        fit_.sensitivity = monotone(cells, multiplier=2).points
        if not fit_.reasons:
            _cross(training, key, fit_)
    return out


def pooled(training: Training) -> dict[str, int]:
    """(c): one logistic scale per time class over all its training positions."""

    by_class: dict[str, list[Cells]] = {}
    for (tc, _band), raw in training.cells.items():
        by_class.setdefault(tc, []).append(_cells(raw))
    return {tc: rounded(fit(merge(*cells))) for tc, cells in sorted(by_class.items())}


def _nearest(lows: list[int], band: int) -> int:
    return min(lows, key=lambda low: (abs(low - band), low))  # the lower one on a tie


# -- QM-D §6.2: the fixed curves the validation month is scored against ------------------------


@dataclass
class KeyCurves:
    rows: list[tuple[Row, Row, Row, Row, Row]]  # per x: (a), (b), (c), (d), (e)
    table: list[int]  # (a) as points, for gate 6 and the plateau report
    logistic: list[int]  # (d) as points
    own: bool  # the key is a kept band itself (gate 3 scores own positions only)
    table_band: int  # the band (a) reads
    logistic_band: int | None  # the band (d) reads; None when (d) is the pooled curve
    fallback: bool  # (d) is not the key's own logistic


class Curves:
    """(a)–(e) per key, built from the selection; nothing here reads the validation month."""

    def __init__(self, fits: dict[Key, BandFit], pools: dict[str, int]) -> None:
        self.fits = fits
        self.pools = pools
        self.kept: dict[str, list[int]] = {}
        self.fittable: dict[str, list[int]] = {}
        for (tc, band), f in fits.items():
            if f.kept:
                self.kept.setdefault(tc, []).append(band)
            if f.fittable:
                self.fittable.setdefault(tc, []).append(band)
        self._cache: dict[Key, KeyCurves | None] = {}
        self._rows: dict[tuple, list[Row]] = {}

    def _memo(self, tag: tuple, values: list[int]) -> list[Row]:
        if tag not in self._rows:
            self._rows[tag] = rows(values)
        return self._rows[tag]

    def of(self, key: Key) -> KeyCurves | None:
        if key not in self._cache:
            self._cache[key] = self._build(key)
        return self._cache[key]

    def _build(self, key: Key) -> KeyCurves | None:
        tc, band = key
        if tc not in self.kept:
            return None  # the runtime refuses this time class (NO_BAND): outside the population
        near = _nearest(self.kept[tc], band)
        chosen = self.fits[(tc, near)]
        assert chosen.points is not None and chosen.sensitivity is not None
        table = points_of(chosen.points)
        if band in self.fittable.get(tc, []):
            logistic_band: int | None = band
        elif tc in self.fittable:
            logistic_band = _nearest(self.fittable[tc], band)
        else:
            logistic_band = None  # no fittable band: (d) is the pooled curve (re-review B2)
        scale = self.pools[tc] if logistic_band is None else self.fits[(tc, logistic_band)].logistic
        logistic = logistic_of(scale)
        a = self._memo(("a", tc, near), table)
        b = self._memo(("logistic", DEFAULT_SCALE), logistic_of(DEFAULT_SCALE))
        c = self._memo(("logistic", self.pools[tc]), logistic_of(self.pools[tc]))
        d = self._memo(("logistic", scale), logistic)
        e = self._memo(("e", tc, near), points_of(chosen.sensitivity))
        return KeyCurves(
            list(zip(a, b, c, d, e, strict=True)),
            table,
            logistic,
            near == band,
            near,
            logistic_band,
            logistic_band != band,
        )


# -- QM-D §6.2: the gates and the report -------------------------------------------------------


@dataclass
class Report:
    per_band: dict[str, dict]
    aggregate: dict
    reliability: dict[str, dict]
    plateaus: dict[str, dict]
    mate_allowing: dict[str, dict[str, int]]
    selection: dict[str, dict]
    passed: dict[str, bool]


def _bootstrap(validation: Validation) -> tuple[list[float], list[float], list[float]]:
    """Differences of (a) from (b), (c), (d): 1 000 resamples of whole games (QM-D §8.2)."""

    rng = random.Random(SEED)
    n = validation.game_n
    la, lb, lc, ld = validation.game_loss
    diffs = [array("d", (a - b for a, b in zip(la, other, strict=True))) for other in (lb, lc, ld)]
    games = len(n)
    out: tuple[list[float], list[float], list[float]] = ([], [], [])
    if not games:
        return out
    population = range(games)
    for _ in range(RESAMPLES):
        pick = rng.choices(population, k=games)
        m = sum(map(n.__getitem__, pick))
        for found, d in zip(out, diffs, strict=True):
            found.append(sum(map(d.__getitem__, pick)) / m)
    for found in out:
        found.sort()
    return out


def _interval(diffs: list[float]) -> list[float] | None:
    if not diffs:
        return None
    return [diffs[int(0.025 * RESAMPLES)], diffs[int(0.975 * RESAMPLES) - 1]]


def _bins(raw: list[list[float]], clusters: list[list[float]] | None = None) -> list[dict]:
    out = []
    for i, (n, sp, sy) in enumerate(raw):
        row: dict = {"n": int(n)}
        if n:
            row["p"], row["y"] = sp / n, sy / n
            row["ok"] = n < RELIABILITY_MIN or abs(sy / n - sp / n) <= RELIABILITY_TOLERANCE
            if clusters is not None and clusters[i][1]:
                r, m, rr, rm, mm = clusters[i]
                mean = r / m
                var = rr - 2 * mean * rm + mean * mean * mm  # Σ (r_g − mean · n_g)²
                row["cluster_se"] = math.sqrt(max(var, 0.0)) / m
        out.append(row)
    return out


def _plateaus(points: tuple[int, ...] | None) -> list[list[int]]:
    """Runs of equal points that start below 600 cp, as [first knot, last knot]."""

    if points is None:
        return []
    out: list[list[int]] = []
    start = None
    for i in range(1, len(points)):
        if points[i] == points[i - 1]:
            start = i - 1 if start is None else start
        elif start is not None:
            out.append([MONOTONE_V1_KNOTS[start], MONOTONE_V1_KNOTS[i - 1]])
            start = None
    if start is not None:
        out.append([MONOTONE_V1_KNOTS[start], MONOTONE_V1_KNOTS[-1]])
    return [run for run in out if run[0] < 600]


def validate(training: Training, validation: Validation, curves: Curves) -> Report:
    sums: dict[Key, BandSums] = validation.sums
    total = sum(s.positions for s in sums.values())
    names = ("table", "default_1000", "pooled", "band_logistic")
    log_loss = {
        name: (sum(s.log_loss[c] for s in sums.values()) / total if total else math.nan)
        for c, name in enumerate(names)
    }
    to_b, to_c, to_d = _bootstrap(validation)
    intervals = {"vs_default": _interval(to_b), "vs_pooled": _interval(to_c),
                 "vs_band_logistic": _interval(to_d)}  # fmt: skip
    gate2 = bool(total) and all(v is not None and v[1] < 0 for v in intervals.values())
    aggregate = {
        "positions": total,
        "games": len(validation.game_n),
        "fallback_positions": sum(s.fallback for s in sums.values()),
        "log_loss": log_loss,
        "difference_95": intervals,
        "bootstrap": {
            "resamples": RESAMPLES,
            "seed": SEED,
            "generator": "random.Random",
            "units": "games",
        },
    }

    per_band: dict[str, dict] = {}
    reliability: dict[str, dict] = {}
    plateaus: dict[str, dict] = {}
    mates: dict[str, dict[str, int]] = {}
    gate3 = True
    labels = (*names, "sensitivity")
    for key, s in sorted(sums.items()):
        label = f"{key[0]} {key[1]}"
        scored = curves.of(key)
        assert scored is not None
        per_band[label] = {
            "positions": s.positions,
            "table_band": scored.table_band,
            "clamped": not scored.own,
            "logistic_band": scored.logistic_band,
            "fallback": scored.fallback,
            "log_loss": dict(zip(labels, (v / s.positions for v in s.log_loss), strict=True)),
            "brier": dict(zip(labels, (v / s.positions for v in s.brier), strict=True)),
        }
        mates[label] = s.mate_allowing
        if not scored.own:
            continue  # gate 3 and the plateau report: kept bands on their own positions
        table_bins = _bins(s.bins[0], s.clusters)
        reliability[label] = {
            "table": table_bins,
            "band_logistic": _bins(s.bins[1]),
            "sensitivity": _bins(s.bins[2]),
        }
        gate3 = gate3 and all(b.get("ok", True) for b in table_bins)
        erased = s.erased / s.moves if s.moves else 0.0
        plateaus[label] = {
            "plateaus_below_600": _plateaus(curves.fits[key].points),
            "moves": s.moves,
            "worse": s.worse,
            "plateau_zero_share": s.plateau_zero / s.worse if s.worse else 0.0,
            "erased_share": erased,
            "converse_share": s.converse / s.moves if s.moves else 0.0,
            "flagged": erased > ERASED_FLAG,
        }

    selection: dict[str, dict] = {}
    for (key, evaluated), (games, hp, draws, rating) in sorted(training.selection.items()):
        row = selection.setdefault(f"{key[0]} {key[1]}", {})
        row["evaluated" if evaluated else "other"] = {
            "games": games,
            "white_score": hp / 2 / games,
            "draw_rate": draws / games,
            "mean_rating": rating / games,
        }
    gate1 = validation.positions >= training.positions / 5
    return Report(per_band, aggregate, reliability, plateaus, mates, selection,
                  {"gate1": gate1, "gate2": gate2, "gate3": gate3})  # fmt: skip


def weight_flags(fits: dict[Key, BandFit]) -> dict[str, dict]:
    """Gate 4 for every kept band (Q2 review C1): MEASURED with its deviation and whether it
    exceeds 10 units, or UNESTIMABLE with the knots the game-weighted samples do not cover."""

    out: dict[str, dict] = {}
    for (tc, band), f in sorted(fits.items()):
        if not f.kept:
            continue
        if f.weighted_deviation is None:
            out[f"{tc} {band}"] = {"status": "UNESTIMABLE",
                                   "unestimated": list(f.weighted_unestimated)}  # fmt: skip
        else:
            out[f"{tc} {band}"] = {
                "status": "MEASURED",
                "deviation": f.weighted_deviation,
                "flagged": f.weighted_deviation > WEIGHT_FLAG,
            }
    return out
