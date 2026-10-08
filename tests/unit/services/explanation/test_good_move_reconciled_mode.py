"""P2-C1 downstream gate: a reconciled unranked EXCELLENT + ONLY_MOVE judgement stays STRONG_MOVE.

P9's frozen rule makes only BEST + ONLY_MOVE an ONLY_MOVE_CANDIDATE; P2-C1 reconciliation keeps
the original MultiPV forcedness and never promotes to BEST, so P9 must see STRONG_MOVE.
"""

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import GoodMoveMode
from calliope.domain.chess import ChessMove
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineLine,
    EngineScore,
    EngineSettings,
    Forcedness,
    ForcednessLevel,
    MoveJudgement,
    MoveQuality,
)
from calliope.services.explanation import GoodMoveExplainer
from calliope.services.explanation.good_move import GoodMovePreparedContext

rules = PythonChessAdapter()
START = rules.position_from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
SETTINGS = EngineSettings(EngineLimit(depth=12), multipv=2, threads=1, hash_mb=16)


def _line(rank, uci, cp):
    move = ChessMove(uci)
    return EngineLine(rank=rank, first_move=move, score=EngineScore.cp(cp), pv=(move,))


ANALYSIS = EngineAnalysis(
    START.position_id,
    EngineIdentity("Stockfish", "19"),
    SETTINGS,
    (_line(1, "e2e4", 40), _line(2, "d2d4", -200)),
)


def _judgement(played, quality, rank):
    return MoveJudgement(
        position_id=START.position_id,
        mover=START.side_to_move,
        move=ChessMove(played),
        best_move=ChessMove("e2e4"),
        quality=quality,
        rank=rank,
        best_score=EngineScore.cp(40),
        played_score=EngineScore.cp(55),  # paired observation may exceed the reference
        cp_loss=0,
        expected_score_loss=None,
        forcedness=Forcedness(ForcednessLevel.ONLY_MOVE, 1, 240),
    )


def _prepare(judgement):
    explainer = GoodMoveExplainer(
        chess=rules,
        facts=None,  # type: ignore[arg-type]
        delta=None,  # type: ignore[arg-type]
        tactical_rules=rules,
        detector=None,  # type: ignore[arg-type]
        counterfactual=None,  # type: ignore[arg-type]
    )
    prepared = explainer.prepare(START, judgement.move, judgement, ANALYSIS)
    assert isinstance(prepared, GoodMovePreparedContext)
    return prepared


def test_reconciled_excellent_only_move_is_a_strong_move():
    prepared = _prepare(_judgement("g1f3", MoveQuality.EXCELLENT, None))
    assert prepared.mode is GoodMoveMode.STRONG_MOVE
    assert [a.move.uci for a in prepared.alternatives] == ["e2e4", "d2d4"]


@pytest.mark.parametrize(
    "played,quality,rank,mode",
    [
        ("e2e4", MoveQuality.BEST, 1, GoodMoveMode.ONLY_MOVE_CANDIDATE),
        ("g1f3", MoveQuality.EXCELLENT, None, GoodMoveMode.STRONG_MOVE),
    ],
)
def test_frozen_p9_mode_rule(played, quality, rank, mode):
    assert _prepare(_judgement(played, quality, rank)).mode is mode
