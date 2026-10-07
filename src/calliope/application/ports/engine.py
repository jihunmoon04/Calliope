"""Application-facing engine analysis port."""

from __future__ import annotations

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
