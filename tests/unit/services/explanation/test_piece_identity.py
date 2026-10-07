from dataclasses import replace

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import (
    BasePieceRef,
    PieceCorrespondence,
    PieceTransition,
    PieceTransitionKind,
)
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType
from calliope.errors import IncompatibleBadMoveContextError
from calliope.services.explanation import BasePieceIdentityMap
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor

rules = PythonChessAdapter()
facts = PositionFactExtractor(rules)
deltas = BoardDeltaAnalyzer(rules, facts)

W, B = Color.WHITE, Color.BLACK
P, N, R, Q, K = (
    PieceType.PAWN,
    PieceType.KNIGHT,
    PieceType.ROOK,
    PieceType.QUEEN,
    PieceType.KING,
)


def ref(color: Color, kind: PieceType, square: str) -> PieceRef:
    return PieceRef(color, kind, square)


def base_ref(color: Color, kind: PieceType, square: str) -> BasePieceRef:
    return BasePieceRef(color, kind, square)


def start(fen: str):
    position = rules.position_from_fen(fen)
    identity = BasePieceIdentityMap.from_facts(facts.extract(position))
    return position, identity


def step(position, identity: BasePieceIdentityMap, uci: str):
    move = rules.legal_move_from_uci(position, uci)
    delta = deltas.analyze(position, move)
    next_position = rules.apply_move(position, move)
    return next_position, identity.advance(delta), delta


def test_composes_identity_across_multiple_pv_plies() -> None:
    position, identity = start("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")
    pawn = base_ref(W, P, "e2")
    black_king = base_ref(B, K, "e8")

    position, identity, d1 = step(position, identity, "e2e4")
    position, identity, d2 = step(position, identity, "e8e7")
    position, identity, d3 = step(position, identity, "e4e5")

    assert identity.position_id == position.position_id
    assert identity.current_piece(pawn) == ref(W, P, "e5")
    assert identity.current_piece(black_king) == ref(B, K, "e7")
    assert identity.base_ref_for(ref(W, P, "e5")) == pawn

    original = BasePieceIdentityMap.from_facts(
        facts.extract(rules.position_from_fen("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"))
    )
    composed = original.advance_all((d1, d2, d3))
    assert composed == identity


def test_branch_maps_keep_one_base_identity_when_piece_is_captured_on_only_one_branch() -> None:
    fen = "4k3/8/8/3p4/8/8/4P3/4K3 w - - 0 1"
    base_position, root = start(fen)
    white_pawn = base_ref(W, P, "e2")

    actual_position, actual, _ = step(base_position, root, "e2e4")
    _, actual, _ = step(actual_position, actual, "d5e4")

    comparator_position, comparator, _ = step(base_position, root, "e2e3")
    _, comparator, _ = step(comparator_position, comparator, "d5d4")

    assert actual.current_piece(white_pawn) is None
    assert comparator.current_piece(white_pawn) == ref(W, P, "e3")
    assert white_pawn in actual.base_pieces == comparator.base_pieces


def test_castling_tracks_king_and_rook_independently() -> None:
    position, identity = start("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    king = base_ref(W, K, "e1")
    rook = base_ref(W, R, "h1")

    _, identity, delta = step(position, identity, "e1g1")

    assert identity.current_piece(king) == ref(W, K, "g1")
    assert identity.current_piece(rook) == ref(W, R, "f1")
    assert {transition.kind for transition in delta.transitions} == {
        PieceTransitionKind.MOVE,
        PieceTransitionKind.CASTLING_ROOK,
    }


def test_promotion_keeps_base_pawn_identity() -> None:
    position, identity = start("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
    pawn = base_ref(W, P, "e7")

    _, identity, _ = step(position, identity, "e7e8q")

    promoted = ref(W, Q, "e8")
    assert identity.current_piece(pawn) == promoted
    assert identity.base_ref_for(promoted) == pawn


def test_capture_promotion_keeps_pawn_identity_and_terminates_captured_piece() -> None:
    position, identity = start("5r1k/4P3/8/8/8/8/8/4K3 w - - 0 1")
    pawn = base_ref(W, P, "e7")
    rook = base_ref(B, R, "f8")

    _, identity, _ = step(position, identity, "e7f8q")

    assert identity.current_piece(pawn) == ref(W, Q, "f8")
    assert identity.current_piece(rook) is None


def test_en_passant_terminates_piece_on_captured_square_not_landing_square() -> None:
    position, identity = start("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2")
    white_pawn = base_ref(W, P, "e5")
    black_pawn = base_ref(B, P, "d5")

    _, identity, delta = step(position, identity, "e5d6")

    assert delta.capture is not None and delta.capture.is_en_passant
    assert delta.capture.captured_square == "d5"
    assert delta.capture.landing_square == "d6"
    assert identity.current_piece(white_pawn) == ref(W, P, "d6")
    assert identity.current_piece(black_pawn) is None


def test_unknown_base_or_current_piece_fails_closed() -> None:
    _, identity = start("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")

    with pytest.raises(IncompatibleBadMoveContextError, match="does not belong"):
        identity.current_piece(base_ref(W, N, "b1"))

    with pytest.raises(IncompatibleBadMoveContextError, match="does not map uniquely"):
        identity.base_ref_for(ref(W, N, "b1"))


def test_delta_must_continue_from_current_position() -> None:
    position, identity = start("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")
    move = rules.legal_move_from_uci(position, "e2e4")
    delta = deltas.analyze(position, move)
    bad = replace(delta, before_position_id="pos_wrong")

    with pytest.raises(IncompatibleBadMoveContextError, match="does not continue"):
        identity.advance(bad)


def test_missing_or_duplicate_correspondence_fails_closed() -> None:
    position, identity = start("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")
    delta = deltas.analyze(position, rules.legal_move_from_uci(position, "e2e4"))

    missing = replace(delta, piece_correspondence=delta.piece_correspondence[:-1])
    with pytest.raises(IncompatibleBadMoveContextError, match="unexplained"):
        identity.advance(missing)

    duplicate = replace(
        delta,
        piece_correspondence=delta.piece_correspondence + (delta.piece_correspondence[0],),
    )
    with pytest.raises(IncompatibleBadMoveContextError, match="duplicate before-piece"):
        identity.advance(duplicate)


def test_type_change_without_promotion_transition_fails_closed() -> None:
    position, identity = start("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")
    delta = deltas.analyze(position, rules.legal_move_from_uci(position, "e2e4"))

    pairs = list(delta.piece_correspondence)
    index = next(i for i, pair in enumerate(pairs) if pair.before == ref(W, P, "e2"))
    pair = pairs[index]
    pairs[index] = PieceCorrespondence(pair.before, ref(W, Q, "e4"))

    # A type-changing correspondence with no transition at all.
    bare = replace(delta, piece_correspondence=tuple(pairs), transitions=())
    with pytest.raises(IncompatibleBadMoveContextError, match="without a promotion"):
        identity.advance(bare)

    # A type-changing correspondence labelled as an ordinary MOVE.
    labelled = replace(
        delta,
        piece_correspondence=tuple(pairs),
        transitions=(PieceTransition(PieceTransitionKind.MOVE, pair.before, ref(W, Q, "e4")),),
    )
    with pytest.raises(IncompatibleBadMoveContextError, match="non-promotion transition"):
        identity.advance(labelled)

    # A transition that no correspondence backs.
    orphan = replace(
        delta,
        transitions=(PieceTransition(PieceTransitionKind.MOVE, pair.before, ref(W, P, "e3")),),
    )
    with pytest.raises(IncompatibleBadMoveContextError, match="no matching correspondence"):
        identity.advance(orphan)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (ref(W, P, "e7"), ref(W, P, "e8")),
        (ref(W, P, "e7"), ref(W, K, "e8")),
        (ref(W, N, "e7"), ref(W, Q, "e8")),
    ],
)
def test_invalid_promotion_transition_fails_closed(before: PieceRef, after: PieceRef) -> None:
    position, identity = start("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
    delta = deltas.analyze(position, rules.legal_move_from_uci(position, "e7e8q"))
    pairs = tuple(
        PieceCorrespondence(before, after) if p.before == ref(W, P, "e7") else p
        for p in delta.piece_correspondence
    )
    bad = replace(
        delta,
        piece_correspondence=pairs,
        transitions=(PieceTransition(PieceTransitionKind.PROMOTION, before, after),),
    )
    with pytest.raises(IncompatibleBadMoveContextError):
        identity.advance(bad)


def test_capture_must_bind_capturer_through_correspondence() -> None:
    position, identity = start("4k3/8/8/3p4/8/8/8/3RK3 w - - 0 1")
    delta = deltas.analyze(position, ChessMove("d1d5"))
    assert delta.capture is not None

    pairs = tuple(
        pair for pair in delta.piece_correspondence if pair.before != delta.capture.capturer_before
    )
    bad = replace(delta, piece_correspondence=pairs)

    with pytest.raises(IncompatibleBadMoveContextError, match="capturer"):
        identity.advance(bad)


def test_identity_map_constructor_rejects_conflicting_entries() -> None:
    base = base_ref(W, P, "e2")

    with pytest.raises(IncompatibleBadMoveContextError, match="position ids"):
        BasePieceIdentityMap("", "pos_current", ((base, ref(W, P, "e2")),))

    with pytest.raises(IncompatibleBadMoveContextError, match="color differs"):
        BasePieceIdentityMap(
            "pos_base",
            "pos_current",
            ((base, ref(B, P, "e2")),),
        )

    other = base_ref(W, N, "g1")
    current = ref(W, P, "e2")
    with pytest.raises(IncompatibleBadMoveContextError, match="same current piece"):
        BasePieceIdentityMap(
            "pos_base",
            "pos_current",
            ((base, current), (other, current)),
        )


def test_capture_of_same_color_fails_closed() -> None:
    position, identity = start("4k3/8/8/3p4/8/8/8/3RK3 w - - 0 1")
    delta = deltas.analyze(position, ChessMove("d1d5"))
    assert delta.capture is not None

    corrupted = replace(
        delta.capture,
        captured=ref(W, K, "e1"),
        captured_square="e1",
    )
    bad = replace(delta, capture=corrupted)

    with pytest.raises(IncompatibleBadMoveContextError, match="capturer's color"):
        identity.advance(bad)


def capture_delta():
    position, identity = start("4k3/8/8/3p4/8/8/8/3RK3 w - - 0 1")
    delta = deltas.analyze(position, ChessMove("d1d5"))
    assert delta.capture is not None
    return identity, delta


def test_captured_piece_must_be_live_and_not_survive() -> None:
    identity, delta = capture_delta()
    captured = delta.capture.captured

    survives = replace(
        delta,
        piece_correspondence=delta.piece_correspondence
        + (PieceCorrespondence(captured, ref(B, P, "d4")),),
    )
    with pytest.raises(IncompatibleBadMoveContextError, match="surviving correspondence"):
        identity.advance(survives)

    ghost = replace(
        delta,
        capture=replace(delta.capture, captured=ref(B, N, "d5")),
    )
    with pytest.raises(IncompatibleBadMoveContextError, match="not live"):
        identity.advance(ghost)


def test_capture_squares_must_be_coherent() -> None:
    identity, delta = capture_delta()

    wrong_square = replace(delta, capture=replace(delta.capture, captured_square="d6"))
    with pytest.raises(IncompatibleBadMoveContextError, match="captured_square"):
        identity.advance(wrong_square)

    wrong_landing = replace(delta, capture=replace(delta.capture, landing_square="d6"))
    with pytest.raises(IncompatibleBadMoveContextError, match="landing square"):
        identity.advance(wrong_landing)

    # An ordinary capture labelled en passant: captured on the landing square.
    fake_ep = replace(delta, capture=replace(delta.capture, is_en_passant=True))
    with pytest.raises(IncompatibleBadMoveContextError, match="en passant"):
        identity.advance(fake_ep)


def test_en_passant_label_must_match_squares_and_pawns() -> None:
    position, identity = start("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2")
    delta = deltas.analyze(position, rules.legal_move_from_uci(position, "e5d6"))
    assert delta.capture is not None and delta.capture.is_en_passant

    unlabelled = replace(delta, capture=replace(delta.capture, is_en_passant=False))
    with pytest.raises(IncompatibleBadMoveContextError, match="en passant"):
        identity.advance(unlabelled)


def test_duplicate_after_piece_and_empty_after_position_fail_closed() -> None:
    position, identity = start("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")
    delta = deltas.analyze(position, rules.legal_move_from_uci(position, "e2e4"))
    pairs = delta.piece_correspondence
    clash = tuple(
        PieceCorrespondence(p.before, pairs[0].after) if i == 1 else p for i, p in enumerate(pairs)
    )
    with pytest.raises(IncompatibleBadMoveContextError):
        identity.advance(replace(delta, piece_correspondence=clash))

    with pytest.raises(IncompatibleBadMoveContextError, match="after_position_id"):
        identity.advance(replace(delta, after_position_id=""))


def test_constructor_rejects_square_collisions_order_and_type_mismatch() -> None:
    pawn = base_ref(W, P, "e2")
    with pytest.raises(IncompatibleBadMoveContextError, match="one base square"):
        BasePieceIdentityMap(
            "pos_base", "pos_current", ((pawn, None), (base_ref(B, N, "e2"), None))
        )

    with pytest.raises(IncompatibleBadMoveContextError, match="same current square"):
        BasePieceIdentityMap(
            "pos_base",
            "pos_current",
            ((pawn, ref(W, P, "e4")), (base_ref(W, Q, "d1"), ref(W, Q, "e4"))),
        )

    with pytest.raises(IncompatibleBadMoveContextError, match="canonical"):
        BasePieceIdentityMap(
            "pos_base",
            "pos_current",
            ((pawn, ref(W, P, "e2")), (base_ref(W, Q, "d1"), ref(W, Q, "d1"))),
        )

    with pytest.raises(IncompatibleBadMoveContextError, match="incompatible"):
        BasePieceIdentityMap("pos_base", "pos_current", ((pawn, ref(W, K, "e8")),))
    with pytest.raises(IncompatibleBadMoveContextError, match="incompatible"):
        BasePieceIdentityMap("pos_base", "pos_current", ((base_ref(W, N, "g1"), ref(W, Q, "g1")),))
    with pytest.raises(IncompatibleBadMoveContextError, match="duplicate base"):
        BasePieceIdentityMap("pos_base", "pos_current", ((pawn, None), (pawn, None)))

    promoted = BasePieceIdentityMap("pos_base", "pos_current", ((pawn, ref(W, Q, "e8")),))
    assert promoted.current_piece(pawn) == ref(W, Q, "e8")


def test_branching_does_not_mutate_root_and_rejects_foreign_delta() -> None:
    base_position, root = start("4k3/8/8/3p4/8/8/4P3/4K3 w - - 0 1")
    snapshot = (root.position_id, root.base_pieces, root.live_pieces)

    _, actual, _ = step(base_position, root, "e2e4")
    _, comparator, comparator_delta = step(base_position, root, "e2e3")

    assert (root.position_id, root.base_pieces, root.live_pieces) == snapshot
    assert actual.base_position_id == comparator.base_position_id == root.position_id
    # A comparator-branch delta cannot be applied to the actual branch.
    with pytest.raises(IncompatibleBadMoveContextError, match="does not continue"):
        actual.advance(comparator_delta)
    assert root.advance_all(()) == root
