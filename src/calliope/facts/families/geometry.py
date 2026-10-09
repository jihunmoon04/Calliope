"""Board-geometry primitives shared by the F2 POSITION families (F2-D §1).

Geometry means python-chess attack sets: a slider stops at, and includes, the first piece of
either colour; a pawn attacks its two forward diagonals only; a king attacks its neighbours; an
absolutely pinned piece keeps its full attack set. Absolute pins follow the ray rule of F2-D §2.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from calliope.facts.keys import PieceType

Direction = tuple[int, int]  # unit step (file delta, rank delta)

ORTHOGONAL: tuple[Direction, ...] = ((-1, 0), (0, -1), (0, 1), (1, 0))
DIAGONAL: tuple[Direction, ...] = ((-1, -1), (-1, 1), (1, -1), (1, 1))
DIRECTIONS: tuple[Direction, ...] = tuple(sorted(ORTHOGONAL + DIAGONAL))

SLIDER_DIRECTIONS: dict[chess.PieceType, tuple[Direction, ...]] = {
    chess.BISHOP: DIAGONAL,
    chess.ROOK: ORTHOGONAL,
    chess.QUEEN: DIRECTIONS,
}


def _ray(square: int, direction: Direction) -> tuple[int, ...]:
    df, dr = direction
    file, rank = chess.square_file(square) + df, chess.square_rank(square) + dr
    out: list[int] = []
    while 0 <= file < 8 and 0 <= rank < 8:
        out.append(chess.square(file, rank))
        file, rank = file + df, rank + dr
    return tuple(out)


# RAYS[square][direction]: the squares from `square` (exclusive) to the board edge, near to far.
RAYS: tuple[dict[Direction, tuple[int, ...]], ...] = tuple(
    {d: _ray(sq, d) for d in DIRECTIONS} for sq in chess.SQUARES
)


def moves_along(piece_type: chess.PieceType, direction: Direction) -> bool:
    """A slider of this type moves along `direction` (rook/queen orthogonal, bishop/queen diagonal)."""

    return direction in SLIDER_DIRECTIONS.get(piece_type, ())


@dataclass(frozen=True, slots=True)
class Relation:
    """A piece taking part in a geometric relation, e.g. an attacker of a square (F2-D §1.4)."""

    square: str
    piece_type: PieceType
    absolutely_pinned: bool


@dataclass(frozen=True, slots=True)
class Pin:
    """An absolute pin: the pinner's square and the unit step from the king toward the pinner."""

    pinner: str
    direction: Direction


def absolute_pins(board: chess.Board) -> dict[int, Pin]:
    """Pinned square -> pin, for both colours, by the ray rule of F2-D §2.

    X of colour C is pinned iff, walking from C's king in direction d, the first occupant is X
    and the next occupant is an enemy slider that moves along d.
    """

    pins: dict[int, Pin] = {}
    occupied = board.occupied
    for color in chess.COLORS:
        king = board.king(color)
        if king is None:
            continue
        own = board.occupied_co[color]
        for direction in DIRECTIONS:
            first: int | None = None
            for square in RAYS[king][direction]:
                if not occupied & chess.BB_SQUARES[square]:
                    continue
                if first is None:
                    if not own & chess.BB_SQUARES[square]:
                        break  # an enemy piece first: nothing is pinned on this ray
                    first = square
                    continue
                if not own & chess.BB_SQUARES[square]:
                    piece_type = board.piece_type_at(square)
                    assert piece_type is not None
                    if moves_along(piece_type, direction):
                        pins[first] = Pin(chess.square_name(square), direction)
                break
    return pins


@dataclass(frozen=True, slots=True)
class AttackTable:
    """Every piece's attack set, and per square the pieces whose set holds it, by colour."""

    attacks: dict[int, int]  # occupied square -> attacks_mask
    attackers: tuple[list[int], list[int]]  # [chess.BLACK / chess.WHITE][square] -> piece mask
    relation: dict[int, Relation]  # occupied square -> its relation record (shared)

    def relations(self, mask: int) -> tuple[Relation, ...]:
        """The pieces on `mask` as relations, in square order."""

        if not mask:
            return ()
        relation = self.relation
        return tuple(relation[sq] for sq in bits(mask))


def attack_table(board: chess.Board, pinned: dict[int, Pin]) -> AttackTable:
    attacks: dict[int, int] = {}
    attackers: tuple[list[int], list[int]] = ([0] * 64, [0] * 64)
    relation: dict[int, Relation] = {}
    for square, piece in board.piece_map().items():
        mask = board.attacks_mask(square)
        attacks[square] = mask
        bit = 1 << square
        by_target = attackers[piece.color]
        for target in bits(mask):
            by_target[target] |= bit
        relation[square] = Relation(
            chess.square_name(square), PieceType.of(piece.piece_type), square in pinned
        )
    return AttackTable(attacks, attackers, relation)


def bits(mask: int) -> list[int]:
    """The squares of `mask` in board order (a faster `chess.scan_forward`)."""

    out: list[int] = []
    while mask:
        low = mask & -mask
        out.append(low.bit_length() - 1)
        mask ^= low
    return out


def squares(mask: int) -> tuple[str, ...]:
    """The square names of `mask` in board order."""

    names = chess.SQUARE_NAMES
    out: list[str] = []
    while mask:
        low = mask & -mask
        out.append(names[low.bit_length() - 1])
        mask ^= low
    return tuple(out)
