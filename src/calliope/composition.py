"""Composition root wiring the canonical Calliope engine."""

from __future__ import annotations

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.application.analyze_game import AnalyzeGameUnavailable
from calliope.application.analyze_move import AnalyzeMoveService
from calliope.engine import CalliopeEngine
from calliope.services.judgement.move_judge import MoveJudge


def create_calliope_engine(
    stockfish_command: str | list[str] = "stockfish",
    *,
    startup_timeout_s: float = 10.0,
    default_depth: int = 12,
    default_multipv: int = 5,
) -> CalliopeEngine:
    """Build a facade that owns a Stockfish process; call ``close()`` when done.

    Raises ``EngineStartupError`` if Stockfish cannot be started.
    """
    stockfish = StockfishAdapter.start(stockfish_command, timeout_s=startup_timeout_s)
    move_service = AnalyzeMoveService(
        chess=PythonChessAdapter(),
        engine=stockfish,
        judge=MoveJudge(),
        default_depth=default_depth,
        default_multipv=default_multipv,
    )
    return CalliopeEngine(move_service, AnalyzeGameUnavailable(), stockfish.close)
