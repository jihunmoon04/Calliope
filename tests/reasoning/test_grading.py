"""`quality_v2` (Q-D §3–§6, test obligations §9.1–§9.7): the curve, its resolution and its readers."""

from __future__ import annotations

from itertools import pairwise

import pytest
from scripted import fen_after, scripted
from story import R, S, claim, line, run, status
from test_quality import NO_WDL

from calliope.facts import Color, Cp, EngineProfile, FactEngine, Mate, RootSpec, Wdl
from calliope.reasoning import (
    LOGISTIC,
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
)
from calliope.reasoning.encoding import canonical_bytes
from calliope.reasoning.grading import convert, logistic_digest, round_half_even_div, runtime_scale

PROFILE = EngineProfile()

TABLE = b"""
[table]
name = "test_curve_v1"
pool = "lichess"
model = "logistic10"
band_width = 200
cp_ratio_permille = 1000

[[band]]
time_class = "rapid"
low = 800
source_scale = 1307
scale = 1307
positions = 210364
shard_low = 1256
shard_high = 1382

[[band]]
time_class = "rapid"
low = 1200
source_scale = 957
scale = 957
positions = 576197
shard_low = 910
shard_high = 990

[[band]]
time_class = "rapid"
low = 1400
source_scale = 908
scale = 908
positions = 721256
shard_low = 872
shard_high = 950

[[band]]
time_class = "classical"
low = 1400
source_scale = 850
scale = 850
positions = 100000
shard_low = 822
shard_high = 888
"""

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


def test_score_points_from_the_mover() -> None:
    curve = Curve(1000, CurveSource.DEFAULT)
    assert score_points(Mate(Color.WHITE, 3), Color.WHITE, curve) == 2000
    assert score_points(Mate(Color.WHITE, 3), Color.BLACK, curve) == 0
    assert score_points(Cp(100), Color.WHITE, curve) == 1115
    assert score_points(Cp(100), Color.BLACK, curve) == 885


# -- §9.3 resolution -----------------------------------------------------------------------------


def test_precedence_explicit_then_table_then_default() -> None:
    rated = GradingSpec(white_rating=1250, black_rating=1250, time_class="rapid")
    assert resolve(GradingSpec(), SHIPPED) == Grading(
        "quality_v2", Curve(1000, CurveSource.DEFAULT)
    )
    explicit = resolve(GradingSpec(scale=1100), BUILD).curve
    assert explicit == Curve(1100, CurveSource.EXPLICIT)
    table = resolve(rated, BUILD).curve
    assert (table.source, table.scale, table.band, table.table) == (
        CurveSource.TABLE,
        957,
        1200,
        "test_curve_v1",
    )
    assert resolve(GradingSpec("quality_v1"), BUILD) == Grading("quality_v1", None)


def test_an_explicit_scale_overrides_ratings_even_in_the_shipped_build() -> None:
    spec = GradingSpec(scale=1000, white_rating=800, time_class="rapid")
    curve = resolve(spec, SHIPPED).curve
    assert curve == Curve(1000, CurveSource.EXPLICIT, ratings_overridden=True)


def test_the_average_rating_floored_or_the_one_given() -> None:
    both = resolve(GradingSpec(white_rating=1201, black_rating=1400, time_class="rapid"), BUILD)
    assert (both.curve.rating, both.curve.band) == (1300, 1200)  # 2601 // 2
    one = resolve(GradingSpec(black_rating=1450, time_class="rapid"), BUILD)
    assert (one.curve.rating, one.curve.band, one.curve.scale) == (1450, 1400, 908)


def test_a_missing_band_clamps_to_the_nearest_lower_on_a_tie() -> None:
    far = resolve(GradingSpec(white_rating=2100, time_class="rapid"), BUILD).curve
    assert (far.band, far.band_clamped, far.scale) == (1400, True, 908)
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
            resolve(spec, SHIPPED)
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
    assert (curve.rating, curve.band, curve.scale) == (1542, 1400, 908)  # (1290 + 1795) // 2
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


def _table(**band) -> bytes:
    fields = {
        "time_class": '"rapid"',
        "low": 800,
        "source_scale": 1000,
        "scale": 1000,
        "positions": 100000,
        "shard_low": 950,
        "shard_high": 1100,
        **band,
    }
    ratio = fields.pop("ratio", 1000)
    rows = "\n".join(f"{k} = {v}" for k, v in fields.items())
    head = (
        '[table]\nname = "t"\npool = "lichess"\nmodel = "logistic10"\nband_width = 200\n'
        f"cp_ratio_permille = {ratio}\n"
    )
    return f"{head}\n[[band]]\n{rows}\n".encode()


def test_runtime_scale_is_derived_from_stored_integers() -> None:
    assert runtime_scale(3000, 1234) == 3702  # third re-review C2
    assert round_half_even_div(1, 2) == 0 and round_half_even_div(3, 2) == 2
    assert load_curve_table(_table(source_scale=3000, scale=3702, ratio=1234, shard_low=2900,
                                   shard_high=3300)).bands[0].scale == 3702  # fmt: skip


@pytest.mark.parametrize(
    ("band", "message"),
    [
        ({"positions": 99999}, "positions"),
        ({"shard_high": 1101}, "shard spread"),  # 151 > 0.15 × 1000
        ({"source_scale": 4000, "scale": 4000, "shard_low": 3900, "shard_high": 4100}, "bound"),
        ({"scale": 1001}, "derived"),
        ({"ratio": 1050}, "cp_ratio_permille"),  # within 10 %: stored as 1000
        ({"ratio": 1300}, "derived"),  # scale must then be 1300
        ({"low": 850}, "boundary"),
        ({"time_class": '"daily"'}, "time class"),
        ({"scale": 1000.0}, "float"),
    ],
)
def test_a_defective_curve_table_is_refused(band: dict, message: str) -> None:
    with pytest.raises(ReasoningError, match=message):
        load_curve_table(_table(**band))


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
    assert [name for name, _ in curves] == ["test_curve_v1"]
    assert [name for name, _ in conversions] == ["test_conversion_v1"]
    assert SHIPPED.identity()[1:3] == ((), ())


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
    curve = Curve(1000, CurveSource.DEFAULT)
    b, p = _pair(loss)
    best = LineScore(1, "a", Cp(b), Wdl(0, 1000, 0), score_points(Cp(b), Color.WHITE, curve))
    played = LineScore(3, "b", Cp(p), Wdl(0, 1000, 0), score_points(Cp(p), Color.WHITE, curve))
    assert grade(played, best, Color.WHITE) == (loss, expected_grade)


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
    assert judgement.curve == Curve(1000, CurveSource.DEFAULT) == zero.grading.curve
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
    assert [j.curve for j in zero.judgements] == [Curve(900, CurveSource.EXPLICIT)] * 2


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
    assert v2.labels == ()  # no GREAT without the only move
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
        Grading("quality_v2", Curve(1000, CurveSource.EXPLICIT))
    )
    again = _round_zero({}, ("e4",), GradingSpec(scale=1000))
    assert canonical_bytes(again.judgements[0]) == canonical_bytes(a.judgements[0])
