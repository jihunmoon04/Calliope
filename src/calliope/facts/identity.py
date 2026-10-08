"""Physical piece identity (design F0 §4): assigned on the root frame, advanced only by exact moves."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import chess

from calliope.facts.keys import Color, PieceId, PieceType

PieceMap = tuple[tuple[str, PieceId], ...]  # (square, piece) in canonical square order

_ROOK_CASTLING = {
    chess.G1: (chess.H1, chess.F1),
    chess.C1: (chess.A1, chess.D1),
    chess.G8: (chess.H8, chess.F8),
    chess.C8: (chess.A8, chess.D8),
}


@dataclass(frozen=True, slots=True)
class IdentityStep:
    """How identity moved across one edge."""

    mover: PieceId
    captured: PieceId | None
    victim_square: str | None
    rook: tuple[PieceId, str, str] | None  # castling rook: (piece, from, to)
    pieces_after: PieceMap


def root_pieces(board: chess.Board) -> PieceMap:
    return tuple(
        (
            chess.square_name(square),
            PieceId.at_root(
                Color.of(piece.color), PieceType.of(piece.piece_type), chess.square_name(square)
            ),
        )
        for square, piece in sorted(board.piece_map().items())
    )


def advance(board: chess.Board, move: chess.Move, pieces: PieceMap) -> IdentityStep:
    """Identity after `move` on `board` (the position before the move); `move` must be legal."""

    by_square: dict[int, PieceId] = {chess.parse_square(sq): pid for sq, pid in pieces}
    mover = by_square.pop(move.from_square)
    captured: PieceId | None = None
    victim: int | None = None
    if board.is_en_passant(move):
        victim = move.to_square + (-8 if board.turn == chess.WHITE else 8)
    elif board.piece_at(move.to_square) is not None:
        victim = move.to_square
    if victim is not None:
        captured = by_square.pop(victim)
    rook: tuple[PieceId, str, str] | None = None
    if board.is_castling(move):
        rook_from, rook_to = _ROOK_CASTLING[move.to_square]
        rook_id = by_square.pop(rook_from)
        by_square[rook_to] = rook_id
        rook = (rook_id, chess.square_name(rook_from), chess.square_name(rook_to))
    by_square[move.to_square] = mover
    return IdentityStep(
        mover=mover,
        captured=captured,
        victim_square=None if victim is None else chess.square_name(victim),
        rook=rook,
        pieces_after=_ordered(by_square),
    )


def _ordered(by_square: Mapping[int, PieceId]) -> PieceMap:
    return tuple((chess.square_name(sq), by_square[sq]) for sq in sorted(by_square))
