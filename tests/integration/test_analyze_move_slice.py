import os
import shutil

import chess
import pytest

from calliope import (
    AnalyzeGameRequest,
    AnalyzeMoveRequest,
    create_calliope_engine,
)
from calliope.contracts import PUBLIC_SCHEMA_VERSION
from calliope.errors import CalliopeClosedError, FeatureUnavailableError

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH") or shutil.which("stockfish")

pytestmark = pytest.mark.skipif(STOCKFISH is None, reason="Stockfish binary not available")

FEN = "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1"
MOVE = "f7g7"


def test_fixture_is_legal_mate_in_one():
    board = chess.Board(FEN)
    move = chess.Move.from_uci(MOVE)
    assert move in board.legal_moves
    board.push(move)
    assert board.is_checkmate()


def test_vertical_slice_and_lifecycle():
    engine = create_calliope_engine(STOCKFISH)  # type: ignore[arg-type]
    request = AnalyzeMoveRequest(fen=FEN, move_uci=MOVE)
    result = engine.analyze_move(request)

    assert result.schema_version == PUBLIC_SCHEMA_VERSION
    assert result.position_fen == FEN
    assert result.judgement.move_uci == MOVE
    assert result.judgement.best_move_uci == MOVE
    assert result.judgement.quality == "best"
    assert result.judgement.rank == 1
    assert result.claims == ()
    assert result.variations == ()
    assert result.commentary is None
    assert "stockfish" in result.metadata["engine"]["name"].lower()

    with pytest.raises(FeatureUnavailableError):
        engine.analyze_game(AnalyzeGameRequest(pgn="*"))

    engine.close()
    engine.close()
    with pytest.raises(CalliopeClosedError):
        engine.analyze_move(request)
