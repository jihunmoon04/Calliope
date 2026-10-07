import os
import shutil
from collections.abc import Iterator

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.domain.chess import ChessMove, Color
from calliope.domain.engine import EngineLimit, EngineSettings
from calliope.errors import EngineClosedError

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH") or shutil.which("stockfish")

pytestmark = pytest.mark.skipif(STOCKFISH is None, reason="Stockfish binary not available")

rules = PythonChessAdapter()
START = rules.position_from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")


@pytest.fixture(scope="module")
def adapter() -> Iterator[StockfishAdapter]:
    with StockfishAdapter.start(STOCKFISH) as stockfish:  # type: ignore[arg-type]
        yield stockfish


def test_sf01_startpos_multipv(adapter: StockfishAdapter) -> None:
    result = adapter.analyze(START, EngineSettings(limit=EngineLimit(depth=8), multipv=3))
    assert [line.rank for line in result.lines] == [1, 2, 3]
    for line in result.lines:
        assert line.score is not None
        assert line.first_move == line.pv[0]
        assert all(move.san for move in line.pv)
    assert "stockfish" in result.engine.name.lower()


def test_sf02_root_move(adapter: StockfishAdapter) -> None:
    result = adapter.analyze(
        START, EngineSettings(limit=EngineLimit(depth=8)), (ChessMove("e2e4"),)
    )
    assert result.best_line.first_move.uci == "e2e4"


def test_sf03_mate_in_one_white(adapter: StockfishAdapter) -> None:
    position = rules.position_from_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
    score = adapter.analyze(position, EngineSettings(limit=EngineLimit(depth=8))).best_line.score
    assert score.centipawns is None
    assert score.mate is not None
    assert score.mate.winner is Color.WHITE
    assert score.mate.moves == 1


def test_sf03_mate_in_one_black_to_move_is_white_pov(adapter: StockfishAdapter) -> None:
    position = rules.position_from_fen("r5k1/8/8/8/8/8/5PPP/6K1 b - - 0 1")
    score = adapter.analyze(position, EngineSettings(limit=EngineLimit(depth=8))).best_line.score
    assert score.mate is not None
    assert score.mate.winner is Color.BLACK
    assert score.mate.moves == 1


def test_black_to_move_cp_is_white_pov(adapter: StockfishAdapter) -> None:
    # Black to move, Black has lost its queen: White POV must be clearly positive.
    position = rules.position_from_fen("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1")
    score = adapter.analyze(position, EngineSettings(limit=EngineLimit(depth=8))).best_line.score
    assert score.centipawns is not None
    assert score.centipawns > 300


def test_sf04_wdl(adapter: StockfishAdapter) -> None:
    result = adapter.analyze(START, EngineSettings(limit=EngineLimit(depth=8)))
    wdl = result.best_line.wdl
    if "UCI_ShowWDL" in adapter._engine.options:
        assert wdl is not None
        assert wdl.white_win + wdl.draw + wdl.black_win == pytest.approx(1.0)
    else:
        assert wdl is None


def test_threads_hash_options(adapter: StockfishAdapter) -> None:
    result = adapter.analyze(
        START, EngineSettings(limit=EngineLimit(depth=6), threads=1, hash_mb=16)
    )
    assert result.best_line.rank == 1


def test_sf05_lifecycle() -> None:
    stockfish = StockfishAdapter.start(STOCKFISH)  # type: ignore[arg-type]
    result = stockfish.analyze(START, EngineSettings(limit=EngineLimit(nodes=2000)))
    assert result.lines
    stockfish.close()
    stockfish.close()
    with pytest.raises(EngineClosedError):
        stockfish.analyze(START, EngineSettings(limit=EngineLimit(depth=2)))
