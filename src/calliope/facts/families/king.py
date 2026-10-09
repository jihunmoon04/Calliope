"""`king` (POSITION, DEFINED, `king_zone_v1`): king zone, shield, nearby files, flight squares.

Zone attackers are geometric and come from `squares` (F2-D §6): a square behind a checked king
on the checking line has no geometric attacker, because the king blocks the ray. Flight squares
are legal for the side to move (from `status`) and geometric for the other side.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.geometry import Relation
from calliope.facts.families.pawns import ByColor, FileFacts, PawnsFacts
from calliope.facts.families.squares import SquaresFacts
from calliope.facts.families.status import StatusFacts
from calliope.facts.keys import Color
from calliope.facts.tree import Scope
from calliope.facts.values import FactClass


class FlightKind(StrEnum):
    LEGAL = "legal"  # side to move: king destinations in `status.legal_moves`, castling excluded
    GEOMETRIC = "geometric"  # other side: neighbours not own-occupied and not enemy-attacked


@dataclass(frozen=True, slots=True)
class ZoneSquare:
    square: str
    attackers: tuple[Relation, ...]  # enemy geometric attackers


@dataclass(frozen=True, slots=True)
class FlightSquares:
    kind: FlightKind
    squares: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KingFacts:
    color: Color
    square: str
    zone: tuple[ZoneSquare, ...]  # the king's square and its neighbours, a1 … h8
    shield: tuple[str, ...]  # own pawns, king file ± 1, first and second rank in front
    files_near: tuple[FileFacts, ...]  # king file ± 1 on the board
    flight_squares: FlightSquares


class KingFamily:
    name: ClassVar[str] = "king"
    version: ClassVar[str] = "king_zone_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.DEFINED
    requires: ClassVar[tuple[str, ...]] = ("status", "squares", "pawns")

    def compute(self, ctx: FamilyContext) -> ByColor[KingFacts]:
        return ByColor(_king(ctx, chess.WHITE), _king(ctx, chess.BLACK))


def _king(ctx: FamilyContext, color: chess.Color) -> KingFacts:
    board = ctx.board
    status: StatusFacts = ctx.records["status"]
    squares: SquaresFacts = ctx.records["squares"]
    pawns: PawnsFacts = ctx.records["pawns"]
    king = board.king(color)
    assert king is not None
    name = chess.square_name(king)
    neighbours = board.attacks_mask(king)
    zone_mask = neighbours | chess.BB_SQUARES[king]

    def enemy_attackers(square: int) -> tuple[Relation, ...]:
        facts = squares.squares[square]
        return facts.black_attackers if color == chess.WHITE else facts.white_attackers

    zone = tuple(
        ZoneSquare(chess.square_name(sq), enemy_attackers(sq))
        for sq in chess.scan_forward(zone_mask)
    )

    file, rank = chess.square_file(king), chess.square_rank(king)
    forward = 1 if color == chess.WHITE else -1
    own_pawns = board.pawns & board.occupied_co[color]
    shield_mask = 0
    for step in (1, 2):
        r = rank + forward * step
        if not 0 <= r < 8:
            break
        for f in (file - 1, file, file + 1):
            if 0 <= f < 8:
                shield_mask |= chess.BB_SQUARES[chess.square(f, r)]

    if color == board.turn:
        destinations = {
            chess.parse_square(m.uci[2:4])
            for m in status.legal_moves
            if m.uci[:2] == name and abs(chess.parse_square(m.uci[2:4]) % 8 - file) < 2
        }
        flight = FlightSquares(FlightKind.LEGAL, _names(sorted(destinations)))
    else:
        own = board.occupied_co[color]
        free = [sq for sq in chess.scan_forward(neighbours & ~own) if not enemy_attackers(sq)]
        flight = FlightSquares(FlightKind.GEOMETRIC, _names(free))

    return KingFacts(
        color=Color.of(color),
        square=name,
        zone=zone,
        shield=_names(chess.scan_forward(shield_mask & own_pawns)),
        files_near=tuple(pawns.files[f] for f in (file - 1, file, file + 1) if 0 <= f < 8),
        flight_squares=flight,
    )


def _names(squares) -> tuple[str, ...]:
    return tuple(chess.square_name(sq) for sq in squares)
