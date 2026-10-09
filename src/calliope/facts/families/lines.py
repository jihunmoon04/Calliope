"""`lines` (POSITION, RULE): slider rays, x-rays and batteries (F2-D §4).

An x-ray continuation is never an attack. A battery is an unordered pair of same-colour sliders
on one line, recorded once with the line pointing from the lower to the higher square.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.geometry import RAYS, SLIDER_DIRECTIONS, Direction, moves_along
from calliope.facts.keys import Color, PieceType
from calliope.facts.tree import Scope
from calliope.facts.values import FactClass


@dataclass(frozen=True, slots=True)
class RayOccupant:
    square: str
    color: Color
    piece_type: PieceType


@dataclass(frozen=True, slots=True)
class XRay:
    """The squares past the first blocker up to and including the second. Never an attack."""

    squares: tuple[str, ...]
    first: RayOccupant
    second: RayOccupant


@dataclass(frozen=True, slots=True)
class Ray:
    source: str
    direction: Direction
    squares: tuple[str, ...]  # to the board edge, near to far
    occupants: tuple[RayOccupant, ...]  # near to far
    edge_empty: bool  # no square in this direction (ACT D4)
    unblocked: bool  # squares, but no occupant
    first_blocker: RayOccupant | None
    visible: tuple[str, ...]  # up to and including the first blocker
    xray: XRay | None


@dataclass(frozen=True, slots=True)
class Battery:
    pieces: tuple[str, str]  # (lower square, higher square)
    line: Direction  # from the lower to the higher square


@dataclass(frozen=True, slots=True)
class LinesFacts:
    rays: tuple[Ray, ...]  # by source square, then direction
    batteries: tuple[Battery, ...]  # by pieces

    def ray(self, source: str, direction: Direction) -> Ray | None:
        return next((r for r in self.rays if r.source == source and r.direction == direction), None)


class LinesFamily:
    name: ClassVar[str] = "lines"
    version: ClassVar[str] = "lines_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.RULE
    requires: ClassVar[tuple[str, ...]] = ()

    def compute(self, ctx: FamilyContext) -> LinesFacts:
        board = ctx.board
        occupied = board.occupied
        rays: list[Ray] = []
        batteries: list[Battery] = []
        sliders = board.bishops | board.rooks | board.queens
        for source in chess.scan_forward(sliders):
            slider = board.piece_at(source)
            assert slider is not None
            name = chess.square_name(source)
            for direction in SLIDER_DIRECTIONS[slider.piece_type]:
                path = RAYS[source][direction]
                hits = [sq for sq in path if occupied & chess.BB_SQUARES[sq]]
                occupants = tuple(_occupant(board, sq) for sq in hits)
                visible = path if not hits else path[: path.index(hits[0]) + 1]
                xray = None
                if len(hits) >= 2:
                    start, stop = path.index(hits[0]) + 1, path.index(hits[1]) + 1
                    xray = XRay(_names(path[start:stop]), occupants[0], occupants[1])
                rays.append(
                    Ray(
                        source=name,
                        direction=direction,
                        squares=_names(path),
                        occupants=occupants,
                        edge_empty=not path,
                        unblocked=bool(path) and not hits,
                        first_blocker=occupants[0] if occupants else None,
                        visible=_names(visible),
                        xray=xray,
                    )
                )
                if hits and hits[0] > source:  # each pair once, seen from its lower square
                    partner = board.piece_at(hits[0])
                    assert partner is not None
                    if partner.color == slider.color and moves_along(partner.piece_type, direction):
                        batteries.append(Battery((name, chess.square_name(hits[0])), direction))
        return LinesFacts(tuple(rays), tuple(sorted(batteries, key=_battery_order)))


def _occupant(board: chess.Board, square: int) -> RayOccupant:
    piece = board.piece_at(square)
    assert piece is not None
    return RayOccupant(
        chess.square_name(square), Color.of(piece.color), PieceType.of(piece.piece_type)
    )


def _names(path: tuple[int, ...]) -> tuple[str, ...]:
    return tuple(chess.square_name(sq) for sq in path)


def _battery_order(battery: Battery) -> tuple[int, int]:
    return (chess.parse_square(battery.pieces[0]), chess.parse_square(battery.pieces[1]))
