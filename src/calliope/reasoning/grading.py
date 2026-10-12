"""Grading policies: which curve turns the scores of S into expected points (Q-D §3–§4, QM-D).

`quality_v1` reads Stockfish's WDL (R0-D §7.2). `quality_v2` reads the score of each line of S
through a human expected-score curve:
- an explicit or default scale `c` uses the logistic `1 / (1 + 10^(−cp / c))`, evaluated in
  integers through the frozen table `LOGISTIC` (Q-D §4.2);
- ratings with a time class read a band of the build's curve table: a monotone, antisymmetric,
  piecewise-linear table of integer knots (`table_points`, QM-D §4).

A build (`GradingBuild`) holds the curve tables and the chess.com conversions; tables reach a build
only through `load_curve_table` and `load_conversion`, which check them (QM-D §9, Q-D §3.1).
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal
from enum import StrEnum
from itertools import pairwise

from calliope.reasoning.errors import InvalidAnalysisRequest, ReasoningError

QUALITY_V1 = "quality_v1"
QUALITY_V2 = "quality_v2"
POLICIES = (QUALITY_V1, QUALITY_V2)
DEFAULT_SCALE = 1000
TIME_CLASSES = ("bullet", "blitz", "rapid", "classical")


def time_class(control: str) -> str | None:
    """Lichess's rule on `base + 40 × increment` seconds (Q-D §3); None for correspondence.

    Moved here from `tools/calibrate_curve` (AS-D S10) so that `calliope.server` can use it."""

    base, sep, increment = control.partition("+")
    if not sep or not base.isdigit() or not increment.isdigit():
        return None
    duration = int(base) + 40 * int(increment)
    if duration < 180:
        return "bullet"
    if duration < 480:
        return "blitz"
    if duration < 1500:
        return "rapid"
    return "classical"


def chesscom_time_class(control: str) -> str | None:
    """chess.com writes `600` for 10 | 0 and `1/259200` for daily games."""

    if "/" in control:
        return None
    return time_class(control if "+" in control else f"{control}+0")


POOLS = ("lichess", "chesscom")
CHESSCOM_POOLS = ("bullet", "blitz", "rapid")  # chess.com has no live classical pool (Q-D §3.1)
SCALES = (100, 20000)
RATINGS = (0, 4000)
MIN_POSITIONS = 100_000
LOGISTIC10 = "logistic10"
MONOTONE_V1 = "monotone_v1"
# the knots of `monotone_v1`, in source cp (QM-D §5 step 2): dense near 0, sparse in the tails
MONOTONE_V1_KNOTS = (
    tuple(range(0, 300, 10)) + tuple(range(300, 600, 25)) + tuple(range(600, 1501, 50))
)
MAX_SHARD_DEVIATION = 10  # QM-D §6.1, in 1/2000
COVERED_BELOW = 600  # every knot below this must be estimated (QM-D §6.1)

# -- the standard curve in integers (Q-D §4.2) -----------------------------------------------------

T = 4000


# SHA-256 of the canonical encoding of `LOGISTIC`; checked at import (Q1 review B1)
LOGISTIC_DIGEST = "85063e831ba0d77340f4d65356c4ed5baaac23eed5cdb79310a9743652626be2"


def _logistic() -> tuple[int, ...]:
    """Every operation, the last rounding included, runs in its own context: the result never
    depends on the process's current `decimal` context (Q1 review B1)."""

    ctx = Context(prec=40, rounding=ROUND_HALF_EVEN)
    ten = Decimal(10)
    values = []
    for t in range(T + 1):
        x = ctx.power(ten, ctx.divide(Decimal(-t), Decimal(1000)))
        values.append(int(ctx.to_integral_value(ctx.divide(Decimal(2000), ctx.add(Decimal(1), x)))))
    return tuple(values)


def _digest(values: tuple[int, ...]) -> str:
    from calliope.facts import canonical

    return hashlib.sha256(canonical(values, {})).hexdigest()  # a tuple of ints needs no types


LOGISTIC = _logistic()
if _digest(LOGISTIC) != LOGISTIC_DIGEST:
    raise ReasoningError("the standard curve LOGISTIC does not match its pinned digest")


def logistic_digest() -> str:
    """SHA-256 of `LOGISTIC` in the canonical encoding, as built into the identity (Q-D §6)."""

    return _digest(LOGISTIC)


def curve_points(m: int, c: int) -> int:
    """Expected points in 1/2000 at `m` centipawns from the mover's view, scale `c`."""

    v = LOGISTIC[min(T, (abs(m) * 1000) // c)]
    return v if m >= 0 else 2000 - v


def table_points(m: int, points: tuple[tuple[int, int], ...]) -> int:
    """Expected points in 1/2000 at `m` centipawns from the mover's view, read from the knots
    `(x_i, e_i)` of a band, `x_0 = 0`, `e_0 = 1000` (QM-D §4)."""

    a = abs(m)
    x_n, v = points[-1]
    if a < x_n:
        for (xa, ea), (xb, eb) in pairwise(points):
            if xa <= a < xb:
                v = ea + (a - xa) * (eb - ea) // (xb - xa)
                break
    return v if m >= 0 else 2000 - v


def round_half_even_div(n: int, d: int) -> int:
    """`n / d` rounded half to even, in integers (`n ≥ 0`, `d > 0`)."""

    q, r = divmod(n, d)
    if 2 * r > d or (2 * r == d and q % 2 == 1):
        q += 1
    return q


# -- request and resolution (Q-D §3) ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GradingSpec:
    policy: str = QUALITY_V2
    scale: int | None = None  # explicit c, both sides
    white_rating: int | None = None
    black_rating: int | None = None
    rating_pool: str = "lichess"  # "lichess" | "chesscom"
    time_class: str | None = None  # "bullet" | "blitz" | "rapid" | "classical"


class CurveSource(StrEnum):
    EXPLICIT = "explicit"
    TABLE = "table"
    DEFAULT = "default"


@dataclass(frozen=True, slots=True)
class Curve:
    model: str  # "logistic10" (explicit, default) | "monotone_v1" (table) (QM-D §7)
    scale: int | None  # c under logistic10; None under monotone_v1
    source: CurveSource
    table: str | None = None
    time_class: str | None = None
    conversion: str | None = None  # the conversion table, under `chesscom`
    conversion_pool: str | None = None  # the chess.com pool whose anchors were used
    conversion_clamped: bool = False  # a rating fell strictly outside the anchors
    rating: int | None = None  # the Lichess-scale rating the band was read from
    band: int | None = None
    band_clamped: bool = False  # the band was not in the table; the nearest band was used
    ratings_overridden: bool = False  # ratings given, not used: an explicit scale won


@dataclass(frozen=True, slots=True)
class Grading:
    """The resolved grading (Q-D §3 `ResolvedGrading`, §5.1): the policy and its curve."""

    policy: str
    curve: Curve | None  # None under quality_v1
    points: tuple[tuple[int, int], ...] | None = None  # runtime knots of a TABLE band (QM-D §7)


V1 = Grading(QUALITY_V1, None)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_spec(spec: GradingSpec) -> None:
    """The structural checks of Q-D §3; failures raise `InvalidAnalysisRequest`."""

    if not isinstance(spec, GradingSpec):
        raise InvalidAnalysisRequest("grading must be a GradingSpec")
    if spec.policy not in POLICIES:
        raise InvalidAnalysisRequest(f"unknown grading policy {spec.policy!r}")
    ratings = (spec.white_rating, spec.black_rating)
    unused = spec.scale is not None or any(r is not None for r in ratings) or spec.time_class
    if spec.policy == QUALITY_V1 and unused:
        raise InvalidAnalysisRequest("quality_v1 takes no scale, rating or time class")
    if spec.scale is not None and not (
        _is_int(spec.scale) and SCALES[0] <= spec.scale <= SCALES[1]
    ):
        raise InvalidAnalysisRequest(f"scale must be an integer in [{SCALES[0]}, {SCALES[1]}]")
    for r in ratings:
        if r is not None and not (_is_int(r) and RATINGS[0] <= r <= RATINGS[1]):
            raise InvalidAnalysisRequest(
                f"a rating must be an integer in [{RATINGS[0]}, {RATINGS[1]}]"
            )
    if spec.rating_pool not in POOLS:
        raise InvalidAnalysisRequest(f"unknown rating pool {spec.rating_pool!r}")
    if spec.time_class is not None and spec.time_class not in TIME_CLASSES:
        raise InvalidAnalysisRequest(f"unknown time class {spec.time_class!r}")
    rated = any(r is not None for r in ratings)
    if rated != (spec.time_class is not None):
        raise InvalidAnalysisRequest("a rating and a time class come together (Q-D §3)")


def resolve(spec: GradingSpec, build: GradingBuild) -> Grading:
    """The curve of an analysis (Q-D §3); a pure function of the request and the build."""

    check_spec(spec)
    if spec.policy == QUALITY_V1:
        return V1
    given = tuple(r for r in (spec.white_rating, spec.black_rating) if r is not None)
    if spec.scale is not None:
        curve = Curve(LOGISTIC10, spec.scale, CurveSource.EXPLICIT, ratings_overridden=bool(given))
        return Grading(QUALITY_V2, curve)
    if not given:
        return Grading(QUALITY_V2, Curve(LOGISTIC10, DEFAULT_SCALE, CurveSource.DEFAULT))
    assert spec.time_class is not None
    table = build.curve_table()
    if table is None:
        raise InvalidAnalysisRequest(
            "CALIBRATION_UNAVAILABLE: this build has no curve table; pass an explicit scale"
        )
    conversion = conversion_pool = None
    conversion_clamped = False
    if spec.rating_pool == "chesscom":
        found = build.conversion()
        if found is None:
            raise InvalidAnalysisRequest(
                "CALIBRATION_UNAVAILABLE: this build has no chess.com conversion; "
                "pass an explicit scale"
            )
        conversion = found.name
        conversion_pool = spec.time_class if spec.time_class in CHESSCOM_POOLS else "rapid"
        anchors = found.anchors(conversion_pool)
        converted = tuple(convert(r, anchors) for r in given)
        given = tuple(value for value, _ in converted)
        conversion_clamped = any(clamped for _, clamped in converted)
    rating = sum(given) // len(given)
    band = rating // table.band_width * table.band_width
    bands = sorted(b.low for b in table.bands if b.time_class == spec.time_class)
    if not bands:
        raise InvalidAnalysisRequest(
            f"NO_BAND: the curve table {table.name} has no band for {spec.time_class}; "
            "pass an explicit scale"
        )
    chosen = min(bands, key=lambda low: (abs(low - band), low))  # the lower one on a tie
    entry = table.band(spec.time_class, chosen)
    curve = Curve(
        MONOTONE_V1,
        None,
        CurveSource.TABLE,
        table=table.name,
        time_class=spec.time_class,
        conversion=conversion,
        conversion_pool=conversion_pool,
        conversion_clamped=conversion_clamped,
        rating=rating,
        band=chosen,
        band_clamped=chosen != band,
    )
    return Grading(QUALITY_V2, curve, tuple(zip(table.knots, entry.points, strict=True)))


def convert(r: int, anchors: tuple[tuple[int, int], ...]) -> tuple[int, bool]:
    """A chess.com rating on the Lichess scale and whether it was clamped (Q-D §3.1)."""

    x0, y0 = anchors[0]
    xn, yn = anchors[-1]
    if r < x0:
        return y0, True
    if r > xn:
        return yn, True
    if r == xn:
        return yn, False
    for (xa, ya), (xb, yb) in pairwise(anchors):
        if xa <= r < xb:
            return ya + (r - xa) * (yb - ya) // (xb - xa), False
    raise AssertionError("unreachable: r is within the anchors")


# -- curve tables and conversions (QM-D §9, Q-D §3.1) ----------------------------------------------


@dataclass(frozen=True, slots=True)
class CurveBand:
    time_class: str
    low: int  # the band is [low, low + band_width)
    points: tuple[int, ...]  # e_i at each knot of MONOTONE_V1_KNOTS, in 1/2000 (QM-D §5)
    positions: int
    shard_deviation: int  # QM-D §6.1
    interpolated: tuple[int, ...]  # unestimated knots, source cp (QM-D §5 step 5)


@dataclass(frozen=True, slots=True)
class CurveTable:
    name: str
    pool: str
    band_width: int
    cp_ratio_permille: int
    digest: str  # SHA-256 of the file's bytes
    bands: tuple[CurveBand, ...]
    knots: tuple[int, ...]  # runtime knots, Calliope cp (QM-D §6.4)

    def band(self, time_class: str, low: int) -> CurveBand:
        return next(b for b in self.bands if b.time_class == time_class and b.low == low)


@dataclass(frozen=True, slots=True)
class ConversionTable:
    name: str
    digest: str
    pools: tuple[tuple[str, tuple[tuple[int, int], ...]], ...]  # (chess.com pool, anchors)

    def anchors(self, pool: str) -> tuple[tuple[int, int], ...]:
        return dict(self.pools)[pool]


@dataclass(frozen=True, slots=True)
class GradingBuild:
    """The grading data of a build: the current curve table and chess.com conversion."""

    curves: tuple[CurveTable, ...] = ()
    conversions: tuple[ConversionTable, ...] = ()

    def curve_table(self) -> CurveTable | None:
        """The current table on the Lichess scale: the last one of the build."""

        tables = [t for t in self.curves if t.pool == "lichess"]
        return tables[-1] if tables else None

    def conversion(self) -> ConversionTable | None:
        return self.conversions[-1] if self.conversions else None

    def identity(self) -> tuple:
        """What the build contributes to `ReasoningBuild` (Q-D §6)."""

        return (
            POLICIES,
            tuple((t.name, t.digest) for t in self.curves),
            tuple((c.name, c.digest) for c in self.conversions),
            logistic_digest(),
        )


def runtime_knots(knots: tuple[int, ...], cp_ratio_permille: int) -> tuple[int, ...]:
    """The knots in Calliope cp from stored integers only (QM-D §6.4)."""

    return tuple(round_half_even_div(x * cp_ratio_permille, 1000) for x in knots)


def _no_floats(value: object, where: str) -> None:
    if isinstance(value, float):
        raise ReasoningError(f"{where}: a float in a grading table (integers only)")
    if isinstance(value, dict):
        for k, v in value.items():
            _no_floats(v, f"{where}.{k}")
    if isinstance(value, list):
        for i, v in enumerate(value):
            _no_floats(v, f"{where}[{i}]")


def _int(record: dict, key: str, where: str) -> int:
    value = record.get(key)
    if not _is_int(value):
        raise ReasoningError(f"{where}: {key} must be an integer")
    return value


def _text(record: dict, key: str, where: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ReasoningError(f"{where}: {key} must be a non-empty string")
    return value


def _parse(data: bytes, what: str) -> dict:
    """TOML to a dict; every parse failure is a `ReasoningError` (Q-D §8, Q1 review C2)."""

    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ReasoningError(f"{what}: not valid UTF-8 TOML: {error}") from error
    _no_floats(raw, what)
    return raw


def _section(raw: dict, key: str, where: str) -> dict:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ReasoningError(f"{where}: [{key}] must be a table")
    return value


def _ints(record: dict, key: str, where: str) -> tuple[int, ...]:
    value = record.get(key)
    if not isinstance(value, list) or not all(_is_int(v) for v in value):
        raise ReasoningError(f"{where}: {key} must be a list of integers")
    return tuple(value)


def load_curve_table(data: bytes) -> CurveTable:
    """Parse and check a curve table (QM-D §9); a defect raises `ReasoningError`."""

    raw = _parse(data, "curve table")
    head = _section(raw, "table", "curve table")
    name = _text(head, "name", "curve table")
    if head.get("pool") != "lichess" or head.get("model") != MONOTONE_V1:
        raise ReasoningError(f"{name}: pool must be lichess and model {MONOTONE_V1}")
    # provenance (Q-D §7.2, Q1 review C1): what was read, what was used, and how it was fitted
    for key in ("source", "filters", "fit"):
        _text(head, key, name)
    read, games_read, games_used = (_int(head, k, name) for k in
                                    ("bytes_read", "games_read", "games_used"))  # fmt: skip
    if min(read, games_read, games_used) < 0 or games_used > games_read:
        raise ReasoningError(f"{name}: bytes_read, games_read, games_used inconsistent")
    width = _int(head, "band_width", name)
    ratio = _int(head, "cp_ratio_permille", name)
    if width <= 0 or ratio <= 0 or (ratio != 1000 and abs(ratio - 1000) <= 100):
        raise ReasoningError(f"{name}: bad band_width or cp_ratio_permille (Q-D §7.4 step 2)")
    if _ints(head, "knots", name) != MONOTONE_V1_KNOTS:
        raise ReasoningError(f"{name}: knots are not the {MONOTONE_V1} grid (QM-D §9)")
    knots = runtime_knots(MONOTONE_V1_KNOTS, ratio)
    if any(a >= b for a, b in pairwise(knots)):
        raise ReasoningError(f"{name}: runtime knots collide at cp_ratio_permille {ratio}")
    records = raw.get("band", [])
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ReasoningError(f"{name}: [[band]] must be an array of tables")
    bands: list[CurveBand] = []
    for i, record in enumerate(records):
        where = f"{name} band {i}"
        time_class = record.get("time_class")
        if time_class not in TIME_CLASSES:
            raise ReasoningError(f"{where}: unknown time class {time_class!r}")
        band = CurveBand(
            time_class,
            _int(record, "low", where),
            _ints(record, "points", where),
            _int(record, "positions", where),
            _int(record, "shard_deviation", where),
            _ints(record, "interpolated", where),
        )
        if band.low < 0 or band.low % width:
            raise ReasoningError(f"{where}: low is not a band boundary")
        if len(band.points) != len(MONOTONE_V1_KNOTS) or band.points[0] != 1000:
            raise ReasoningError(f"{where}: points must be one per knot, from 1000 (QM-D §4)")
        if any(a > b for a, b in pairwise(band.points)) or band.points[-1] > 2000:
            raise ReasoningError(f"{where}: points must be non-decreasing, at most 2000")
        if band.positions < MIN_POSITIONS:
            raise ReasoningError(f"{where}: fewer than {MIN_POSITIONS} positions (QM-D §6.1)")
        if not 0 <= band.shard_deviation <= MAX_SHARD_DEVIATION:
            raise ReasoningError(
                f"{where}: shard deviation above {MAX_SHARD_DEVIATION} (QM-D §6.1)"
            )
        if any(x not in MONOTONE_V1_KNOTS or x < COVERED_BELOW for x in band.interpolated) or any(
            a >= b for a, b in pairwise(band.interpolated)
        ):
            raise ReasoningError(
                f"{where}: interpolated must be increasing knots ≥ {COVERED_BELOW}"
            )
        bands.append(band)
    keys = [(b.time_class, b.low) for b in bands]
    if not bands or len(set(keys)) != len(keys):
        raise ReasoningError(f"{name}: no bands, or a band twice")
    digest = hashlib.sha256(data).hexdigest()
    return CurveTable(name, "lichess", width, ratio, digest, tuple(bands), knots)


def load_conversion(data: bytes) -> ConversionTable:
    """Parse and check a chess.com conversion (Q-D §3.1)."""

    raw = _parse(data, "conversion")
    head = _section(raw, "conversion", "conversion")
    name = _text(head, "name", "conversion")
    for key in ("source", "retrieved", "method"):
        if not isinstance(head.get(key), str) or not head[key]:
            raise ReasoningError(f"{name}: no {key} (provenance, Q-D §3.1)")
    pools = []
    for pool in CHESSCOM_POOLS:
        rows = _section(raw, pool, name).get("anchors")
        if not isinstance(rows, list) or len(rows) < 2:
            raise ReasoningError(f"{name}: {pool} needs at least two anchors")
        anchors = []
        for row in rows:
            if not (isinstance(row, list) and len(row) == 2 and all(_is_int(v) for v in row)):
                raise ReasoningError(f"{name}: {pool} anchors are integer pairs")
            anchors.append((row[0], row[1]))
        for (xa, ya), (xb, yb) in pairwise(anchors):
            if not (xa < xb and ya < yb):
                raise ReasoningError(f"{name}: {pool} anchors must strictly increase")
        pools.append((pool, tuple(anchors)))
    return ConversionTable(name, hashlib.sha256(data).hexdigest(), tuple(pools))


def shipped() -> GradingBuild:
    """The tables in `reasoning/curves/`, by file name; a defective file stops the import."""

    from importlib.resources import files

    curves: list[CurveTable] = []
    conversions: list[ConversionTable] = []
    folder = files("calliope.reasoning") / "curves"
    for entry in sorted(folder.iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".toml"):
            continue
        data = entry.read_bytes()
        sections = _parse(data, entry.name)
        if "conversion" in sections:
            conversions.append(load_conversion(data))
        elif "table" in sections:
            curves.append(load_curve_table(data))
        else:
            raise ReasoningError(f"{entry.name}: neither a curve table nor a conversion")
    return GradingBuild(tuple(curves), tuple(conversions))


SHIPPED = shipped()  # the build's grading data (Q-D §10: tables arrive with Q2)
