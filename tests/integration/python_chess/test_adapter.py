import chess

from calliope.adapters.python_chess import PythonChessAdapter


def test_adapter_fen_matches_python_chess_strict_en_passant_serialization() -> None:
    adapter = PythonChessAdapter()
    board = chess.Board()
    snapshot = adapter.position_from_fen(board.fen())

    move = adapter.legal_move_from_uci(snapshot, "e2e4")
    result = adapter.apply_move(snapshot, move)
    board.push_uci("e2e4")

    assert result.fen == board.fen(shredder=False, en_passant="fen", promoted=False)
    assert result.fen.split()[3] == "e3"


def test_adapter_reconstructs_canonical_position_for_special_move() -> None:
    adapter = PythonChessAdapter()
    position = adapter.position_from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")

    result = adapter.apply_move(position, adapter.legal_move_from_uci(position, "e1c1"))
    expected = chess.Board(position.fen)
    expected.push_uci("e1c1")

    assert result.fen == expected.fen(shredder=False, en_passant="fen", promoted=False)
