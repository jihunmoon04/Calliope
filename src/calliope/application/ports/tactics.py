"""Application-facing exact rule observations needed by tactical detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from calliope.domain.chess import ChessMove, Color, PieceRef, PositionSnapshot


@dataclass(frozen=True, slots=True)
class AbsolutePinObservation:
    """``pinned`` cannot legally leave the line between ``pinner`` and its own ``king``."""

    pinner: PieceRef
    pinned: PieceRef
    king: PieceRef


@dataclass(frozen=True, slots=True)
class TacticalObservation:
    """Exact chess-rule observation; no tactical interpretation."""

    position_id: str
    side_to_move: Color
    legal_moves: tuple[ChessMove, ...]
    absolute_pins: tuple[AbsolutePinObservation, ...]


class TacticalObservationPort(Protocol):
    def observe_tactics(self, position: PositionSnapshot) -> TacticalObservation: ...
