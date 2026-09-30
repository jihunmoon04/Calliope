"""Canonical chess-move value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChessMove:
    """Position-independent move identity plus optional position-derived presentation."""

    uci: str
    san: str | None = None

    def __post_init__(self) -> None:
        if not self.uci:
            raise ValueError("uci must not be empty")


@dataclass(frozen=True, slots=True)
class MoveRecord:
    """One move connecting two immutable position identities."""

    move: ChessMove
    before_position_id: str
    after_position_id: str
    ply: int

    def __post_init__(self) -> None:
        if self.ply < 0:
            raise ValueError("ply must be non-negative")
