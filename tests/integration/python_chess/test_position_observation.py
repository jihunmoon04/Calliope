
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.chess import AttackRelation, Color, MaterialCount, PieceRef, PieceType
from calliope.services.position import PositionFactExtractor

rules = PythonChessAdapter()
extractor = PositionFactExtractor(rules)

W, B = Color.WHITE, Color.BLACK
P, N, Bi, R, Q, K = (
    PieceType.PAWN,
    PieceType.KNIGHT,
    PieceType.BISHOP,
    PieceType.ROOK,
    PieceType.QUEEN,
    PieceType.KING,
)


def facts(fen: str):
    return extractor.extract(rules.position_from_fen(fen))


def state(f, square: str):
    return next(s for s in f.pieces if s.piece.square == square)


def test_start_position():
    f = facts("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    assert len(f.pieces) == 32
    expected = MaterialCount(pawns=8, knights=2, bishops=2, rooks=2, queens=1)
    assert f.material.white == expected
    assert f.material.black == expected
    assert not f.side_to_move_in_check
    assert not f.side_to_move_checkmated
    assert f.legal_captures == ()
    assert state(f, "a1").piece == PieceRef(W, R, "a1")


def test_attack_and_defense_exact():
    f = facts("4k3/8/8/3p4/8/8/8/3RK3 w - - 0 1")
    rook = state(f, "d1")
    assert rook.attacks == ("a1", "b1", "c1", "e1", "d2", "d3", "d4", "d5")
    assert rook.attacked_by == ()
    assert rook.defended_by == (PieceRef(W, K, "e1"),)
    pawn = state(f, "d5")
    assert pawn.attacks == ("c4", "e4")
    assert pawn.attacked_by == (PieceRef(W, R, "d1"),)
    assert pawn.defended_by == ()
    assert AttackRelation(PieceRef(W, R, "d1"), "d5") in f.attacks
    keys = [(square_key(a.attacker.square), square_key(a.target_square)) for a in f.attacks]
    assert keys == sorted(keys)
    order = [square_key(s.piece.square) for s in f.pieces]
    assert order == sorted(order)


def square_key(square: str) -> int:
    return (int(square[1]) - 1) * 8 + ord(square[0]) - ord("a")


def test_pinned_attacker_attack_is_not_legal_capture():
    f = facts("4r2k/8/8/8/8/3p4/4B3/4K3 w - - 0 1")
    bishop = PieceRef(W, Bi, "e2")
    assert AttackRelation(bishop, "d3") in f.attacks
    pawn = state(f, "d3")
    assert bishop in pawn.attacked_by
    assert all(c.move.uci != "e2d3" for c in f.legal_captures)
    assert not pawn.legally_capturable_now
    assert not pawn.hanging_now


def test_hanging_piece():
    f = facts("4k3/8/8/3p4/8/8/8/3RK3 w - - 0 1")
    pawn = state(f, "d5")
    assert pawn.legally_capturable_now
    assert pawn.hanging_now
    (capture,) = f.legal_captures
    assert capture.move.uci == "d1d5"
    assert capture.move.san == "Rxd5"
    assert capture.landing_square == capture.captured_square == "d5"
    assert not capture.is_en_passant


def test_defended_piece_not_hanging():
    f = facts("4k3/8/2p5/3p4/8/8/8/3RK3 w - - 0 1")
    pawn = state(f, "d5")
    assert pawn.defended_by == (PieceRef(B, P, "c6"),)
    assert pawn.legally_capturable_now
    assert not pawn.hanging_now


def test_king_never_hanging_and_check_state():
    f = facts("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
    king = state(f, "e1")
    assert king.attacked_by == (PieceRef(B, R, "e2"),)
    assert not king.hanging_now
    assert not state(f, "e8").hanging_now
    assert f.side_to_move_in_check
    assert not f.side_to_move_checkmated


def test_checkmate():
    f = facts("R5k1/5ppp/8/8/8/8/8/6K1 b - - 0 1")
    assert f.side_to_move_in_check
    assert f.side_to_move_checkmated
    assert f.legal_captures == ()


def test_en_passant():
    f = facts("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2")
    (capture,) = f.legal_captures
    assert capture.is_en_passant
    assert capture.move.uci == "e5d6"
    assert capture.move.san == "exd6"
    assert capture.landing_square == "d6"
    assert capture.captured_square == "d5"
    assert capture.captured == PieceRef(B, P, "d5")
    assert capture.capturer == PieceRef(W, P, "e5")
    pawn = state(f, "d5")
    assert pawn.legally_capturable_now
    assert not pawn.hanging_now


def test_repeated_extraction_identical():
    position = rules.position_from_fen("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
    assert extractor.extract(position) == extractor.extract(position)
