"""`squares` (POSITION, RULE): occupant and geometric attackers of every square (F2-D §3).

On an occupied square, the occupant colour's attackers are its `pieces.defenders` and the other
colour's attackers are its `pieces.attackers`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.geometry import Relation, absolute_pins, attack_table
from calliope.facts.keys import Color, PieceType
from calliope.facts.tree import Scope
from calliope.facts.values import FactClass


@dataclass(frozen=True, slots=True)
class Occupant:
    color: Color
    piece_type: PieceType


@dataclass(frozen=True, slots=True)
class SquareFacts:
    square: str
    occupant: Occupant | None
    white_attackers: tuple[Relation, ...]
    black_attackers: tuple[Relation, ...]
    white_count: int
    black_count: int


@dataclass(frozen=True, slots=True)
class SquaresFacts:
    squares: tuple[SquareFacts, ...]  # all 64, a1 … h8

    def at(self, square: str) -> SquareFacts:
        return self.squares[chess.parse_square(square)]


class SquaresFamily:
    name: ClassVar[str] = "squares"
    version: ClassVar[str] = "squares_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.RULE
    requires: ClassVar[tuple[str, ...]] = ()

    def compute(self, ctx: FamilyContext) -> SquaresFacts:
        board = ctx.board
        table = attack_table(board, absolute_pins(board))
        pieces = board.piece_map()
        out: list[SquareFacts] = []
        for square in chess.SQUARES:
            piece = pieces.get(square)
            white = table.relations(table.attackers[chess.WHITE][square])
            black = table.relations(table.attackers[chess.BLACK][square])
            out.append(
                SquareFacts(
                    square=chess.SQUARE_NAMES[square],
                    occupant=None
                    if piece is None
                    else Occupant(Color.of(piece.color), PieceType.of(piece.piece_type)),
                    white_attackers=white,
                    black_attackers=black,
                    white_count=len(white),
                    black_count=len(black),
                )
            )
        return SquaresFacts(tuple(out))
