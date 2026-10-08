"""`status` (POSITION, RULE): side to move, check, terminal rules, legal moves (design F0 §6.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.keys import Color, PieceType
from calliope.facts.tree import Scope
from calliope.facts.values import FactClass


@dataclass(frozen=True, slots=True)
class LegalMove:
    uci: str
    san: str


@dataclass(frozen=True, slots=True)
class LegalCapture:
    uci: str
    capturer_square: str
    capturer_type: PieceType
    victim_square: str  # differs from `landing_square` exactly for en passant
    victim_type: PieceType
    landing_square: str
    en_passant: bool
    promotion: PieceType | None


@dataclass(frozen=True, slots=True)
class StatusFacts:
    side_to_move: Color
    in_check: bool
    checkers: tuple[str, ...]  # squares of the pieces giving check
    checkmate: bool
    stalemate: bool
    insufficient_material: bool  # python-chess's conservative test (§7.8)
    legal_move_count: int
    legal_moves: tuple[LegalMove, ...]
    legal_captures: tuple[LegalCapture, ...]
    checking_moves: tuple[str, ...]
    mating_moves: tuple[str, ...]  # exact mate-in-1
    promotions: tuple[str, ...]


class StatusFamily:
    name: ClassVar[str] = "status"
    version: ClassVar[str] = "status_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.RULE
    requires: ClassVar[tuple[str, ...]] = ()

    def compute(self, ctx: FamilyContext) -> StatusFacts:
        board = ctx.board.copy(stack=False)
        moves = sorted(board.legal_moves, key=lambda m: m.uci())
        captures: list[LegalCapture] = []
        checking: list[str] = []
        mating: list[str] = []
        for move in moves:
            if board.is_capture(move):
                captures.append(_capture(board, move))
            if board.gives_check(move):
                checking.append(move.uci())
                board.push(move)
                if board.is_checkmate():
                    mating.append(move.uci())
                board.pop()
        legal = tuple(LegalMove(m.uci(), board.san(m)) for m in moves)
        return StatusFacts(
            side_to_move=Color.of(board.turn),
            in_check=board.is_check(),
            checkers=tuple(chess.square_name(sq) for sq in sorted(board.checkers())),
            checkmate=board.is_checkmate(),
            stalemate=board.is_stalemate(),
            insufficient_material=board.is_insufficient_material(),
            legal_move_count=len(moves),
            legal_moves=legal,
            legal_captures=tuple(captures),
            checking_moves=tuple(checking),
            mating_moves=tuple(mating),
            promotions=tuple(m.uci() for m in moves if m.promotion is not None),
        )


def _capture(board: chess.Board, move: chess.Move) -> LegalCapture:
    en_passant = board.is_en_passant(move)
    victim = (
        move.to_square + (-8 if board.turn == chess.WHITE else 8) if en_passant else move.to_square
    )
    capturer = board.piece_at(move.from_square)
    victim_piece = board.piece_at(victim)
    assert capturer is not None and victim_piece is not None
    return LegalCapture(
        uci=move.uci(),
        capturer_square=chess.square_name(move.from_square),
        capturer_type=PieceType.of(capturer.piece_type),
        victim_square=chess.square_name(victim),
        victim_type=PieceType.of(victim_piece.piece_type),
        landing_square=chess.square_name(move.to_square),
        en_passant=en_passant,
        promotion=None if move.promotion is None else PieceType.of(move.promotion),
    )
