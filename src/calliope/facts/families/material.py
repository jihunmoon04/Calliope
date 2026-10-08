"""`material` (POSITION, RULE with one DEFINED component): counts and `points_v1` (§6.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.tree import Scope
from calliope.facts.values import Defined, FactClass

POINTS_V1 = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


@dataclass(frozen=True, slots=True)
class MaterialCount:
    pawns: int
    knights: int
    bishops: int
    rooks: int
    queens: int
    light_square_bishops: int
    dark_square_bishops: int


@dataclass(frozen=True, slots=True)
class MaterialFacts:
    white: MaterialCount
    black: MaterialCount
    points: Defined[tuple[int, int]]  # (white, black) under points_v1 — a counting convention


class MaterialFamily:
    name: ClassVar[str] = "material"
    version: ClassVar[str] = "material_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.RULE
    requires: ClassVar[tuple[str, ...]] = ()

    def compute(self, ctx: FamilyContext) -> MaterialFacts:
        board = ctx.board
        return MaterialFacts(
            white=_count(board, chess.WHITE),
            black=_count(board, chess.BLACK),
            points=Defined("points_v1", (_points(board, chess.WHITE), _points(board, chess.BLACK))),
        )


def _count(board: chess.Board, color: chess.Color) -> MaterialCount:
    bishops = board.pieces(chess.BISHOP, color)
    return MaterialCount(
        pawns=len(board.pieces(chess.PAWN, color)),
        knights=len(board.pieces(chess.KNIGHT, color)),
        bishops=len(bishops),
        rooks=len(board.pieces(chess.ROOK, color)),
        queens=len(board.pieces(chess.QUEEN, color)),
        light_square_bishops=len(bishops & chess.BB_LIGHT_SQUARES),
        dark_square_bishops=len(bishops & chess.BB_DARK_SQUARES),
    )


def _points(board: chess.Board, color: chess.Color) -> int:
    return sum(value * len(board.pieces(kind, color)) for kind, value in POINTS_V1.items())
