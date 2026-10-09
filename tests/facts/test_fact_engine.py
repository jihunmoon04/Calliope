"""F1 behaviour of the fact engine: inputs, identity, revisions, roles, refusals, draw history."""

import chess
import pytest

from calliope.facts import (
    EXPLORED,
    PLAYED,
    BudgetExceededError,
    ExtendRequest,
    FactEngine,
    IllegalMoveError,
    InputLine,
    InvalidPositionError,
    InvalidRequestError,
    NodeId,
    OpenRequest,
    PieceId,
    PositionKey,
    RoleKind,
    RootSpec,
    SessionBudget,
    TerminalKind,
    UnsupportedVariantError,
    analysis,
)
from calliope.facts.board import MoveRejectedError, canonical_move
from calliope.facts.families import Capture, CastlingSide, Promotion, RookTransfer
from calliope.facts.tree import DrawRule, LineEnd
from calliope.facts.values import HISTORY_UNKNOWN, AtLeast, NotApplicable, NotComputed

ENGINE = FactEngine()
CASTLING = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"


def _session(*moves: str, fen: str | None = None, label: str = "game", **kwargs):
    tree = ENGINE.open(OpenRequest(root=RootSpec(fen=fen), **kwargs))
    if moves:
        ENGINE.extend(tree, ExtendRequest((InputLine(label, moves),), PLAYED))
    return tree


def _end(tree, label: str = "game", kind: str = "played", segment: int = 0) -> NodeId:
    return tree.view().input_line(label, RoleKind(kind), segment=segment).nodes[-1]


# -- canonicalization (§2.3) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("fen", "alias", "canonical"),
    [
        (CASTLING, "e1h1", "e1g1"),
        (CASTLING, "e1g1", "e1g1"),
        (CASTLING, "e1a1", "e1c1"),
        (CASTLING, "e1c1", "e1c1"),
        (CASTLING.replace(" w ", " b "), "e8h8", "e8g8"),
        (CASTLING.replace(" w ", " b "), "e8g8", "e8g8"),
        (CASTLING.replace(" w ", " b "), "e8a8", "e8c8"),
        (CASTLING.replace(" w ", " b "), "e8c8", "e8c8"),
        (CASTLING, "O-O", "e1g1"),
        (CASTLING, "O-O-O", "e1c1"),
    ],
)
def test_every_castling_notation_becomes_the_king_move(
    fen: str, alias: str, canonical: str
) -> None:
    assert canonical_move(chess.Board(fen), alias).uci() == canonical


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("0000", "null"),
        ("--", "null"),
        ("Z0", "null"),
        ("@@@@", "null"),
        ("e2e4q", "not legal"),
        ("", "empty"),
        ("Nbd2x", "neither"),
    ],
)
def test_bad_move_texts_are_refused(text: str, reason: str) -> None:
    with pytest.raises(MoveRejectedError, match=reason):
        canonical_move(chess.Board(), text)


def test_uci_and_san_reach_the_same_node() -> None:
    uci = _session("e2e4", "e7e5", "g1f3")
    san = _session("e4", "e5", "Nf3")
    assert _end(uci) == _end(san)


def test_illegal_line_is_refused_with_label_and_ply_and_nothing_is_committed() -> None:
    tree = _session("e4", "e5")
    before = (tree.rev, len(tree.view().nodes()))
    with pytest.raises(IllegalMoveError) as refused:
        ENGINE.extend(
            tree,
            ExtendRequest(
                (InputLine("ok", ("d4",)), InputLine("bad", ("d4", "d5", "Ke3"))), EXPLORED
            ),
        )
    assert (refused.value.label, refused.value.ply, refused.value.move) == ("bad", 3, "Ke3")
    assert (tree.rev, len(tree.view().nodes())) == before


def test_invalid_and_chess960_roots_are_refused() -> None:
    with pytest.raises(InvalidPositionError):
        ENGINE.open(OpenRequest(root=RootSpec(fen="8/8/8/8/8/8/8/8 w - - 0 1")))
    with pytest.raises(UnsupportedVariantError):
        ENGINE.open(OpenRequest(root=RootSpec(fen="rk6/8/8/8/8/8/8/RK5R w H - 0 1")))
    with pytest.raises(IllegalMoveError, match="<root>"):
        ENGINE.open(OpenRequest(root=RootSpec(moves=("e4", "e4"))))


# -- identities (§3.1) ---------------------------------------------------------------------


def test_position_key_counts_only_legal_en_passant() -> None:
    no_capture = chess.Board()
    no_capture.push_uci("e2e4")
    assert PositionKey.of(no_capture).value.endswith(" -")
    capture = chess.Board("rnbqkbnr/ppp1pppp/8/8/3p4/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    capture.push_uci("e2e4")
    assert PositionKey.of(capture).value.endswith(" e3")


def test_root_id_depends_on_history_not_on_lines() -> None:
    a = ENGINE.open(OpenRequest(root=RootSpec(moves=("e4", "e5"))))
    b = ENGINE.open(OpenRequest(root=RootSpec(moves=("e2e4", "e7e5")), budget=SessionBudget(9)))
    fen = ENGINE.open(OpenRequest(root=RootSpec(fen=a.view().node(a.root).fen)))
    assert a.root_id == b.root_id != fen.root_id
    assert a.view().node(a.root).position_key == fen.view().node(fen.root).position_key


def test_transpositions_are_two_nodes_sharing_position_facts() -> None:
    tree = _session()
    ENGINE.extend(
        tree,
        ExtendRequest(
            (InputLine("a", ("Nf3", "Nf6", "g3")), InputLine("b", ("g3", "Nf6", "Nf3"))), EXPLORED
        ),
    )
    view = tree.view()
    a, b = _end(tree, "a", "explored"), _end(tree, "b", "explored")
    assert a != b and view.node(a).position_key == view.node(b).position_key
    assert view.fact("status", a) is view.fact("status", b)
    assert view.fact("move", a).uci == "g2g3" and view.fact("move", b).uci == "g1f3"


# -- piece identity (§4) -------------------------------------------------------------------


def test_castling_moves_king_and_rook_identities() -> None:
    tree = _session("O-O", "O-O-O", fen=CASTLING)
    view = tree.view()
    end = view.node(_end(tree))
    assert end.piece_at("g1") == PieceId("w.K.e1") and end.piece_at("f1") == PieceId("w.R.h1")
    assert end.piece_at("c8") == PieceId("b.K.e8") and end.piece_at("d8") == PieceId("b.R.a8")
    first = view.path(end.node_id)[1]
    facts = view.fact("move", first)
    assert facts.castling is CastlingSide.KINGSIDE
    assert facts.events == (RookTransfer(PieceId("w.R.h1"), "h1", "f1"),)


def test_en_passant_captures_the_victim_square() -> None:
    tree = _session("e4", "a6", "e5", "d5", "exd6")
    view = tree.view()
    end = _end(tree)
    (capture,) = view.fact("move", end).events
    assert capture == Capture(PieceId("b.P.d7"), capture.piece_type, "d5", en_passant=True)
    assert view.node(end).piece_at("d6") == PieceId("w.P.e2")
    assert view.node(end).square_of(PieceId("b.P.d7")) is None


def test_capture_promotion_keeps_pawn_identity_with_ordered_events() -> None:
    tree = _session("bxa8=N", fen="r3k3/1P6/8/8/8/8/8/4K3 w - - 0 1")
    view = tree.view()
    end = _end(tree)
    events = view.fact("move", end).events
    assert [type(e) for e in events] == [Capture, Promotion]
    assert events[0].piece == PieceId("b.R.a8") and events[1].piece == PieceId("w.P.b7")
    assert view.node(end).piece_at("a8") == PieceId("w.P.b7")
    assert view.fact("material", end).white.knights == 1


def test_the_same_piece_has_the_same_id_in_every_branch() -> None:
    tree = _session()
    ENGINE.extend(
        tree, ExtendRequest((InputLine("x", ("Nf3",)), InputLine("y", ("Nh3",))), EXPLORED)
    )
    view = tree.view()
    x, y = _end(tree, "x", "explored"), _end(tree, "y", "explored")
    assert view.fact("move", x).piece == view.fact("move", y).piece == PieceId("w.N.g1")


# -- revisions, roles and lines (§3.2, §3.3) ------------------------------------------------


def test_each_request_is_one_revision_and_old_views_stay_pinned() -> None:
    tree = _session("e4")
    assert tree.rev == 2
    rev2 = tree.view()
    ENGINE.extend(tree, ExtendRequest((InputLine("game", ("e5",)),), PLAYED))
    assert tree.rev == 3
    end = _end(tree, segment=1)
    assert not rev2.has_node(end) and tree.view().has_node(end)
    assert [d.request for d in tree.view().manifest()] == ["open", "extend", "extend"]
    assert len(tree.view(2).manifest()) == 2


def test_a_label_continues_from_its_end_and_indexes_continue() -> None:
    tree = _session("e4", "e5")
    ENGINE.extend(tree, ExtendRequest((InputLine("game", ("Nf3",)),), PLAYED))
    view = tree.view()
    second = view.input_line("game", segment=1)
    assert second.first_index == 2 and len(second.nodes) == 2
    (role,) = view.roles(second.nodes[-1])
    assert (role.kind, role.label, role.index) == (RoleKind.PLAYED, "game", 3)
    with pytest.raises(InvalidRequestError, match="continues only"):
        ENGINE.extend(tree, ExtendRequest((InputLine("game", ("d4",), start=tree.root),), PLAYED))


def test_input_roles_accumulate_on_shared_nodes() -> None:
    tree = _session("e4", "e5")
    ENGINE.extend(tree, ExtendRequest((InputLine("idea", ("e4", "c5")),), analysis("probe-block")))
    view = tree.view()
    e4 = view.child(tree.root, "e2e4")
    kinds = [(r.kind, r.by) for r in view.roles(e4)]
    assert kinds == [(RoleKind.PLAYED, ""), (RoleKind.ANALYSIS, "probe-block")]
    assert view.manifest()[-1].nodes_added == 1


def test_request_shape_refusals() -> None:
    tree = _session("e4")
    with pytest.raises(InvalidRequestError, match="unique"):
        ENGINE.extend(
            tree, ExtendRequest((InputLine("a", ("d4",)), InputLine("a", ("c4",))), EXPLORED)
        )
    with pytest.raises(InvalidRequestError, match="unknown node"):
        ENGINE.extend(
            tree, ExtendRequest((InputLine("a", ("d4",), start=NodeId("n_x")),), EXPLORED)
        )
    with pytest.raises(InvalidRequestError, match="no moves"):
        ENGINE.extend(tree, ExtendRequest((InputLine("a", ()),), EXPLORED))
    with pytest.raises(ValueError):
        analysis("")


def test_budget_refuses_before_building() -> None:
    tree = _session("e4", budget=SessionBudget(max_nodes=3))
    with pytest.raises(BudgetExceededError):
        ENGINE.extend(tree, ExtendRequest((InputLine("game", ("e5", "Nf3")),), PLAYED))
    assert tree.rev == 2 and len(tree.view().nodes()) == 2
    ENGINE.extend(tree, ExtendRequest((InputLine("game", ("e5",)),), PLAYED))
    assert len(tree.view().nodes()) == 3


def test_unselected_family_and_root_edge_are_typed() -> None:
    tree = _session("e4", families=())
    view = tree.view()
    assert isinstance(view.fact("material", _end(tree)), NotComputed)
    assert isinstance(view.fact("move", tree.root), NotApplicable)
    with pytest.raises(InvalidRequestError, match="unknown"):
        ENGINE.open(OpenRequest(families=("no_such_family",)))


# -- history completeness and draw rules (§2.2, §6.9, §7.8) ----------------------------------

SHUFFLE = ("Nf3", "Nf6", "Ng1", "Ng8")


def test_threefold_reached_and_claimable_by_move_are_distinct() -> None:
    tree = _session(*SHUFFLE, *SHUFFLE[:3])
    view = tree.view()
    draw = view.fact("draw", _end(tree))
    assert draw.occurrences == 2 and draw.threefold_reached is False
    assert draw.threefold_claimable_by_move is True  # ...Ng8 makes the third occurrence
    ENGINE.extend(tree, ExtendRequest((InputLine("game", ("Ng8",)),), PLAYED))
    draw = tree.view().fact("draw", _end(tree, segment=1))
    assert draw.occurrences == 3 and draw.threefold_reached is True


def test_fivefold_ends_the_game_and_later_input_is_after_terminal() -> None:
    tree = _session(*(SHUFFLE * 4), "Nc3")
    view = tree.view()
    path = view.input_line("game", segment=0).nodes
    fivefold = view.node(path[16])
    assert fivefold.terminal.kind is TerminalKind.AUTOMATIC_DRAW
    assert fivefold.terminal.rule is DrawRule.FIVEFOLD_REPETITION
    assert view.node(path[17]).after_terminal and not fivefold.after_terminal
    assert view.input_line("game", segment=0).end is LineEnd.INPUT_END


def test_bare_fen_with_clock_has_incomplete_history_and_sound_draw_facts() -> None:
    fen = "4k3/8/8/8/8/8/8/4K2R w K - 20 40"
    tree = _session("Kf1", "Kf8", "Ke1", "Ke8", fen=fen)
    view = tree.view()
    root, end = view.node(tree.root), view.node(_end(tree))
    assert not root.history_complete and root.known_plies == 0
    draw = view.fact("draw", end.node_id)
    assert draw.occurrences == AtLeast(1)  # castling rights differ from the root after Kf1
    assert draw.threefold_reached is HISTORY_UNKNOWN or draw.threefold_reached is False
    assert end.terminal.kind is TerminalKind.UNPROVEN


def test_bare_fen_with_zero_clock_is_complete() -> None:
    tree = _session("Kd1", fen="4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    view = tree.view()
    assert view.node(tree.root).history_complete
    assert view.node(_end(tree)).terminal.kind is TerminalKind.NONE
    assert view.fact("draw", _end(tree)).fivefold_reached is False


def test_fen_plus_moves_is_complete_only_where_the_clock_allows() -> None:
    tree = ENGINE.open(
        OpenRequest(root=RootSpec(fen="4k3/8/8/8/8/8/8/R3K3 w - - 6 10", moves=("Kd1", "Kd8")))
    )
    root = tree.view().node(tree.root)
    assert root.known_plies == 2 and root.halfmove_clock == 8 and not root.history_complete
    ENGINE.extend(tree, ExtendRequest((InputLine("g", ("Ra8+",)),), EXPLORED))
    assert not tree.view().node(_end(tree, "g", "explored")).history_complete


def test_seventy_five_move_rule_and_insufficient_material_are_automatic_draws() -> None:
    tree = _session("Kf1", "Kf8", fen="4k3/8/8/8/8/8/8/R3K3 w - - 149 120")
    view = tree.view()
    first = view.input_line("game", segment=0).nodes[1]
    assert view.node(first).terminal.rule is DrawRule.SEVENTY_FIVE_MOVE
    assert view.node(_end(tree)).after_terminal

    bare = ENGINE.open(OpenRequest(root=RootSpec(fen="4k3/8/8/8/8/8/8/4K3 w - - 0 1")))
    assert bare.view().node(bare.root).terminal.rule is DrawRule.INSUFFICIENT_MATERIAL
    ENGINE.extend(bare, ExtendRequest((InputLine("g", ("Kd1",)),), EXPLORED))
    assert bare.view().node(_end(bare, "g", "explored")).after_terminal


def test_checkmate_line_end_and_mating_moves() -> None:
    tree = _session("f3", "e5", "g4")
    view = tree.view()
    assert view.fact("status", _end(tree)).mating_moves == ("d8h4",)
    ENGINE.extend(tree, ExtendRequest((InputLine("game", ("Qh4#",)),), PLAYED))
    view = tree.view()
    line = view.input_line("game", segment=1)
    assert line.end is LineEnd.CHECKMATE
    assert view.node(line.nodes[-1]).terminal.kind is TerminalKind.CHECKMATE
    assert view.fact("move", line.nodes[-1]).gives_mate


# -- F1 review regressions -------------------------------------------------------------------


def test_null_moves_are_refused_on_every_path() -> None:
    with pytest.raises(IllegalMoveError, match="null"):
        ENGINE.open(OpenRequest(root=RootSpec(moves=("e4", "--"))))
    tree = _session("e4")
    with pytest.raises(IllegalMoveError, match="null"):
        ENGINE.extend(tree, ExtendRequest((InputLine("game", ("Z0",)),), PLAYED))
    assert tree.rev == 2


def test_root_after_terminal_comes_from_known_pre_root_history() -> None:
    fivefold = ENGINE.open(OpenRequest(root=RootSpec(moves=(*(SHUFFLE * 4), "Nc3"))))
    assert fivefold.view().node(fivefold.root).after_terminal
    played = _session(*(SHUFFLE * 4), "Nc3")
    assert played.view().node(_end(played)).after_terminal  # same answer as an extended line

    rook = "4k3/8/8/8/8/8/8/R3K3 w - - 149 120"
    seventy_five = ENGINE.open(OpenRequest(root=RootSpec(fen=rook, moves=("Kf1", "Kf8"))))
    root = seventy_five.view().node(seventy_five.root)
    assert root.after_terminal and root.terminal.rule is DrawRule.SEVENTY_FIVE_MOVE

    exactly = ENGINE.open(OpenRequest(root=RootSpec(fen=rook.replace(" 149 ", " 150 "))))
    node = exactly.view().node(exactly.root)
    assert node.terminal.rule is DrawRule.SEVENTY_FIVE_MOVE and not node.after_terminal
    beyond = ENGINE.open(OpenRequest(root=RootSpec(fen=rook.replace(" 149 ", " 160 "))))
    assert beyond.view().node(beyond.root).after_terminal  # clock > 150 proves an earlier end


def test_after_terminal_is_proven_ended_only() -> None:
    board = chess.Board()
    for san in SHUFFLE * 4:
        board.push_san(san)
    bare = ENGINE.open(OpenRequest(root=RootSpec(fen=board.fen())))  # fivefold hidden in history
    root = bare.view().node(bare.root)
    assert root.terminal.kind is TerminalKind.UNPROVEN and not root.after_terminal
    ENGINE.extend(bare, ExtendRequest((InputLine("g", ("Nc3",)),), EXPLORED))
    assert not bare.view().node(_end(bare, "g", "explored")).after_terminal


def test_line_ids_are_structured_and_never_overwritten() -> None:
    tree = _session()
    ENGINE.extend(tree, ExtendRequest((InputLine("b:c", ("e4",)),), analysis("a")))
    pinned = tree.view()
    ENGINE.extend(tree, ExtendRequest((InputLine("c", ("d4",)),), analysis("a:b")))
    first = pinned.input_line("b:c", RoleKind.ANALYSIS, by="a")
    second = tree.view().input_line("c", RoleKind.ANALYSIS, by="a:b")
    assert first.line_id != second.line_id
    assert pinned.input_line("b:c", RoleKind.ANALYSIS, by="a") is first
    ENGINE.extend(tree, ExtendRequest((InputLine("b:c", ("e5",)),), analysis("a")))
    assert tree.view().input_line("b:c", RoleKind.ANALYSIS, by="a").segment == 1


def test_manifest_names_rule_definitions_and_coverage() -> None:
    tree = _session("e4", "e5")
    view = tree.view()
    open_delta = view.manifest()[0]
    assert dict(open_delta.definitions)["insufficient_material"].startswith("python-chess")
    covered = dict(view.coverage("draw"))
    assert set(covered) == {n.node_id for n in view.nodes()}
    assert covered[tree.root] == 1 and covered[_end(tree)] == 2


def test_seventy_five_move_boundary_before_the_root() -> None:
    # parent of the root has clock 149: not yet ended; one more ply reaches 150 at the root
    tree = ENGINE.open(
        OpenRequest(root=RootSpec(fen="4k3/8/8/8/8/8/8/R3K3 w - - 148 120", moves=("Kf1", "Kf8")))
    )
    root = tree.view().node(tree.root)
    assert root.halfmove_clock == 150 and not root.after_terminal
    assert root.terminal.rule is DrawRule.SEVENTY_FIVE_MOVE


def test_lines_follow_canonical_role_order() -> None:
    tree = _session("e4")
    ENGINE.extend(tree, ExtendRequest((InputLine("a", ("d4",)),), analysis("x")))
    ENGINE.extend(tree, ExtendRequest((InputLine("b", ("c4",)),), EXPLORED))
    assert [line.kind for line in tree.view().lines()] == [
        RoleKind.PLAYED,
        RoleKind.EXPLORED,
        RoleKind.ANALYSIS,
    ]
