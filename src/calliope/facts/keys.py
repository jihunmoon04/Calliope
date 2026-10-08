"""Shared vocabulary and identities of the fact engine (design F0 §3.1, §4).

Nothing here imports the legacy MVP packages; `Color` and `PieceType` are redefined on purpose.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

import chess

SQUARE_NAMES: tuple[str, ...] = tuple(chess.SQUARE_NAMES)


class Color(StrEnum):
    WHITE = "white"
    BLACK = "black"

    @property
    def opposite(self) -> Color:
        return Color.BLACK if self is Color.WHITE else Color.WHITE

    @classmethod
    def of(cls, side: chess.Color) -> Color:
        return cls.WHITE if side == chess.WHITE else cls.BLACK


class PieceType(StrEnum):
    PAWN = "pawn"
    KNIGHT = "knight"
    BISHOP = "bishop"
    ROOK = "rook"
    QUEEN = "queen"
    KING = "king"

    @classmethod
    def of(cls, piece_type: chess.PieceType) -> PieceType:
        return _FROM_CHESS[piece_type]

    @property
    def letter(self) -> str:
        return _LETTER[self]


_FROM_CHESS = {
    chess.PAWN: PieceType.PAWN,
    chess.KNIGHT: PieceType.KNIGHT,
    chess.BISHOP: PieceType.BISHOP,
    chess.ROOK: PieceType.ROOK,
    chess.QUEEN: PieceType.QUEEN,
    chess.KING: PieceType.KING,
}
_LETTER = {
    PieceType.PAWN: "P",
    PieceType.KNIGHT: "N",
    PieceType.BISHOP: "B",
    PieceType.ROOK: "R",
    PieceType.QUEEN: "Q",
    PieceType.KING: "K",
}


def square_index(name: str) -> int:
    """Canonical square order a1, b1, …, h8 (design §3.5)."""

    return chess.parse_square(name)


@dataclass(frozen=True, slots=True, order=True)
class PieceId:
    """A physical piece, named by its colour, type and square on the root frame (`w.N.g1`).

    A promoted pawn keeps its id; its current type is read from the node, not from the id.
    """

    value: str

    @classmethod
    def at_root(cls, color: Color, piece_type: PieceType, square: str) -> PieceId:
        return cls(f"{'w' if color is Color.WHITE else 'b'}.{piece_type.letter}.{square}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class PositionKey:
    """Placement, side to move, castling rights and the *legal* en passant square.

    The value is python-chess's EPD (`en_passant="legal"`), i.e. FIDE repetition identity:
    clocks are excluded, and an en passant square counts only if a legal capture exists.
    """

    value: str

    @classmethod
    def of(cls, board: chess.Board) -> PositionKey:
        return cls(board.epd(en_passant="legal"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class RootId:
    """Digest of the normalized root specification (start position + pre-root moves)."""

    value: str

    @classmethod
    def of(cls, start_fen: str, pre_root_moves: tuple[str, ...]) -> RootId:
        return cls("r_" + digest("root", start_fen, *pre_root_moves))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class NodeId:
    """digest(parent `NodeId`, canonical move); the root node's id is derived from its `RootId`."""

    value: str

    @classmethod
    def root(cls, root_id: RootId) -> NodeId:
        return cls(root_id.value)

    @classmethod
    def child(cls, parent: NodeId, move_uci: str) -> NodeId:
        return cls("n_" + digest("node", parent.value, move_uci))

    def __str__(self) -> str:
        return self.value


def digest(*parts: str) -> str:
    """Stable 24-hex digest of an ordered tuple of strings (unit-separator joined)."""

    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]
