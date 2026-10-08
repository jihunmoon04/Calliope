"""Application-facing engine analysis port."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from calliope.domain.chess import ChessMove, PositionSnapshot
from calliope.domain.engine import EngineAnalysis, EngineSettings


class EngineAnalysisPort(Protocol):
    """Produce a normalized engine analysis for one position."""

    def analyze(
        self,
        position: PositionSnapshot,
        settings: EngineSettings,
        root_moves: tuple[ChessMove, ...] | None = None,
    ) -> EngineAnalysis:
        """Analyze the position, optionally restricted to the supplied root moves."""
        ...


class EngineRequestSessionPort(Protocol):
    """Request-wide engine session over one shared engine process.

    Entering the session serializes the caller against every other session on the same engine
    and starts a fresh engine game; every analysis made by the entering thread until exit
    belongs to that one game.
    """

    def request_session(self) -> AbstractContextManager[None]:
        """Enter one request-wide engine session."""
        ...
