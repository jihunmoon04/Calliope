"""Canonical engine score and WDL models.

All scalar evaluations use White's perspective internally.  Adapters must normalize raw
engine/provider conventions before constructing these models.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.domain.chess.position import Color


@dataclass(frozen=True, slots=True)
class MateScore:
    """Forced mate represented without ambiguous signed-mate conventions."""

    winner: Color
    moves: int

    def __post_init__(self) -> None:
        if self.moves < 0:
            raise ValueError("mate distance must be non-negative")

    def for_color(self, color: Color) -> int:
        """Positive means the requested color mates; negative means it is mated."""

        return self.moves if self.winner is color else -self.moves


@dataclass(frozen=True, slots=True)
class EngineScore:
    """White-POV centipawn score or a forced-mate result, never both."""

    centipawns: int | None = None
    mate: MateScore | None = None

    def __post_init__(self) -> None:
        if (self.centipawns is None) == (self.mate is None):
            raise ValueError("exactly one of centipawns or mate must be set")

    @classmethod
    def cp(cls, value: int) -> "EngineScore":
        return cls(centipawns=value)

    @classmethod
    def forced_mate(cls, winner: Color, moves: int) -> "EngineScore":
        return cls(mate=MateScore(winner=winner, moves=moves))

    def centipawns_for(self, color: Color) -> int | None:
        if self.centipawns is None:
            return None
        return self.centipawns if color is Color.WHITE else -self.centipawns

    def mate_for(self, color: Color) -> int | None:
        if self.mate is None:
            return None
        return self.mate.for_color(color)


@dataclass(frozen=True, slots=True)
class WDL:
    """Normalized game-outcome probabilities from White's perspective."""

    white_win: float
    draw: float
    black_win: float

    def __post_init__(self) -> None:
        values = (self.white_win, self.draw, self.black_win)
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError("WDL probabilities must be between 0 and 1")
        if abs(sum(values) - 1.0) > 1e-6:
            raise ValueError("WDL probabilities must sum to 1")

    def expected_score(self, color: Color) -> float:
        if color is Color.WHITE:
            return self.white_win + self.draw * 0.5
        return self.black_win + self.draw * 0.5
