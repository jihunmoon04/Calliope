import random
from dataclasses import fields, replace

import chess
import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.application.ports.tactics import AbsolutePinObservation
from calliope.domain.analysis.activity import (
    AttackFootprintChange,
    AttackTargetKind,
    RayChange,
)
from calliope.domain.chess import ChessMove, Color, LegalCapture, PieceRef, PieceType
from calliope.errors import (
    IllegalMoveError,
    IncompatibleBoardDeltaError,
    IncompatiblePositionObservationError,
    IncompatibleTacticalContextError,
)
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import (
    ActivityAnalyzer,
    ActivityLineAnalyzer,
    ActivityTransitionAnalyzer,
)
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer

START = chess.STARTING_FEN
W, B = Color.WHITE, Color.BLACK


class CountingTactics:
    """Delegate to the adapter, optionally rewriting its observation, and count calls."""

    def __init__(self, rules, rewrite=None):
        self.rules, self.rewrite, self.calls = rules, rewrite, 0

    def observe_tactics(self, position):
        self.calls += 1
        observation = self.rules.observe_tactics(position)
        return self.rewrite(observation) if self.rewrite else observation


def build(rewrite=None):
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    transitions = TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))
    tactics = CountingTactics(rules, rewrite)
    activity = ActivityAnalyzer(positions, tactics)
    return (
        rules,
        activity,
        ActivityTransitionAnalyzer(transitions, activity),
        ActivityLineAnalyzer(LineAnalyzer(transitions), activity),
        tactics,
    )


@pytest.fixture
def services():
    return build()


def piece_at(result, square):
    return next(p for p in result.activity.pieces if p.piece.square == square)


def square_at(result, square):
    return next(s for s in result.activity.squares if s.square == square)


def ray(result, square, direction):
    return next(
        r for r in result.activity.rays if r.source.square == square and r.direction == direction
    )


def ucis(moves):
    return tuple(m.uci for m in moves)


def test_pinned_attacker_keeps_geometry_without_legal_capture(services):
    rules, activity, *_ = services
    result = activity.analyze(rules.position_from_fen("4r1k1/8/8/8/3p4/8/4N3/4K3 w - - 0 1"))
    knight = piece_at(result, "e2")
    assert knight.enemy_attacks == ("d4",)
    assert knight.legal_moves_now == () and knight.legal_captures_now == ()
    assert knight.legal_destinations_now == ()
    assert knight.piece in square_at(result, "d4").white_attackers
    assert square_at(result, "d4").current_legal_captures == ()
    (pin,) = result.activity.absolute_pins
    assert (pin.pinner.square, pin.pinned.square, pin.king.square) == ("e8", "e2", "e1")
    assert ray(result, "e8", (0, -1)).occupants[:2] == (pin.pinned, pin.king)


def test_in_check_piece_keeps_geometry_but_lists_only_legal_responses(services):
    rules, activity, *_ = services
    result = activity.analyze(rules.position_from_fen("4r1k1/8/8/8/8/R7/8/4K3 w - - 0 1"))
    rook = piece_at(result, "a3")
    assert rook.geometric_attack_count == 14
    assert ucis(rook.legal_moves_now) == ("a3e3",)
    assert rook.legal_destinations_now == ("e3",)


def test_friendly_and_enemy_first_blockers_bound_visibility(services):
    rules, activity, *_ = services
    friendly = activity.analyze(rules.position_from_fen("4k3/8/8/p7/8/P7/8/R3K3 w - - 0 1"))
    file_ray = ray(friendly, "a1", (0, 1))
    assert [p.square for p in file_ray.occupants] == ["a3", "a5"]
    assert file_ray.first_blocker.color is W
    assert file_ray.visible_squares == ("a2", "a3")
    assert "a4" not in piece_at(friendly, "a1").footprint
    assert piece_at(friendly, "a1").piece not in square_at(friendly, "a4").white_attackers
    assert piece_at(friendly, "a1").friendly_attacks == ("e1", "a3")

    enemy = activity.analyze(rules.position_from_fen("4k3/8/8/p7/8/8/8/R3K3 w - - 0 1"))
    enemy_ray = ray(enemy, "a1", (0, 1))
    assert enemy_ray.first_blocker.color is B
    assert enemy_ray.visible_squares == ("a2", "a3", "a4", "a5")
    assert enemy_ray.squares[-1] == "a8" and "a6" not in piece_at(enemy, "a1").footprint


def test_nearest_blocker_moving_exposes_only_up_to_second_blocker(services):
    rules, _, transitions, *_ = services
    step = transitions.analyze(
        rules.position_from_fen("4k3/p7/8/8/8/N7/8/R3K3 w - - 0 1"), ChessMove("a3b5")
    )
    change = next(
        c
        for c in step.ray_changes
        if c.before and c.before.source.square == "a1" and c.direction == (0, 1)
    )
    assert change.added_visible == ("a4", "a5", "a6", "a7")
    assert change.removed_visible == ()
    assert change.blockers_changed
    assert change.after.visible_squares[-1] == "a7"
    assert "a8" not in piece_at(step.after_activity, "a1").footprint


def test_relocated_blocker_is_not_reported_as_a_new_piece(services):
    rules, _, transitions, *_ = services
    # The c1 bishop's nearest blocker slides further along the same (1, 1) ray.
    step = transitions.analyze(
        rules.position_from_fen("4k3/8/8/8/8/8/3B4/2B1K3 w - - 0 1"), ChessMove("d2e3")
    )
    change = next(
        c for c in step.ray_changes if c.before.source.square == "c1" and c.direction == (1, 1)
    )
    assert change.before.occupants != change.after.occupants  # raw PieceRefs differ
    assert change.added_visible == ("e3",) and not change.blockers_changed
    # A blocker leaving the ray is a blocker-sequence change.
    step = transitions.analyze(
        rules.position_from_fen("4k3/8/8/8/8/8/3N4/2B1K3 w - - 0 1"), ChessMove("d2f3")
    )
    change = next(
        c for c in step.ray_changes if c.before.source.square == "c1" and c.direction == (1, 1)
    )
    assert change.blockers_changed and change.after.occupants == ()


def test_edge_empty_and_unblocked_rays_are_distinct(services):
    rules, activity, *_ = services
    result = activity.analyze(rules.position_from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 0 1"))
    assert ray(result, "a1", (-1, 0)).edge_empty and ray(result, "a1", (0, -1)).edge_empty
    clear = ray(result, "a1", (0, 1))
    assert clear.unblocked and not clear.edge_empty and len(clear.squares) == 7
    assert clear.first_blocker is None and ray(result, "a1", (-1, 0)).first_blocker is None
    assert ray(result, "a1", (1, 0)).first_blocker.piece_type is PieceType.KING
    assert [r.direction for r in result.activity.rays if r.source.square == "a1"] == [
        (-1, 0),
        (0, -1),
        (0, 1),
        (1, 0),
    ]


def test_knights_and_pawns_have_footprints_but_no_rays(services):
    rules, activity, *_ = services
    result = activity.analyze(rules.position_from_fen(START))
    assert len(result.activity.rays) == 4 * 4 + 4 * 4 + 2 * 8
    assert {r.source.piece_type for r in result.activity.rays} == {
        PieceType.BISHOP,
        PieceType.ROOK,
        PieceType.QUEEN,
    }
    assert piece_at(result, "b1").footprint == ("d2", "a3", "c3")
    assert piece_at(result, "b1").friendly_attacks == ("d2",)
    assert piece_at(result, "e2").footprint == ("d3", "f3")


def test_pawn_advances_and_castling_lie_outside_the_footprint(services):
    rules, activity, *_ = services
    start = activity.analyze(rules.position_from_fen(START))
    pawn = piece_at(start, "e2")
    assert pawn.legal_destinations_now == ("e3", "e4")
    assert not set(pawn.legal_destinations_now) & set(pawn.footprint)
    castle = activity.analyze(rules.position_from_fen("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1"))
    king = piece_at(castle, "e1")
    assert {"g1", "c1"} <= set(king.legal_destinations_now)
    assert not {"g1", "c1"} & set(king.footprint)
    assert ucis(king.legal_moves_now).count("e1g1") == 1
    assert "e1h1" not in ucis(king.legal_moves_now)
    assert all("e1" not in u[2:] for u in ucis(piece_at(castle, "h1").legal_moves_now))


def test_castling_is_one_king_action_with_both_physical_moves(services):
    rules, _, transitions, *_ = services
    step = transitions.analyze(
        rules.position_from_fen("4k3/8/8/8/8/8/8/4K2R w K - 0 1"), ChessMove("e1g1")
    )
    assert len(step.structural.board_delta.transitions) == 2
    sources = {c.before.source.square for c in step.ray_changes}
    assert sources == {"h1"}
    assert {c.after.source.square for c in step.ray_changes} == {"f1"}


def test_promotion_choices_share_one_destination_and_add_queen_rays(services):
    rules, activity, transitions, *_ = services
    position = rules.position_from_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    pawn = piece_at(activity.analyze(position), "a7")
    assert ucis(pawn.legal_moves_now) == ("a7a8b", "a7a8n", "a7a8q", "a7a8r")
    assert pawn.legal_move_count_now == 4 and pawn.legal_destinations_now == ("a8",)
    step = transitions.analyze(position, ChessMove("a7a8q"))
    assert all(c.before is None for c in step.ray_changes)
    assert len(step.ray_changes) == 8
    assert {c.after.source.piece_type for c in step.ray_changes} == {PieceType.QUEEN}
    (pawn_change,) = [c for c in step.attack_footprint_changes if c.before.square == "a7"]
    assert pawn_change.after.piece_type is PieceType.QUEEN


def test_en_passant_uses_actual_victim_square(services):
    rules, activity, transitions, *_ = services
    position = rules.position_from_fen("k7/8/8/3Pp3/8/8/8/K3R3 w - e6 0 1")
    landing = square_at(activity.analyze(position), "e6")
    (capture,) = landing.current_legal_captures
    assert landing.occupant is None
    assert capture.is_en_passant and capture.captured_square == "e5"
    step = transitions.analyze(position, ChessMove("d5e6"))
    file_ray = next(c for c in step.ray_changes if c.before.source.square == "e1")
    assert file_ray.added_visible == ("e6",) and file_ray.blockers_changed
    assert [p.square for p in file_ray.after.occupants] == ["e6"]
    captured = next(c for c in step.attack_footprint_changes if c.before.square == "e5")
    assert captured.after is None and captured.added_targets == ()


def test_snapshot_ep_field_without_ep_action_creates_no_capture(services):
    rules, activity, *_ = services
    position = rules.apply_move(rules.position_from_fen(START), ChessMove("e2e4"))
    assert position.en_passant_square == "e3"
    result = activity.analyze(position)
    assert square_at(result, "e3").current_legal_captures == ()
    assert all(p.legal_captures_now in (None, ()) for p in result.activity.pieces)


def test_side_flip_leaves_opponent_legal_fields_unobserved(services):
    rules, _, transitions, *_ = services
    step = transitions.analyze(rules.position_from_fen(START), ChessMove("e2e4"))
    for frame, mover in ((step.before_activity, W), (step.after_activity, B)):
        for activity in frame.activity.pieces:
            observed = activity.legal_moves_now is not None
            assert observed is (activity.piece.color is mover)
            if not observed:
                assert activity.legal_destinations_now is None
                assert activity.legal_move_count_now is None
    change_fields = {f.name for f in fields(AttackFootprintChange)} | {
        f.name for f in fields(RayChange)
    }
    assert not any("legal" in name or "mobility" in name for name in change_fields)


def test_same_count_changed_targets_are_recorded(services):
    rules, _, transitions, *_ = services
    step = transitions.analyze(
        rules.position_from_fen("k7/8/8/8/3R4/8/8/7K w - - 0 1"), ChessMove("d4e4")
    )
    before, after = piece_at(step.before_activity, "d4"), piece_at(step.after_activity, "e4")
    assert before.geometric_attack_count == after.geometric_attack_count == 14
    (change,) = [c for c in step.attack_footprint_changes if c.before.square == "d4"]
    assert "e1" in change.added_targets and "d1" in change.removed_targets
    assert len(change.added_targets) == len(change.removed_targets)


def test_occupancy_class_change_is_separate_from_target_change(services):
    rules, _, transitions, *_ = services
    # Black pawn steps into the white rook's existing visible square: d6 stays a target.
    step = transitions.analyze(
        rules.position_from_fen("4k3/3p4/8/8/8/8/8/3RK3 b - - 0 1"), ChessMove("d7d6")
    )
    (change,) = [c for c in step.attack_footprint_changes if c.before.square == "d1"]
    assert change.removed_targets == ("d7",) and change.added_targets == ()
    assert [(o.square, o.before, o.after) for o in change.occupancy_changes] == [
        ("d6", AttackTargetKind.EMPTY, AttackTargetKind.ENEMY)
    ]


def test_same_type_identity_permutation_rejected_before_activity(monkeypatch):
    rules, _, transitions, lines, tactics = build()
    original = BoardDeltaAnalyzer.analyze

    def swapped(self, before, move):
        delta = original(self, before, move)
        pairs = {p.before.square: p for p in delta.piece_correspondence}
        a2, h2 = pairs["a2"], pairs["h2"]
        return replace(
            delta,
            piece_correspondence=tuple(
                replace(p, after=h2.after)
                if p is a2
                else replace(p, after=a2.after)
                if p is h2
                else p
                for p in delta.piece_correspondence
            ),
        )

    monkeypatch.setattr(BoardDeltaAnalyzer, "analyze", swapped)
    with pytest.raises(IncompatibleBoardDeltaError):
        transitions.analyze(rules.position_from_fen(START), ChessMove("e2e4"))
    with pytest.raises(IncompatibleBoardDeltaError):
        lines.analyze(rules.position_from_fen(START), (ChessMove("e2e4"),))
    assert tactics.calls == 0


def _mirror_square(square):
    return square[0] + str(9 - int(square[1]))


def _mirror_piece(piece):
    return PieceRef(piece.color.opposite, piece.piece_type, _mirror_square(piece.square))


@pytest.mark.parametrize("seed", range(4))
def test_color_rank_mirror_maps_geometry_and_side_context(services, seed):
    rules, activity, *_ = services
    rng, board = random.Random(seed), chess.Board()
    for _ in range(24):
        board.push(rng.choice(list(board.legal_moves)))
    original = activity.analyze(rules.position_from_fen(board.fen()))
    mirrored = activity.analyze(rules.position_from_fen(board.mirror().fen()))
    assert mirrored.activity.side_to_move is original.activity.side_to_move.opposite
    rays = {(r.source, r.direction): r for r in mirrored.activity.rays}
    for r in original.activity.rays:
        m = rays[_mirror_piece(r.source), (r.direction[0], -r.direction[1])]
        assert m.squares == tuple(map(_mirror_square, r.squares))
        assert m.occupants == tuple(map(_mirror_piece, r.occupants))
    assert len(rays) == len(original.activity.rays)
    pieces = {p.piece: p for p in mirrored.activity.pieces}
    for p in original.activity.pieces:
        m = pieces[_mirror_piece(p.piece)]
        assert set(m.footprint) == set(map(_mirror_square, p.footprint))
        assert set(m.enemy_attacks) == set(map(_mirror_square, p.enemy_attacks))
        if p.legal_destinations_now is None:
            assert m.legal_destinations_now is None
        else:
            assert set(m.legal_destinations_now) == set(
                map(_mirror_square, p.legal_destinations_now)
            )


def _rewrite(**changes):
    return lambda observation: replace(observation, **changes)


EP_FEN = "k7/8/8/3Pp3/8/8/8/K3R3 w - e6 0 1"


@pytest.mark.parametrize(
    "rewrite",
    [
        pytest.param(_rewrite(position_id="pos_wrong"), id="wrong-id"),
        pytest.param(_rewrite(side_to_move=B), id="wrong-side"),
        pytest.param(
            lambda o: replace(o, legal_moves=o.legal_moves + o.legal_moves[:1]), id="duplicate"
        ),
        pytest.param(lambda o: replace(o, legal_moves=o.legal_moves[::-1]), id="unsorted"),
        pytest.param(
            lambda o: replace(o, legal_moves=tuple(m for m in o.legal_moves if m.uci != "d5e6")),
            id="missing-p4-capture",
        ),
        pytest.param(
            lambda o: replace(
                o,
                legal_moves=tuple(
                    sorted(o.legal_moves + (ChessMove("a8b8"),), key=lambda m: m.uci)
                ),
            ),
            id="opponent-source",
        ),
        pytest.param(
            lambda o: replace(
                o,
                legal_moves=tuple(
                    sorted(o.legal_moves + (ChessMove("d5d6q"),), key=lambda m: m.uci)
                ),
            ),
            id="bogus-promotion-suffix",
        ),
        pytest.param(
            lambda o: replace(
                o,
                legal_moves=tuple(
                    sorted(o.legal_moves + (ChessMove("E1E2"),), key=lambda m: m.uci)
                ),
            ),
            id="non-canonical-uci",
        ),
    ],
)
def test_incompatible_tactical_observation_is_refused(rewrite):
    rules, activity, *_ = build(rewrite)
    with pytest.raises(IncompatibleTacticalContextError):
        activity.analyze(rules.position_from_fen(EP_FEN))


def test_missing_promotion_suffix_is_refused():
    def add(o):
        return replace(
            o, legal_moves=tuple(sorted(o.legal_moves + (ChessMove("a7a8"),), key=lambda m: m.uci))
        )

    rules, activity, *_ = build(add)
    with pytest.raises(IncompatibleTacticalContextError):
        activity.analyze(rules.position_from_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1"))


def test_san_differences_alone_are_accepted():
    rules, activity, *_ = build(
        lambda o: replace(o, legal_moves=tuple(ChessMove(m.uci) for m in o.legal_moves))
    )
    result = activity.analyze(rules.position_from_fen(EP_FEN))
    assert [c.move.uci for c in piece_at(result, "d5").legal_captures_now] == ["d5e6"]
    assert piece_at(result, "d5").legal_moves_now[0].san is None


@pytest.mark.parametrize(
    "damage",
    ["drop-all", "wrong-victim", "ep-flag-on-normal", "wrong-capturer"],
)
def test_p4_capture_mismatch_is_refused(services, damage):
    rules, activity, *_ = services
    fen = "4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1"
    structural = activity.positions.analyze(rules.position_from_fen(fen))
    (capture,) = structural.facts.legal_captures
    if damage == "drop-all":
        captures = ()
    elif damage == "wrong-victim":
        captures = (replace(capture, captured=PieceRef(B, PieceType.QUEEN, "d5")),)
    elif damage == "ep-flag-on-normal":
        captures = (
            LegalCapture(
                capture.move, capture.capturer, PieceRef(B, PieceType.PAWN, "d4"), "d5", "d4", True
            ),
        )
    else:
        captures = (replace(capture, capturer=PieceRef(W, PieceType.KNIGHT, "e4")),)
    broken = replace(structural, facts=replace(structural.facts, legal_captures=captures))
    with pytest.raises(IncompatibleTacticalContextError):
        activity._from_position_analysis(broken)


def test_ray_disagreeing_with_p4_attacks_is_refused(services):
    rules, activity, *_ = services
    structural = activity.positions.analyze(
        rules.position_from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    )
    facts = structural.facts
    attacks = tuple(
        a for a in facts.attacks if (a.attacker.square, a.target_square) != ("a1", "a8")
    )
    pieces = tuple(
        replace(s, attacks=tuple(t for t in s.attacks if t != "a8"))
        if s.piece.square == "a1"
        else s
        for s in facts.pieces
    )
    broken = replace(structural, facts=replace(facts, attacks=attacks, pieces=pieces))
    with pytest.raises(IncompatiblePositionObservationError):
        activity._from_position_analysis(broken)


PIN_FEN = "4r1k1/8/8/8/3p4/8/P3N3/4K3 w - - 0 1"


@pytest.mark.parametrize(
    "damage", ["wrong-pinned", "swapped-order", "non-slider-pinner", "off-board"]
)
def test_malformed_pins_are_refused(damage):
    def rewrite(o):
        (pin,) = o.absolute_pins
        if damage == "wrong-pinned":
            bad = replace(pin, pinned=PieceRef(W, PieceType.PAWN, "a2"))
        elif damage == "swapped-order":
            bad = AbsolutePinObservation(pin.pinner, pin.king, pin.pinned)
        elif damage == "non-slider-pinner":
            bad = replace(pin, pinner=PieceRef(B, PieceType.KING, "g8"))
        else:
            bad = replace(pin, pinner=PieceRef(B, PieceType.ROOK, "e7"))
        return replace(o, absolute_pins=(bad,))

    rules, activity, *_ = build(rewrite)
    with pytest.raises((IncompatibleTacticalContextError, IncompatiblePositionObservationError)):
        activity.analyze(rules.position_from_fen(PIN_FEN))


def test_line_frames_and_steps_bind_without_second_replay(monkeypatch):
    rules, _, _, lines, tactics = build()
    counts = {"observe_position": 0, "transition": 0}
    observe, transition = PythonChessAdapter.observe_position, TransitionAnalyzer.analyze

    def counted_observe(self, position):
        counts["observe_position"] += 1
        return observe(self, position)

    def counted_transition(self, before, move):
        counts["transition"] += 1
        return transition(self, before, move)

    monkeypatch.setattr(PythonChessAdapter, "observe_position", counted_observe)
    monkeypatch.setattr(TransitionAnalyzer, "analyze", counted_transition)
    moves = tuple(ChessMove(m) for m in ("e2e4", "d7d5", "e4d5", "d8d5", "b1c3"))
    initial = rules.position_from_fen(START)
    structural_only = LineAnalyzer(lines.lines.transitions).analyze(initial, moves)
    baseline = dict(counts)
    result = lines.analyze(initial, moves)
    assert counts["transition"] - baseline["transition"] == len(moves)
    assert counts["observe_position"] - baseline["observe_position"] == baseline["observe_position"]
    assert tactics.calls == len(moves) + 1
    assert len(result.activity_frames) == len(moves) + 1
    assert len(result.activity_transitions) == len(moves)
    assert [f.activity.position_id for f in result.activity_frames] == [
        structural_only.initial.position.position_id,
        *(t.after.position.position_id for t in structural_only.transitions),
    ]
    for i, step in enumerate(result.activity_transitions):
        assert step.before_activity is result.activity_frames[i]
        assert step.after_activity is result.activity_frames[i + 1]


def test_line_limit_rejected_before_activity_observation():
    def fail(_):
        raise AssertionError("activity must not be observed")

    rules, _, _, lines, tactics = build(fail)
    with pytest.raises(ValueError):
        lines.analyze(rules.position_from_fen(START), (ChessMove("e2e4"),) * 65)
    with pytest.raises(ValueError):
        lines.analyze(rules.position_from_fen(START), (ChessMove("e2e4"),) * 2, max_plies=1)
    assert tactics.calls == 0


def test_illegal_later_move_returns_no_partial_activity(services):
    rules, _, _, lines, _ = services
    with pytest.raises(IllegalMoveError):
        lines.analyze(rules.position_from_fen(START), (ChessMove("e2e4"), ChessMove("e2e4")))


@pytest.mark.parametrize("seed", range(6))
def test_random_legal_lines_keep_ray_p4_agreement_and_frame_binding(services, seed):
    rules, _, _, lines, _ = services
    rng, board, moves = random.Random(seed), chess.Board(), []
    while len(moves) < 32 and not board.is_game_over():
        move = rng.choice(list(board.legal_moves))
        moves.append(move.uci())
        board.push(move)
    result = lines.analyze(rules.position_from_fen(START), tuple(ChessMove(m) for m in moves))
    final = result.activity_frames[-1]
    replay = chess.Board()
    for m in moves:
        replay.push_uci(m)
    for activity in final.activity.pieces:
        square = chess.parse_square(activity.piece.square)
        assert set(activity.footprint) == {chess.square_name(s) for s in replay.attacks(square)}
        if activity.legal_moves_now is not None:
            assert set(ucis(activity.legal_moves_now)) == {
                m.uci() for m in replay.legal_moves if m.from_square == square
            }


def test_pin_behind_another_blocker_is_refused_by_ray_order():
    # e-file: e8 rook, e4 pawn, e2 knight, e1 king. The knight is not absolutely pinned.
    fen = "4r1k1/8/8/8/4P3/8/4N3/4K3 w - - 0 1"

    def fake_pin(o):
        assert o.absolute_pins == ()
        pin = AbsolutePinObservation(
            PieceRef(B, PieceType.ROOK, "e8"),
            PieceRef(W, PieceType.KNIGHT, "e2"),
            PieceRef(W, PieceType.KING, "e1"),
        )
        return replace(o, absolute_pins=(pin,))

    rules, activity, *_ = build(fake_pin)
    with pytest.raises(IncompatiblePositionObservationError, match="ray occupants"):
        activity.analyze(rules.position_from_fen(fen))
