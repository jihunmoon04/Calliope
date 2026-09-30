"""Canonical immutable chess-position models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256


class Color(StrEnum):
    WHITE = "white"
    BLACK = "black"

    @property
    def opposite(self) -> "Color":
        return Color.BLACK if self is Color.WHITE else Color.WHITE


def position_id_from_fen(canonical_fen: str) -> str:
    """Return a deterministic id for an adapter-normalized full FEN."""

    digest = sha256(canonical_fen.encode("utf-8")).hexdigest()
    return f"pos_{digest[:24]}"


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """Immutable identity and state of one legal chess position.

    The python-chess adapter is responsible for parsing/normalizing FEN and validating
    chess legality before this object is created.
    """

    position_id: str
    fen: str
    ply: int
    side_to_move: Color
    castling_rights: str
    en_passant_square: str | None
    halfmove_clock: int
    fullmove_number: int

    def __post_init__(self) -> None:
        if self.ply < 0:
            raise ValueError("ply must be non-negative")
        if self.halfmove_clock < 0:
            raise ValueError("halfmove_clock must be non-negative")
        if self.fullmove_number < 1:
            raise ValueError("fullmove_number must be at least 1")
        expected_id = position_id_from_fen(self.fen)
        if self.position_id != expected_id:
            raise ValueError("position_id must match the canonical FEN")

    @classmethod
    def create(
        cls,
        *,
        fen: str,
        ply: int,
        side_to_move: Color,
        castling_rights: str,
        en_passant_square: str | None,
        halfmove_clock: int,
        fullmove_number: int,
    ) -> "PositionSnapshot":
        return cls(
            position_id=position_id_from_fen(fen),
            fen=fen,
            ply=ply,
            side_to_move=side_to_move,
            castling_rights=castling_rights,
            en_passant_square=en_passant_square,
            halfmove_clock=halfmove_clock,
            fullmove_number=fullmove_number,
        )
