"""`same_side_delta` (SPAN, RULE, `same_side_delta_v1`): grandparent → node (F2-D §7.2).

Side-dependent facts are compared only between a node and its grandparent, which have the same
side to move; nothing is diffed across a side flip. Pieces are mapped by `PieceId` across both
edges. A node without a grandparent in the tree holds a stored `NotApplicable` (the engine
stores it for every SPAN family).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.delta import PiecePair
from calliope.facts.families.king import KingFacts
from calliope.facts.families.pawns import ByColor
from calliope.facts.families.pieces import PiecesFacts
from calliope.facts.families.status import StatusFacts
from calliope.facts.identity import PieceMap
from calliope.facts.keys import PieceId, PieceType
from calliope.facts.tree import Scope
from calliope.facts.values import CAPTURED, Absent, FactClass


@dataclass(frozen=True, slots=True)
class SetDiff[T]:
    gained: tuple[T, ...]
    lost: tuple[T, ...]


@dataclass(frozen=True, slots=True)
class SideMember:
    """A piece of the side to move: its type at the grandparent and at the node."""

    piece: PieceId
    before: PieceType
    after: PieceType | Absent


@dataclass(frozen=True, slots=True)
class DestinationChange:
    piece: PieceId
    gained: tuple[str, ...]
    lost: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapturableChange:
    """A piece of the side not to move whose `legally_capturable_now` changed."""

    piece: PieceId
    before: bool
    after: bool | Absent


@dataclass(frozen=True, slots=True)
class SameSideDelta:
    pieces: tuple[SideMember, ...]
    legal_destinations: tuple[DestinationChange, ...]  # pieces present at both ends, changed
    legal_captures: SetDiff[PiecePair]  # capturer → victim
    capturable_now: tuple[CapturableChange, ...]
    flight_squares: SetDiff[str]  # the moving side's king, legal flight squares
    legal_move_count: tuple[int, int]  # (grandparent, node)


class SameSideDeltaFamily:
    name: ClassVar[str] = "same_side_delta"
    version: ClassVar[str] = "same_side_delta_v1"
    scope: ClassVar[Scope] = Scope.SPAN
    fact_class: ClassVar[FactClass] = FactClass.RULE
    requires: ClassVar[tuple[str, ...]] = ("status", "pieces", "king")

    def compute(self, ctx: FamilyContext) -> SameSideDelta:
        grand_map, _parent_map, node_map = ctx.pieces_maps
        before = _side(ctx.grandparent_records, grand_map)
        after = _side(ctx.records, node_map)
        assert before.status.side_to_move is after.status.side_to_move

        members = tuple(
            SideMember(pid, kind, after.types.get(pid, CAPTURED))
            for pid, kind in sorted(before.types.items())
        )
        destinations: list[DestinationChange] = []
        for pid in sorted(before.destinations.keys() & after.destinations.keys()):
            old, new = set(before.destinations[pid]), set(after.destinations[pid])
            if old != new:
                destinations.append(
                    DestinationChange(pid, _ordered(new - old), _ordered(old - new))
                )
        capturable: list[CapturableChange] = []
        for pid, was in sorted(before.capturable.items()):
            now: bool | Absent = after.capturable.get(pid, CAPTURED)
            if now != was:
                capturable.append(CapturableChange(pid, was, now))
        old_flight, new_flight = set(before.flight), set(after.flight)
        return SameSideDelta(
            pieces=members,
            legal_destinations=tuple(destinations),
            legal_captures=SetDiff(
                tuple(sorted(after.captures - before.captures)),
                tuple(sorted(before.captures - after.captures)),
            ),
            capturable_now=tuple(capturable),
            flight_squares=SetDiff(
                _ordered(new_flight - old_flight), _ordered(old_flight - new_flight)
            ),
            legal_move_count=(before.status.legal_move_count, after.status.legal_move_count),
        )


@dataclass(frozen=True, slots=True)
class _Side:
    status: StatusFacts
    types: dict[PieceId, PieceType]  # side to move
    destinations: dict[PieceId, tuple[str, ...]]  # side to move
    capturable: dict[PieceId, bool]  # side not to move
    captures: frozenset[PiecePair]
    flight: tuple[str, ...]


def _side(records: Mapping[str, Any], piece_map: PieceMap) -> _Side:
    ids = dict(piece_map)
    status: StatusFacts = records["status"]
    pieces: PiecesFacts = records["pieces"]
    kings: ByColor[KingFacts] = records["king"]
    mover = status.side_to_move
    types: dict[PieceId, PieceType] = {}
    destinations: dict[PieceId, tuple[str, ...]] = {}
    capturable: dict[PieceId, bool] = {}
    for piece in pieces.pieces:
        pid = ids[piece.square]
        if piece.color is mover:
            types[pid] = piece.piece_type
            assert isinstance(piece.legal_destinations, tuple)
            destinations[pid] = piece.legal_destinations
        else:
            assert isinstance(piece.legally_capturable_now, bool)
            capturable[pid] = piece.legally_capturable_now
    captures = frozenset(
        PiecePair(ids[c.capturer_square], ids[c.victim_square]) for c in status.legal_captures
    )
    return _Side(
        status=status,
        types=types,
        destinations=destinations,
        capturable=capturable,
        captures=captures,
        flight=kings.of(mover).flight_squares.squares,
    )


def _ordered(squares: set[str]) -> tuple[str, ...]:
    return tuple(sorted(squares, key=chess.parse_square))
