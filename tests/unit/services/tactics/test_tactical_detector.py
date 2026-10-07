from dataclasses import replace

import pytest

import calliope.domain.analysis.tactics as tactics_module
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.application.ports.tactics import AbsolutePinObservation
from calliope.domain.analysis import (
    TacticalCandidate,
    TacticalCandidateKind,
    TacticalCandidateStatus,
)
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType
from calliope.errors import IncompatibleTacticalContextError
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

rules = PythonChessAdapter()
extractor = PositionFactExtractor(rules)
analyzer = BoardDeltaAnalyzer(rules, extractor)
detector = TacticalDetector()

W, B = Color.WHITE, Color.BLACK
P, N, Bi, R, Q, K = (
    PieceType.PAWN,
    PieceType.KNIGHT,
    PieceType.BISHOP,
    PieceType.ROOK,
    PieceType.QUEEN,
    PieceType.KING,
)
Kind = TacticalCandidateKind


def ref(color, kind, square):
    return PieceRef(color, kind, square)


def context(fen: str, uci: str):
    before = rules.position_from_fen(fen)
    move = ChessMove(uci)
    after = rules.apply_move(before, move)
    return {
        "before": extractor.extract(before),
        "after": extractor.extract(after),
        "delta": analyzer.analyze(before, move),
        "before_rules": rules.observe_tactics(before),
        "after_rules": rules.observe_tactics(after),
    }


def detect(fen: str, uci: str):
    return detector.detect(**context(fen, uci))


def of_kind(detection, kind):
    return [c for c in detection.candidates if c.kind is kind]


def kinds(detection):
    return {c.kind for c in detection.candidates}


def test_check():
    d = detect("4k3/8/8/8/8/8/8/R3K3 w - - 0 1", "a1a8")
    (check,) = of_kind(d, Kind.CHECK)
    assert check.actors == (ref(W, R, "a8"),)
    assert check.targets == (ref(B, K, "e8"),)
    assert check.status is TacticalCandidateStatus.DETECTED
    assert Kind.CHECKMATE not in kinds(d)
    assert Kind.DIRECT_ATTACK not in kinds(d)  # the king target is not a direct attack


def test_checkmate_suppresses_check_and_forced_response():
    d = detect("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1", "a1a8")
    assert kinds(d) == {Kind.CHECKMATE}
    (mate,) = d.candidates
    assert mate.actors == (ref(W, R, "a8"),)
    assert mate.targets == (ref(B, K, "g8"),)


def test_hanging_piece_with_actual_capturers():
    d = detect("4k3/8/8/8/4p3/8/8/4K1N1 w - - 0 1", "g1f3")
    (hanging,) = of_kind(d, Kind.HANGING_PIECE)
    assert hanging.actors == (ref(B, P, "e4"),)
    assert hanging.targets == (ref(W, N, "f3"),)


def test_pinned_geometric_attacker_is_not_a_hanging_capturer():
    fen = "4k3/4b3/8/5P2/8/8/8/4RK2 w - - 0 1"
    d = detect(fen, "f5f6")
    assert Kind.HANGING_PIECE not in kinds(d)
    # the pin already existed before the move
    assert Kind.ABSOLUTE_PIN not in kinds(d)
    (attack,) = of_kind(d, Kind.DIRECT_ATTACK)
    assert attack.actors == (ref(W, P, "f6"),)
    assert attack.targets == (ref(B, Bi, "e7"),)


def test_direct_attack_ignores_empty_squares():
    d = detect("4k3/8/8/8/8/8/8/4K1N1 w - - 0 1", "g1f3")
    assert Kind.DIRECT_ATTACK not in kinds(d)
    assert d.candidates == ()


def test_fork_positive():
    d = detect("q3k3/8/8/1N6/8/8/8/4K3 w - - 0 1", "b5c7")
    (fork,) = of_kind(d, Kind.FORK)
    assert fork.actors == (ref(W, N, "c7"),)
    assert fork.targets == (ref(B, Q, "a8"), ref(B, K, "e8"))
    assert Kind.CHECK in kinds(d)


def test_fork_negative_single_enemy():
    d = detect("4k3/8/8/1N6/8/8/8/4K3 w - - 0 1", "b5c7")
    assert Kind.FORK not in kinds(d)


def test_fork_negative_unchanged_multi_attack():
    d = detect("r3r1k1/2N5/8/8/8/8/8/4K3 w - - 0 1", "e1d1")
    assert Kind.FORK not in kinds(d)
    assert Kind.DIRECT_ATTACK not in kinds(d)


def test_double_attack():
    d = detect("7k/3q4/4n3/8/8/8/4B3/4R1K1 w - - 0 1", "e2b5")
    (double,) = of_kind(d, Kind.DOUBLE_ATTACK)
    assert double.actors == (ref(W, R, "e1"), ref(W, Bi, "b5"))
    assert double.targets == (ref(B, N, "e6"), ref(B, Q, "d7"))
    assert Kind.FORK not in kinds(d)


def test_new_absolute_pin():
    d = detect("4k3/3n4/8/8/8/8/4B3/4K3 w - - 0 1", "e2b5")
    (pin,) = of_kind(d, Kind.ABSOLUTE_PIN)
    assert pin.actors == (ref(W, Bi, "b5"),)
    assert pin.targets == (ref(B, N, "d7"),)
    assert pin.related == (ref(B, K, "e8"),)
    assert pin.status is TacticalCandidateStatus.DETECTED


def test_removal_of_defender_positive():
    d = detect("4k3/1p6/B1n5/8/8/8/8/4K3 w - - 0 1", "a6b7")
    (removal,) = of_kind(d, Kind.REMOVAL_OF_DEFENDER)
    assert removal.actors == (ref(W, Bi, "b7"),)
    assert removal.targets == (ref(B, N, "c6"),)
    assert removal.related == (ref(B, P, "b7"),)


def test_removal_negative_defender_only_moved():
    d = detect("4k3/1p6/2n5/8/8/8/8/4K3 b - - 0 1", "b7b6")
    assert Kind.REMOVAL_OF_DEFENDER not in kinds(d)


def test_removal_negative_target_not_attacked():
    d = detect("4k3/1p6/2n5/8/8/8/8/1R2K3 w - - 0 1", "b1b7")
    assert Kind.REMOVAL_OF_DEFENDER not in kinds(d)


def test_forced_response():
    d = detect("7k/8/5K2/8/8/8/8/R7 w - - 0 1", "a1a8")
    (forced,) = of_kind(d, Kind.FORCED_RESPONSE)
    assert forced.responses == (ChessMove("h8h7", "Kh7"),)
    assert Kind.CHECK in kinds(d)


def test_stalemate_has_no_forced_response():
    d = detect("7k/8/5K2/8/8/8/6Q1/8 w - - 0 1", "g2g6")
    assert kinds(d) == set()


def test_detected_only_and_deterministic():
    fen = "q3k3/8/8/1N6/8/8/8/4K3 w - - 0 1"
    first, second = detect(fen, "b5c7"), detect(fen, "b5c7")
    assert first == second
    assert all(c.status is TacticalCandidateStatus.DETECTED for c in first.candidates)
    assert len(set(first.candidates)) == len(first.candidates)
    order = [(c.kind.value, tuple(a.square for a in c.actors)) for c in first.candidates]
    assert order == sorted(order, key=lambda o: o[0])


def test_no_threat_model():
    names = {m.name for m in Kind} | {m.name for m in tactics_module.TacticalCandidateStatus}
    assert not names & {"DIRECT_THREAT", "VERIFIED_THREAT", "WINNING_ATTACK"}
    assert not hasattr(tactics_module, "DirectThreat")


@pytest.mark.parametrize(
    "kind, kwargs",
    [
        (Kind.CHECK, {"actors": (ref(W, R, "a8"),), "targets": (ref(B, Q, "e8"),)}),
        (Kind.FORK, {"actors": (ref(W, N, "c7"),), "targets": (ref(B, Q, "a8"),)}),
        (Kind.FORCED_RESPONSE, {"responses": ()}),
        (Kind.ABSOLUTE_PIN, {"actors": (ref(W, Bi, "b5"),), "targets": (ref(B, N, "d7"),)}),
    ],
)
def test_candidate_shape_invariants(kind, kwargs):
    with pytest.raises(ValueError):
        TacticalCandidate(kind, TacticalCandidateStatus.DETECTED, **kwargs)


# ---- context validation ---------------------------------------------------------------

FEN = "4k3/8/8/8/8/8/8/R3K3 w - - 0 1"


def test_context_mismatches_fail_closed():
    ctx = context(FEN, "a1a8")
    bad = [
        {"before_rules": replace(ctx["before_rules"], position_id="pos_x")},
        {"after_rules": replace(ctx["after_rules"], position_id="pos_x")},
        {"before": replace(ctx["before"], position_id="pos_x")},
        {"after": replace(ctx["after"], position_id="pos_x")},
        {"before_rules": replace(ctx["before_rules"], side_to_move=B)},
        {"after_rules": replace(ctx["after_rules"], side_to_move=W)},
    ]
    for override in bad:
        with pytest.raises(IncompatibleTacticalContextError):
            detector.detect(**{**ctx, **override})


def test_checkmate_inconsistency_fails_closed():
    ctx = context("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1", "a1a8")
    fake_move = ChessMove("g8f8", "Kf8")
    with pytest.raises(IncompatibleTacticalContextError):
        detector.detect(
            **{**ctx, "after_rules": replace(ctx["after_rules"], legal_moves=(fake_move,))}
        )


def test_pin_referencing_missing_piece_fails_closed():
    ctx = context(FEN, "a1a8")
    ghost = AbsolutePinObservation(ref(W, R, "h1"), ref(B, N, "h5"), ref(B, K, "e8"))
    with pytest.raises(IncompatibleTacticalContextError):
        detector.detect(
            **{**ctx, "after_rules": replace(ctx["after_rules"], absolute_pins=(ghost,))}
        )


def test_pin_with_inconsistent_colors_fails_closed():
    ctx = context("4k3/3n4/8/1B6/8/8/8/4K3 w - - 0 1", "e1e2")
    pin = ctx["before_rules"].absolute_pins[0]
    broken = AbsolutePinObservation(pin.pinned, pin.pinner, pin.king)
    with pytest.raises(IncompatibleTacticalContextError):
        detector.detect(
            **{**ctx, "before_rules": replace(ctx["before_rules"], absolute_pins=(broken,))}
        )
