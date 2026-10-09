"""`pieces` (POSITION, RULE): per-piece geometry and legal projections (F2-D §2).

Legal fields are projections of `status`; they exist only for the side to move (the other
side reads `NOT_OBSERVED`), except `legally_capturable_now`, which exists only for the side not
to move.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.geometry import Pin, Relation, absolute_pins, attack_table, squares
from calliope.facts.families.status import StatusFacts
from calliope.facts.keys import Color, PieceType
from calliope.facts.tree import Scope
from calliope.facts.values import NOT_OBSERVED, Defined, FactClass, NotObserved

PIECE_ORDER_V1 = "piece_order_v1"
# piece_order_v1: K > Q > R > B = N > P
PIECE_ORDER_RANK = {
    PieceType.PAWN: 0,
    PieceType.KNIGHT: 1,
    PieceType.BISHOP: 1,
    PieceType.ROOK: 2,
    PieceType.QUEEN: 3,
    PieceType.KING: 4,
}
_TYPE_INDEX = {piece_type: i for i, piece_type in enumerate(PieceType)}


@dataclass(frozen=True, slots=True)
class Footprint:
    """The attack set split by target occupancy; disjoint parts covering the set (ACT D1)."""

    empty: tuple[str, ...]
    friendly: tuple[str, ...]
    enemy: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PieceFacts:
    square: str
    color: Color
    piece_type: PieceType
    attacks: Footprint
    attackers: tuple[Relation, ...]  # enemy pieces whose attack set holds this square
    defenders: tuple[Relation, ...]  # friendly pieces (other than this one) whose set holds it
    attacker_count: int
    defender_count: int
    lowest_attacker_types: Defined[tuple[PieceType, ...]]  # piece_order_v1
    attacked_without_defender: bool
    attackers_exceed_defenders: bool
    absolutely_pinned: Pin | None
    legal_destinations: tuple[str, ...] | NotObserved
    legal_moves: tuple[str, ...] | NotObserved  # canonical UCI, in `status` order
    legally_capturable_now: bool | NotObserved


@dataclass(frozen=True, slots=True)
class PiecesFacts:
    pieces: tuple[PieceFacts, ...]  # by square

    def at(self, square: str) -> PieceFacts | None:
        return next((p for p in self.pieces if p.square == square), None)


class PiecesFamily:
    name: ClassVar[str] = "pieces"
    version: ClassVar[str] = "pieces_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.RULE
    requires: ClassVar[tuple[str, ...]] = ("status",)

    def compute(self, ctx: FamilyContext) -> PiecesFacts:
        board = ctx.board
        status: StatusFacts = ctx.records["status"]
        pinned = absolute_pins(board)
        table = attack_table(board, pinned)
        moves_from: dict[str, list[str]] = {}
        for legal in status.legal_moves:
            moves_from.setdefault(legal.uci[:2], []).append(legal.uci)
        victims = {capture.victim_square for capture in status.legal_captures}
        out: list[PieceFacts] = []
        for square, piece in sorted(board.piece_map().items()):
            name = chess.square_name(square)
            own = board.occupied_co[piece.color]
            enemy = board.occupied_co[not piece.color]
            attacks = table.attacks[square]
            attackers = table.relations(table.attackers[not piece.color][square])
            defenders = table.relations(table.attackers[piece.color][square])  # never itself
            to_move = piece.color == board.turn
            if to_move:
                moves = tuple(moves_from.get(name, ()))
                destinations: tuple[str, ...] | NotObserved = tuple(
                    sorted({uci[2:4] for uci in moves}, key=chess.parse_square)
                )
                legal_moves: tuple[str, ...] | NotObserved = moves
                capturable: bool | NotObserved = NOT_OBSERVED
            else:
                destinations = legal_moves = NOT_OBSERVED
                capturable = name in victims
            out.append(
                PieceFacts(
                    square=name,
                    color=Color.of(piece.color),
                    piece_type=PieceType.of(piece.piece_type),
                    attacks=Footprint(
                        empty=squares(attacks & ~board.occupied),
                        friendly=squares(attacks & own),
                        enemy=squares(attacks & enemy),
                    ),
                    attackers=attackers,
                    defenders=defenders,
                    attacker_count=len(attackers),
                    defender_count=len(defenders),
                    lowest_attacker_types=Defined(PIECE_ORDER_V1, lowest_types(attackers)),
                    attacked_without_defender=bool(attackers) and not defenders,
                    attackers_exceed_defenders=len(attackers) > len(defenders),
                    absolutely_pinned=pinned.get(square),
                    legal_destinations=destinations,
                    legal_moves=legal_moves,
                    legally_capturable_now=capturable,
                )
            )
        return PiecesFacts(tuple(out))


def lowest_types(attackers: tuple[Relation, ...]) -> tuple[PieceType, ...]:
    """Attacker types of the lowest `piece_order_v1` rank, in `PieceType` order."""

    if not attackers:
        return ()
    lowest = min(PIECE_ORDER_RANK[a.piece_type] for a in attackers)
    kinds = {a.piece_type for a in attackers if PIECE_ORDER_RANK[a.piece_type] == lowest}
    return tuple(sorted(kinds, key=_TYPE_INDEX.__getitem__))
