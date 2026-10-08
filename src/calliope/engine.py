"""Canonical public Calliope engine facade."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Protocol, Self

from calliope.contracts import (
    AnalyzeGameRequest,
    AnalyzeMoveRequest,
    GameAnalysisResult,
    MoveAnalysisResult,
    ObservedMoveAnalysisResult,
    ObservedMoveRequest,
)
from calliope.errors import CalliopeClosedError, FeatureUnavailableError


class MoveAnalysisUseCase(Protocol):
    """Internal application port consumed by the public facade."""

    def execute(self, request: AnalyzeMoveRequest) -> MoveAnalysisResult: ...


class GameAnalysisUseCase(Protocol):
    """Internal application port consumed by the public facade."""

    def execute(self, request: AnalyzeGameRequest) -> GameAnalysisResult: ...


class ObservedMoveAnalysisUseCase(Protocol):
    """Internal application port for the explicit schema-0.3 observation opt-in."""

    def execute(self, request: ObservedMoveRequest) -> ObservedMoveAnalysisResult: ...


@dataclass(slots=True)
class CalliopeEngine:
    """Single public entry point for all Calliope analysis.

    The facade deliberately does not expose internal analyzers.  A concrete composition root
    will wire Stockfish, python-chess, deterministic services, counterfactual verification,
    and optional verbalization behind these application ports.
    """

    _move_analysis: MoveAnalysisUseCase
    _game_analysis: GameAnalysisUseCase
    _close_hook: Callable[[], None] | None = None
    _observed_move_analysis: ObservedMoveAnalysisUseCase | None = None
    _closed: bool = field(default=False, init=False)

    def analyze_move(self, request: AnalyzeMoveRequest) -> MoveAnalysisResult:
        self._ensure_open()
        return self._move_analysis.execute(request)

    def analyze_move_with_observations(
        self, request: ObservedMoveRequest
    ) -> ObservedMoveAnalysisResult:
        """Explicit opt-in: the unchanged schema-0.2 result nested in a schema-0.3 envelope."""
        self._ensure_open()
        if self._observed_move_analysis is None:
            raise FeatureUnavailableError("observations are not configured for this engine")
        return self._observed_move_analysis.execute(request)

    def analyze_game(self, request: AnalyzeGameRequest) -> GameAnalysisResult:
        self._ensure_open()
        return self._game_analysis.execute(request)

    def close(self) -> None:
        """Release owned resources.  Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._close_hook is not None:
            self._close_hook()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise CalliopeClosedError("CalliopeEngine is closed")
