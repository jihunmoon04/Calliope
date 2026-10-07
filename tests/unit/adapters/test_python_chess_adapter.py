import chess
import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.chess import ChessMove, Color
from calliope.errors import (
    IllegalMoveError,
    InvalidFenError,
    InvalidPositionError,
    InvalidUciError,
    NullMoveNotAllowedError,
)


@pytest.fixture
def adapter() -> PythonChessAdapter:
    return PythonChessAdapter()


def test_starting_position_fields(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen(chess.STARTING_FEN)

    assert position.side_to_move is Color.WHITE
    assert position.castling_rights == "KQkq"
    assert position.en_passant_square is None
    assert position.halfmove_clock == 0
    assert position.fullmove_number == 1
    assert position.ply == 0


def test_black_to_move_ply_uses_board_semantics(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1")

    assert position.side_to_move is Color.BLACK
    assert position.ply == 1


def test_malformed_fen_raises_calliope_error(adapter: PythonChessAdapter) -> None:
    with pytest.raises(InvalidFenError):
        adapter.position_from_fen("this is not fen")


def test_empty_fen_is_rejected(adapter: PythonChessAdapter) -> None:
    with pytest.raises(InvalidFenError):
        adapter.position_from_fen("  \t\n")


def test_parseable_invalid_position_raises_invalid_position(adapter: PythonChessAdapter) -> None:
    with pytest.raises(InvalidPositionError):
        adapter.position_from_fen("8/8/8/8/8/8/8/8 w - - 0 1")


def test_canonical_fen_roundtrip_preserves_position_identity(adapter: PythonChessAdapter) -> None:
    original = adapter.position_from_fen("  " + chess.STARTING_FEN + "  ")
    reparsed = adapter.position_from_fen(original.fen)

    assert reparsed.fen == original.fen
    assert reparsed.position_id == original.position_id
    assert reparsed == original


def test_legal_uci_returns_canonical_uci_and_source_san(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen(chess.STARTING_FEN)

    move = adapter.legal_move_from_uci(position, " e2e4 ")

    assert move.uci == "e2e4"
    assert move.san == "e4"


def test_illegal_uci_move_is_rejected(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen(chess.STARTING_FEN)

    with pytest.raises(IllegalMoveError):
        adapter.legal_move_from_uci(position, "e2e5")


def test_malformed_uci_is_rejected_without_case_correction(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen(chess.STARTING_FEN)

    with pytest.raises(InvalidUciError):
        adapter.legal_move_from_uci(position, "e2e9")
    with pytest.raises(InvalidUciError):
        adapter.legal_move_from_uci(position, "E2E4")


def test_null_move_is_rejected(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen(chess.STARTING_FEN)

    with pytest.raises(NullMoveNotAllowedError):
        adapter.legal_move_from_uci(position, "0000")


def test_pinned_piece_cannot_expose_its_king(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen("k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1")

    with pytest.raises(IllegalMoveError):
        adapter.legal_move_from_uci(position, "e2d2")


def test_castling_moves_king_and_rook_and_clears_rights(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")

    move = adapter.legal_move_from_uci(position, "e1g1")
    result = adapter.apply_move(position, move)
    board = chess.Board(result.fen)

    assert move.san == "O-O"
    assert board.piece_at(chess.G1) == chess.Piece(chess.KING, chess.WHITE)
    assert board.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)
    assert "K" not in result.castling_rights
    assert "Q" not in result.castling_rights


CASTLING_FEN = "r3k2r/8/8/8/8/8/8/R3K2R {side} KQkq - 0 1"


@pytest.mark.parametrize(
    ("side", "supplied", "canonical", "san"),
    [
        ("w", "e1g1", "e1g1", "O-O"),
        ("w", "e1h1", "e1g1", "O-O"),
        ("w", "e1c1", "e1c1", "O-O-O"),
        ("w", "e1a1", "e1c1", "O-O-O"),
        ("b", "e8g8", "e8g8", "O-O"),
        ("b", "e8h8", "e8g8", "O-O"),
        ("b", "e8c8", "e8c8", "O-O-O"),
        ("b", "e8a8", "e8c8", "O-O-O"),
    ],
)
def test_standard_castling_notation_is_canonicalized(
    adapter: PythonChessAdapter, side: str, supplied: str, canonical: str, san: str
) -> None:
    position = adapter.position_from_fen(CASTLING_FEN.format(side=side))

    move = adapter.legal_move_from_uci(position, f" {supplied} ")

    assert move == ChessMove(canonical, san)
    assert adapter.apply_move(position, ChessMove(supplied)) == adapter.apply_move(
        position, ChessMove(canonical)
    )


def test_king_to_rook_notation_is_illegal_without_castling_rights(
    adapter: PythonChessAdapter,
) -> None:
    position = adapter.position_from_fen("r3k2r/8/8/8/8/8/8/R3K2R w - - 0 1")

    for uci in ("e1h1", "e1g1"):
        with pytest.raises(IllegalMoveError):
            adapter.legal_move_from_uci(position, uci)
        with pytest.raises(IllegalMoveError):
            adapter.apply_move(position, ChessMove(uci))


def test_apply_move_keeps_error_contract(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen(chess.STARTING_FEN)

    with pytest.raises(InvalidUciError):
        adapter.apply_move(position, ChessMove("e2e9"))
    with pytest.raises(NullMoveNotAllowedError):
        adapter.apply_move(position, ChessMove("0000"))
    with pytest.raises(IllegalMoveError):
        adapter.apply_move(position, ChessMove("e2e5"))


def test_promotion_is_legal_and_missing_promotion_is_illegal(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen("7k/P7/8/8/8/8/8/K7 w - - 0 1")

    move = adapter.legal_move_from_uci(position, "a7a8q")
    result = adapter.apply_move(position, move)

    assert move.uci == "a7a8q"
    assert chess.Board(result.fen).piece_at(chess.A8) == chess.Piece(chess.QUEEN, chess.WHITE)
    with pytest.raises(IllegalMoveError):
        adapter.legal_move_from_uci(position, "a7a8")


def test_en_passant_capture_removes_pawn_and_clears_target(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen("8/8/8/3pP3/8/8/8/K6k w - d6 0 1")

    result = adapter.apply_move(position, adapter.legal_move_from_uci(position, "e5d6"))
    board = chess.Board(result.fen)

    assert board.piece_at(chess.D6) == chess.Piece(chess.PAWN, chess.WHITE)
    assert board.piece_at(chess.D5) is None
    assert result.en_passant_square is None


def test_double_pawn_push_keeps_strict_en_passant_target(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen(chess.STARTING_FEN)

    result = adapter.apply_move(position, adapter.legal_move_from_uci(position, "e2e4"))

    assert result.en_passant_square == "e3"
    assert result.fen.split()[3] == "e3"


def test_apply_move_ignores_untrusted_san_and_rechecks_uci(adapter: PythonChessAdapter) -> None:
    position = adapter.position_from_fen(chess.STARTING_FEN)
    forged_presentation = ChessMove(uci="e2e4", san="Qxh7#")

    result = adapter.apply_move(position, forged_presentation)

    assert result.side_to_move is Color.BLACK
    assert chess.Board(result.fen).piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)


def test_apply_move_revalidates_move_for_current_position(adapter: PythonChessAdapter) -> None:
    start = adapter.position_from_fen(chess.STARTING_FEN)
    previously_validated = adapter.legal_move_from_uci(start, "e2e4")
    other_position = adapter.apply_move(start, ChessMove(uci="e2e3"))

    with pytest.raises(IllegalMoveError):
        adapter.apply_move(other_position, previously_validated)


def test_applying_move_does_not_mutate_source_snapshot(adapter: PythonChessAdapter) -> None:
    before = adapter.position_from_fen(chess.STARTING_FEN)
    before_copy = before

    after = adapter.apply_move(before, adapter.legal_move_from_uci(before, "e2e4"))

    assert before == before_copy
    assert before.position_id == before_copy.position_id
    assert after.position_id != before.position_id


def test_adapter_keeps_no_request_board_state(adapter: PythonChessAdapter) -> None:
    first = adapter.position_from_fen(chess.STARTING_FEN)
    adapter.apply_move(first, adapter.legal_move_from_uci(first, "e2e4"))
    second = adapter.position_from_fen(chess.STARTING_FEN)

    assert second == first
    assert "board" not in vars(adapter)
