"""Deterministic board facts for one position.

Only rule-level observations live here: no evaluation, no tactical interpretation.
Squares are lowercase algebraic names; ordering follows board index (a1, b1, ..., h8).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.chess.move import ChessMove
from calliope.domain.chess.position import Color


class PieceType(StrEnum):
    PAWN = "pawn"
    KNIGHT = "knight"
    BISHOP = "bishop"
    ROOK = "rook"
    QUEEN = "queen"
    KING = "king"


def square_index(square: str) -> int:
    """Board index of an algebraic square: a1=0, b1=1, ..., h8=63."""

    if len(square) != 2 or square[0] not in "abcdefgh" or square[1] not in "12345678":
        raise ValueError(f"invalid square: {square!r}")
    return (int(square[1]) - 1) * 8 + (ord(square[0]) - ord("a"))


@dataclass(frozen=True, slots=True)
class PieceRef:
    color: Color
    piece_type: PieceType
    square: str

    def __post_init__(self) -> None:
        square_index(self.square)


@dataclass(frozen=True, slots=True)
class AttackRelation:
    """The piece attacks the target square by chess rules (not necessarily a legal capture)."""

    attacker: PieceRef
    target_square: str

    def __post_init__(self) -> None:
        square_index(self.target_square)


@dataclass(frozen=True, slots=True)
class LegalCapture:
    move: ChessMove
    capturer: PieceRef
    captured: PieceRef
    landing_square: str
    captured_square: str
    is_en_passant: bool = False

    def __post_init__(self) -> None:
        if self.captured.square != self.captured_square:
            raise ValueError("captured piece must stand on captured_square")
        if self.is_en_passant == (self.landing_square == self.captured_square):
            raise ValueError("landing and captured squares differ exactly for en passant")


@dataclass(frozen=True, slots=True)
class MaterialCount:
    """Piece counts only; kings are excluded and no values are assigned."""

    pawns: int
    knights: int
    bishops: int
    rooks: int
    queens: int


@dataclass(frozen=True, slots=True)
class MaterialState:
    white: MaterialCount
    black: MaterialCount


@dataclass(frozen=True, slots=True)
class PieceState:
    piece: PieceRef
    attacks: tuple[str, ...]
    attacked_by: tuple[PieceRef, ...]
    defended_by: tuple[PieceRef, ...]
    legally_capturable_now: bool
    hanging_now: bool


@dataclass(frozen=True, slots=True)
class PositionObservation:
    """Exact low-level observation produced at the rules-library boundary."""

    position_id: str
    pieces: tuple[PieceRef, ...]
    attacks: tuple[AttackRelation, ...]
    legal_captures: tuple[LegalCapture, ...]
    side_to_move_in_check: bool
    side_to_move_checkmated: bool


@dataclass(frozen=True, slots=True)
class PositionFacts:
    position_id: str
    pieces: tuple[PieceState, ...]
    material: MaterialState
    attacks: tuple[AttackRelation, ...]
    legal_captures: tuple[LegalCapture, ...]
    side_to_move_in_check: bool
    side_to_move_checkmated: bool
