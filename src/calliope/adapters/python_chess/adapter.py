"""Stateless python-chess adapter for Calliope's immutable chess values."""

from __future__ import annotations

import chess

from calliope.application.ports.chess import ChessRulesPort
from calliope.domain.chess import ChessMove, Color, PositionSnapshot
from calliope.errors import (
    IllegalMoveError,
    InvalidFenError,
    InvalidPositionError,
    InvalidUciError,
    NullMoveNotAllowedError,
)


class PythonChessAdapter(ChessRulesPort):
    """Translate standard-chess FEN/UCI inputs into validated Calliope values.

    No board is retained on this instance. Each operation reconstructs its board from
    the immutable position FEN it receives.
    """

    def position_from_fen(self, fen: str) -> PositionSnapshot:
        raw_fen = fen.strip()
        if not raw_fen:
            raise InvalidFenError("FEN must not be empty")

        try:
            board = chess.Board(raw_fen, chess960=False)
        except ValueError:
            raise InvalidFenError("FEN syntax is invalid") from None

        if not board.is_valid():
            raise InvalidPositionError("FEN describes an invalid chess position")

        return self._snapshot_from_board(board)

    def legal_move_from_uci(
        self,
        position: PositionSnapshot,
        move_uci: str,
    ) -> ChessMove:
        board = self._board_from_snapshot(position)
        parsed_move = self._parse_uci(move_uci)
        self._reject_null_move(parsed_move)
        if parsed_move not in board.legal_moves:
            raise IllegalMoveError(f"Move {move_uci.strip()!r} is not legal in this position")

        return ChessMove(uci=parsed_move.uci(), san=board.san(parsed_move))

    def apply_move(
        self,
        position: PositionSnapshot,
        move: ChessMove,
    ) -> PositionSnapshot:
        board = self._board_from_snapshot(position)
        parsed_move = self._parse_uci(move.uci)
        self._reject_null_move(parsed_move)
        if parsed_move not in board.legal_moves:
            raise IllegalMoveError(f"Move {move.uci.strip()!r} is not legal in this position")

        board.push(parsed_move)
        return self._snapshot_from_board(board)

    @staticmethod
    def _board_from_snapshot(position: PositionSnapshot) -> chess.Board:
        try:
            board = chess.Board(position.fen, chess960=False)
        except ValueError:
            raise InvalidFenError("PositionSnapshot contains invalid FEN syntax") from None
        if not board.is_valid():
            raise InvalidPositionError("PositionSnapshot contains an invalid chess position")
        return board

    @staticmethod
    def _parse_uci(move_uci: str) -> chess.Move:
        stripped_uci = move_uci.strip()
        try:
            return chess.Move.from_uci(stripped_uci)
        except ValueError:
            raise InvalidUciError(f"UCI syntax is invalid: {stripped_uci!r}") from None

    @staticmethod
    def _reject_null_move(move: chess.Move) -> None:
        if move == chess.Move.null():
            raise NullMoveNotAllowedError("Null move '0000' is not allowed")

    @staticmethod
    def _canonical_fen(board: chess.Board) -> str:
        return board.fen(shredder=False, en_passant="fen", promoted=False)

    @classmethod
    def _snapshot_from_board(cls, board: chess.Board) -> PositionSnapshot:
        en_passant_square = (
            chess.square_name(board.ep_square) if board.ep_square is not None else None
        )
        return PositionSnapshot.create(
            fen=cls._canonical_fen(board),
            ply=board.ply(),
            side_to_move=Color.WHITE if board.turn == chess.WHITE else Color.BLACK,
            castling_rights=board.castling_xfen(),
            en_passant_square=en_passant_square,
            halfmove_clock=board.halfmove_clock,
            fullmove_number=board.fullmove_number,
        )
