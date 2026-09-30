"""Canonical public Calliope engine facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from calliope.contracts import (
    AnalyzeGameRequest,
    AnalyzeMoveRequest,
    GameAnalysisResult,
    MoveAnalysisResult,
)


class MoveAnalysisUseCase(Protocol):
    """Internal application port consumed by the public facade."""

    def execute(self, request: AnalyzeMoveRequest) -> MoveAnalysisResult: ...


class GameAnalysisUseCase(Protocol):
    """Internal application port consumed by the public facade."""

    def execute(self, request: AnalyzeGameRequest) -> GameAnalysisResult: ...


@dataclass(slots=True)
class CalliopeEngine:
    """Single public entry point for all Calliope analysis.

    The facade deliberately does not expose internal analyzers.  A concrete composition root
    will wire Stockfish, python-chess, deterministic services, counterfactual verification,
    and optional verbalization behind these application ports.
    """

    _move_analysis: MoveAnalysisUseCase
    _game_analysis: GameAnalysisUseCase

    def analyze_move(self, request: AnalyzeMoveRequest) -> MoveAnalysisResult:
        return self._move_analysis.execute(request)

    def analyze_game(self, request: AnalyzeGameRequest) -> GameAnalysisResult:
        return self._game_analysis.execute(request)
