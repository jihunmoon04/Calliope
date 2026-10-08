"""The only place that parses chess input: root setup and the one move canonicalizer (§2.3).

Every move — input UCI, input SAN and (from F4) every engine PV move — goes through
`canonical_move` before it becomes an edge, a key or an engine argument.
"""

from __future__ import annotations

import chess

from calliope.facts.errors import InvalidPositionError, UnsupportedVariantError
from calliope.facts.keys import PositionKey


class MoveRejectedError(ValueError):
    """A move text that cannot become an edge; callers attach line label and ply."""


def canonical_move(board: chess.Board, text: str) -> chess.Move:
    """Resolve UCI or SAN against `board` and return the single standard-chess move.

    UCI is tried first; all castling notations (king-to-rook `e1h1` included) resolve to the
    standard king move (`e1g1`). Null moves, malformed promotion suffixes and illegal moves are
    refused.
    """

    stripped = text.strip()
    if not stripped:
        raise MoveRejectedError("is empty")
    try:
        syntax = chess.Move.from_uci(stripped)
    except ValueError:
        syntax = None
    if syntax is not None:
        if not syntax:
            raise MoveRejectedError("is a null move")
        try:
            return board.parse_uci(stripped)
        except ValueError:
            raise MoveRejectedError("is not legal here") from None
    try:
        return board.parse_san(stripped)
    except chess.AmbiguousMoveError:
        raise MoveRejectedError("is ambiguous SAN") from None
    except ValueError:
        raise MoveRejectedError("is neither legal UCI nor legal SAN here") from None


def node_fen(board: chess.Board) -> str:
    """Full position of a node: placement, side, castling, *legal* en passant, clocks."""

    return board.fen(en_passant="legal")


def position_key(board: chess.Board) -> PositionKey:
    return PositionKey.of(board)


def parse_start_fen(fen: str | None) -> chess.Board:
    if fen is None:
        return chess.Board()
    try:
        board = chess.Board(fen.strip())
    except ValueError as error:
        raise InvalidPositionError(f"FEN {fen!r} cannot be parsed: {error}") from None
    if board.has_chess960_castling_rights():
        raise UnsupportedVariantError(f"FEN {fen!r} has Chess960 castling rights")
    status = board.status()
    if status != chess.STATUS_VALID:
        raise InvalidPositionError(f"FEN {fen!r} is not a valid position (status {status!r})")
    return board
