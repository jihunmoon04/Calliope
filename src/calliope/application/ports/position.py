"""Application-facing position observation port."""

from __future__ import annotations

from typing import Protocol

from calliope.domain.chess import PositionObservation, PositionSnapshot


class PositionObservationPort(Protocol):
    """Observe exact board facts of one position."""

    def observe_position(self, position: PositionSnapshot) -> PositionObservation: ...
