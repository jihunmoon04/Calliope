from dataclasses import replace

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis.activity import (
    ActivityLineAnalysis,
    ActivityPositionAnalysis,
    ActivityTransitionAnalysis,
    AttackFootprintChange,
    AttackTargetKind,
    PieceActivity,
    RayChange,
    SliderRay,
    SquareAccess,
    TargetOccupancyChange,
    ray_path,
)
from calliope.domain.chess import ChessMove, Color, PieceRef, PieceType
from calliope.errors import IncompatiblePositionObservationError
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import (
    ActivityAnalyzer,
    ActivityLineAnalyzer,
    ActivityTransitionAnalyzer,
)
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer

W, B = Color.WHITE, Color.BLACK
ROOK = PieceRef(W, PieceType.ROOK, "a1")
Bad = IncompatiblePositionObservationError


def p(color, kind, square):
    return PieceRef(color, kind, square)


@pytest.fixture(scope="module")
def analyzers():
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    transitions = TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))
    activity = ActivityAnalyzer(positions, rules)
    return (
        rules,
        activity,
        ActivityTransitionAnalyzer(transitions, activity),
        ActivityLineAnalyzer(LineAnalyzer(transitions), activity),
    )


def test_ray_path_is_near_to_far_and_excludes_source():
    assert ray_path("a1", (1, 1)) == ("b2", "c3", "d4", "e5", "f6", "g7", "h8")
    assert ray_path("a1", (-1, 0)) == ()
    assert ray_path("d4", (0, -1)) == ("d3", "d2", "d1")


def test_valid_ray_derives_blocker_and_visibility():
    ray = SliderRay(
        ROOK,
        (0, 1),
        ray_path("a1", (0, 1)),
        (p(W, PieceType.PAWN, "a3"), p(B, PieceType.PAWN, "a6")),
    )
    assert ray.first_blocker.square == "a3"
    assert ray.visible_squares == ("a2", "a3")
    assert not ray.unblocked and not ray.edge_empty


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"source": p(W, PieceType.KNIGHT, "a1")}, id="non-slider"),
        pytest.param({"direction": (1, 1)}, id="rook-diagonal"),
        pytest.param({"direction": (0, 2)}, id="non-unit"),
        pytest.param({"squares": ("a2", "a3")}, id="truncated-path"),
        pytest.param({"squares": tuple(reversed(ray_path("a1", (0, 1))))}, id="far-to-near"),
        pytest.param({"occupants": (p(B, PieceType.PAWN, "b3"),)}, id="occupant-off-ray"),
        pytest.param(
            {"occupants": (p(B, PieceType.PAWN, "a6"), p(W, PieceType.PAWN, "a3"))},
            id="occupants-out-of-order",
        ),
        pytest.param(
            {"occupants": (p(W, PieceType.PAWN, "a3"), p(W, PieceType.PAWN, "a3"))},
            id="duplicate-occupant",
        ),
    ],
)
def test_malformed_ray_is_refused(kwargs):
    base = {"source": ROOK, "direction": (0, 1), "squares": ray_path("a1", (0, 1)), "occupants": ()}
    with pytest.raises(Bad):
        SliderRay(**{**base, **kwargs})


def activity(**kwargs):
    base = {
        "piece": ROOK,
        "footprint": ("b1", "a2"),
        "empty_attacks": ("a2",),
        "friendly_attacks": ("b1",),
        "enemy_attacks": (),
        "legal_moves_now": (ChessMove("a1a2"),),
        "legal_captures_now": (),
    }
    return PieceActivity(**{**base, **kwargs})


def test_piece_activity_counts_and_destinations_are_derived():
    moves = tuple(ChessMove(u) for u in ("a7a8b", "a7a8n", "a7a8q", "a7a8r"))
    pawn = PieceActivity(p(W, PieceType.PAWN, "a7"), ("b8",), ("b8",), (), (), moves, ())
    assert pawn.legal_move_count_now == 4 and pawn.legal_destinations_now == ("a8",)
    assert pawn.geometric_attack_count == 1
    unobserved = activity(legal_moves_now=None, legal_captures_now=None)
    assert unobserved.legal_destinations_now is None and unobserved.legal_capture_count_now is None


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"footprint": ("a2", "b1")}, id="unsorted-footprint"),
        pytest.param({"friendly_attacks": ("a2", "b1"), "empty_attacks": ("a2",)}, id="overlap"),
        pytest.param({"friendly_attacks": ()}, id="missing-partition"),
        pytest.param({"enemy_attacks": ("c1",)}, id="partition-outside-footprint"),
        pytest.param(
            {"footprint": ("a1", "b1", "a2"), "empty_attacks": ("a1", "a2")}, id="own-square"
        ),
        pytest.param({"legal_moves_now": (ChessMove("b1b2"),)}, id="move-from-other-square"),
        pytest.param({"legal_moves_now": (ChessMove("a1a2"),) * 2}, id="duplicate-move"),
        pytest.param({"legal_captures_now": None}, id="half-observed"),
    ],
)
def test_malformed_piece_activity_is_refused(kwargs):
    with pytest.raises(Bad):
        activity(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"occupant": p(W, PieceType.PAWN, "e5")}, id="occupant-elsewhere"),
        pytest.param({"white_attackers": (p(B, PieceType.ROOK, "e1"),)}, id="wrong-color"),
        pytest.param({"white_attackers": (p(W, PieceType.ROOK, "e4"),)}, id="attacker-on-square"),
        pytest.param(
            {"white_attackers": (p(W, PieceType.ROOK, "e8"), p(W, PieceType.ROOK, "e1"))},
            id="unsorted-attackers",
        ),
    ],
)
def test_malformed_square_access_is_refused(kwargs):
    base = {
        "square": "e4",
        "occupant": None,
        "white_attackers": (),
        "black_attackers": (),
        "current_legal_captures": (),
    }
    with pytest.raises(Bad):
        SquareAccess(**{**base, **kwargs})


def test_square_capture_must_land_on_its_square(analyzers):
    rules, analyzer, *_ = analyzers
    result = analyzer.analyze(rules.position_from_fen("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1"))
    (capture,) = result.activity.source_facts.legal_captures
    with pytest.raises(Bad):
        SquareAccess("e5", None, (), (), (capture,))


def _replace_item(items, index, **changes):
    return items[:index] + (replace(items[index], **changes),) + items[index + 1 :]


@pytest.mark.parametrize(
    "damage",
    [
        "version",
        "position-id",
        "square",
        "piece-geometry",
        "opponent-legal",
        "mover-unobserved",
        "piece-capture",
        "ray",
        "missing-ray",
        "missing-piece",
    ],
)
def test_activity_facts_must_agree_with_source_anchor(analyzers, damage):
    rules, analyzer, *_ = analyzers
    facts = analyzer.analyze(rules.position_from_fen("4k3/8/8/3p4/4P3/8/8/R3K3 w - - 0 1")).activity
    white = next(i for i, a in enumerate(facts.pieces) if a.piece.square == "e4")
    black = next(i for i, a in enumerate(facts.pieces) if a.piece.color is B)
    pieces, rays = facts.pieces, facts.rays

    def damaged():
        if damage == "version":
            return replace(facts, definition_version="activity_v0")
        if damage == "position-id":
            return replace(facts, position_id="pos_other")
        if damage == "square":
            king = p(B, PieceType.KING, "e8")
            return replace(facts, squares=_replace_item(facts.squares, 0, black_attackers=(king,)))
        if damage == "piece-geometry":
            return replace(
                facts, pieces=_replace_item(pieces, white, footprint=("d5",), enemy_attacks=("d5",))
            )
        if damage == "opponent-legal":
            return replace(
                facts,
                pieces=_replace_item(pieces, black, legal_moves_now=(), legal_captures_now=()),
            )
        if damage == "mover-unobserved":
            return replace(
                facts,
                pieces=_replace_item(pieces, white, legal_moves_now=None, legal_captures_now=None),
            )
        if damage == "piece-capture":
            return replace(facts, pieces=_replace_item(pieces, white, legal_captures_now=()))
        if damage == "ray":
            blocked = next(i for i, r in enumerate(rays) if r.occupants)
            return replace(facts, rays=_replace_item(rays, blocked, occupants=()))
        if damage == "missing-ray":
            return replace(facts, rays=rays[1:])
        return replace(facts, pieces=pieces[1:])

    with pytest.raises(Bad):
        damaged()


def test_wrapper_records_bind_frames(analyzers):
    rules, analyzer, transitions, lines = analyzers
    start = rules.position_from_fen("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")
    frame = analyzer.analyze(start)
    other = analyzer.analyze(rules.position_from_fen("4k3/8/8/8/8/8/3P4/4K3 w - - 0 1"))
    with pytest.raises(Bad):
        ActivityPositionAnalysis(other.structural, frame.activity)
    with pytest.raises(Bad):
        replace(frame, activity=replace(frame.activity, side_to_move=B))

    step = transitions.analyze(start, ChessMove("e2e4"))
    with pytest.raises(Bad):
        ActivityTransitionAnalysis(
            step.structural, step.after_activity, step.before_activity, (), ()
        )

    line = lines.analyze(start, (ChessMove("e2e4"), ChessMove("e8d8")))
    with pytest.raises(Bad):
        ActivityLineAnalysis(line.structural, line.activity_frames[:-1], line.activity_transitions)
    with pytest.raises(Bad):
        ActivityLineAnalysis(line.structural, line.activity_frames, line.activity_transitions[::-1])
    with pytest.raises(Bad):
        ActivityLineAnalysis(line.structural, line.activity_frames[::-1], line.activity_transitions)


PAWN = PieceRef(W, PieceType.PAWN, "e2")


@pytest.mark.parametrize(
    ("piece", "uci"),
    [
        pytest.param(PAWN, "e2zz", id="invalid-target"),
        pytest.param(PAWN, "e2e2", id="same-square"),
        pytest.param(PAWN, "e2e4q", id="suffix-without-last-rank"),
        pytest.param(PAWN, "E2E4", id="uppercase"),
        pytest.param(PAWN, "e2e4 ", id="trailing-space"),
        pytest.param(p(W, PieceType.PAWN, "a7"), "a7a8", id="missing-promotion-suffix"),
        pytest.param(p(B, PieceType.PAWN, "a2"), "a2a1k", id="king-promotion"),
        pytest.param(ROOK, "a1a8q", id="non-pawn-suffix"),
    ],
)
def test_piece_activity_refuses_structurally_invalid_uci(piece, uci):
    with pytest.raises(Bad):
        PieceActivity(piece, (), (), (), (), (ChessMove(uci),), ())


def test_structurally_valid_promotions_and_castling_are_accepted():
    black_pawn = p(B, PieceType.PAWN, "b2")
    moves = tuple(ChessMove(u) for u in ("b2a1q", "b2b1n"))
    assert PieceActivity(black_pawn, (), (), (), (), moves, ()).legal_destinations_now == (
        "a1",
        "b1",
    )
    king = p(W, PieceType.KING, "e1")
    castle = PieceActivity(king, (), (), (), (), (ChessMove("e1g1"),), ())
    assert castle.legal_destinations_now == ("g1",)


def test_invalid_uci_cannot_reach_activity_facts(analyzers):
    rules, analyzer, *_ = analyzers
    facts = analyzer.analyze(rules.position_from_fen("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")).activity
    pawn = next(i for i, a in enumerate(facts.pieces) if a.piece.square == "e2")
    for uci in ("e2zz", "e2e2", "e2e4q"):
        with pytest.raises(Bad):
            replace(
                facts, pieces=_replace_item(facts.pieces, pawn, legal_moves_now=(ChessMove(uci),))
            )


@pytest.mark.parametrize("square", ["z9", "e44", "", None, 4])
def test_invalid_squares_raise_the_contract_error(square):
    with pytest.raises(Bad):
        SquareAccess(square, None, (), (), ())
    with pytest.raises(Bad):
        PieceActivity(ROOK, (square,), (square,), (), (), None, None)
    with pytest.raises(Bad):
        TargetOccupancyChange(square, AttackTargetKind.EMPTY, AttackTargetKind.ENEMY)
    with pytest.raises(Bad):
        AttackFootprintChange(ROOK, None, (square,), (), ())
    with pytest.raises(Bad):
        RayChange((0, 1), None, None, (), (square,), True)


def test_change_records_refuse_non_canonical_or_empty_changes():
    with pytest.raises(Bad):
        TargetOccupancyChange("e4", AttackTargetKind.EMPTY, AttackTargetKind.EMPTY)
    with pytest.raises(Bad):
        AttackFootprintChange(ROOK, None, ("a2", "b1"), (), ())


def test_invalid_capture_landing_in_source_facts_raises_the_contract_error(analyzers):
    rules, analyzer, *_ = analyzers
    frame = analyzer.analyze(rules.position_from_fen("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1"))
    facts = frame.activity.source_facts
    (capture,) = facts.legal_captures
    broken = replace(capture, landing_square="z9", is_en_passant=True)
    with pytest.raises(Bad):
        replace(frame.activity, source_facts=replace(facts, legal_captures=(broken,)))
