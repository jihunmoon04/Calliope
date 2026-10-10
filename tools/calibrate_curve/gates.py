"""Band criteria (Q-D §7.3) and the validation gates (§7.5) with the deployed loss (§7.6)."""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass

from calliope.reasoning import curve_points
from calliope.reasoning.grading import MIN_POSITIONS
from calliope.reasoning.observer import BANDS
from tools.calibrate_curve.data import SHARDS, Key, Training, Validation, unpack
from tools.calibrate_curve.fit import fit, inside, merge, rounded

DEFAULT_SCALE = 1000
SPREAD = 0.15
CLAMP = 1 / 4000  # half a unit of 1/2000 (Q-D §7.6)
RESAMPLES = 1000
SEED = 20261010
RELIABILITY_MIN = 2000
RELIABILITY_TOLERANCE = 0.03
WEIGHT_FLAG = 0.10


def _cells(raw: dict[int, list[int]]) -> dict[int, tuple[float, float]]:
    return {x: (float(n), hp / 2) for x, (n, hp) in raw.items()}


@dataclass
class BandFit:
    key: Key
    positions: int
    source_scale: int
    shard_scales: tuple[int, ...]
    weighted_scale: int
    reasons: list[str]  # why §7.3 or gate 2 left the band out; empty = kept

    @property
    def kept(self) -> bool:
        return not self.reasons


def band_fits(training: Training) -> dict[Key, BandFit]:
    """§7.3 on every (time class, band) of the training month."""

    out: dict[Key, BandFit] = {}
    for key in sorted(training.cells):
        raw = training.cells[key]
        positions = sum(n for n, _ in raw.values())
        reasons = []
        if positions < MIN_POSITIONS:
            reasons.append(f"positions {positions} < {MIN_POSITIONS}")
            out[key] = BandFit(key, positions, 0, (), 0, reasons)
            continue
        scale = rounded(fit(_cells(raw)))
        shards = tuple(rounded(fit(_cells(s))) if s else 0 for s in training.shards[key][:SHARDS])
        weighted = rounded(fit({x: (w, y) for x, (w, y) in training.weighted[key].items()}))
        if max(shards) - min(shards) > SPREAD * scale:
            reasons.append(f"shard spread {max(shards) - min(shards)} > 0.15 × {scale}")
        if not inside(scale):
            reasons.append(f"source_scale {scale} at a search bound")
        out[key] = BandFit(key, positions, scale, shards, weighted, reasons)
    return out


def pooled(training: Training) -> dict[str, int]:
    """(c): one scale per time class over all its positions (gate 2)."""

    by_class: dict[str, list[dict]] = {}
    for (tc, _band), raw in training.cells.items():
        by_class.setdefault(tc, []).append(_cells(raw))
    return {tc: rounded(fit(merge(*cells))) for tc, cells in sorted(by_class.items())}


class Losses:
    """Deployed per-position losses (§7.6): `p = curve_points(x, c) / 2000`, clamped for L."""

    def __init__(self) -> None:
        self._tables: dict[int, list[tuple[float, float, float, float, float, float, float]]] = {}

    def table(self, scale: int):
        if scale not in self._tables:
            rows = []
            for x in range(-1500, 1501):
                p = curve_points(x, scale) / 2000
                q = min(max(p, CLAMP), 1 - CLAMP)
                l0, l1 = -math.log(1 - q), -math.log(q)
                rows.append((l0, (l0 + l1) / 2, l1, p * p, (p - 0.5) ** 2, (1 - p) ** 2, p))
            self._tables[scale] = rows
        return self._tables[scale]

    def at(self, scale: int, x: int, y: int) -> tuple[float, float, float]:
        """(log loss, Brier, p) for y code 0 / 1 / 2 (loss, draw, win for White)."""

        row = self.table(scale)[x + 1500]
        return row[y], row[3 + y], row[6]


def _nearest(kept: list[int], band: int) -> int:
    return min(kept, key=lambda low: (abs(low - band), low))


@dataclass
class Report:
    bands: dict[Key, BandFit]
    pooled: dict[str, int]
    per_band: dict[str, dict]
    aggregate: dict
    reliability: dict[str, list[dict]]
    mate_allowing: dict[str, dict[str, int]]
    selection: dict[str, dict]
    passed: dict[str, bool]


def validate(training: Training, validation: Validation, fits: dict[Key, BandFit]) -> Report:
    losses = Losses()
    total: Counter = Counter()
    for bucket in validation.buckets:
        total.update(bucket)
    keys = {kid: key for key, kid in validation.keys.items()}
    pools = pooled(training)

    # gate 2, per band: a candidate band stays only if its own curve is not worse than c = 1000
    sums: dict[Key, list[float]] = {}
    for packed, count in total.items():
        kid, x, y = unpack(packed)
        key = keys[kid]
        fit_ = fits.get(key)
        if fit_ is None or fit_.reasons:
            continue
        own, _, _ = losses.at(fit_.source_scale, x, y)
        base, _, _ = losses.at(DEFAULT_SCALE, x, y)
        s = sums.setdefault(key, [0.0, 0.0, 0.0])
        s[0] += count
        s[1] += own * count
        s[2] += base * count
    for key, fit_ in fits.items():
        if fit_.reasons:
            continue
        s = sums.get(key)
        if s is None:
            fit_.reasons.append("no validation positions")
        elif s[1] > s[2]:
            fit_.reasons.append(
                f"validation log loss {s[1] / s[0]:.6f} > c=1000's {s[2] / s[0]:.6f}"
            )

    kept: dict[str, list[int]] = {}
    for (tc, band), fit_ in fits.items():
        if fit_.kept:
            kept.setdefault(tc, []).append(band)
    scale_of: dict[Key, tuple[int, bool]] = {}  # (a): the resolved source scale, clamped?
    for kid, (tc, band) in keys.items():
        if tc in kept:
            near = _nearest(kept[tc], band)
            scale_of[(tc, band)] = (fits[(tc, near)].source_scale, near != band)

    # gate 2, aggregate, per bucket for the bootstrap; per band for the report
    per_band: dict[Key, list[float]] = {}
    per_bucket: list[list[float]] = []
    bins_by_bucket: list[dict[tuple[Key, int], list[float]]] = []  # for the cluster SE of gate 3
    for bucket in validation.buckets:
        acc = [0.0] * 4  # n, La, Lb, Lc
        bins: dict[tuple[Key, int], list[float]] = {}
        for packed, count in Counter(bucket).items():
            kid, x, y = unpack(packed)
            key = keys[kid]
            if key not in scale_of:
                continue
            la, ba, pa = losses.at(scale_of[key][0], x, y)
            lb, bb, _ = losses.at(DEFAULT_SCALE, x, y)
            if not scale_of[key][1]:
                cell = bins.setdefault((key, min(9, int(pa * 10))), [0.0, 0.0])
                cell[0] += count
                cell[1] += (y / 2 - pa) * count
            lc, bc, _ = losses.at(pools[key[0]], x, y)
            acc[0] += count
            acc[1] += la * count
            acc[2] += lb * count
            acc[3] += lc * count
            r = per_band.setdefault(key, [0.0] * 7)
            for i, v in enumerate((1, la, lb, lc, ba, bb, bc)):
                r[i] += v * count
        per_bucket.append(acc)
        bins_by_bucket.append(bins)
    n = sum(b[0] for b in per_bucket)
    rng = random.Random(SEED)
    diffs_b, diffs_c = [], []
    for _ in range(RESAMPLES if n else 0):
        pick = rng.choices(per_bucket, k=len(per_bucket))
        m = sum(b[0] for b in pick)
        diffs_b.append((sum(b[1] for b in pick) - sum(b[2] for b in pick)) / m)
        diffs_c.append((sum(b[1] for b in pick) - sum(b[3] for b in pick)) / m)
    diffs_b.sort()
    diffs_c.sort()
    lo, hi = int(0.025 * RESAMPLES), int(0.975 * RESAMPLES) - 1
    la = sum(b[1] for b in per_bucket) / n if n else math.nan
    aggregate = {
        "positions": int(n),
        "log_loss": {
            "table": la,
            "default_1000": sum(b[2] for b in per_bucket) / n if n else math.nan,
            "pooled": sum(b[3] for b in per_bucket) / n if n else math.nan,
        },
        "difference_vs_default_95": [diffs_b[lo], diffs_b[hi]] if n else None,
        "difference_vs_pooled_95": [diffs_c[lo], diffs_c[hi]] if n else None,
        "bootstrap": {"resamples": RESAMPLES, "seed": SEED, "generator": "random.Random",
                      "units": f"{len(per_bucket)} buckets of games by arrival order"},
    }  # fmt: skip
    gate2 = bool(n) and diffs_b[hi] < 0 and diffs_c[hi] < 0

    # gate 3, reliability of every kept band on its own positions
    reliability: dict[str, list[dict]] = {}
    gate3 = True
    for packed, count in total.items():
        kid, x, y = unpack(packed)
        key = keys[kid]
        if key not in scale_of or scale_of[key][1]:
            continue
        _, _, p = losses.at(scale_of[key][0], x, y)
        bins = reliability.setdefault(f"{key[0]} {key[1]}", [
            {"n": 0, "p": 0.0, "y": 0.0} for _ in range(10)])  # fmt: skip
        b = bins[min(9, int(p * 10))]
        b["n"] += count
        b["p"] += p * count
        b["y"] += y / 2 * count
    # report only: the cluster-robust standard error of y − p per bin, buckets of whole games as
    # clusters (positions of one game share its result, so positions overstate the information)
    for key, index in sorted({k for b in bins_by_bucket for k in b}):
        cells = [b.get((key, index), (0.0, 0.0)) for b in bins_by_bucket]
        total_n = sum(c[0] for c in cells)
        mean = sum(c[1] for c in cells) / total_n
        var = sum((c[1] - mean * c[0]) ** 2 for c in cells) * len(cells) / (len(cells) - 1)
        reliability[f"{key[0]} {key[1]}"][index]["cluster_se"] = math.sqrt(var) / total_n
    for bins in reliability.values():
        for b in bins:
            if b["n"]:
                b["p"] /= b["n"]
                b["y"] /= b["n"]
                b["ok"] = b["n"] < RELIABILITY_MIN or abs(b["y"] - b["p"]) <= RELIABILITY_TOLERANCE
                gate3 = gate3 and b["ok"]

    # gate 6: moves that let the eval turn into a mate against the mover, graded by E(before)
    mates: dict[str, dict[str, int]] = {}
    for kid, before in validation.mate_allowing:
        key = keys[kid]
        if key not in scale_of:
            continue
        loss = curve_points(before, scale_of[key][0])
        grade = next((name for bound, name in BANDS if loss < bound), "BLUNDER")
        row = mates.setdefault(f"{key[0]} {key[1]}", {})
        row[grade] = row.get(grade, 0) + 1

    # gate 5: evaluated games against all games of the training month
    selection: dict[str, dict] = {}
    for (key, evaluated), (games, hp, draws, rating) in sorted(training.selection.items()):
        row = selection.setdefault(f"{key[0]} {key[1]}", {})
        row["evaluated" if evaluated else "other"] = {
            "games": games,
            "white_score": hp / 2 / games,
            "draw_rate": draws / games,
            "mean_rating": rating / games,
        }

    report_bands = {}
    for key, r in sorted(per_band.items()):
        report_bands[f"{key[0]} {key[1]}"] = {
            "positions": int(r[0]),
            "clamped": scale_of[key][1],
            "scale": scale_of[key][0],
            "log_loss": [r[1] / r[0], r[2] / r[0], r[3] / r[0]],
            "brier": [r[4] / r[0], r[5] / r[0], r[6] / r[0]],
        }
    gate1 = validation.positions >= training.positions / 5
    return Report(fits, pools, report_bands, aggregate, reliability, mates, selection,
                  {"gate1": gate1, "gate2": gate2, "gate3": gate3})  # fmt: skip


def weight_flags(fits: dict[Key, BandFit]) -> dict[str, int]:
    """Gate 4: kept bands whose game-weighted scale is more than 10 % away."""

    return {
        f"{tc} {band}": f.weighted_scale
        for (tc, band), f in fits.items()
        if f.kept and abs(f.weighted_scale - f.source_scale) > WEIGHT_FLAG * f.source_scale
    }
