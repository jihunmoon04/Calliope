import random
from dataclasses import replace

import chess
import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.analysis import MaterialChange, PieceTransitionKind
from calliope.domain.analysis.positional import LineEndKind
from calliope.domain.chess import ChessMove, Color, PieceType
from calliope.errors import IllegalMoveError, IncompatibleBoardDeltaError
from calliope.services.position import (
    BoardDeltaAnalyzer,
    PositionFactExtractor,
)
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer

START = chess.STARTING_FEN
W, B = Color.WHITE, Color.BLACK
P, Q = PieceType.PAWN, PieceType.QUEEN


@pytest.fixture
def services():
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    transitions = TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))
    return rules, positions, transitions, LineAnalyzer(transitions)


def pawn_at(result, square):
    return next(p for p in result.features.pawns if p.pawn.square == square)


def test_initial_features_and_p4_are_preserved(services):
    rules, positions, _, _ = services
    snapshot = rules.position_from_fen(START)
    result = positions.analyze(snapshot)
    assert result.facts == PositionFactExtractor(rules).extract(snapshot)
    assert result.features.definition_version == "positional_v1"
    assert result.features.position_id == snapshot.position_id
    assert len(result.features.pawns) == 16
    assert all(not p.isolated and not p.doubled and not p.passed for p in result.features.pawns)
    assert all(f.white_pawns == f.black_pawns == 1 for f in result.features.files)
    assert not any(
        f.open or f.semi_open_for(W) or f.semi_open_for(B) for f in result.features.files
    )
    assert result == positions.analyze(snapshot)


@pytest.mark.parametrize(
    "fen,square,isolated,doubled,passed",
    [
        ("4k3/8/8/8/8/8/P7/4K3 w - - 0 1", "a2", True, False, True),
        ("4k3/8/8/8/P7/8/P7/4K3 w - - 0 1", "a2", True, True, True),
        ("4k3/8/8/8/P7/8/P7/4K3 w - - 0 1", "a4", True, True, True),
        # A friendly pawn on an adjacent file at ANY rank prevents isolation.
        ("4k3/8/1P6/8/8/8/P7/4K3 w - - 0 1", "a2", False, False, True),
        ("4k3/8/8/1p6/P7/8/8/4K3 w - - 0 1", "a4", True, False, False),
        # Same-rank and behind pawns do not disqualify passed status in v1.
        ("4k3/8/8/8/Pp6/8/8/4K3 w - - 0 1", "a4", True, False, True),
        ("4k3/8/8/8/P7/1p6/8/4K3 w - - 0 1", "a4", True, False, True),
        # Black's forward direction is reversed.
        ("4k3/8/8/p7/1P6/8/8/4K3 b - - 0 1", "a5", True, False, False),
        ("4k3/8/1P6/p7/8/8/8/4K3 b - - 0 1", "a5", True, False, True),
    ],
)
def test_pawn_definitions(services, fen, square, isolated, doubled, passed):
    rules, positions, _, _ = services
    pawn = pawn_at(positions.analyze(rules.position_from_fen(fen)), square)
    assert (pawn.isolated, pawn.doubled, pawn.passed) == (isolated, doubled, passed)


def test_support_is_geometric_even_when_supporter_is_pinned(services):
    rules, positions, _, _ = services
    snapshot = rules.position_from_fen("k3r3/8/8/8/8/3P4/4P3/4K3 w - - 0 1")
    result = positions.analyze(snapshot)
    assert [p.square for p in pawn_at(result, "d3").pawn_supporters] == ["e2"]
    assert not any(c.move.uci == "e2d3" for c in result.facts.legal_captures)
    assert rules.observe_tactics(snapshot).absolute_pins[0].pinned.square == "e2"


def test_open_files_are_not_semi_open(services):
    rules, positions, _, _ = services
    result = positions.analyze(rules.position_from_fen("4k3/2p5/8/8/8/8/1P6/4K3 w - - 0 1"))
    a, b, c = result.features.files[:3]
    assert a.open and not a.semi_open_for(W) and not a.semi_open_for(B)
    assert not b.open and b.semi_open_for(B) and not b.semi_open_for(W)
    assert not c.open and c.semi_open_for(W) and not c.semi_open_for(B)


def test_color_rank_mirror_preserves_definitions(services):
    rules, positions, _, _ = services
    board = chess.Board("4k3/2p5/8/3p4/P2P4/2P5/P7/4K3 w - - 0 1")
    original = positions.analyze(rules.position_from_fen(board.fen()))
    mirrored = positions.analyze(rules.position_from_fen(board.mirror().fen()))
    for pawn in original.features.pawns:
        square = pawn.pawn.square[0] + str(9 - int(pawn.pawn.square[1]))
        other = pawn_at(mirrored, square)
        assert other.pawn.color is pawn.pawn.color.opposite
        assert (pawn.isolated, pawn.doubled, pawn.passed) == (
            other.isolated,
            other.doubled,
            other.passed,
        )
        assert [p.square[0] + str(9 - int(p.square[1])) for p in pawn.pawn_supporters] == [
            p.square for p in other.pawn_supporters
        ]
    for f, m in zip(original.features.files, mirrored.features.files, strict=True):
        assert (f.white_pawns, f.black_pawns) == (m.black_pawns, m.white_pawns)


def test_movement_alone_is_not_structural_improvement(services):
    rules, _, transitions, _ = services
    result = transitions.analyze(
        rules.position_from_fen("4k3/8/8/8/8/8/P7/4K3 w - - 0 1"), ChessMove("a2a3")
    )
    assert result.pawn_changes == result.file_changes == ()
    assert len(result.board_delta.transitions) == 1


def test_capture_changes_stationary_pawn_and_files(services):
    rules, _, transitions, _ = services
    result = transitions.analyze(
        rules.position_from_fen("4k3/8/8/3p4/2P1P3/8/8/4K3 w - - 0 1"), ChessMove("e4d5")
    )
    stationary = next(c for c in result.pawn_changes if c.before.pawn.square == "c4")
    assert stationary.before.isolated and not stationary.before.passed
    assert not stationary.after.isolated and stationary.after.passed
    removed = next(c for c in result.pawn_changes if c.before.pawn.color is B)
    assert removed.after is None
    assert [c.before.file for c in result.file_changes] == ["d", "e"]
    assert result.board_delta.material_changes == (MaterialChange(B, P, -1),)


def test_support_removal_is_tracked(services):
    rules, _, transitions, _ = services
    result = transitions.analyze(
        rules.position_from_fen("4k3/8/8/8/8/3P4/4P3/4K3 w - - 0 1"), ChessMove("e2e3")
    )
    change = next(c for c in result.pawn_changes if c.before.pawn.square == "d3")
    assert change.before.pawn_supporters and not change.after.pawn_supporters


@pytest.mark.parametrize("uci", ["e1g1", " e1h1 "])
def test_castling_normalization_and_existing_delta(services, uci):
    rules, _, transitions, _ = services
    result = transitions.analyze(
        rules.position_from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"), ChessMove(uci, "wrong")
    )
    assert result.board_delta.move.uci == "e1g1"
    assert result.board_delta.move.san == "O-O"
    assert len(result.board_delta.transitions) == 2
    assert result.pawn_changes == result.file_changes == ()


def test_line_tracks_recaptures_and_original_identity(services):
    rules, _, _, lines = services
    result = lines.analyze(
        rules.position_from_fen(START),
        tuple(ChessMove(m) for m in ("e2e4", "d7d5", "e4d5", "d8d5")),
    )
    assert result.material_changes == (MaterialChange(W, P, -1), MaterialChange(B, P, -1))
    assert result.end_kind is LineEndKind.PROVIDED_LINE_END
    history = next(h for h in result.piece_histories if h.base.base_square == "e2")
    assert [p.square if p else None for p in history.states] == ["e2", "e4", "e4", "d5", None]
    assert len(result.transitions) == 4
    assert all(len(h.states) == 5 for h in result.piece_histories)
    for before, after in zip(result.transitions, result.transitions[1:]):
        assert before.after == after.before


def test_en_passant_line_tracks_actual_captured_square(services):
    rules, _, _, lines = services
    result = lines.analyze(
        rules.position_from_fen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"),
        (ChessMove("e5d6"),),
    )
    captured = next(h for h in result.piece_histories if h.base.base_square == "d5")
    assert captured.states[-1] is None
    assert result.transitions[0].board_delta.capture.captured_square == "d5"
    assert result.transitions[0].board_delta.capture.landing_square == "d6"
    assert result.material_changes == (MaterialChange(B, P, -1),)


def test_promotion_retains_pawn_identity_and_counts_type_change(services):
    rules, _, _, lines = services
    result = lines.analyze(
        rules.position_from_fen("8/4P3/8/8/8/8/k7/4K3 w - - 0 1"),
        (ChessMove("e7e8q"),),
    )
    history = next(h for h in result.piece_histories if h.base.base_square == "e7")
    assert history.base.piece_type is P
    assert history.states[-1].piece_type is Q
    assert result.transitions[0].pawn_changes[0].after is None
    assert result.material_changes == (MaterialChange(W, P, -1), MaterialChange(W, Q, 1))


def test_empty_line_and_checkmate_end(services):
    rules, _, _, lines = services
    empty = lines.analyze(rules.position_from_fen(START), ())
    assert empty.initial == empty.final
    assert empty.transitions == empty.material_changes == ()
    assert all(len(h.states) == 1 for h in empty.piece_histories)
    mate = lines.analyze(
        rules.position_from_fen(START),
        tuple(ChessMove(m) for m in ("f2f3", "e7e5", "g2g4", "d8h4")),
    )
    assert mate.end_kind is LineEndKind.CHECKMATE


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, 257])
def test_invalid_line_budget(services, limit):
    rules, _, _, lines = services
    with pytest.raises(ValueError, match="max_plies"):
        lines.analyze(rules.position_from_fen(START), (), max_plies=limit)


def test_line_limit_rejects_before_observation(services, monkeypatch):
    rules, _, _, lines = services

    def unexpected(self, position):
        pytest.fail("over-budget input must fail before position analysis")

    monkeypatch.setattr(PositionAnalyzer, "analyze", unexpected)
    with pytest.raises(ValueError, match="exceeds"):
        lines.analyze(
            rules.position_from_fen(START), (ChessMove("e2e4"), ChessMove("e7e5")), max_plies=1
        )


def test_illegal_later_move_returns_no_partial_result(services):
    rules, _, _, lines = services
    with pytest.raises(IllegalMoveError):
        lines.analyze(rules.position_from_fen(START), (ChessMove("e2e4"), ChessMove("d8d5")))
    assert lines.analyze(rules.position_from_fen(START), ()).transitions == ()


def test_mismatched_delta_rejected(services, monkeypatch):
    rules, _, transitions, _ = services
    original = BoardDeltaAnalyzer.analyze

    def mismatched(self, before, move):
        return replace(original(self, before, move), after_position_id="wrong")

    monkeypatch.setattr(BoardDeltaAnalyzer, "analyze", mismatched)
    with pytest.raises(IncompatibleBoardDeltaError, match="match"):
        transitions.analyze(rules.position_from_fen(START), ChessMove("e2e4"))


@pytest.mark.parametrize("damage", ["missing_pair", "wrong_after_piece", "wrong_material"])
def test_matching_ids_do_not_hide_incompatible_delta(services, monkeypatch, damage):
    rules, _, transitions, _ = services
    original = BoardDeltaAnalyzer.analyze

    def damaged(self, before, move):
        delta = original(self, before, move)
        if damage == "missing_pair":
            return replace(
                delta,
                piece_correspondence=tuple(
                    p for p in delta.piece_correspondence if p.before.square != "a2"
                ),
            )
        if damage == "wrong_after_piece":
            return replace(
                delta,
                piece_correspondence=tuple(
                    replace(p, after=replace(p.after, square="a4"))
                    if p.before.square == "a2"
                    else p
                    for p in delta.piece_correspondence
                ),
            )
        return replace(delta, material_changes=(MaterialChange(W, P, -1),))

    monkeypatch.setattr(BoardDeltaAnalyzer, "analyze", damaged)
    with pytest.raises(IncompatibleBoardDeltaError):
        transitions.analyze(
            rules.position_from_fen("4k3/8/8/8/8/8/P7/4K3 w - - 0 1"), ChessMove("a2a3")
        )


def test_line_rejects_disconnected_before_analysis(services, monkeypatch):
    rules, _, _, lines = services
    original = TransitionAnalyzer.analyze

    def disconnected(self, before, move):
        step = original(self, before, move)
        return replace(step, before=step.after)

    monkeypatch.setattr(TransitionAnalyzer, "analyze", disconnected)
    with pytest.raises(IncompatibleBoardDeltaError):
        lines.analyze(rules.position_from_fen(START), (ChessMove("e2e4"),))


def test_line_rejects_corrupt_material_total(services, monkeypatch):
    rules, _, _, lines = services
    original = TransitionAnalyzer.analyze

    def corrupt_total(self, before, move):
        step = original(self, before, move)
        return replace(
            step,
            board_delta=replace(step.board_delta, material_changes=(MaterialChange(W, P, -1),)),
        )

    monkeypatch.setattr(TransitionAnalyzer, "analyze", corrupt_total)
    with pytest.raises(IncompatibleBoardDeltaError, match="endpoint"):
        lines.analyze(rules.position_from_fen(START), (ChessMove("e2e4"),))


@pytest.mark.parametrize("seed", range(8))
def test_legal_line_frames_match_independent_board_replay(services, seed):
    rules, _, _, lines = services
    rng = random.Random(seed)
    board = chess.Board()
    frames = [board.copy()]
    moves = []
    for _ in range(32):
        legal = sorted(board.legal_moves, key=lambda m: m.uci())
        if not legal:
            break
        move = rng.choice(legal)
        moves.append(ChessMove(move.uci()))
        board.push(move)
        frames.append(board.copy())
    result = lines.analyze(rules.position_from_fen(START), tuple(moves))
    observed = [result.initial] + [t.after for t in result.transitions]
    assert len(observed) == len(frames)
    for index, (analysis, expected) in enumerate(zip(observed, frames, strict=True)):
        pieces = {
            s.piece.square: (s.piece.color is W, s.piece.piece_type.value)
            for s in analysis.facts.pieces
        }
        assert pieces == {
            chess.square_name(sq): (p.color, chess.piece_name(p.piece_type))
            for sq, p in expected.piece_map().items()
        }
        histories = [h.states[index] for h in result.piece_histories if h.states[index] is not None]
        assert {p.square for p in histories} == set(pieces)
        assert len(histories) == len(pieces)
    # Counts at endpoints independently cross-check the accumulated per-ply result.
    types = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
    expected_changes = {
        (color, chess.piece_name(kind)): len(board.pieces(kind, color))
        - len(frames[0].pieces(kind, color))
        for color in (chess.WHITE, chess.BLACK)
        for kind in types
        if len(board.pieces(kind, color)) != len(frames[0].pieces(kind, color))
    }
    assert {(c.color is W, c.piece_type.value): c.count_delta for c in result.material_changes} == (
        expected_changes
    )


@pytest.mark.parametrize("via_line", [False, True])
@pytest.mark.parametrize(
    "fen,uci,swap,missing_transitions",
    [
        (START, "e2e4", ("a2", "h2"), False),
        (START, "e2e4", ("e2", "d2"), False),
        ("4k3/8/8/8/8/8/P2PP3/4K3 w - - 0 1", "e1f1", ("a2", "d2"), False),
        (START, "e2e4", None, True),
        ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1", None, True),
    ],
)
def test_f1_permuted_identity_or_missing_transition_rejected(
    services, monkeypatch, via_line, fen, uci, swap, missing_transitions
):
    rules, _, transitions, lines = services
    original = BoardDeltaAnalyzer.analyze

    def corrupt(self, before, move):
        delta = original(self, before, move)
        if missing_transitions:
            return replace(delta, transitions=())
        pairs = {p.before.square: p for p in delta.piece_correspondence}
        replacements = {
            pairs[swap[0]].before: pairs[swap[1]].after,
            pairs[swap[1]].before: pairs[swap[0]].after,
        }
        # Rebind transition endpoints as well, so existing accounting/type checks
        # still pass. The failure must be the new actual-move correspondence check.
        return replace(
            delta,
            piece_correspondence=tuple(
                replace(p, after=replacements.get(p.before, p.after))
                for p in delta.piece_correspondence
            ),
            transitions=tuple(
                replace(t, after=replacements.get(t.before, t.after)) for t in delta.transitions
            ),
        )

    monkeypatch.setattr(BoardDeltaAnalyzer, "analyze", corrupt)
    position = rules.position_from_fen(fen)
    with pytest.raises(IncompatibleBoardDeltaError):
        if via_line:
            lines.analyze(position, (ChessMove(uci),))
        else:
            transitions.analyze(position, ChessMove(uci))


@pytest.mark.parametrize("damage", ["swapped_rooks", "wrong_rook_kind", "missing_rook"])
def test_castling_rook_correspondence_and_transition_required(services, monkeypatch, damage):
    rules, _, transitions, _ = services
    original = BoardDeltaAnalyzer.analyze

    def corrupt(self, before, move):
        delta = original(self, before, move)
        if damage == "swapped_rooks":
            pairs = {p.before.square: p for p in delta.piece_correspondence}
            swapped = {pairs["a1"].before: pairs["h1"].after, pairs["h1"].before: pairs["a1"].after}
            return replace(
                delta,
                piece_correspondence=tuple(
                    replace(p, after=swapped.get(p.before, p.after))
                    for p in delta.piece_correspondence
                ),
                transitions=tuple(
                    replace(t, after=swapped.get(t.before, t.after)) for t in delta.transitions
                ),
            )
        return replace(
            delta,
            transitions=tuple(
                replace(t, kind=PieceTransitionKind.MOVE)
                if t.kind is PieceTransitionKind.CASTLING_ROOK
                else t
                for t in delta.transitions
                if damage != "missing_rook" or t.kind is not PieceTransitionKind.CASTLING_ROOK
            ),
        )

    monkeypatch.setattr(BoardDeltaAnalyzer, "analyze", corrupt)
    with pytest.raises(IncompatibleBoardDeltaError):
        transitions.analyze(
            rules.position_from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"), ChessMove("e1g1")
        )


@pytest.mark.parametrize("uci", ["e1g1", "e1c1", "e8g8", "e8c8"])
def test_move_check_accepts_all_standard_castlings(services, uci):
    rules, _, transitions, _ = services
    turn = "w" if uci.startswith("e1") else "b"
    result = transitions.analyze(
        rules.position_from_fen(f"r3k2r/8/8/8/8/8/8/R3K2R {turn} KQkq - 0 1"), ChessMove(uci)
    )
    assert len(result.board_delta.transitions) == 2
    assert {t.kind for t in result.board_delta.transitions} == {
        PieceTransitionKind.MOVE,
        PieceTransitionKind.CASTLING_ROOK,
    }


@pytest.mark.parametrize("suffix", ["q", "r", "b", "n"])
@pytest.mark.parametrize("color", [W, B])
def test_move_check_accepts_promotions_and_underpromotions(services, suffix, color):
    rules, _, transitions, _ = services
    fen, prefix = (
        ("8/4P3/8/8/8/8/k7/4K3 w - - 0 1", "e7e8")
        if color is W
        else ("4k3/K7/8/8/8/8/4p3/8 b - - 0 1", "e2e1")
    )
    result = transitions.analyze(rules.position_from_fen(fen), ChessMove(prefix + suffix))
    assert result.board_delta.transitions[0].kind is PieceTransitionKind.PROMOTION
