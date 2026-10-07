from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType

rules = PythonChessAdapter()


def observe(fen: str):
    return rules.observe_tactics(rules.position_from_fen(fen))


def test_legal_moves_exact_sorted_with_san():
    obs = observe("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    ucis = [m.uci for m in obs.legal_moves]
    assert len(ucis) == 20
    assert ucis == sorted(ucis)
    assert obs.legal_moves[0] == ChessMove("a2a3", "a3")
    assert ChessMove("g1f3", "Nf3") in obs.legal_moves
    assert all(m.san for m in obs.legal_moves)
    assert obs.side_to_move is Color.WHITE
    assert obs.absolute_pins == ()


def test_single_legal_move_and_mate():
    obs = observe("7k/8/5K2/8/8/8/8/R7 w - - 0 1")
    assert obs.legal_moves != ()
    mate = observe("R5k1/5ppp/8/8/8/8/8/4K3 b - - 0 1")
    assert mate.legal_moves == ()


def test_absolute_pin_resolved_exactly():
    obs = observe("4k3/3n4/8/1B6/8/8/8/4K3 b - - 0 1")
    (pin,) = obs.absolute_pins
    assert pin.pinner == PieceRef(Color.WHITE, PieceType.BISHOP, "b5")
    assert pin.pinned == PieceRef(Color.BLACK, PieceType.KNIGHT, "d7")
    assert pin.king == PieceRef(Color.BLACK, PieceType.KING, "e8")


def test_orthogonal_queen_pin_and_both_colors():
    obs = observe("4k3/4b3/8/8/8/8/8/4QK2 b - - 0 1")
    (pin,) = obs.absolute_pins
    assert pin.pinner == PieceRef(Color.WHITE, PieceType.QUEEN, "e1")
    assert pin.pinned == PieceRef(Color.BLACK, PieceType.BISHOP, "e7")


def test_relative_pin_is_not_absolute():
    # white rook a1 -- black knight a4 -- black rook a8: only a relative pin
    obs = observe("r6k/8/8/8/n7/8/8/R3K3 w - - 0 1")
    assert obs.absolute_pins == ()
