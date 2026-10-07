from dataclasses import replace

import pytest

from calliope.domain.chess import ChessMove, Color
from calliope.domain.engine import (
    WDL,
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineLine,
    EngineScore,
    EngineSettings,
    ForcednessLevel,
    MoveQuality,
)
from calliope.errors import IncompatibleAnalysisError
from calliope.services.judgement import MoveJudge

W, B = Color.WHITE, Color.BLACK
MOVES = ["a2a3", "b2b3", "c2c3", "d2d3", "e2e3", "f2f3", "g2g3"]
ENGINE = EngineIdentity("Stockfish", "17")
LIMIT = EngineLimit(depth=12)


def wdl_for(white_expected: float) -> WDL:
    return WDL(white_expected, 0.0, 1.0 - white_expected)


def line(rank, score, wdl=None, uci=None):
    uci = uci or MOVES[rank - 1]
    m = ChessMove(uci)
    return EngineLine(rank=rank, first_move=m, score=score, pv=(m,), wdl=wdl)


def cp(v):
    return EngineScore.cp(v)


def analysis(lines, *, multipv=None, pid="p", engine=ENGINE, limit=LIMIT, threads=1, hash_mb=16):
    return EngineAnalysis(
        position_id=pid,
        engine=engine,
        settings=EngineSettings(
            limit=limit, multipv=multipv or len(lines), threads=threads, hash_mb=hash_mb
        ),
        lines=tuple(lines),
    )


def played(score, uci, wdl=None, **kw):
    m = ChessMove(uci)
    return analysis(
        [EngineLine(rank=1, first_move=m, score=score, pv=(m,), wdl=wdl)], multipv=1, **kw
    )


def judge(pos_lines, uci, played_score=None, mover=W, played_wdl=None, **kw):
    pos = analysis(pos_lines)
    pl = played(played_score or cp(0), uci, played_wdl, **kw)
    return MoveJudge().judge(
        mover=mover, move=ChessMove(uci), position_analysis=pos, played_analysis=pl
    )


# --- core -----------------------------------------------------------------

def test_exact_best() -> None:
    j = judge([line(1, cp(50)), line(2, cp(0))], "a2a3", cp(50))
    assert j.quality is MoveQuality.BEST and j.rank == 1 and j.cp_loss == 0


def test_equal_alternative_is_excellent_not_best() -> None:
    j = judge([line(1, cp(20)), line(2, cp(20))], "b2b3", cp(20))
    assert j.quality is MoveQuality.EXCELLENT
    assert j.rank == 2 and j.cp_loss == 0


def test_cp_fallback_thresholds() -> None:
    for loss, q in [(20, MoveQuality.EXCELLENT), (50, MoveQuality.GOOD),
                    (100, MoveQuality.INACCURACY), (200, MoveQuality.MISTAKE),
                    (201, MoveQuality.BLUNDER)]:
        j = judge([line(1, cp(0))], "z2z3", cp(-loss))
        assert j.quality is q and j.rank is None and j.cp_loss == loss
        assert j.expected_score_loss is None


def test_black_mover_pov() -> None:
    j = judge([line(1, cp(-120))], "z2z3", cp(30), mover=B)
    assert j.cp_loss == 150 and j.quality is MoveQuality.MISTAKE
    j = judge([line(1, cp(120))], "z2z3", cp(-30), mover=W)
    assert j.cp_loss == 150


def test_wdl_priority_negligible_loss() -> None:
    j = judge([line(1, cp(800), wdl_for(0.995))], "z2z3", cp(700), played_wdl=wdl_for(0.990))
    assert j.cp_loss == 100
    assert j.expected_score_loss == pytest.approx(0.005)
    assert j.quality is MoveQuality.EXCELLENT


def test_wdl_priority_result_swing() -> None:
    j = judge([line(1, cp(30), wdl_for(0.65))], "z2z3", cp(25), played_wdl=wdl_for(0.51))
    assert j.expected_score_loss == pytest.approx(0.14)
    assert j.quality is MoveQuality.MISTAKE


def test_wdl_black_pov() -> None:
    j = judge([line(1, cp(0), wdl_for(0.4))], "z2z3", cp(0), mover=B, played_wdl=wdl_for(0.6))
    assert j.expected_score_loss == pytest.approx(0.2)
    assert j.quality is MoveQuality.BLUNDER


def test_wdl_only_one_side_gives_none() -> None:
    j = judge([line(1, cp(0), wdl_for(0.5))], "z2z3", cp(-30))
    assert j.expected_score_loss is None and j.quality is MoveQuality.GOOD


def test_cp_noise_clamped_and_excess_rejected() -> None:
    j = judge([line(1, cp(0))], "z2z3", cp(15))
    assert j.cp_loss == 0 and j.quality is MoveQuality.EXCELLENT
    with pytest.raises(IncompatibleAnalysisError):
        judge([line(1, cp(0))], "z2z3", cp(21))


def test_wdl_noise_clamped_and_excess_rejected() -> None:
    j = judge([line(1, cp(0), wdl_for(0.5))], "z2z3", cp(0), played_wdl=wdl_for(0.505))
    assert j.expected_score_loss == 0.0
    with pytest.raises(IncompatibleAnalysisError):
        judge([line(1, cp(0), wdl_for(0.5))], "z2z3", cp(0), played_wdl=wdl_for(0.52))


# --- played score source ----------------------------------------------------

def test_played_score_from_multipv_when_inside() -> None:
    j = judge([line(1, cp(50)), line(2, cp(40))], "b2b3", cp(45))
    assert j.played_score == cp(40)
    assert j.cp_loss == 10


def test_played_score_from_played_analysis_when_outside() -> None:
    j = judge([line(1, cp(50)), line(2, cp(40))], "z2z3", cp(10))
    assert j.played_score == cp(10) and j.cp_loss == 40 and j.rank is None


# --- mate -------------------------------------------------------------------

M = EngineScore.forced_mate


@pytest.mark.parametrize(
    ("played_score", "quality"),
    [
        (M(W, 3), MoveQuality.EXCELLENT),
        (M(W, 4), MoveQuality.GOOD),
        (M(W, 5), MoveQuality.INACCURACY),
        (M(W, 6), MoveQuality.INACCURACY),
        (M(W, 7), MoveQuality.MISTAKE),
        (cp(500), MoveQuality.BLUNDER),
        (M(B, 4), MoveQuality.BLUNDER),
    ],
)
def test_winning_mate_matrix(played_score, quality) -> None:
    j = judge([line(1, M(W, 3))], "z2z3", played_score)
    assert j.quality is quality and j.cp_loss is None


def test_winning_mate_exact_best() -> None:
    j = judge([line(1, M(W, 3)), line(2, cp(0))], "a2a3", M(W, 3))
    assert j.quality is MoveQuality.BEST and j.cp_loss is None


def test_best_cp_played_opponent_mate_blunder() -> None:
    assert judge([line(1, cp(0))], "z2z3", M(B, 2)).quality is MoveQuality.BLUNDER


def test_best_cp_played_mover_mate_rejected() -> None:
    with pytest.raises(IncompatibleAnalysisError):
        judge([line(1, cp(0))], "z2z3", M(W, 2))


def test_mate_faster_than_best_rejected() -> None:
    with pytest.raises(IncompatibleAnalysisError):
        judge([line(1, M(W, 5))], "z2z3", M(W, 3))


@pytest.mark.parametrize(
    ("played_score", "quality"),
    [(M(B, 8), MoveQuality.EXCELLENT), (M(B, 7), MoveQuality.GOOD),
     (M(B, 5), MoveQuality.INACCURACY), (M(B, 4), MoveQuality.MISTAKE)],
)
def test_losing_mate_matrix(played_score, quality) -> None:
    j = judge([line(1, M(B, 8))], "z2z3", played_score)
    assert j.quality is quality and j.cp_loss is None


@pytest.mark.parametrize("bad", [cp(-300), M(W, 3), M(B, 12)])
def test_losing_mate_better_than_best_rejected(bad) -> None:
    with pytest.raises(IncompatibleAnalysisError):
        judge([line(1, M(B, 8))], "z2z3", bad)


def test_black_mover_mate() -> None:
    j = judge([line(1, M(B, 3))], "z2z3", M(B, 4), mover=B)
    assert j.quality is MoveQuality.GOOD


# --- forcedness -------------------------------------------------------------

BAD = -400


def f(scores, **kw):
    lines = [line(i + 1, s) for i, s in enumerate(scores)]
    return judge(lines, "a2a3", scores[0], **kw).forcedness


def test_only_move() -> None:
    fc = f([cp(0), cp(BAD)])
    assert (fc.level, fc.acceptable_move_count) == (ForcednessLevel.ONLY_MOVE, 1)
    assert fc.best_to_second_gap_cp == 400


def test_narrow() -> None:
    fc = f([cp(0), cp(-10), cp(BAD)])
    assert (fc.level, fc.acceptable_move_count) == (ForcednessLevel.NARROW, 2)


def test_flexible_exact() -> None:
    fc = f([cp(0), cp(-10), cp(-20), cp(BAD)])
    assert (fc.level, fc.acceptable_move_count) == (ForcednessLevel.FLEXIBLE, 3)


def test_many_with_unacceptable_observed() -> None:
    fc = f([cp(0)] * 5 + [cp(BAD)])
    assert (fc.level, fc.acceptable_move_count) == (ForcednessLevel.MANY_EQUIVALENT, 5)


def test_truncated_flexible() -> None:
    fc = f([cp(0), cp(-10), cp(-20)])
    assert (fc.level, fc.acceptable_move_count) == (ForcednessLevel.FLEXIBLE, None)


def test_truncated_many() -> None:
    fc = f([cp(0)] * 5)
    assert (fc.level, fc.acceptable_move_count) == (ForcednessLevel.MANY_EQUIVALENT, None)


def test_truncated_two_unknown() -> None:
    fc = f([cp(0), cp(-10)])
    assert (fc.level, fc.acceptable_move_count) == (ForcednessLevel.UNKNOWN, None)


def test_single_line_unknown() -> None:
    fc = f([cp(0)])
    assert fc.level is ForcednessLevel.UNKNOWN and fc.best_to_second_gap_cp is None


def test_forcedness_independent_of_quality() -> None:
    lines = [line(1, cp(0)), line(2, cp(BAD))]
    only = judge(lines, "a2a3", cp(0))
    many = judge([line(i, cp(0)) for i in range(1, 6)], "a2a3", cp(0))
    assert only.quality is many.quality is MoveQuality.BEST
    assert only.forcedness.level is ForcednessLevel.ONLY_MOVE
    assert many.forcedness.level is ForcednessLevel.MANY_EQUIVALENT


def test_forced_loss_unknown() -> None:
    lines = [line(1, M(B, 5)), line(2, cp(-900))]
    assert judge(lines, "a2a3", M(B, 5)).forcedness.level is ForcednessLevel.UNKNOWN


def test_winning_mate_slower_alternative_acceptable() -> None:
    lines = [line(1, M(W, 3)), line(2, M(W, 9)), line(3, cp(300))]
    fc = judge(lines, "a2a3", M(W, 3)).forcedness
    assert (fc.level, fc.acceptable_move_count) == (ForcednessLevel.NARROW, 2)
    assert fc.best_to_second_gap_cp is None


def test_winning_mate_only_move() -> None:
    lines = [line(1, M(W, 3)), line(2, cp(300))]
    fc = judge(lines, "a2a3", M(W, 3)).forcedness
    assert (fc.level, fc.acceptable_move_count) == (ForcednessLevel.ONLY_MOVE, 1)


def test_gap_black_pov_and_noise() -> None:
    fc = f([cp(-300), cp(-100)], mover=B)
    assert fc.best_to_second_gap_cp == 200
    fc = f([cp(0), cp(10)])
    assert fc.best_to_second_gap_cp == 0
    with pytest.raises(IncompatibleAnalysisError):
        f([cp(0), cp(50)])


def test_candidate_ordering_contradiction() -> None:
    with pytest.raises(IncompatibleAnalysisError):
        f([cp(0), cp(100), cp(100)])


# --- compatibility ------------------------------------------------------------

def run(pos, pl, uci="a2a3"):
    return MoveJudge().judge(
        mover=W, move=ChessMove(uci), position_analysis=pos, played_analysis=pl
    )


def base_pos():
    return analysis([line(1, cp(0)), line(2, cp(-10))])


def test_valid_multipv_difference_ok() -> None:
    assert run(base_pos(), played(cp(0), "a2a3")).quality is MoveQuality.BEST


@pytest.mark.parametrize(
    "kw",
    [
        {"pid": "other"},
        {"engine": EngineIdentity("Stockfish", "16")},
        {"limit": EngineLimit(depth=20)},
        {"threads": 2},
        {"hash_mb": 32},
    ],
)
def test_incompatible_settings(kw) -> None:
    with pytest.raises(IncompatibleAnalysisError):
        run(base_pos(), played(cp(0), "a2a3", **kw))


def test_played_multipv_not_one() -> None:
    pl = played(cp(0), "a2a3")
    pl = replace(pl, settings=replace(pl.settings, multipv=2))
    with pytest.raises(IncompatibleAnalysisError):
        run(base_pos(), pl)


def test_played_has_two_lines() -> None:
    pl = replace(played(cp(0), "a2a3"), lines=(line(1, cp(0), uci="a2a3"), line(2, cp(0), uci="b2b3")))
    with pytest.raises(IncompatibleAnalysisError):
        run(base_pos(), pl)


def test_played_root_mismatch() -> None:
    with pytest.raises(IncompatibleAnalysisError):
        run(base_pos(), played(cp(0), "b2b3"), uci="a2a3")


def test_rank_gap() -> None:
    pos = analysis([line(1, cp(0)), line(3, cp(-10))], multipv=3)
    with pytest.raises(IncompatibleAnalysisError):
        run(pos, played(cp(0), "a2a3"))


def test_duplicate_first_move() -> None:
    pos = analysis([line(1, cp(0)), line(2, cp(-10), uci="a2a3")])
    with pytest.raises(IncompatibleAnalysisError):
        run(pos, played(cp(0), "a2a3"))
