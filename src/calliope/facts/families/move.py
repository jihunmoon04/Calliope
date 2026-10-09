"""`move` (EDGE, RULE): what the move of an edge is and does to piece identity (§6.10, §4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.keys import Color, PieceId, PieceType
from calliope.facts.tree import Scope
from calliope.facts.values import FactClass


class CastlingSide(StrEnum):
    KINGSIDE = "kingside"
    QUEENSIDE = "queenside"


@dataclass(frozen=True, slots=True)
class Capture:
    piece: PieceId
    piece_type: PieceType
    square: str  # victim square; differs from the landing square exactly for en passant
    en_passant: bool


@dataclass(frozen=True, slots=True)
class Promotion:
    piece: PieceId  # keeps the pawn's identity
    to: PieceType


@dataclass(frozen=True, slots=True)
class RookTransfer:
    piece: PieceId
    from_square: str
    to_square: str


MoveEvent = Capture | Promotion | RookTransfer


@dataclass(frozen=True, slots=True)
class MoveFacts:
    uci: str
    san: str
    mover: Color
    piece: PieceId
    piece_type: PieceType  # type before the move
    from_square: str
    to_square: str
    castling: CastlingSide | None
    gives_check: bool
    gives_mate: bool
    events: tuple[MoveEvent, ...]  # ordered: capture before promotion; castling rook transfer


class MoveFamily:
    name: ClassVar[str] = "move"
    version: ClassVar[str] = "move_v1"
    scope: ClassVar[Scope] = Scope.EDGE
    fact_class: ClassVar[FactClass] = FactClass.RULE
    requires: ClassVar[tuple[str, ...]] = ()
    # record types of this family, for the closed type registry (F5-D §2)
    record_types: ClassVar[tuple[type, ...]] = (
        MoveFacts,
        Capture,
        Promotion,
        RookTransfer,
        CastlingSide,
    )

    def compute(self, ctx: FamilyContext) -> MoveFacts:
        before, move, step = ctx.parent_board, ctx.move, ctx.identity
        assert before is not None and move is not None and step is not None
        moved = before.piece_at(move.from_square)
        assert moved is not None
        events: list[MoveEvent] = []
        if step.captured is not None:
            assert step.victim_square is not None
            victim = before.piece_at(chess.parse_square(step.victim_square))
            assert victim is not None
            events.append(
                Capture(
                    piece=step.captured,
                    piece_type=PieceType.of(victim.piece_type),
                    square=step.victim_square,
                    en_passant=before.is_en_passant(move),
                )
            )
        if move.promotion is not None:
            events.append(Promotion(piece=step.mover, to=PieceType.of(move.promotion)))
        castling: CastlingSide | None = None
        if step.rook is not None:
            rook, rook_from, rook_to = step.rook
            events.append(RookTransfer(piece=rook, from_square=rook_from, to_square=rook_to))
            kingside = before.is_kingside_castling(move)
            castling = CastlingSide.KINGSIDE if kingside else CastlingSide.QUEENSIDE
        after = ctx.board
        return MoveFacts(
            uci=move.uci(),
            san=before.san(move),
            mover=Color.of(before.turn),
            piece=step.mover,
            piece_type=PieceType.of(moved.piece_type),
            from_square=chess.square_name(move.from_square),
            to_square=chess.square_name(move.to_square),
            castling=castling,
            gives_check=after.is_check(),
            gives_mate=after.is_checkmate(),
            events=tuple(events),
        )
