from dataclasses import replace

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import (
    CheckChange,
    CheckChangeKind,
    DefenseChange,
    MaterialChange,
    PieceTransitionKind,
    RelationChangeKind,
)
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceState, PieceType
from calliope.errors import IncompatibleBoardDeltaError
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor

rules = PythonChessAdapter()
extractor = PositionFactExtractor(rules)
analyzer = BoardDeltaAnalyzer(rules, extractor)

W, B = Color.WHITE, Color.BLACK
P, N, Bi, R, Q, K = (
    PieceType.PAWN,
    PieceType.KNIGHT,
    PieceType.BISHOP,
    PieceType.ROOK,
    PieceType.QUEEN,
    PieceType.KING,
)
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def run(fen: str, uci: str):
    return analyzer.analyze(rules.position_from_fen(fen), ChessMove(uci))


def ref(color, kind, square):
    return PieceRef(color, kind, square)


def attacks(changes):
    return [(c.attacker, c.target_square) for c in changes]


def assert_complete_accounting(fen: str, delta, captured: int = 0):
    position = rules.position_from_fen(fen)
    before = extractor.extract(position)
    after = extractor.extract(rules.apply_move(position, delta.move))
    assert len(delta.piece_correspondence) == len(before.pieces) - captured
    assert len(delta.piece_correspondence) == len(after.pieces)
    assert {c.before for c in delta.piece_correspondence} <= {s.piece for s in before.pieces}
    assert {c.after for c in delta.piece_correspondence} == {s.piece for s in after.pieces}


def test_quiet_move():
    delta = run(START, "g1f3")
    assert [(t.kind, t.before, t.after) for t in delta.transitions] == [
        (PieceTransitionKind.MOVE, ref(W, N, "g1"), ref(W, N, "f3"))
    ]
    assert delta.capture is None
    assert delta.material_changes == ()
    assert delta.mover is W
    assert_complete_accounting(START, delta)
    knight = ref(W, N, "f3")
    assert attacks(delta.removed_attacks) == [
        (ref(W, N, "g1"), "e2"),
        (ref(W, N, "g1"), "f3"),
        (ref(W, N, "g1"), "h3"),
    ]
    assert attacks(delta.new_attacks) == [
        (ref(W, R, "h1"), "f1"),
        (knight, "e1"),
        (knight, "g1"),
        (knight, "d2"),
        (knight, "h2"),
        (knight, "d4"),
        (knight, "h4"),
        (knight, "e5"),
        (knight, "g5"),
    ]
    assert delta.check_changes == ()


def test_retained_attack_is_not_a_delta():
    delta = run("r3k3/8/8/8/8/8/8/R3K3 w - - 0 1", "a1a2")
    changed = set(attacks(delta.new_attacks)) | set(attacks(delta.removed_attacks))
    # the moving rook attacks a8 both before and after; the black rook attacks a2 both times
    assert not any(a.color is W and a.piece_type is R and t == "a8" for a, t in changed)
    assert not any(a.color is B and a.piece_type is R and t == "a2" for a, t in changed)
    # its attack on the vacated/occupied squares does change
    assert (ref(B, R, "a8"), "a1") in attacks(delta.removed_attacks)
    assert (ref(W, R, "a2"), "a1") in attacks(delta.new_attacks)


def test_normal_capture():
    fen = "4k3/8/8/3p4/8/8/8/3RK3 w - - 0 1"
    delta = run(fen, "d1d5")
    cap = delta.capture
    assert cap is not None
    assert cap.captured == ref(B, P, "d5")
    assert (cap.captured_square, cap.landing_square, cap.is_en_passant) == ("d5", "d5", False)
    assert cap.capturer_before == ref(W, R, "d1")
    assert cap.capturer_after == ref(W, R, "d5")
    assert delta.material_changes == (MaterialChange(B, P, -1),)
    assert_complete_accounting(fen, delta, captured=1)
    assert all(c.after.square != "d5" or c.after.color is W for c in delta.piece_correspondence)
    removed = attacks(delta.removed_attacks)
    assert (ref(B, P, "d5"), "c4") in removed
    assert (ref(B, P, "d5"), "e4") in removed


def test_en_passant():
    fen = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"
    delta = run(fen, "e5d6")
    assert [(t.before, t.after) for t in delta.transitions] == [(ref(W, P, "e5"), ref(W, P, "d6"))]
    cap = delta.capture
    assert cap is not None
    assert cap.is_en_passant
    assert (cap.landing_square, cap.captured_square) == ("d6", "d5")
    assert cap.captured == ref(B, P, "d5")
    assert delta.material_changes == (MaterialChange(B, P, -1),)
    assert_complete_accounting(fen, delta, captured=1)


def test_promotion():
    fen = "8/4P3/8/8/8/8/k7/4K3 w - - 0 1"
    delta = run(fen, "e7e8q")
    assert [(t.kind, t.before, t.after) for t in delta.transitions] == [
        (PieceTransitionKind.PROMOTION, ref(W, P, "e7"), ref(W, Q, "e8"))
    ]
    assert delta.capture is None
    assert delta.material_changes == (MaterialChange(W, P, -1), MaterialChange(W, Q, 1))
    assert_complete_accounting(fen, delta)


def test_promotion_capture():
    fen = "5r1k/4P3/8/8/8/8/8/4K3 w - - 0 1"
    delta = run(fen, "e7f8q")
    assert [(t.kind, t.before, t.after) for t in delta.transitions] == [
        (PieceTransitionKind.PROMOTION, ref(W, P, "e7"), ref(W, Q, "f8"))
    ]
    assert delta.capture is not None
    assert delta.capture.captured == ref(B, R, "f8")
    assert delta.capture.capturer_after == ref(W, Q, "f8")
    assert delta.material_changes == (
        MaterialChange(W, P, -1),
        MaterialChange(W, Q, 1),
        MaterialChange(B, R, -1),
    )
    assert_complete_accounting(fen, delta, captured=1)


@pytest.mark.parametrize(
    "fen, uci, color, king, rook",
    [
        ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1", W, ("e1", "g1"), ("h1", "f1")),
        ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1c1", W, ("e1", "c1"), ("a1", "d1")),
        ("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1", "e8g8", B, ("e8", "g8"), ("h8", "f8")),
        ("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1", "e8c8", B, ("e8", "c8"), ("a8", "d8")),
    ],
)
def test_castling(fen, uci, color, king, rook):
    delta = run(fen, uci)
    assert [(t.kind, t.before, t.after) for t in delta.transitions] == sorted(
        [
            (PieceTransitionKind.MOVE, ref(color, K, king[0]), ref(color, K, king[1])),
            (
                PieceTransitionKind.CASTLING_ROOK,
                ref(color, R, rook[0]),
                ref(color, R, rook[1]),
            ),
        ],
        key=lambda t: (int(t[1].square[1]), t[1].square[0]),
    )
    assert delta.capture is None
    assert delta.material_changes == ()
    assert_complete_accounting(fen, delta)


def test_defense_removed_and_retained_defense_not_duplicated():
    fen = "4k3/8/8/8/8/8/N7/R3K3 w - - 0 1"
    delta = run(fen, "a1b1")
    assert delta.new_defenses == ()
    # the rook defended Na2 before; it defends the king both before and after (retained)
    assert delta.removed_defenses == (
        DefenseChange(RelationChangeKind.REMOVED, ref(W, R, "a1"), ref(W, N, "a2")),
    )


def test_captured_defender_removes_defense():
    fen = "4k3/8/8/3p4/4p3/8/8/3RK3 w - - 0 1"
    delta = run(fen, "d1d5")
    assert (
        DefenseChange(RelationChangeKind.REMOVED, ref(B, P, "d5"), ref(B, P, "e4"))
        in delta.removed_defenses
    )


def test_unblocked_line_is_plain_new_attack_and_check():
    fen = "4k3/8/8/8/8/8/4B3/4RK2 w - - 0 1"
    delta = run(fen, "e2d3")
    assert (ref(W, R, "e1"), "e8") in attacks(delta.new_attacks)
    assert delta.check_changes == (CheckChange(CheckChangeKind.CREATED, B),)


def test_check_removed():
    delta = run("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1", "e1e2")
    assert delta.check_changes == (CheckChange(CheckChangeKind.REMOVED, W),)


def test_check_to_check():
    delta = run("4r3/8/8/8/5k2/8/8/4K1N1 w - - 0 1", "g1e2")
    assert delta.check_changes == (
        CheckChange(CheckChangeKind.REMOVED, W),
        CheckChange(CheckChangeKind.CREATED, B),
    )


def test_deterministic_and_sorted():
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    assert run(fen, "f1b5") == run(fen, "f1b5")
    delta = run(fen, "f1b5")

    def key(sq):
        return (int(sq[1]), sq[0])

    squares = [c.before.square for c in delta.piece_correspondence]
    assert squares == sorted(squares, key=key)
    pairs = [(c.attacker.square, c.target_square) for c in delta.new_attacks]
    assert pairs == sorted(pairs, key=lambda p: (key(p[0]), key(p[1])))


class TamperedFacts:
    """Return real facts, but corrupt the second (after) extraction."""

    def __init__(self, mutate):
        self.mutate = mutate
        self.calls = 0

    def extract(self, position):
        facts = extractor.extract(position)
        self.calls += 1
        return self.mutate(facts) if self.calls == 2 else facts


def _drop_piece(facts):
    return replace(
        facts,
        pieces=facts.pieces[:-1] if facts.pieces[-1].piece.square != "e1" else facts.pieces[1:],
    )


def _add_piece(facts):
    ghost = PieceState(ref(B, P, "h5"), (), (), (), False, False)
    return replace(facts, pieces=facts.pieces + (ghost,))


@pytest.mark.parametrize("mutate", [_drop_piece, _add_piece])
def test_unexplained_pieces_fail_closed(mutate):
    tampered = BoardDeltaAnalyzer(rules, TamperedFacts(mutate))  # type: ignore[arg-type]
    with pytest.raises(IncompatibleBoardDeltaError):
        tampered.analyze(
            rules.position_from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 0 1"), ChessMove("a1a2")
        )


def test_no_state_dependent_delta_kinds():
    import calliope.domain.analysis.delta as module

    names = {n.lower() for n in dir(module)}
    assert not any("hanging" in n or "legalcapture" in n or "motif" in n for n in names)
