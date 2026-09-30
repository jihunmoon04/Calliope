import pytest

from calliope.domain.chess import ChessMove, Color
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineLine,
    EngineScore,
    EngineSettings,
    MateScore,
    WDL,
)


def test_centipawn_score_has_unambiguous_white_pov() -> None:
    score = EngineScore.cp(35)

    assert score.centipawns_for(Color.WHITE) == 35
    assert score.centipawns_for(Color.BLACK) == -35


def test_mate_score_has_explicit_winner() -> None:
    score = EngineScore.forced_mate(Color.BLACK, 3)

    assert score.mate == MateScore(Color.BLACK, 3)
    assert score.mate_for(Color.BLACK) == 3
    assert score.mate_for(Color.WHITE) == -3


def test_wdl_expected_score_is_projected_per_color() -> None:
    wdl = WDL(white_win=0.6, draw=0.3, black_win=0.1)

    assert wdl.expected_score(Color.WHITE) == pytest.approx(0.75)
    assert wdl.expected_score(Color.BLACK) == pytest.approx(0.25)


def test_engine_analysis_requires_rank_one_and_consistent_pv() -> None:
    move = ChessMove("a1a2")
    line = EngineLine(
        rank=1,
        first_move=move,
        score=EngineScore.cp(0),
        pv=(move,),
    )
    analysis = EngineAnalysis(
        position_id="pos_example",
        engine=EngineIdentity("Stockfish"),
        settings=EngineSettings(limit=EngineLimit(depth=12), multipv=1),
        lines=(line,),
    )

    assert analysis.best_line == line
