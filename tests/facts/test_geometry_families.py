"""F2: board-geometry families, deltas, `ensure` and tiers (F2-D §10.2–§10.6)."""

import random
from dataclasses import replace
from itertools import pairwise

import chess
import pytest
from geometry_auditor import plain_king, plain_lines, plain_pawns, plain_pieces, plain_squares

from calliope.facts import (
    EXPLORED,
    PLAYED,
    ExtendRequest,
    FactEngine,
    InputLine,
    InvalidRequestError,
    OpenRequest,
    PieceId,
    RootSpec,
)
from calliope.facts.engine import key_board
from calliope.facts.families import REGISTRY, MoveFamily, PiecesFamily, StatusFamily
from calliope.facts.families.delta import MAKERS, SET_COMPONENTS, relations_of
from calliope.facts.families.king import FlightKind
from calliope.facts.families.pawns import FileState
from calliope.facts.keys import Color, PieceType
from calliope.facts.request import EnsureRequest
from calliope.facts.tree import Scope
from calliope.facts.values import CAPTURED, PROMOTED, NotApplicable, NotComputed, NotObserved

ENGINE = FactEngine()
GEOMETRY = ("pieces", "squares", "lines", "pawns", "king", "delta", "same_side_delta")


def _root(fen: str, **kwargs):
    tree = ENGINE.open(OpenRequest(root=RootSpec(fen=fen), **kwargs))
    return tree, tree.view()


def _line(fen: str | None, *moves: str, **kwargs):
    tree = ENGINE.open(OpenRequest(root=RootSpec(fen=fen), **kwargs))
    ENGINE.extend(tree, ExtendRequest((InputLine("l", moves),), PLAYED))
    view = tree.view()
    return tree, view, view.input_line("l").nodes


def _piece(view, node, square):
    return view.fact("pieces", node).at(square)


def _rels(relations):
    return [(r.square, r.piece_type.value, r.absolutely_pinned) for r in relations]


def _pid(value: str) -> PieceId:
    return PieceId(value)


# -- §8: every reproduced legacy defect --------------------------------------------------------


def test_d1_a_target_walking_into_an_attack_begins_a_piece_attack() -> None:
    _tree, view, nodes = _line("7k/8/8/8/2n5/8/8/K2R4 b - - 0 1", "c4d2")
    began = view.fact("delta", nodes[1]).piece_attacks.began
    assert any(p.source == _pid("w.R.d1") and p.target == _pid("b.N.c4") for p in began)


def test_e1_a_pinned_defender_is_kept_and_flagged() -> None:
    _tree, view = _root("4r2k/8/8/8/1b2P3/8/3N4/4K3 b - - 0 1")
    pawn = _piece(view, view.root, "e4")
    assert _rels(pawn.defenders) == [("d2", "knight", True)]
    assert _piece(view, view.root, "d2").absolutely_pinned.pinner == "b4"


def test_e2_the_king_is_a_defender_with_its_type() -> None:
    _tree, view = _root("4r2k/8/6b1/8/4P3/3K4/8/8 b - - 0 1")
    pawn = _piece(view, view.root, "e4")
    assert _rels(pawn.defenders) == [("d3", "king", False)]
    assert pawn.attacker_count == 2 and pawn.attackers_exceed_defenders


def test_e3_a_king_attacker_that_cannot_capture() -> None:
    _tree, view = _root("8/8/8/3k4/4P3/5P2/8/K7 b - - 0 1")
    pawn = _piece(view, view.root, "e4")
    assert _rels(pawn.attackers) == [("d5", "king", False)]
    assert pawn.lowest_attacker_types.value == (PieceType.KING,)
    assert pawn.legally_capturable_now is False  # f3 defends: Kxe4 is illegal
    assert isinstance(_piece(view, view.root, "d5").legally_capturable_now, NotObserved)


def test_e4_a_battery_backer_is_exposed_as_xray_and_battery() -> None:
    _tree, view = _root("3r3k/8/8/3P4/8/8/3R4/3RK3 w - - 0 1")
    lines = view.fact("lines", view.root)
    ray = lines.ray("d1", (0, 1))
    assert ray.visible == ("d2",)
    assert ray.xray.squares == ("d3", "d4", "d5") and ray.xray.second.square == "d5"
    assert [(b.pieces, b.line) for b in lines.batteries] == [(("d1", "d2"), (0, 1))]
    assert _rels(_piece(view, view.root, "d5").defenders) == [("d2", "rook", False)]


def test_e5_en_passant_victim_has_no_pawn_attacker_yet_is_capturable() -> None:
    _tree, view, nodes = _line("7k/3p4/8/4P3/8/8/8/K7 b - - 0 1", "d7d5")
    victim = _piece(view, nodes[1], "d5")
    assert victim.attackers == () and victim.legally_capturable_now is True
    assert "d6" in _piece(view, nodes[1], "e5").attacks.empty
    captures = view.fact("status", nodes[1]).legal_captures
    assert [(c.victim_square, c.en_passant) for c in captures] == [("d5", True)]


def test_e6_en_passant_does_not_mask_attacked_without_defender() -> None:
    _tree, view, nodes = _line("7k/3p4/8/4P3/8/8/8/K2R4 b - - 0 1", "d7d5")
    victim = _piece(view, nodes[1], "d5")
    assert _rels(victim.attackers) == [("d1", "rook", False)]
    assert victim.attacked_without_defender and victim.legally_capturable_now is True


def test_e7_side_dependent_fields_are_not_observed_for_the_other_side() -> None:
    _tree, view = _root("7k/8/8/3n4/8/8/8/K2R4 b - - 0 1")
    knight, rook = _piece(view, view.root, "d5"), _piece(view, view.root, "d1")
    assert isinstance(knight.legally_capturable_now, NotObserved)
    assert knight.legal_destinations == ("c3", "e3", "b4", "f4", "b6", "f6", "c7", "e7")
    assert isinstance(rook.legal_moves, NotObserved)
    assert isinstance(rook.legal_destinations, NotObserved)
    assert rook.legally_capturable_now is False


def test_s1_doubled_passed_pawns_carry_own_pawn_ahead() -> None:
    _tree, view = _root("7k/8/8/4P3/4P3/8/8/K7 w - - 0 1")
    pawns = view.fact("pawns", view.root)
    rear, front = pawns.at("e4"), pawns.at("e5")
    assert rear.passed and front.passed and rear.doubled and front.doubled
    assert rear.own_pawn_ahead and not front.own_pawn_ahead


def test_en_passant_pin_is_only_a_missing_legal_capture() -> None:
    _tree, view = _root("7k/8/8/KPp4r/8/8/8/8 w - c6 0 1")
    node = view.node(view.root)
    assert node.position_key.value.endswith(" -")
    assert "b5c6" not in {m.uci for m in view.fact("status", view.root).legal_moves}
    assert _piece(view, view.root, "b5").absolutely_pinned is None


def test_p1_attacked_without_defender_is_not_capturable() -> None:
    _tree, view = _root("7k/8/8/4r2b/8/5N2/8/3K4 w - - 0 1")
    rook = _piece(view, view.root, "e5")
    assert rook.attacked_without_defender and rook.legally_capturable_now is False
    assert _rels(rook.attackers) == [("f3", "knight", True)]


# -- §2 pins ----------------------------------------------------------------------------------


def test_pin_is_the_first_slider_on_the_ray_not_the_pin_mask() -> None:
    fen = "3r3k/3r4/8/3N4/3K4/8/8/7r w - - 0 1"
    _tree, view = _root(fen)
    pin = _piece(view, view.root, "d5").absolutely_pinned
    assert (pin.pinner, pin.direction) == ("d7", (0, 1))
    board = chess.Board(fen)
    mask = chess.SquareSet(board.pin_mask(chess.WHITE, chess.D5))
    assert chess.D7 in mask and chess.D8 in mask  # the mask cannot name the pinner
    assert board.pin_mask(chess.BLACK, chess.D5) == chess.BB_ALL  # wrong-colour query
    assert board.pin_mask(chess.WHITE, chess.D6) == chess.BB_ALL  # empty-square query
    assert view.fact("pieces", view.root).at("d6") is None


def test_pin_behind_another_blocker_is_no_pin() -> None:
    _tree, view = _root("4r1k1/8/8/8/4P3/8/4N3/4K3 w - - 0 1")
    assert _piece(view, view.root, "e2").absolutely_pinned is None


def test_pinned_attacker_keeps_geometry_without_legal_capture() -> None:
    _tree, view = _root("4r1k1/8/8/8/3p4/8/4N3/4K3 w - - 0 1")
    knight = _piece(view, view.root, "e2")
    assert knight.attacks.enemy == ("d4",)
    assert knight.legal_moves == () and knight.legal_destinations == ()
    assert ("e2", "knight", True) in _rels(view.fact("squares", view.root).at("d4").white_attackers)
    assert knight.absolutely_pinned.pinner == "e8" and knight.absolutely_pinned.direction == (0, 1)
    ray = view.fact("lines", view.root).ray("e8", (0, -1))
    assert [o.square for o in ray.occupants[:2]] == ["e2", "e1"]


# -- §4 rays and batteries -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fen", "expected"),
    [
        ("4k3/8/8/8/8/8/3R4/3RK3 w - - 0 1", [(("d1", "d2"), (0, 1))]),
        ("4k3/8/8/8/8/8/2B5/3QK3 w - - 0 1", [(("d1", "c2"), (-1, 1))]),
        ("4k3/8/8/8/3Q4/2P5/1B6/4K3 w - - 0 1", []),  # a bishop behind a pawn
        ("4k3/8/8/8/8/3Q4/3R4/3RK3 w - - 0 1", [(("d1", "d2"), (0, 1)), (("d2", "d3"), (0, 1))]),
        ("4k3/8/8/8/8/8/3B4/3RK3 w - - 0 1", []),  # a rook and a bishop
        ("4k3/8/8/8/8/8/3N4/3RK3 w - - 0 1", []),  # a knight in front
        ("3rk3/8/8/8/8/8/8/3RK3 w - - 0 1", []),  # different colours
    ],
)
def test_batteries_are_unordered_and_recorded_once(fen: str, expected: list) -> None:
    _tree, view = _root(fen)
    lines = view.fact("lines", view.root)
    assert [(b.pieces, b.line) for b in lines.batteries] == expected


def test_edge_empty_and_unblocked_rays_are_distinct() -> None:
    _tree, view = _root("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    lines = view.fact("lines", view.root)
    assert [r.direction for r in lines.rays if r.source == "a1"] == [
        (-1, 0),
        (0, -1),
        (0, 1),
        (1, 0),
    ]
    assert lines.ray("a1", (-1, 0)).edge_empty and lines.ray("a1", (0, -1)).edge_empty
    clear = lines.ray("a1", (0, 1))
    assert clear.unblocked and not clear.edge_empty and len(clear.squares) == 7
    assert clear.first_blocker is None and lines.ray("a1", (-1, 0)).first_blocker is None
    assert lines.ray("a1", (1, 0)).first_blocker.piece_type is PieceType.KING


def test_nearest_blocker_moving_exposes_only_up_to_the_second_blocker() -> None:
    # activity "discovery": the a3 knight leaves the a1 rook's file
    _tree, view, nodes = _line("4k3/p7/8/8/8/N7/8/R3K3 w - - 0 1", "a3b5")
    before = view.fact("lines", nodes[0]).ray("a1", (0, 1))
    after = view.fact("lines", nodes[1]).ray("a1", (0, 1))
    assert before.visible == ("a2", "a3") and after.visible[-1] == "a7"
    assert set(after.visible) - set(before.visible) == {"a4", "a5", "a6", "a7"}
    assert after.xray is None and "a8" not in _piece(view, nodes[1], "a1").attacks.empty
    change = view.fact("delta", nodes[1])
    began = {c.square for c in change.square_control.began if c.piece == _pid("w.R.a1")}
    assert began == {"a4", "a5", "a6", "a7"}
    (xray,) = change.xrays.ended
    assert (xray.slider, xray.first, xray.second) == (
        _pid("w.R.a1"),
        _pid("w.N.a3"),
        _pid("b.P.a7"),
    )


def test_relocated_blocker_keeps_its_identity() -> None:
    # the c1 bishop's nearest blocker slides further along the same (1, 1) ray
    _tree, view, nodes = _line("4k3/8/8/8/8/8/3B4/2B1K3 w - - 0 1", "d2e3")
    change = view.fact("delta", nodes[1])
    began = {c.square for c in change.square_control.began if c.piece == _pid("w.B.c1")}
    assert began == {"e3"}
    assert view.fact("lines", nodes[1]).ray("c1", (1, 1)).first_blocker.square == "e3"
    assert not change.batteries.began and not change.batteries.ended  # the same pair, by id
    # a blocker leaving the ray clears it
    _tree, view, nodes = _line("4k3/8/8/8/8/8/3N4/2B1K3 w - - 0 1", "d2f3")
    assert view.fact("lines", nodes[1]).ray("c1", (1, 1)).occupants == ()


def test_en_passant_capture_opens_the_file_ray_to_the_landing_square() -> None:
    _tree, view, nodes = _line("k7/8/8/3Pp3/8/8/8/K3R3 w - e6 0 1", "d5e6")
    capture = next(c for c in view.fact("status", nodes[0]).legal_captures if c.uci == "d5e6")
    assert capture.en_passant and capture.victim_square == "e5"
    ray = view.fact("lines", nodes[1]).ray("e1", (0, 1))
    assert [o.square for o in ray.occupants] == ["e6"] and ray.visible[-1] == "e6"
    change = view.fact("delta", nodes[1])
    assert (_pid("w.R.e1"), _pid("b.P.e5")) in {
        (p.source, p.target) for p in change.piece_attacks.ended
    }
    assert {c.square for c in change.square_control.began if c.piece == _pid("w.R.e1")} == {"e6"}
    assert [(c.piece, c.after) for c in change.pawn_flags if c.after == CAPTURED] == [
        (_pid("b.P.e5"), CAPTURED)
    ]


def test_friendly_and_enemy_first_blockers_bound_visibility() -> None:
    _tree, view = _root("4k3/8/8/p7/8/P7/8/R3K3 w - - 0 1")
    ray = view.fact("lines", view.root).ray("a1", (0, 1))
    assert [o.square for o in ray.occupants] == ["a3", "a5"]
    assert ray.first_blocker.color is Color.WHITE and ray.visible == ("a2", "a3")
    assert ray.xray.squares == ("a4", "a5")
    assert "a4" not in _piece(view, view.root, "a1").attacks.empty
    assert _piece(view, view.root, "a1").attacks.friendly == ("e1", "a3")
    _tree, view = _root("4k3/8/8/p7/8/8/8/R3K3 w - - 0 1")
    ray = view.fact("lines", view.root).ray("a1", (0, 1))
    assert ray.first_blocker.color is Color.BLACK and ray.visible == ("a2", "a3", "a4", "a5")
    assert ray.squares[-1] == "a8" and ray.xray is None


def test_knights_and_pawns_have_footprints_but_no_rays() -> None:
    tree = ENGINE.open(OpenRequest())
    view = tree.view()
    lines = view.fact("lines", tree.root)
    assert len(lines.rays) == 4 * 4 + 4 * 4 + 2 * 8
    assert {r.source for r in lines.rays} == {
        "a1",
        "c1",
        "d1",
        "f1",
        "h1",
        "a8",
        "c8",
        "d8",
        "f8",
        "h8",
    }
    knight = _piece(view, tree.root, "b1")
    assert (knight.attacks.empty, knight.attacks.friendly) == (("a3", "c3"), ("d2",))
    pawn = _piece(view, tree.root, "e2")
    assert pawn.attacks.empty == ("d3", "f3") and pawn.legal_destinations == ("e3", "e4")


def test_castling_and_promotion_destinations() -> None:
    _tree, view = _root("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    king = _piece(view, view.root, "e1")
    assert {"g1", "c1"} <= set(king.legal_destinations)
    assert not {"g1", "c1"} & set(king.attacks.empty)
    assert king.legal_moves.count("e1g1") == 1 and "e1h1" not in king.legal_moves
    flight = view.fact("king", view.root).white.flight_squares
    assert flight.kind is FlightKind.LEGAL and "g1" not in flight.squares
    _tree, view = _root("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    pawn = _piece(view, view.root, "a7")
    assert pawn.legal_moves == ("a7a8b", "a7a8n", "a7a8q", "a7a8r")
    assert pawn.legal_destinations == ("a8",)


def test_in_check_piece_keeps_geometry_but_lists_only_legal_moves() -> None:
    _tree, view = _root("4r1k1/8/8/8/8/R7/8/4K3 w - - 0 1")
    rook = _piece(view, view.root, "a3")
    attacked = rook.attacks
    assert len(attacked.empty + attacked.friendly + attacked.enemy) == 14
    assert rook.legal_moves == ("a3e3",) and rook.legal_destinations == ("e3",)


# -- §5 pawns: positional_v1 fixtures and new definitions ----------------------------------------


@pytest.mark.parametrize(
    ("fen", "square", "isolated", "doubled", "passed"),
    [
        ("4k3/8/8/8/8/8/P7/4K3 w - - 0 1", "a2", True, False, True),
        ("4k3/8/8/8/P7/8/P7/4K3 w - - 0 1", "a2", True, True, True),
        ("4k3/8/8/8/P7/8/P7/4K3 w - - 0 1", "a4", True, True, True),
        ("4k3/8/1P6/8/8/8/P7/4K3 w - - 0 1", "a2", False, False, True),
        ("4k3/8/8/1p6/P7/8/8/4K3 w - - 0 1", "a4", True, False, False),
        ("4k3/8/8/8/Pp6/8/8/4K3 w - - 0 1", "a4", True, False, True),
        ("4k3/8/8/8/P7/1p6/8/4K3 w - - 0 1", "a4", True, False, True),
        ("4k3/8/8/p7/1P6/8/8/4K3 b - - 0 1", "a5", True, False, False),
        ("4k3/8/1P6/p7/8/8/8/4K3 b - - 0 1", "a5", True, False, True),
    ],
)
def test_positional_v1_pawn_table(fen, square, isolated, doubled, passed) -> None:
    _tree, view = _root(fen)
    pawn = view.fact("pawns", view.root).at(square)
    assert (pawn.isolated, pawn.doubled, pawn.passed) == (isolated, doubled, passed)


def test_support_is_geometric_even_when_the_supporter_is_pinned() -> None:
    _tree, view = _root("k3r3/8/8/8/8/3P4/4P3/4K3 w - - 0 1")
    assert view.fact("pawns", view.root).at("d3").supporters == ("e2",)
    assert _piece(view, view.root, "e2").absolutely_pinned.pinner == "e8"


def test_open_files_are_not_semi_open() -> None:
    _tree, view = _root("4k3/2p5/8/8/8/8/1P6/4K3 w - - 0 1")
    a, b, c = view.fact("pawns", view.root).files[:3]
    assert a.state is FileState.OPEN
    assert b.state is FileState.SEMI_OPEN_BLACK  # no black pawn, a white one
    assert c.state is FileState.SEMI_OPEN_WHITE


def test_backward_phalanx_chains_islands_and_cones() -> None:
    _tree, view = _root("4k3/8/8/3p4/2P5/1P2P3/P7/4K3 w - - 0 1")
    pawns = view.fact("pawns", view.root)
    assert pawns.at("e3").isolated
    assert not pawns.at("e3").backward  # isolated pawns are never backward
    (chain,) = [c for c in pawns.chains if c.color is Color.WHITE]
    assert chain.squares == ("a2", "b3", "c4") and chain.bases == ("a2",) and chain.heads == ("c4",)
    assert pawns.islands.white == (("a", "b", "c"), ("e",)) and pawns.islands.black == (("d",),)
    assert "c4" not in pawns.outside_enemy_pawn_cones.white  # d5 covers c4 and e4 down to c1/e1
    assert "c1" not in pawns.outside_enemy_pawn_cones.white
    assert "d4" in pawns.outside_enemy_pawn_cones.white
    _tree, view = _root("4k3/8/8/3p4/8/2P1P3/3P4/4K3 w - - 0 1")
    pawns = view.fact("pawns", view.root)
    assert pawns.at("d2").supporters == () and pawns.at("c3").supporters == ("d2",)
    assert pawns.at("c3").phalanx == ()  # c and e are two files apart
    (chain,) = [c for c in pawns.chains if c.color is Color.WHITE]
    assert chain.bases == ("d2",) and chain.heads == ("c3", "e3")
    # a backward pawn: e3's neighbours are all ahead and its stop square e4 is attacked by d5
    _tree, view = _root("4k3/8/8/3p4/3P1P2/4P3/8/4K3 w - - 0 1")
    pawn = view.fact("pawns", view.root).at("e3")
    assert pawn.backward and not pawn.isolated
    _tree, view = _root("4k3/8/8/8/8/8/3PP3/4K3 w - - 0 1")
    assert view.fact("pawns", view.root).at("d2").phalanx == ("e2",)


def test_a_promoted_pawn_leaves_every_pawn_fact() -> None:
    _tree, view, nodes = _line("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8q")
    assert view.fact("pawns", nodes[1]).pawns == ()
    change = view.fact("delta", nodes[1])
    assert [(c.piece, c.after) for c in change.pawn_flags] == [(_pid("w.P.a7"), PROMOTED)]


# -- §6 king ------------------------------------------------------------------------------------


def test_square_behind_a_checked_king_has_no_geometric_attacker() -> None:
    _tree, view = _root("8/8/8/R3k3/8/8/8/K7 b - - 0 1")
    king = view.fact("king", view.root).black
    zone = {z.square: z.attackers for z in king.zone}
    assert zone["f5"] == () and zone["d5"] != ()
    assert king.flight_squares.kind is FlightKind.LEGAL
    assert "f5" not in king.flight_squares.squares  # legal: from `status`


def test_shield_and_files_near_and_geometric_flight() -> None:
    _tree, view = _root("6k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1")
    white = view.fact("king", view.root).white
    assert white.shield == ("f2", "g2", "h2")
    assert [f.file for f in white.files_near] == ["f", "g", "h"]
    assert white.flight_squares.kind is FlightKind.GEOMETRIC
    assert white.flight_squares.squares == ("f1", "h1")
    black = view.fact("king", view.root).black
    assert black.shield == ("f7", "g7", "h7")
    _tree, view = _root("4k3/4p3/8/8/8/8/8/K6R w - - 0 1")
    assert view.fact("king", view.root).black.shield == ("e7",)
    _tree, view = _root("8/8/8/8/8/8/1P6/1K2k3 w - - 0 1")
    assert view.fact("king", view.root).white.shield == ("b2",)
    _tree, view = _root("1K6/1P6/8/8/8/8/8/4k3 w - - 0 1")
    assert view.fact("king", view.root).white.shield == ()  # the black king is on its last rank


# -- §7 deltas ----------------------------------------------------------------------------------


def test_d04_en_passant_file_states_and_capture() -> None:
    _tree, view, nodes = _line("8/8/8/3pP3/8/8/8/4K2k w - d6 0 1", "e5d6")
    change = view.fact("delta", nodes[1])
    files = {c.file: (c.before.state, c.after.state) for c in change.files}
    assert files == {
        "d": (FileState.SEMI_OPEN_WHITE, FileState.SEMI_OPEN_BLACK),
        "e": (FileState.SEMI_OPEN_BLACK, FileState.OPEN),
    }
    flags = {c.piece: c.after for c in change.piece_flags}
    assert flags[_pid("b.P.d5")] == CAPTURED


def test_d07_capture_promotion_keeps_identity_and_flags() -> None:
    _tree, view, nodes = _line("1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7b8q")
    change = view.fact("delta", nodes[1])
    assert [(c.piece, c.after) for c in change.pawn_flags] == [(_pid("w.P.a7"), PROMOTED)]
    assert _pid("b.R.b8") in {c.piece for c in change.piece_flags}
    assert all(p.source != _pid("b.R.b8") for p in change.piece_attacks.began)
    assert any(c.piece == _pid("w.P.a7") for c in change.square_control.began)


@pytest.mark.parametrize(
    ("move", "rook", "square"), [("e1g1", "w.R.h1", "f2"), ("e1c1", "w.R.a1", "d2")]
)
def test_d05_castling_moves_the_rook_under_its_own_identity(move, rook, square) -> None:
    _tree, view, nodes = _line("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", move)
    change = view.fact("delta", nodes[1])
    began = {(c.piece, c.square) for c in change.square_control.began}
    assert (_pid(rook), square) in began
    assert all(c.piece.value.startswith("w.") for c in change.square_control.began)
    assert view.node(nodes[1]).piece_at(square[0] + "1") == _pid(rook)


@pytest.mark.parametrize("case", ["D08", "D19"])
def test_d08_d19_an_unmoved_pin_appears_when_a_blocker_leaves(case: str) -> None:
    _tree, view, nodes = _line("4k3/4n3/8/8/8/8/4B3/K3R3 w - - 0 1", "e2f3")
    change = view.fact("delta", nodes[1])
    (pin,) = change.pins.began
    assert (pin.pinner, pin.pinned, pin.king) == (_pid("w.R.e1"), _pid("b.N.e7"), _pid("b.K.e8"))
    assert any(c.piece == _pid("w.R.e1") for c in change.square_control.began)


def test_d09_a_capture_changes_the_file_state() -> None:
    _tree, view, nodes = _line("4k3/8/8/p7/8/8/8/R3K3 w - - 0 1", "a1a5")
    (file_change,) = view.fact("delta", nodes[1]).files
    assert (file_change.file, file_change.before.state, file_change.after.state) == (
        "a",
        FileState.SEMI_OPEN_WHITE,
        FileState.OPEN,
    )


def test_d10_an_unmoved_pawn_gains_a_supporter() -> None:
    _tree, view, nodes = _line("4k3/8/8/3P4/8/8/4P3/4K3 w - - 0 1", "e2e4")
    began = view.fact("delta", nodes[1]).pawn_supports.began
    assert [(p.source, p.target) for p in began] == [(_pid("w.P.e2"), _pid("w.P.d5"))]


def test_d20_an_unmoved_pawn_changes_flags() -> None:
    _tree, view, nodes = _line("4k3/8/8/3p4/2P1P3/8/8/4K3 w - - 0 1", "e4d5")
    flags = {c.piece: (c.before, c.after) for c in view.fact("delta", nodes[1]).pawn_flags}
    before, after = flags[_pid("w.P.c4")]
    assert before.isolated and not after.isolated  # d5 is now a friendly pawn
    assert not before.passed and after.passed  # and no black pawn is left


def test_e12_a_temporary_pin_on_a_later_participant() -> None:
    _tree, view, nodes = _line("r5k1/8/8/8/3p4/8/4N3/4K3 b - - 0 1", "a8e8", "e1f1", "e8a8", "e2d4")
    pins = [
        [
            (p.absolutely_pinned.pinner, p.square)
            for p in view.fact("pieces", node).pieces
            if p.absolutely_pinned is not None
        ]
        for node in nodes
    ]
    assert pins == [[], [("e8", "e2")], [], [], []]
    ended = view.fact("delta", nodes[2]).pins.ended
    assert [(p.pinner, p.pinned, p.king) for p in ended] == [
        (_pid("b.R.a8"), _pid("w.N.e2"), _pid("w.K.e1"))
    ]


def test_e15_the_castling_rook_keeps_its_identity_in_deltas() -> None:
    _tree, view, nodes = _line("4k3/5p2/8/8/8/8/8/4K2R w K - 0 1", "e1g1", "e8d8", "f1f7")
    change = view.fact("delta", nodes[3])
    assert [(p.source, p.target) for p in change.piece_attacks.ended] == [
        (_pid("w.R.h1"), _pid("b.P.f7"))
    ]
    assert [(c.piece, c.after) for c in change.pawn_flags] == [(_pid("b.P.f7"), CAPTURED)]
    first = view.fact("delta", nodes[1])
    assert any(c.piece == _pid("w.R.h1") and c.square == "f2" for c in first.square_control.began)


# -- same_side_delta (§7.2) -------------------------------------------------------------------


def test_same_side_delta_is_not_applicable_without_a_grandparent() -> None:
    _tree, view, nodes = _line(None, "e4", "e5", "Nf3")
    reason = NotApplicable("no same-side ancestor in the tree")
    assert view.fact("same_side_delta", nodes[0]) == reason
    assert view.fact("same_side_delta", nodes[1]) == reason
    record = view.fact("same_side_delta", nodes[2])
    assert record.legal_move_count == (20, 29)
    tree = ENGINE.open(OpenRequest(root=RootSpec(moves=("e4", "e5"))))
    assert tree.view().fact("same_side_delta", tree.root) == reason  # pre-root is not a node


def test_same_side_delta_capture_in_either_ply() -> None:
    # ply 1: White captures d5; ply 2: Black recaptures on d5
    _tree, view, nodes = _line(None, "e4", "d5", "exd5", "Qxd5")
    first = view.fact("same_side_delta", nodes[3])  # Black to move at e4 … d5 and after exd5
    assert any(m.piece == _pid("b.P.d7") and m.after == CAPTURED for m in first.pieces)
    second = view.fact("same_side_delta", nodes[4])  # White to move: e-pawn captured
    assert any(m.piece == _pid("w.P.e2") and m.after == CAPTURED for m in second.pieces)
    gone = [c for c in second.capturable_now if c.after == CAPTURED]
    assert gone == [] or all(c.piece.value.startswith("b.") for c in gone)
    _tree, view, nodes = _line("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1", "exd5", "Ke7")
    record = view.fact("same_side_delta", nodes[2])
    assert [(c.piece, c.before, c.after) for c in record.capturable_now] == [
        (_pid("b.P.d5"), True, CAPTURED)
    ]


def test_same_side_delta_promotion_castling_and_en_passant() -> None:
    _tree, view, nodes = _line("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a8=Q+", "Kd7")
    record = view.fact("same_side_delta", nodes[2])
    promoted = next(m for m in record.pieces if m.piece == _pid("w.P.a7"))
    assert (promoted.before, promoted.after) == (PieceType.PAWN, PieceType.QUEEN)
    assert any(d.piece == _pid("w.P.a7") for d in record.legal_destinations)

    # promotion in the second ply: Black's new queen becomes capturable
    _tree, view, nodes = _line("4k3/8/8/8/8/8/p7/1R2K3 w - - 0 1", "Kf2", "a1=Q")
    record = view.fact("same_side_delta", nodes[2])
    assert [(c.piece, c.before, c.after) for c in record.capturable_now] == [
        (_pid("b.P.a2"), False, True)
    ]
    assert [(p.source, p.target) for p in record.legal_captures.gained] == [
        (_pid("w.R.b1"), _pid("b.P.a2"))
    ]

    _tree, view, nodes = _line("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "O-O", "O-O-O")
    record = view.fact("same_side_delta", nodes[2])
    king = next(d for d in record.legal_destinations if d.piece == _pid("w.K.e1"))
    assert {"c1", "g1"} <= set(king.lost)
    assert "g1" not in record.flight_squares.lost  # castling is never a flight square
    rook = next(d for d in record.legal_destinations if d.piece == _pid("w.R.h1"))
    assert "f8" in rook.gained  # the castled rook now stands on f1
    assert [(c.piece, c.before, c.after) for c in record.capturable_now] == [
        (_pid("b.R.a8"), True, False),
        (_pid("b.R.h8"), True, False),
    ]

    # en passant in the second ply (White captures; Black's d7 pawn disappears)
    _tree, view, nodes = _line("4k3/3p4/8/4P3/8/8/8/4K3 b - - 0 1", "d5", "exd6", "Kf7")
    record = view.fact("same_side_delta", nodes[2])
    assert any(m.piece == _pid("b.P.d7") and m.after == CAPTURED for m in record.pieces)
    # … and in the first ply, seen from the side that captured
    record = view.fact("same_side_delta", nodes[3])
    assert [(c.piece, c.before, c.after) for c in record.capturable_now] == [
        (_pid("b.P.d7"), True, CAPTURED)
    ]
    assert [(p.source, p.target) for p in record.legal_captures.lost] == [
        (_pid("w.P.e5"), _pid("b.P.d7"))
    ]


# -- invariants (§10.2) ------------------------------------------------------------------------


def _random_lines(seed: int, games: int, plies: int = 70) -> list[tuple[str, ...]]:
    rng = random.Random(seed)
    out = []
    for _ in range(games):
        board = chess.Board()
        moves = []
        while len(moves) < plies and not board.is_game_over():
            legal = list(board.legal_moves)
            captures = [m for m in legal if board.is_capture(m) or m.promotion]
            move = rng.choice(captures if captures and rng.random() < 0.4 else legal)
            moves.append(move.uci())
            board.push(move)
        out.append(tuple(moves))
    return out


def test_geometry_invariants_on_random_games() -> None:
    for moves in _random_lines(7, 12):
        _tree, view, nodes = _line(None, *moves)
        for node_id in nodes:
            node = view.node(node_id)
            board = chess.Board(node.fen)
            pieces = view.fact("pieces", node_id)
            lines = view.fact("lines", node_id)
            squares = view.fact("squares", node_id)
            for piece in pieces.pieces:
                sq = chess.parse_square(piece.square)
                parts = (piece.attacks.empty, piece.attacks.friendly, piece.attacks.enemy)
                flat = [s for part in parts for s in part]
                assert len(flat) == len(set(flat))  # disjoint
                assert set(flat) == {chess.square_name(t) for t in board.attacks(sq)}  # cover
                visible = {s for r in lines.rays if r.source == piece.square for s in r.visible}
                if piece.piece_type in (PieceType.BISHOP, PieceType.ROOK, PieceType.QUEEN):
                    assert visible == set(flat)
                own = Color.WHITE if board.color_at(sq) else Color.BLACK
                assert (piece.absolutely_pinned is not None) == board.is_pinned(
                    own is Color.WHITE, sq
                )
                if piece.absolutely_pinned is not None:
                    pin = piece.absolutely_pinned
                    king = (
                        view.fact("king", node_id).white
                        if own is Color.WHITE
                        else view.fact("king", node_id).black
                    )
                    ray = _walk_from(board, king.square, pin.direction)
                    assert ray[:2] == [piece.square, pin.pinner]
                here = squares.at(piece.square)
                mine, theirs = (
                    (here.white_attackers, here.black_attackers)
                    if own is Color.WHITE
                    else (here.black_attackers, here.white_attackers)
                )
                assert mine == piece.defenders and theirs == piece.attackers
            pairs = [frozenset(b.pieces) for b in lines.batteries]
            assert len(pairs) == len(set(pairs))  # every battery once


def _walk_from(board: chess.Board, square: str, direction) -> list[str]:
    f, r = (
        chess.square_file(chess.parse_square(square)),
        chess.square_rank(chess.parse_square(square)),
    )
    out = []
    f, r = f + direction[0], r + direction[1]
    while 0 <= f < 8 and 0 <= r < 8:
        if board.piece_at(chess.square(f, r)) is not None:
            out.append(chess.square_name(chess.square(f, r)))
        f, r = f + direction[0], r + direction[1]
    return out


def test_delta_applied_to_the_parent_sets_gives_the_child_sets() -> None:
    for moves in _random_lines(11, 10):
        _tree, view, nodes = _line(None, *moves)
        for parent_id, child_id in pairwise(nodes):
            parent, child = view.node(parent_id), view.node(child_id)
            records = {}
            for node in (parent, child):
                records[node.node_id] = relations_of(
                    {f: view.fact(f, node.node_id) for f in ("pieces", "lines", "pawns", "king")},
                    node.pieces,
                )
            before, after = records[parent_id], records[child_id]
            change = view.fact("delta", child_id)
            for component in SET_COMPONENTS:
                make = MAKERS[component]
                old = {make(r) for r in getattr(before, component)}
                new = {make(r) for r in getattr(after, component)}
                diff = getattr(change, component)
                assert (old - set(diff.ended)) | set(diff.began) == new
                assert set(diff.began).isdisjoint(old) and set(diff.ended) <= old


# -- equivalences and `ensure` (§9, §10.3) ------------------------------------------------------


def _all_records(view, nodes):
    return {(f, n): view.fact(f, n) for n in nodes for f in view.families()}


def test_eager_tree_equals_minimal_tree_plus_ensure() -> None:
    for moves in _random_lines(3, 4, plies=40):
        _full, full_view, nodes = _line(None, *moves)
        minimal, _view, same_nodes = _line(None, *moves, families=())
        assert nodes == same_nodes
        rev = ENGINE.ensure(minimal, EnsureRequest(nodes, tuple(f.name for f in REGISTRY)))
        assert rev == minimal.rev == 3
        assert _all_records(minimal.view(), nodes) == _all_records(full_view, nodes)


def test_position_records_are_equal_across_transpositions_with_different_clocks() -> None:
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - {} 3"
    _a, early = _root(fen.format(2))
    _b, late = _root(fen.format(37))
    assert early.node(early.root).position_key == late.node(late.root).position_key
    for family in ("status", "pieces", "squares", "lines", "pawns", "king"):
        assert early.fact(family, early.root) == late.fact(family, late.root)
    tree = ENGINE.open(OpenRequest())
    ENGINE.extend(
        tree,
        ExtendRequest(
            (InputLine("a", ("Nf3", "Nf6", "g3")), InputLine("b", ("g3", "Nf6", "Nf3"))), EXPLORED
        ),
    )
    view = tree.view()
    a = view.input_line("a", EXPLORED.kind).nodes[-1]
    b = view.input_line("b", EXPLORED.kind).nodes[-1]
    assert view.fact("pieces", a) is view.fact("pieces", b)
    assert view.fact("delta", a) != view.fact("delta", b)  # edges differ


def test_position_families_never_see_the_node_board(monkeypatch) -> None:
    seen: list[chess.Board] = []
    original = PiecesFamily.compute

    def spy(self, ctx):
        seen.append(ctx.board)
        return original(self, ctx)

    monkeypatch.setattr(PiecesFamily, "compute", spy)
    _line("4k3/8/8/8/8/8/4P3/4K3 w - - 17 40", "e4", "Kd7")
    assert seen and all(b.halfmove_clock == 0 and b.fullmove_number == 1 for b in seen)
    assert all(not b.move_stack for b in seen)


def test_eager_set_is_closed_under_requires() -> None:
    tree = ENGINE.open(OpenRequest(families=("king",)))
    view = tree.view()
    assert view.eager() == {"status", "draw", "move", "king", "squares", "pawns"}
    assert view.fact("pieces", tree.root) == NotComputed("not requested")
    assert view.manifest()[0].eager == ("status", "draw", "move", "squares", "pawns", "king")
    tree = ENGINE.open(OpenRequest(families=("delta",)))
    assert {"pieces", "lines", "pawns", "king", "squares"} <= tree.view().eager()


def test_ensure_resolves_parent_and_grandparent_dependencies() -> None:
    tree, _view, nodes = _line(None, "e4", "e5", "Nf3", families=())
    rev = ENGINE.ensure(tree, EnsureRequest((nodes[3],), ("delta",)))
    view = tree.view()
    assert rev == 3 and view.manifest()[-1].request == "ensure"
    assert not isinstance(view.fact("delta", nodes[3]), NotComputed)
    assert not isinstance(view.fact("pieces", nodes[2]), NotComputed)  # the parent
    assert isinstance(view.fact("pieces", nodes[1]), NotComputed)
    ENGINE.ensure(tree, EnsureRequest((nodes[3],), ("same_side_delta",)))
    view = tree.view()
    assert not isinstance(view.fact("same_side_delta", nodes[3]), NotComputed)
    assert not isinstance(view.fact("pieces", nodes[1]), NotComputed)  # the grandparent
    assert view.fact("delta", nodes[2]) == NotComputed("not requested")
    assert ENGINE.ensure(tree, EnsureRequest((tree.root,), ("delta",))) == tree.rev  # no edge


def test_ensure_refuses_atomically_and_never_recomputes(monkeypatch) -> None:
    tree, _view, nodes = _line(None, "e4", "e5", families=())
    before = (tree.rev, len(tree._store.facts))
    with pytest.raises(InvalidRequestError, match="unknown fact families"):
        ENGINE.ensure(tree, EnsureRequest(nodes, ("pieces", "patterns")))
    with pytest.raises(InvalidRequestError, match="unknown nodes"):
        ENGINE.ensure(
            tree, EnsureRequest((*nodes, replace(nodes[0], value="n_nowhere")), ("pieces",))
        )
    with pytest.raises(InvalidRequestError):
        ENGINE.ensure(tree, EnsureRequest((), ("pieces",)))
    assert (tree.rev, len(tree._store.facts)) == before

    pinned = tree.view()
    rev = ENGINE.ensure(tree, EnsureRequest(nodes, ("pieces",)))
    assert rev == before[0] + 1
    assert pinned.fact("pieces", nodes[1]) == NotComputed("not requested")  # pinned view
    assert not isinstance(tree.view().fact("pieces", nodes[1]), NotComputed)

    calls = []
    original = PiecesFamily.compute
    monkeypatch.setattr(
        PiecesFamily, "compute", lambda self, ctx: calls.append(1) or original(self, ctx)
    )
    manifest = len(tree.view().manifest())
    assert ENGINE.ensure(tree, EnsureRequest(nodes, ("pieces", "status"))) == rev  # nothing missing
    assert calls == [] and len(tree.view().manifest()) == manifest


def test_ensure_refuses_a_family_the_session_does_not_have() -> None:
    small = FactEngine(REGISTRY[:4])
    tree = small.open(OpenRequest())
    small.extend(tree, ExtendRequest((InputLine("l", ("e4",)),), PLAYED))
    nodes = tree.view().input_line("l").nodes
    with pytest.raises(InvalidRequestError, match="unknown fact families"):
        ENGINE.ensure(tree, EnsureRequest(nodes, ("pieces",)))


def test_registry_rejects_scope_violations_and_order() -> None:
    class NodeFamily:
        name, version, scope, fact_class, requires = "n", "n_v1", Scope.NODE, None, ("status",)

    class BadPosition:
        name, version, scope, fact_class, requires = "p", "p_v1", Scope.POSITION, None, ("n",)

    class BadSpan:
        name, version, scope, fact_class, requires = "s", "s_v1", Scope.SPAN, None, ("move",)

    with pytest.raises(ValueError, match="cannot require"):
        FactEngine((StatusFamily(), NodeFamily(), BadPosition()))
    with pytest.raises(ValueError, match="cannot require"):
        FactEngine((StatusFamily(), MoveFamily(), BadSpan()))
    with pytest.raises(ValueError, match="not registered before"):
        FactEngine((NodeFamily(), StatusFamily()))


# -- colour mirror (§10.4) -----------------------------------------------------------------------


def _m(square: str) -> str:
    return square[0] + str(9 - int(square[1]))


def _mirror_piece(row: tuple) -> tuple:
    """A plain `pieces` row seen in the colour mirror (legal moves compared by count)."""

    def rels(items):
        return tuple(sorted(((_m(s), t, p) for s, t, p in items), key=lambda r: _index(r[0])))

    def sqs(items):
        return tuple(sorted((_m(s) for s in items), key=_index))

    sq, color, kind, (empty, friendly, enemy), attackers, defenders, *rest = row
    ac, dc, lowest, awd, aed, pin, dest, moves, capturable = rest
    return (
        _m(sq),
        "black" if color == "white" else "white",
        kind,
        (sqs(empty), sqs(friendly), sqs(enemy)),
        rels(attackers),
        rels(defenders),
        ac,
        dc,
        lowest,
        awd,
        aed,
        None if pin is None else (_m(pin[0]), (pin[1][0], -pin[1][1])),
        dest if dest == "NOT_OBSERVED" else sqs(dest),
        _count(moves),
        capturable,
    )


def _count(moves):
    return moves if moves == "NOT_OBSERVED" else len(moves)


def _index(square: str) -> int:
    return chess.parse_square(square)


def _swap(color: str) -> str:
    return "black" if color == "white" else "white"


def _flip(direction) -> tuple[int, int]:
    return (direction[0], -direction[1])


def _msqs(items) -> tuple[str, ...]:
    return tuple(sorted((_m(s) for s in items), key=_index))


def _mrels(items) -> tuple:
    return tuple(sorted(((_m(s), t, p) for s, t, p in items), key=lambda r: _index(r[0])))


def _mirror_squares(rows: list[tuple]) -> list[tuple]:
    out = [
        (_m(sq), None if occ is None else (_swap(occ[0]), occ[1]), _mrels(b), _mrels(w), bc, wc)
        for sq, occ, w, b, wc, bc in rows
    ]
    return sorted(out, key=lambda r: _index(r[0]))


def _mirror_rays(rays: list[tuple]) -> list[tuple]:
    def occ(o):
        return (_m(o[0]), _swap(o[1]), o[2])

    out = [
        (
            _m(source),
            _flip(d),
            tuple(_m(s) for s in squares),  # near to far is kept
            tuple(occ(o) for o in occupants),
            edge_empty,
            unblocked,
            None if first is None else occ(first),
            tuple(_m(s) for s in visible),
            None if xray is None else (tuple(_m(s) for s in xray[0]), occ(xray[1]), occ(xray[2])),
        )
        for source, d, squares, occupants, edge_empty, unblocked, first, visible, xray in rays
    ]
    return sorted(out, key=lambda r: (_index(r[0]), r[1]))


def _mirror_batteries(batteries: list[tuple]) -> list[tuple]:
    """A line is normalized lower → higher square, so a diagonal maps to (−df, dr)."""

    out = []
    for (a, b), line in batteries:
        low, high = sorted((_m(a), _m(b)), key=_index)
        swapped = low != _m(a)
        out.append(((low, high), (-line[0], line[1]) if swapped else _flip(line)))
    return sorted(out, key=lambda x: (_index(x[0][0]), _index(x[0][1])))


_STATE = {"semi_open_white": "semi_open_black", "semi_open_black": "semi_open_white"}


def _mirror_file(f: tuple) -> tuple:
    return (f[0], f[2], f[1], _STATE.get(f[3], f[3]))


def _mirror_pawns(p: dict) -> dict:
    pawns = sorted(
        (
            (_m(sq), _swap(c), *flags, _msqs(sup), _msqs(ph))
            for sq, c, *flags, sup, ph in p["pawns"]
        ),
        key=lambda r: _index(r[0]),
    )
    chains = sorted(
        ((_swap(c), _msqs(sq), _msqs(bases), _msqs(heads)) for c, sq, bases, heads in p["chains"]),
        key=lambda c: _index(c[1][0]),
    )
    return {
        "pawns": pawns,
        "chains": chains,
        "islands": {"white": p["islands"]["black"], "black": p["islands"]["white"]},
        "files": [_mirror_file(f) for f in p["files"]],
        "cones": {"white": _msqs(p["cones"]["black"]), "black": _msqs(p["cones"]["white"])},
    }


def _mirror_king(k: tuple) -> tuple:
    color, square, zone, shield, files_near, (kind, flight) = k
    return (
        _swap(color),
        _m(square),
        tuple(sorted(((_m(sq), _mrels(a)) for sq, a in zone), key=lambda z: _index(z[0]))),
        _msqs(shield),
        tuple(_mirror_file(f) for f in files_near),
        (kind, _msqs(flight)),
    )


def test_colour_mirror_gives_mirrored_records() -> None:
    """F2-D §10.4 over every POSITION family; directions map to (df, −dr)."""

    for moves in _random_lines(5, 6, plies=50):
        board = chess.Board()
        for uci in moves:
            board.push_uci(uci)
            if board.is_game_over():
                break
            _a, view = _root(board.fen())
            _b, mirror = _root(board.mirror().fen())
            here, there = view.root, mirror.root
            ours = sorted(
                (_mirror_piece(row) for row in plain_pieces(view.fact("pieces", here))),
                key=lambda r: _index(r[0]),
            )
            theirs = [
                (*row[:13], _count(row[13]), row[14])
                for row in plain_pieces(mirror.fact("pieces", there))
            ]
            assert ours == theirs
            assert _mirror_squares(plain_squares(view.fact("squares", here))) == plain_squares(
                mirror.fact("squares", there)
            )
            rays, batteries = plain_lines(view.fact("lines", here))
            m_rays, m_batteries = plain_lines(mirror.fact("lines", there))
            assert _mirror_rays(rays) == m_rays
            assert _mirror_batteries(batteries) == m_batteries
            assert _mirror_pawns(plain_pawns(view.fact("pawns", here))) == plain_pawns(
                mirror.fact("pawns", there)
            )
            kings, m_kings = (
                plain_king(view.fact("king", here)),
                plain_king(mirror.fact("king", there)),
            )
            assert _mirror_king(kings["white"]) == m_kings["black"]
            assert _mirror_king(kings["black"]) == m_kings["white"]


def test_battery_lines_under_the_mirror() -> None:
    _a, view = _root("4k3/8/8/8/8/8/2B5/3QK3 w - - 0 1")
    _b, mirror = _root(chess.Board("4k3/8/8/8/8/8/2B5/3QK3 w - - 0 1").mirror().fen())
    assert plain_lines(view.fact("lines", view.root))[1] == [(("d1", "c2"), (-1, 1))]
    assert plain_lines(mirror.fact("lines", mirror.root))[1] == [(("c7", "d8"), (1, 1))]


# -- cost (§1.9) ---------------------------------------------------------------------------------


def test_key_board_has_only_the_position() -> None:
    tree = ENGINE.open(OpenRequest(root=RootSpec(fen="4k3/8/8/8/8/8/4P3/4K3 w - - 33 70")))
    board = key_board(tree.view().node(tree.root).position_key)
    assert (board.halfmove_clock, board.fullmove_number, board.move_stack) == (0, 1, [])
