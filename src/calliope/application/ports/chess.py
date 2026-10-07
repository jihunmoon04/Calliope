"""Application-facing chess rules port."""

from __future__ import annotations

from typing import Protocol

from calliope.domain.chess import ChessMove, PositionSnapshot


class ChessRulesPort(Protocol):
    """Validate external chess input and return immutable Calliope values."""

    def position_from_fen(self, fen: str) -> PositionSnapshot:
        """Parse, validate, and canonicalize a standard-chess FEN."""
        ...

    def legal_move_from_uci(
        self,
        position: PositionSnapshot,
        move_uci: str,
    ) -> ChessMove:
        """Parse a UCI move and validate it against the source position."""
        ...

    def apply_move(
        self,
        position: PositionSnapshot,
        move: ChessMove,
    ) -> PositionSnapshot:
        """Revalidate and apply the UCI identity of a move."""
        ...
