"""Engine-derived move judgement models.

This module answers how good a move is according to Stockfish.  It intentionally contains
no causal or explanatory prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.chess.move import ChessMove
from calliope.domain.chess.position import Color
from calliope.domain.engine.score import EngineScore


class MoveQuality(StrEnum):
    BEST = "best"
    EXCELLENT = "excellent"
    GOOD = "good"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"


class ForcednessLevel(StrEnum):
    UNKNOWN = "unknown"
    MANY_EQUIVALENT = "many_equivalent"
    FLEXIBLE = "flexible"
    NARROW = "narrow"
    ONLY_MOVE = "only_move"


@dataclass(frozen=True, slots=True)
class Forcedness:
    level: ForcednessLevel = ForcednessLevel.UNKNOWN
    acceptable_move_count: int | None = None
    best_to_second_gap_cp: int | None = None

    def __post_init__(self) -> None:
        if self.acceptable_move_count is not None and self.acceptable_move_count < 1:
            raise ValueError("acceptable_move_count must be positive")
        if self.best_to_second_gap_cp is not None and self.best_to_second_gap_cp < 0:
            raise ValueError("best_to_second_gap_cp must be non-negative")


@dataclass(frozen=True, slots=True)
class MoveJudgement:
    """Stockfish-based judgement for one played move from one position."""

    position_id: str
    mover: Color
    move: ChessMove
    best_move: ChessMove
    quality: MoveQuality
    rank: int | None
    best_score: EngineScore
    played_score: EngineScore
    cp_loss: int | None
    expected_score_loss: float | None
    forcedness: Forcedness = Forcedness()

    def __post_init__(self) -> None:
        if self.rank is not None and self.rank < 1:
            raise ValueError("rank must be positive")
        if self.cp_loss is not None and self.cp_loss < 0:
            raise ValueError("cp_loss must be non-negative")
        if self.expected_score_loss is not None:
            if self.expected_score_loss < 0.0 or self.expected_score_loss > 1.0:
                raise ValueError("expected_score_loss must be between 0 and 1")
