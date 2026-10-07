"""Stateless python-chess adapter for Calliope's immutable chess values."""

from __future__ import annotations

import chess

from calliope.application.ports.chess import ChessRulesPort
from calliope.application.ports.position import PositionObservationPort
from calliope.application.ports.tactics import (
    AbsolutePinObservation,
    TacticalObservation,
    TacticalObservationPort,
)
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
    IncompatibleTacticalContextError,
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


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


class PythonChessAdapter(ChessRulesPort, PositionObservationPort, TacticalObservationPort):
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
        legal_move = self._legal_move(board, move_uci)
        return ChessMove(uci=legal_move.uci(), san=board.san(legal_move))

    def apply_move(
        self,
        position: PositionSnapshot,
        move: ChessMove,
    ) -> PositionSnapshot:
        board = self._board_from_snapshot(position)
        board.push(self._legal_move(board, move.uci))
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

    def observe_tactics(self, position: PositionSnapshot) -> TacticalObservation:
        board = self._board_from_snapshot(position)
        legal_moves = tuple(
            sorted(
                (ChessMove(uci=m.uci(), san=board.san(m)) for m in board.legal_moves),
                key=lambda m: m.uci,
            )
        )

        pins = []
        for color in (chess.WHITE, chess.BLACK):
            king_square = board.king(color)
            if king_square is None:
                continue
            for square in chess.SQUARES:
                piece = board.piece_at(square)
                if piece is None or piece.color != color or piece.piece_type == chess.KING:
                    continue
                if not board.is_pinned(color, square):
                    continue
                pinner_square = self._resolve_pinner(board, king_square, square)
                pins.append(
                    AbsolutePinObservation(
                        pinner=self._piece_ref(board.piece_at(pinner_square), pinner_square),
                        pinned=self._piece_ref(piece, square),
                        king=self._piece_ref(board.piece_at(king_square), king_square),
                    )
                )

        return TacticalObservation(
            position_id=position.position_id,
            side_to_move=Color.WHITE if board.turn == chess.WHITE else Color.BLACK,
            legal_moves=legal_moves,
            absolute_pins=tuple(pins),
        )

    @staticmethod
    def _resolve_pinner(board: chess.Board, king_square: int, pinned_square: int) -> int:
        file_step = _sign(chess.square_file(pinned_square) - chess.square_file(king_square))
        rank_step = _sign(chess.square_rank(pinned_square) - chess.square_rank(king_square))
        orthogonal = file_step == 0 or rank_step == 0
        allowed = {chess.QUEEN, chess.ROOK if orthogonal else chess.BISHOP}
        pinned_color = board.color_at(pinned_square)

        file_, rank = chess.square_file(pinned_square), chess.square_rank(pinned_square)
        while True:
            file_ += file_step
            rank += rank_step
            if not (0 <= file_ < 8 and 0 <= rank < 8):
                break
            square = chess.square(file_, rank)
            piece = board.piece_at(square)
            if piece is None:
                continue
            if piece.color != pinned_color and piece.piece_type in allowed:
                return square
            break
        raise IncompatibleTacticalContextError(
            "pinned piece has no resolvable pinning slider on its ray"
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

    @classmethod
    def _legal_move(cls, board: chess.Board, move_uci: str) -> chess.Move:
        """Resolve UCI against the board and return its canonical standard-chess move.

        Board-aware parsing maps equivalent notations (such as king-takes-rook castling,
        ``e1h1``) to the single standard UCI identity (``e1g1``).
        """

        stripped_uci = move_uci.strip()
        cls._reject_null_move(cls._parse_uci(stripped_uci))
        try:
            return board.parse_uci(stripped_uci)
        except chess.IllegalMoveError:
            raise IllegalMoveError(f"Move {stripped_uci!r} is not legal in this position") from None

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
