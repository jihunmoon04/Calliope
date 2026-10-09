"""`patterns` (POSITION, DEFINED, `patterns_v1`): geometric configurations (F3-D §2).

A pattern asserts only that a configuration holds; never that it wins, works or threatens. The
family reads only the F2 records of the same position (`pieces`, `squares`, `lines`), records
both colours, and reads nothing that depends on the side to move.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.geometry import Direction, Relation
from calliope.facts.families.lines import LinesFacts
from calliope.facts.families.pieces import PIECE_ORDER_RANK, PieceFacts, PiecesFacts
from calliope.facts.families.squares import SquaresFacts
from calliope.facts.keys import Color, PieceType
from calliope.facts.tree import Scope
from calliope.facts.values import FactClass


class Order(StrEnum):
    """A target's `piece_order_v1` rank against the actor's."""

    ABOVE = "above"
    EQUAL = "equal"
    BELOW = "below"


@dataclass(frozen=True, slots=True)
class Target:
    piece: Relation
    order: Order


@dataclass(frozen=True, slots=True)
class MultiTargetAttack:
    actor: Relation
    targets: tuple[Target, ...]  # board order


@dataclass(frozen=True, slots=True)
class LinePattern:
    """A slider's ray with its first two occupants: `front` (nearer) and `back`."""

    slider: Relation
    line: Direction  # the ray's direction, from the slider outward
    front: Relation
    back: Relation


@dataclass(frozen=True, slots=True)
class SoleDefender:
    defender: Relation
    defended: tuple[Relation, ...]  # board order


@dataclass(frozen=True, slots=True)
class BackRank:
    king: Relation
    blockers: tuple[Relation, ...]  # own pieces on the forward squares
    covered: tuple[str, ...]  # forward squares not own-occupied and enemy-attacked


@dataclass(frozen=True, slots=True)
class PatternsFacts:
    multi_target_attacks: tuple[MultiTargetAttack, ...]
    relative_pins: tuple[LinePattern, ...]
    skewers: tuple[LinePattern, ...]
    discovery_lines: tuple[LinePattern, ...]
    sole_defenders: tuple[SoleDefender, ...]
    back_ranks: tuple[BackRank, ...]  # at most one per colour


class PatternsFamily:
    name: ClassVar[str] = "patterns"
    version: ClassVar[str] = "patterns_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.DEFINED
    requires: ClassVar[tuple[str, ...]] = ("pieces", "squares", "lines")
    # record types of this family, for the closed type registry (F5-D §2)
    record_types: ClassVar[tuple[type, ...]] = (
        PatternsFacts,
        MultiTargetAttack,
        Target,
        Order,
        LinePattern,
        SoleDefender,
        BackRank,
        Relation,
    )

    def compute(self, ctx: FamilyContext) -> PatternsFacts:
        pieces: PiecesFacts = ctx.records["pieces"]
        squares: SquaresFacts = ctx.records["squares"]
        lines: LinesFacts = ctx.records["lines"]
        by_square = {p.square: p for p in pieces.pieces}
        relative_pins: list[LinePattern] = []
        skewers: list[LinePattern] = []
        discovery_lines: list[LinePattern] = []
        for ray in lines.rays:  # by source square, then direction
            if len(ray.occupants) < 2:
                continue
            slider = by_square[ray.source]
            a, b = by_square[ray.occupants[0].square], by_square[ray.occupants[1].square]
            if b.color is slider.color:
                continue  # [enemy, own] is an x-ray; [own, own] is no pattern
            pattern = LinePattern(
                participant(slider), ray.direction, participant(a), participant(b)
            )
            if a.color is slider.color:
                discovery_lines.append(pattern)
            elif b.piece_type is PieceType.KING:
                continue  # the absolute pin of `a`: F2 `pieces.absolutely_pinned`
            elif _rank(b) > _rank(a):
                relative_pins.append(pattern)
            elif _rank(a) > _rank(b):
                skewers.append(pattern)
        return PatternsFacts(
            multi_target_attacks=_multi_target_attacks(pieces, by_square),
            relative_pins=tuple(relative_pins),
            skewers=tuple(skewers),
            discovery_lines=tuple(discovery_lines),
            sole_defenders=_sole_defenders(pieces, by_square),
            back_ranks=tuple(
                rank
                for color in Color
                if (rank := _back_rank(pieces, squares, by_square, color)) is not None
            ),
        )


def participant(piece: PieceFacts) -> Relation:
    return Relation(piece.square, piece.piece_type, piece.absolutely_pinned is not None)


def _rank(piece: PieceFacts) -> int:
    return PIECE_ORDER_RANK[piece.piece_type]


def _order(target: PieceFacts, actor: PieceFacts) -> Order:
    if _rank(target) > _rank(actor):
        return Order.ABOVE
    if _rank(target) < _rank(actor):
        return Order.BELOW
    return Order.EQUAL


def _multi_target_attacks(
    pieces: PiecesFacts, by_square: dict[str, PieceFacts]
) -> tuple[MultiTargetAttack, ...]:
    out: list[MultiTargetAttack] = []
    for actor in pieces.pieces:
        enemy = actor.attacks.enemy  # board order; an empty en passant square is never here
        if len(enemy) < 2:
            continue
        targets = tuple(
            Target(participant(by_square[sq]), _order(by_square[sq], actor)) for sq in enemy
        )
        out.append(MultiTargetAttack(participant(actor), targets))
    return tuple(out)


def _sole_defenders(
    pieces: PiecesFacts, by_square: dict[str, PieceFacts]
) -> tuple[SoleDefender, ...]:
    defended: dict[str, list[PieceFacts]] = {}
    for piece in pieces.pieces:  # board order
        if piece.piece_type is PieceType.KING:
            continue  # a king is never captured: its "defenders" are no defence relation
        if piece.attacker_count >= 1 and piece.defender_count == 1:
            defended.setdefault(piece.defenders[0].square, []).append(piece)
    return tuple(
        SoleDefender(participant(by_square[square]), tuple(participant(p) for p in group))
        for square, group in sorted(defended.items(), key=lambda item: chess.parse_square(item[0]))
        if len(group) >= 2
    )


def _back_rank(
    pieces: PiecesFacts,
    squares: SquaresFacts,
    by_square: dict[str, PieceFacts],
    color: Color,
) -> BackRank | None:
    king = next(p for p in pieces.pieces if p.piece_type is PieceType.KING and p.color is color)
    square = chess.parse_square(king.square)
    first, second = (0, 1) if color is Color.WHITE else (7, 6)
    if chess.square_rank(square) != first:
        return None
    file = chess.square_file(square)
    blockers: list[Relation] = []
    covered: list[str] = []
    for f in (file - 1, file, file + 1):
        if not 0 <= f < 8:
            continue
        forward = squares.squares[chess.square(f, second)]
        occupant = by_square.get(forward.square)
        enemy = forward.black_attackers if color is Color.WHITE else forward.white_attackers
        if occupant is not None and occupant.color is color:
            blockers.append(participant(occupant))
        elif enemy:
            covered.append(forward.square)
        else:
            return None  # a free forward square
    if not blockers:
        return None
    return BackRank(participant(king), tuple(blockers), tuple(covered))
