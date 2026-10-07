"""Stateless python-chess adapter for Calliope's immutable chess values."""

from __future__ import annotations

import chess

from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.position import PositionObservationPort
from calliope.domain.chess import (
    AttackRelation,
    ChessMove,
    Color,
    LegalCapture,
    PieceRef,
    PieceType,
    PositionObservation,
    PositionSnapshot,
)
from calliope.errors import (
    IllegalMoveError,
    InvalidFenError,
    InvalidPositionError,
    InvalidUciError,
    NullMoveNotAllowedError,
)

_PIECE_TYPES = {
    chess.PAWN: PieceType.PAWN,
    chess.KNIGHT: PieceType.KNIGHT,
    chess.BISHOP: PieceType.BISHOP,
    chess.ROOK: PieceType.ROOK,
    chess.QUEEN: PieceType.QUEEN,
    chess.KING: PieceType.KING,
}


class PythonChessAdapter(ChessRulesPort, PositionObservationPort):
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

    def observe_position(self, position: PositionSnapshot) -> PositionObservation:
        board = self._board_from_snapshot(position)

        pieces: dict[int, PieceRef] = {}
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece is not None:
                pieces[square] = self._piece_ref(piece, square)

        attacks = tuple(
            AttackRelation(attacker=ref, target_square=chess.square_name(target))
            for square, ref in pieces.items()
            for target in sorted(board.attacks(square))
        )

        captures = []
        for move in board.legal_moves:
            if not board.is_capture(move):
                continue
            is_ep = board.is_en_passant(move)
            captured_square = (
                chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
                if is_ep
                else move.to_square
            )
            captures.append(
                LegalCapture(
                    move=ChessMove(uci=move.uci(), san=board.san(move)),
                    capturer=pieces[move.from_square],
                    captured=pieces[captured_square],
                    landing_square=chess.square_name(move.to_square),
                    captured_square=chess.square_name(captured_square),
                    is_en_passant=is_ep,
                )
            )

        return PositionObservation(
            position_id=position.position_id,
            pieces=tuple(pieces.values()),
            attacks=attacks,
            legal_captures=tuple(sorted(captures, key=lambda c: c.move.uci)),
            side_to_move_in_check=board.is_check(),
            side_to_move_checkmated=board.is_checkmate(),
        )

    @staticmethod
    def _piece_ref(piece: chess.Piece, square: int) -> PieceRef:
        return PieceRef(
            color=Color.WHITE if piece.color == chess.WHITE else Color.BLACK,
            piece_type=_PIECE_TYPES[piece.piece_type],
            square=chess.square_name(square),
        )

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
