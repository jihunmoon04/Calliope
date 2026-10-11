"""`exchange` (POSITION, DEFINED `see_v1`, on request): static exchange evaluation (F6-D).

For every non-king piece: what the opponent wins by starting captures on its square, with legal
captures, least valuable first, either side free to stop (F6-D §2.1–§2.2). For each exposed piece
of the side to move, and for every piece in check: the legal moves after which it is no longer
exposed (§2.3). The family is computed only when a request names it (F6-D §2.0).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import chess

from calliope.facts.families.base import FamilyContext
from calliope.facts.families.material import POINTS_V1
from calliope.facts.keys import Color, PieceType
from calliope.facts.tree import Scope
from calliope.facts.values import (
    NOT_OBSERVED,
    Defined,
    FactClass,
    NotApplicable,
    NotObserved,
)

SEE_V1 = "see_v1"
PROMOTION_BONUS = POINTS_V1[chess.QUEEN] - POINTS_V1[chess.PAWN]
IN_CHECK = NotApplicable("IN_CHECK")
NOT_EXPOSED = NotApplicable("NOT_EXPOSED")


@dataclass(frozen=True, slots=True)
class PieceExchange:
    square: str
    color: Color
    piece_type: PieceType
    gain: Defined[int] | NotApplicable  # see_v1; NotApplicable("IN_CHECK") for the side to move
    first_capture: str | None  # canonical UCI of the swap-off's first capture; None when gain is 0
    hypothetical: bool  # the owner is to move: the turn was passed (F6-D §2.2)
    safe_moves: tuple[str, ...] | NotApplicable | NotObserved  # F6-D §2.3


@dataclass(frozen=True, slots=True)
class ExchangeFacts:
    pieces: tuple[PieceExchange, ...]  # every non-king piece, by square


class ExchangeFamily:
    name: ClassVar[str] = "exchange"
    version: ClassVar[str] = "exchange_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.DEFINED
    requires: ClassVar[tuple[str, ...]] = ()
    on_request: ClassVar[bool] = True  # never eager by default (F6-D §2.0)
    record_types: ClassVar[tuple[type, ...]] = (ExchangeFacts, PieceExchange)

    def compute(self, ctx: FamilyContext) -> ExchangeFacts:
        board = ctx.board
        mover = board.turn
        in_check = board.is_check()
        legal = sorted(board.legal_moves, key=lambda m: m.uci())  # `status` order
        out: list[PieceExchange] = []
        for square, piece in sorted(board.piece_map().items()):
            if piece.piece_type == chess.KING:
                continue
            own = piece.color == mover
            see: Defined[int] | NotApplicable
            if own and in_check:
                see, first = IN_CHECK, None
            else:
                value, first = exposure(board, square)
                see = Defined(SEE_V1, value)
            safe: tuple[str, ...] | NotApplicable | NotObserved
            if not own:
                safe = NOT_OBSERVED
            elif in_check or (isinstance(see, Defined) and see.value >= 1):
                safe = safe_moves(board, square, legal)
            else:
                safe = NOT_EXPOSED
            out.append(
                PieceExchange(
                    square=chess.SQUARE_NAMES[square],
                    color=Color.of(piece.color),
                    piece_type=PieceType.of(piece.piece_type),
                    gain=see,
                    first_capture=first,
                    hypothetical=own,
                    safe_moves=safe,
                )
            )
        return ExchangeFacts(tuple(out))


def _captures(board: chess.Board, square: int) -> list[chess.Move]:
    """Legal captures onto `square`, least valuable capturer first (king last), then by
    from-square; promotions only as a queen; en passant never (its victim is elsewhere)."""

    out = [
        m
        for m in board.legal_moves
        if m.to_square == square
        and not board.is_en_passant(m)
        and m.promotion in (None, chess.QUEEN)
    ]

    def order(m: chess.Move) -> tuple[int, int]:
        kind = board.piece_type_at(m.from_square)
        assert kind is not None
        return (1000 if kind == chess.KING else POINTS_V1[kind], m.from_square)

    return sorted(out, key=order)


def gain(board: chess.Board, square: int) -> tuple[int, str | None]:
    """F6-D §2.1: what the side to move wins by starting captures on `square`."""

    victim = board.piece_type_at(square)
    if victim is None:
        return 0, None
    captures = _captures(board, square)
    if not captures:
        return 0, None
    first = captures[0]
    won = POINTS_V1[victim] + (PROMOTION_BONUS if first.promotion else 0)
    board.push(first)
    reply, _ = gain(board, square)
    board.pop()
    value = max(0, won - reply)
    return value, (first.uci() if value > 0 else None)


def exposure(board: chess.Board, square: int) -> tuple[int, str | None]:
    """F6-D §2.2: the opponent's gain on a piece; for the side to move, with the turn passed."""

    owner = board.color_at(square)
    if owner == board.turn:
        passed = board.copy(stack=False)
        passed.turn = not owner
        passed.ep_square = None
        return gain(passed, square)
    return gain(board, square)


def safe_moves(board: chess.Board, square: int, legal: list[chess.Move]) -> tuple[str, ...]:
    """F6-D §2.3: the legal moves after which the piece on `square` is not exposed."""

    out = []
    for move in legal:
        where = move.to_square if move.from_square == square else square
        board.push(move)
        value, _ = gain(board, where)
        board.pop()
        if value == 0:
            out.append(move.uci())
    return tuple(out)
