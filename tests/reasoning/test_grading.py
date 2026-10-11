"""`quality_v2` (Q-D §3–§6, QM-D §4, §7, §9; test obligations Q-D §9.1–§9.7, QM-D §10.1–§10.5):
the curves, their resolution and their readers."""

from __future__ import annotations

import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest
from scripted import fen_after, scripted
from story import R, S, claim, line, run, status
from test_quality import NO_WDL

from calliope.facts import Color, Cp, EngineProfile, FactEngine, Mate, RootSpec, Wdl
from calliope.reasoning import (
    LOGISTIC,
    MONOTONE_V1_KNOTS,
    SHIPPED,
    AnalysisRequest,
    Controller,
    Curve,
    CurveSource,
    Grade,
    Grading,
    GradingBuild,
    GradingSpec,
    InvalidAnalysisRequest,
    JudgementStatus,
    LineScore,
    ReasoningError,
    curve_points,
    grade,
    load_conversion,
    load_curve_table,
    resolve,
    score_points,
    table_points,
)
from calliope.reasoning.encoding import canonical_bytes
from calliope.reasoning.grading import convert, logistic_digest, round_half_even_div, runtime_knots
from calliope.reasoning.labels import LabelKind

PROFILE = EngineProfile()

HEAD = """[table]
name = "{name}"
pool = "lichess"
model = "monotone_v1"
band_width = 200
knots = {knots}
cp_ratio_permille = {ratio}
source = "https://database.lichess.org/standard/lichess_db_standard_rated_2026-08.pgn.zst"
bytes_read = 30145862359
games_read = 91912325
games_used = 7470000
filters = "rated; standard; |dElo| <= 100; %eval contiguous; ply >= 8; no mate evals"
fit = "symmetrized; gaussian h = knot spacing; coverage 400; weighted isotonic"
"""


def logistic_points(c: int) -> list[int]:
    """A band's points shaped like the logistic at `c`: non-decreasing, from 1000."""

    return [curve_points(x, c) for x in MONOTONE_V1_KNOTS]


def band_row(time_class: str, low: int, points: list[int], **extra) -> str:
    fields = {
        "time_class": f'"{time_class}"',
        "low": low,
        "points": points,
        "positions": 100000,
        "shard_deviation": 6,
        "interpolated": [],
        **extra,
    }
    return "[[band]]\n" + "".join(f"{k} = {v}\n" for k, v in fields.items())


def curve_table(*bands: str, name: str = "test_curve_v2", ratio: int = 1000, knots=None) -> bytes:
    head = HEAD.format(name=name, knots=list(knots or MONOTONE_V1_KNOTS), ratio=ratio)
    return (head + "\n" + "\n".join(bands)).encode()


POINTS = {800: logistic_points(1307), 1200: logistic_points(957), 1400: logistic_points(908)}
TABLE = curve_table(
    band_row("rapid", 800, POINTS[800], positions=210364),
    band_row("rapid", 1200, POINTS[1200], positions=576197),
    band_row("rapid", 1400, POINTS[1400], positions=721256, interpolated=[1400, 1450]),
    band_row("classical", 1400, logistic_points(850)),
)


def knots_of(low: int) -> tuple[tuple[int, int], ...]:
    return tuple(zip(MONOTONE_V1_KNOTS, POINTS[low], strict=True))


CONVERSION = b"""
[conversion]
name = "test_conversion_v1"
source = "https://chessiro.com/chess-rating-converter"
retrieved = "2026-10-10"
method = "survey of about 20 000 players active on both sites"

[rapid]
anchors = [[815, 1290], [995, 1425], [1170, 1555], [1340, 1680], [1420, 1740], [1500, 1795]]

[blitz]
anchors = [[500, 1090], [700, 1225], [900, 1360]]

[bullet]
anchors = [[550, 1060], [685, 1180]]
"""

BUILD = GradingBuild((load_curve_table(TABLE),), (load_conversion(CONVERSION),))
LICHESS_ONLY = GradingBuild((load_curve_table(TABLE),))


# -- §9.1 the standard curve --------------------------------------------------------------------


def test_the_standard_curve_table() -> None:
    assert len(LOGISTIC) == 4001
    assert LOGISTIC[0] == 1000 and LOGISTIC[1000] == 1818
    assert all(a <= b for a, b in pairwise(LOGISTIC))
    assert LOGISTIC[3601] == 1999 and LOGISTIC[3602] == 2000 and LOGISTIC[-1] == 2000
    assert logistic_digest() == "85063e831ba0d77340f4d65356c4ed5baaac23eed5cdb79310a9743652626be2"


def _python(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False
    )


def test_the_curve_does_not_depend_on_the_decimal_context() -> None:
    """Q1 review B1: a first import under another context builds the same table."""

    code = (
        "import decimal\n"
        "decimal.getcontext().rounding = decimal.ROUND_DOWN\n"
        "decimal.getcontext().prec = 3\n"
        "from calliope.reasoning.grading import LOGISTIC, logistic_digest\n"
        "print(LOGISTIC[4], LOGISTIC[100], LOGISTIC[1800], logistic_digest())\n"
    )
    result = _python(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["1005", "1115", "1969", logistic_digest()]


def test_a_table_that_does_not_match_its_digest_stops_the_import() -> None:
    from calliope.reasoning import grading

    source = Path(grading.__file__).read_text()
    assert source.count(grading.LOGISTIC_DIGEST) == 1
    code = (
        "import types, sys\n"
        f"source = {source.replace(grading.LOGISTIC_DIGEST, '0' * 64)!r}\n"
        "module = types.ModuleType('calliope.reasoning.grading_copy')\n"
        "sys.modules[module.__name__] = module\n"
        "try:\n"
        "    exec(compile(source, 'grading_copy', 'exec'), module.__dict__)\n"
        "except Exception as error:\n"
        "    print(type(error).__name__, error)\n"
    )
    result = _python(code)
    assert result.stdout.startswith("ReasoningError the standard curve"), result.stderr


# -- §9.2 expected points ------------------------------------------------------------------------


def test_curve_points() -> None:
    assert curve_points(100, 1000) == 1115 and curve_points(-100, 1000) == 885
    for m in (0, 1, 37, 499, 2500, -1, -37, -2500):
        for c in (150, 625, 1000, 1307):
            assert curve_points(m, c) + curve_points(-m, c) == 2000
    assert curve_points(1, 3) == LOGISTIC[333]  # (1 · 1000) // 3, floored
    assert curve_points(2, 3) == LOGISTIC[666]
    assert curve_points(10**6, 100) == 2000 and curve_points(-(10**6), 100) == 0
    assert curve_points(300, 1300) < curve_points(300, 1000) < curve_points(300, 600)  # flatter


DEFAULT = Grading("quality_v2", Curve("logistic10", 1000, CurveSource.DEFAULT))


def test_score_points_from_the_mover() -> None:
    assert score_points(Mate(Color.WHITE, 3), Color.WHITE, DEFAULT) == 2000
    assert score_points(Mate(Color.WHITE, 3), Color.BLACK, DEFAULT) == 0
    assert score_points(Cp(100), Color.WHITE, DEFAULT) == 1115
    assert score_points(Cp(100), Color.BLACK, DEFAULT) == 885


# -- QM-D §10.1 the band curve -----------------------------------------------------------------

PLATEAU = ((0, 1000), (10, 1030), (20, 1030), (100, 1100), (300, 1100), (600, 1500))


def test_table_points() -> None:
    assert table_points(0, PLATEAU) == 1000
    assert [table_points(x, PLATEAU) for x, _ in PLATEAU] == [e for _, e in PLATEAU]
    assert table_points(5, PLATEAU) == 1015 and table_points(7, PLATEAU) == 1021  # 1000 + 210 // 10
    assert table_points(101, PLATEAU) == 1100  # inside the plateau
    assert table_points(450, PLATEAU) == 1300 and table_points(451, PLATEAU) == 1301  # floored
    assert table_points(600, PLATEAU) == table_points(10**6, PLATEAU) == 1500  # beyond: e_n
    for m in (0, 1, 7, 99, 299, 300, 451, 600, 10**6):
        assert table_points(m, PLATEAU) + table_points(-m, PLATEAU) == 2000
    values = [table_points(m, PLATEAU) for m in range(-2000, 2001)]
    assert all(a <= b for a, b in pairwise(values))


def test_score_points_reads_the_band_under_a_table() -> None:
    grading = Grading("quality_v2", Curve("monotone_v1", None, CurveSource.TABLE), PLATEAU)
    assert score_points(Cp(450), Color.WHITE, grading) == 1300
    assert score_points(Cp(450), Color.BLACK, grading) == 700
    assert score_points(Mate(Color.BLACK, 2), Color.BLACK, grading) == 2000
    assert score_points(Mate(Color.BLACK, 2), Color.WHITE, grading) == 0


# -- §9.3 resolution -----------------------------------------------------------------------------


def test_precedence_explicit_then_table_then_default() -> None:
    rated = GradingSpec(white_rating=1250, black_rating=1250, time_class="rapid")
    assert resolve(GradingSpec(), SHIPPED) == DEFAULT
    explicit = resolve(GradingSpec(scale=1100), BUILD)
    assert explicit == Grading("quality_v2", Curve("logistic10", 1100, CurveSource.EXPLICIT))
    table = resolve(rated, BUILD)
    assert (table.curve.source, table.curve.model, table.curve.scale) == (
        CurveSource.TABLE,
        "monotone_v1",
        None,
    )
    assert (table.curve.band, table.curve.table) == (1200, "test_curve_v2")
    assert table.points == knots_of(1200)
    assert resolve(GradingSpec("quality_v1"), BUILD) == Grading("quality_v1", None)


def test_an_explicit_scale_overrides_ratings_even_in_the_shipped_build() -> None:
    spec = GradingSpec(scale=1000, white_rating=800, time_class="rapid")
    curve = resolve(spec, SHIPPED).curve
    assert curve == Curve("logistic10", 1000, CurveSource.EXPLICIT, ratings_overridden=True)


def test_the_average_rating_floored_or_the_one_given() -> None:
    both = resolve(GradingSpec(white_rating=1201, black_rating=1400, time_class="rapid"), BUILD)
    assert (both.curve.rating, both.curve.band) == (1300, 1200)  # 2601 // 2
    one = resolve(GradingSpec(black_rating=1450, time_class="rapid"), BUILD)
    assert (one.curve.rating, one.curve.band, one.points) == (1450, 1400, knots_of(1400))


def test_a_missing_band_clamps_to_the_nearest_lower_on_a_tie() -> None:
    far = resolve(GradingSpec(white_rating=2100, time_class="rapid"), BUILD)
    assert (far.curve.band, far.curve.band_clamped) == (1400, True)
    assert far.points == knots_of(1400)  # the nearest band's knots (QM-D §10.2)
    tie = resolve(GradingSpec(white_rating=1000, time_class="rapid"), BUILD).curve
    assert (tie.band, tie.band_clamped) == (800, True)  # 800 and 1200 are 200 away
    exact = resolve(GradingSpec(white_rating=800, time_class="rapid"), BUILD).curve
    assert not exact.band_clamped


def test_a_time_class_without_bands_is_refused() -> None:
    with pytest.raises(InvalidAnalysisRequest, match="^NO_BAND"):
        resolve(GradingSpec(white_rating=1500, time_class="bullet"), BUILD)


def test_ratings_without_calibration_are_refused() -> None:
    for pool in ("lichess", "chesscom"):
        spec = GradingSpec(white_rating=1500, rating_pool=pool, time_class="rapid")
        with pytest.raises(InvalidAnalysisRequest, match="^CALIBRATION_UNAVAILABLE"):
            resolve(spec, GradingBuild())
    chesscom = GradingSpec(white_rating=1500, rating_pool="chesscom", time_class="rapid")
    with pytest.raises(InvalidAnalysisRequest, match="^CALIBRATION_UNAVAILABLE"):
        resolve(chesscom, LICHESS_ONLY)  # a curve table but no conversion


def test_the_chesscom_conversion() -> None:
    rapid = BUILD.conversion().anchors("rapid")
    assert convert(815, rapid) == (1290, False)  # the lowest anchor is exact
    assert convert(1500, rapid) == (1795, False)  # so is the highest
    assert convert(814, rapid) == (1290, True)
    assert convert(1501, rapid) == (1795, True)
    assert convert(900, rapid) == (1290 + 85 * 135 // 180, False)  # 1353, floored
    assert convert(995, rapid) == (1425, False)


def test_conversion_comes_before_averaging() -> None:
    spec = GradingSpec(
        white_rating=815, black_rating=1500, rating_pool="chesscom", time_class="rapid"
    )
    curve = resolve(spec, BUILD).curve
    assert (curve.rating, curve.band) == (1542, 1400)  # (1290 + 1795) // 2
    assert (curve.conversion, curve.conversion_pool) == ("test_conversion_v1", "rapid")
    assert not curve.conversion_clamped and not curve.band_clamped


def test_classical_converts_with_the_rapid_anchors_and_clamps_apart() -> None:
    spec = GradingSpec(
        white_rating=600, black_rating=1500, rating_pool="chesscom", time_class="classical"
    )
    curve = resolve(spec, BUILD).curve
    assert curve.conversion_pool == "rapid" and curve.conversion_clamped  # 600 < 815
    assert (curve.rating, curve.band, curve.band_clamped) == (1542, 1400, False)
    blitz = GradingSpec(white_rating=1000, rating_pool="chesscom", time_class="rapid")
    assert resolve(blitz, BUILD).curve.conversion_pool == "rapid"


@pytest.mark.parametrize(
    "spec",
    [
        GradingSpec("quality_v3"),
        GradingSpec("quality_v1", scale=1000),
        GradingSpec("quality_v1", white_rating=1000, time_class="rapid"),
        GradingSpec(scale=99),
        GradingSpec(scale=20001),
        GradingSpec(scale=True),
        GradingSpec(scale=1000.0),  # type: ignore[arg-type]
        GradingSpec(white_rating=-1, time_class="rapid"),
        GradingSpec(white_rating=4001, time_class="rapid"),
        GradingSpec(rating_pool="fide"),
        GradingSpec(white_rating=1000, time_class="daily"),
        GradingSpec(white_rating=1000),  # a rating without a time class
        GradingSpec(time_class="rapid"),  # a time class without a rating
    ],
)
def test_structural_refusals(spec: GradingSpec) -> None:
    with pytest.raises(InvalidAnalysisRequest):
        resolve(spec, BUILD)
    request = AnalysisRequest(RootSpec(), ("e4",), 1, PROFILE, grading=spec)
    with pytest.raises(InvalidAnalysisRequest):
        Controller(FactEngine(engine=scripted({}))).round_zero(request)


def test_a_request_without_a_grading_spec_is_refused() -> None:
    request = AnalysisRequest(RootSpec(), ("e4",), 1, PROFILE, grading="quality_v2")  # type: ignore[arg-type]
    with pytest.raises(InvalidAnalysisRequest):
        Controller(FactEngine(engine=scripted({}))).round_zero(request)


# -- the tables (§7.2–§7.4, §3.1, checked at load) ---------------------------------------------


def _table(*, ratio: int = 1000, knots=None, drop: str | None = None, head=None, **band) -> bytes:
    fields = {"points": logistic_points(1000), **band}
    data = curve_table(band_row(fields.pop("time_class", "rapid"), fields.pop("low", 800),
                                fields.pop("points"), **fields), ratio=ratio, knots=knots)  # fmt: skip
    if drop:
        data = b"".join(
            row + b"\n" for row in data.splitlines() if not row.startswith(drop.encode())
        )
    if head:
        data = data.replace(*head)
    return data


def test_runtime_knots_are_derived_from_stored_integers() -> None:
    assert runtime_knots((0, 10, 1500), 1234) == (0, 12, 1851)
    assert round_half_even_div(1, 2) == 0 and round_half_even_div(3, 2) == 2
    table = load_curve_table(_table(ratio=1300))
    assert table.knots == runtime_knots(MONOTONE_V1_KNOTS, 1300) and table.knots[1] == 13
    assert load_curve_table(_table()).knots == MONOTONE_V1_KNOTS


def test_the_runtime_knots_carry_the_curve_over_to_calliope_cp() -> None:
    """QM-D §10.9: with x_C = 1.3 · x_L, the runtime knots give the source E within ⌈s⌉ + 1."""

    points = logistic_points(700)
    source = tuple(zip(MONOTONE_V1_KNOTS, points, strict=True))
    table = load_curve_table(_table(ratio=1300, points=points))
    runtime = tuple(zip(table.knots, points, strict=True))
    slope = max((eb - ea) / (xb - xa) for (xa, ea), (xb, eb) in pairwise(runtime))
    bound = int(slope) + 2  # ⌈s⌉ + 1
    for x_l in range(-1600, 1601):
        x_c = round(1.3 * x_l)
        assert abs(table_points(x_c, runtime) - table_points(x_l, source)) <= bound


def _two_knot_grid() -> bytes:
    return _table(knots=[0, 1500])


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: _table(positions=99999), "positions"),
        (lambda: _table(shard_deviation=11), "shard deviation"),
        (lambda: _table(ratio=1050), "cp_ratio_permille"),  # within 10 %: stored as 1000
        (lambda: _table(ratio=50), "collide"),  # 10 · 0.05 and 20 · 0.05 round to the same cp
        (lambda: _table(low=850), "boundary"),
        (lambda: _table(time_class="daily"), "time class"),
        (lambda: _table(points=[1000] * 60), "one per knot"),
        (lambda: _table(points=[1001] + logistic_points(1000)[1:]), "from 1000"),
        (lambda: _table(points=[1000, 1100, 1050] + [1100] * 58), "non-decreasing"),
        (lambda: _table(points=[1000] * 60 + [2001]), "at most 2000"),
        (lambda: _table(interpolated=[550]), "interpolated"),  # below 600: must be estimated
        (lambda: _table(interpolated=[1450, 1400]), "interpolated"),
        (lambda: _table(interpolated=[1425]), "interpolated"),  # not a knot
        (_two_knot_grid, "grid"),  # QM-D review B4
        (lambda: _table(knots=[0, 10, *MONOTONE_V1_KNOTS[3:], 1550][:61]), "grid"),
        (lambda: _table(head=(b'model = "monotone_v1"', b'model = "logistic10"')), "model"),
        (
            lambda: _table(head=(b"cp_ratio_permille = 1000", b"cp_ratio_permille = 1000.0")),
            "float",
        ),
    ],
)
def test_a_defective_curve_table_is_refused(make, message: str) -> None:
    with pytest.raises(ReasoningError, match=message):
        load_curve_table(make())


@pytest.mark.parametrize(
    "field", ["source", "bytes_read", "games_read", "games_used", "filters", "fit"]
)
def test_a_curve_table_without_provenance_is_refused(field: str) -> None:
    with pytest.raises(ReasoningError, match=field):
        load_curve_table(_table(drop=field))  # Q1 review C1


def test_a_curve_table_using_more_games_than_it_read_is_refused() -> None:
    with pytest.raises(ReasoningError, match="inconsistent"):
        load_curve_table(_table(head=(b"games_used = 7470000", b"games_used = 91912326")))


@pytest.mark.parametrize(
    "data",
    [
        b"[table\nname = 1",  # not TOML
        b"\xff\xfe",  # not UTF-8
        b"table = 3",  # [table] is not a table
        _table().replace(b"[[band]]", b"band = 3\n[x]"),  # [[band]] is not an array of tables
    ],
)
def test_malformed_curve_tables_raise_reasoning_errors(data: bytes) -> None:
    with pytest.raises(ReasoningError):  # never a TOMLDecodeError or AttributeError (review C2)
        load_curve_table(data)


@pytest.mark.parametrize(
    "data",
    [
        b"[conversion",
        b"conversion = 3",
        CONVERSION.replace(b"[bullet]\nanchors", b"bullet = 5\n[other]\nanchors"),
    ],
)
def test_malformed_conversions_raise_reasoning_errors(data: bytes) -> None:
    with pytest.raises(ReasoningError):
        load_conversion(data)


def test_a_defective_conversion_is_refused() -> None:
    flat = CONVERSION.replace(b"[[500, 1090], [700, 1225]", b"[[500, 1090], [700, 1090]")
    with pytest.raises(ReasoningError, match="strictly increase"):
        load_conversion(flat)
    with pytest.raises(ReasoningError, match="provenance"):
        load_conversion(CONVERSION.replace(b'retrieved = "2026-10-10"\n', b""))
    with pytest.raises(ReasoningError, match="float"):
        load_conversion(CONVERSION.replace(b"[550, 1060]", b"[550, 1060.5]"))


def test_the_build_identity_names_its_tables() -> None:
    policies, curves, conversions, digest = BUILD.identity()
    assert policies == ("quality_v1", "quality_v2") and digest == logistic_digest()
    assert [name for name, _ in curves] == ["test_curve_v2"]
    assert [name for name, _ in conversions] == ["test_conversion_v1"]
    assert GradingBuild().identity()[1:3] == ((), ())


# -- §9.4 grades -------------------------------------------------------------------------------


def _pair(loss: int, c: int = 1000) -> tuple[int, int]:
    """Centipawns (best, played) whose `quality_v2` loss at scale `c` is exactly `loss`."""

    for best in range(80):
        for played in range(best, -3000, -1):
            if curve_points(best, c) - curve_points(played, c) == loss:
                return best, played
    raise AssertionError(f"no pair for loss {loss}")


@pytest.mark.parametrize(
    ("loss", "expected_grade"),
    [
        (39, Grade.EXCELLENT),
        (40, Grade.GOOD),
        (41, Grade.GOOD),
        (99, Grade.GOOD),
        (100, Grade.INACCURACY),
        (101, Grade.INACCURACY),
        (199, Grade.INACCURACY),
        (200, Grade.MISTAKE),
        (201, Grade.MISTAKE),
        (399, Grade.MISTAKE),
        (400, Grade.BLUNDER),
        (401, Grade.BLUNDER),
    ],
)
def test_band_boundaries_from_scores(loss: int, expected_grade: Grade) -> None:
    b, p = _pair(loss)
    best = LineScore(1, "a", Cp(b), Wdl(0, 1000, 0), score_points(Cp(b), Color.WHITE, DEFAULT))
    played = LineScore(3, "b", Cp(p), Wdl(0, 1000, 0), score_points(Cp(p), Color.WHITE, DEFAULT))
    assert grade(played, best, Color.WHITE) == (loss, expected_grade)


# one point per cp up to 600 cp: a loss of `n` points is `n` cp
LINEAR = ((0, 1000), (50, 1050), (100, 1100), (600, 1600))
TABLE_GRADING = Grading("quality_v2", Curve("monotone_v1", None, CurveSource.TABLE), LINEAR)
BOUNDARIES = [
    (39, Grade.EXCELLENT), (40, Grade.GOOD), (41, Grade.GOOD), (99, Grade.GOOD),
    (100, Grade.INACCURACY), (101, Grade.INACCURACY), (199, Grade.INACCURACY),
    (200, Grade.MISTAKE), (201, Grade.MISTAKE), (399, Grade.MISTAKE),
    (400, Grade.BLUNDER), (401, Grade.BLUNDER),
]  # fmt: skip


@pytest.mark.parametrize(("loss", "expected_grade"), BOUNDARIES)
def test_band_boundaries_under_a_table(loss: int, expected_grade: Grade) -> None:
    """QM-D §10.3: the bands under a TABLE grading, from constructed knots; the same lines under
    the default read the logistic."""

    def scored(rank: int, cp: int, grading: Grading) -> LineScore:
        return LineScore(
            rank, "m", Cp(cp), Wdl(0, 1000, 0), score_points(Cp(cp), Color.WHITE, grading)
        )

    best, played = scored(1, 100, TABLE_GRADING), scored(3, 100 - loss, TABLE_GRADING)
    assert grade(played, best, Color.WHITE) == (loss, expected_grade)
    logistic = grade(scored(3, 100 - loss, DEFAULT), scored(1, 100, DEFAULT), Color.WHITE)
    assert logistic[0] == curve_points(100, 1000) - curve_points(100 - loss, 1000)


def _round_zero(table: dict, moves: tuple[str, ...], spec: GradingSpec, identity=None):
    port = scripted(table, identity=identity) if identity else scripted(table)
    request = AnalysisRequest(RootSpec(), moves, len(moves), PROFILE, grading=spec)
    return Controller(FactEngine(engine=port)).round_zero(request)


def test_a_line_without_wdl_is_decided_under_quality_v2() -> None:
    start = fen_after()
    no_wdl = {start: [("e2e4", ("cp", 30), None), ("d2d4", ("cp", -70), None)]}
    zero = _round_zero(no_wdl, ("d4",), GradingSpec(), NO_WDL)
    judgement = zero.judgements[0]
    assert judgement.status is JudgementStatus.DECIDED and judgement.policy == "quality_v2"
    assert judgement.curve == DEFAULT.curve == zero.grading.curve
    assert judgement.loss == curve_points(30, 1000) - curve_points(-70, 1000)
    v1 = _round_zero(no_wdl, ("d4",), GradingSpec("quality_v1"), NO_WDL).judgements[0]
    assert (v1.status, v1.reason, v1.curve) == (
        JudgementStatus.INCONCLUSIVE,
        "WDL_UNAVAILABLE",
        None,
    )


def test_allowing_mate_in_a_lost_position() -> None:
    """−5.00 → mated: BLUNDER at c = 1000, EXCELLENT under saturated WDL (Q-D §2.2)."""

    start = fen_after()
    lost = (0, 0, 1000)
    lines = {start: [("e2e4", ("cp", -500), lost), ("f2f3", ("mate", -1), lost)]}
    v2 = _round_zero(lines, ("f3",), GradingSpec()).judgements[0]
    assert (v2.loss, v2.grade) == (2000 - curve_points(500, 1000), Grade.BLUNDER)  # 481
    v1 = _round_zero(lines, ("f3",), GradingSpec("quality_v1")).judgements[0]
    assert (v1.loss, v1.grade) == (0, Grade.EXCELLENT)


def test_the_previous_move_uses_the_same_curve() -> None:
    zero = _round_zero({}, ("e4", "e5"), GradingSpec(scale=900))
    assert [j.curve for j in zero.judgements] == [
        Curve("logistic10", 900, CurveSource.EXPLICIT)
    ] * 2


# -- §9.5 the readers of E -------------------------------------------------------------------


BACK = "r5k1/5ppp/8/8/8/8/4QPPP/4R1K1 w - - 0 1"
EVEN = (300, 600, 100)


def test_only_move_reads_the_policy() -> None:
    """Rank 2 at +7.00 with an even WDL: 800 under WDL, 333 under the curve (D10: 400)."""

    lines = [
        line(BACK, "Qe8+ Rxe8 Rxe8#", (1000, 0, 0), mate=2),
        line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=700),
    ]
    v1 = run(BACK, "Qe8+", lines, multipv=2)
    assert status(v1, "only_move_v1") is S
    v2 = run(BACK, "Qe8+", lines, multipv=2, grading=GradingSpec())
    assert status(v2, "only_move_v1") is R
    assert LabelKind.GREAT not in {label.kind for label in v2.labels}  # no only move, no GREAT
    scope = claim(v1, "only_move_v1").verdict.scope
    assert scope.policies == ("points_v1", "quality_v1")


def test_sacrifice_sound_reads_the_policy() -> None:
    """E(Lp) is 1100 under WDL and 965 under the curve at −0.30 (threshold 1000)."""

    fen = "7k/6p1/8/8/8/8/Q7/K5R1 w - - 0 1"
    lines = [
        line(fen, "Rxg7 Kxg7 Qb2+ Kg8 Qb8+ Kf7", (500, 100, 400), cp=-30),
        line(fen, "Qb1 Kg8 Qb8+ Kf7 Qb3+ Kf6", EVEN, cp=-40),
        line(fen, "Qd2 Kg8 Qd8+ Kf7 Qd7+ Kf6", EVEN, cp=-50),
    ]
    v1 = run(fen, "Rxg7", lines)
    v2 = run(fen, "Rxg7", lines, grading=GradingSpec())
    assert status(v1, "sacrifice_offer_v1") is S and status(v2, "sacrifice_offer_v1") is S
    assert status(v1, "sacrifice_sound_v1") is S
    assert status(v2, "sacrifice_sound_v1") is R


def test_scopes_name_the_request_policy() -> None:
    lines = [
        line(BACK, "Qe8+ Rxe8 Rxe8#", (1000, 0, 0), mate=2),
        line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50),
    ]
    analysis = run(BACK, "Qe8+", lines, multipv=2, grading=GradingSpec(scale=800))
    only = claim(analysis, "only_move_v1")
    assert only.verdict.scope.policies == ("points_v1", "quality_v2")


# -- §9.6 identity --------------------------------------------------------------------------


def test_the_scale_is_part_of_the_analysis() -> None:
    a = _round_zero({}, ("e4",), GradingSpec(scale=1000))
    b = _round_zero({}, ("e4",), GradingSpec(scale=1100))
    assert a.request != b.request and a.request.grading == GradingSpec(scale=1000)
    assert canonical_bytes(a.judgements[0]) != canonical_bytes(b.judgements[0])
    assert canonical_bytes(a.grading) == canonical_bytes(
        Grading("quality_v2", Curve("logistic10", 1000, CurveSource.EXPLICIT))
    )
    again = _round_zero({}, ("e4",), GradingSpec(scale=1000))
    assert canonical_bytes(again.judgements[0]) == canonical_bytes(a.judgements[0])


def test_the_knots_are_part_of_the_grading() -> None:
    """QM-D §10.4: one knot value apart gives a different grading; the knots round-trip."""

    rated = GradingSpec(white_rating=1250, time_class="rapid")
    grading = resolve(rated, BUILD)
    changed = list(POINTS[1200])
    changed[30] += 1
    other = curve_table(band_row("rapid", 1200, changed))
    moved = resolve(rated, GradingBuild((load_curve_table(other),)))
    assert grading.curve == moved.curve and grading.points != moved.points
    assert canonical_bytes(grading) != canonical_bytes(moved)
    from calliope.facts.storage import _Decoder
    from calliope.reasoning.encoding import encoded, reasoning_registry

    assert _Decoder(reasoning_registry(), None)(encoded(grading)) == grading


# -- the shipped build (Q-D §10: the tables arrive with Q2) ---------------------------------


def test_the_shipped_build_holds_the_chesscom_conversion() -> None:
    conversion = SHIPPED.conversion()
    assert conversion is not None and conversion.name == "chesscom_lichess_v1"
    assert [pool for pool, _ in conversion.pools] == ["bullet", "blitz", "rapid"]
    assert all(len(anchors) == 18 for _, anchors in conversion.pools)
    rapid = conversion.anchors("rapid")
    assert convert(815, rapid) == (1290, False) and convert(1500, rapid) == (1795, False)
    blitz = conversion.anchors("blitz")
    assert convert(500, blitz) == (1090, False) and convert(3000, blitz) == (2745, False)


# -- QM-D §10.11 the shipped table ------------------------------------------------------------


def test_the_shipped_build_holds_the_monotone_table() -> None:
    table = SHIPPED.curve_table()
    assert table is not None and table.name == "human_lichess_2026_08_v2"
    assert table.cp_ratio_permille == 1103 and table.knots[-1] == 1654  # 1654.5, half-even
    assert len(table.bands) == 28
    assert all(b.positions >= 100_000 and b.shard_deviation <= 10 for b in table.bands)
    assert {b.time_class for b in table.bands} == {"blitz", "bullet", "rapid", "classical"}
    grading = resolve(
        GradingSpec(white_rating=1250, black_rating=1250, time_class="rapid"), SHIPPED
    )
    assert (grading.curve.table, grading.curve.band, grading.curve.model) == (
        "human_lichess_2026_08_v2",
        1200,
        "monotone_v1",
    )
    assert grading.points == tuple(zip(table.knots, table.band("rapid", 1200).points, strict=True))
    chesscom = GradingSpec(
        white_rating=813, black_rating=801, rating_pool="chesscom", time_class="rapid"
    )
    converted = resolve(chesscom, SHIPPED).curve
    assert (converted.rating, converted.band, converted.conversion_clamped) == (1290, 1200, True)
