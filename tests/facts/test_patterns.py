"""F3: `patterns` and `pattern_delta` (F3-D §3, §4, §7.2–§7.5)."""

import random
from itertools import pairwise

import chess
import pytest
from geometry_auditor import plain_pattern_delta, plain_patterns

from calliope.facts import (
    EXPLORED,
    PLAYED,
    ExtendRequest,
    FactEngine,
    InputLine,
    OpenRequest,
    RootSpec,
)
from calliope.facts.families.pattern_delta import DefenceEndReason
from calliope.facts.families.pieces import PIECE_ORDER_RANK
from calliope.facts.keys import Color, PieceType
from calliope.facts.request import EnsureRequest
from calliope.facts.values import NotApplicable

ENGINE = FactEngine()
EMPTY = {"multi": [], "rel": [], "skw": [], "disc": [], "sole": [], "back": []}


def _root(fen: str):
    tree = ENGINE.open(OpenRequest(root=RootSpec(fen=fen)))
    return tree.view(), tree.root


def _line(fen: str | None, *moves: str, **kwargs):
    tree = ENGINE.open(OpenRequest(root=RootSpec(fen=fen), **kwargs))
    ENGINE.extend(tree, ExtendRequest((InputLine("l", moves),), PLAYED))
    view = tree.view()
    return tree, view, view.input_line("l").nodes


def _p(square: str, kind: str, pinned: bool = False) -> tuple:
    return (square, kind, pinned)


# -- §3: every fixture, as the complete record ----------------------------------------------------

FIXTURES = {
    "A1": (
        "r3k3/2N5/8/8/8/8/8/4K3 b - - 0 1",
        {
            "multi": [
                (_p("c7", "knight"), ((_p("a8", "rook"), "above"), (_p("e8", "king"), "above")))
            ]
        },
    ),
    "A2": (
        "4k3/8/8/2n1b3/3P4/8/8/4K3 w - - 0 1",
        {
            "multi": [
                (_p("d4", "pawn"), ((_p("c5", "knight"), "above"), (_p("e5", "bishop"), "above")))
            ]
        },
    ),
    "A3": (
        "4k3/8/2r1qb2/8/3N4/8/1K6/8 w - - 0 1",
        {
            "multi": [
                (
                    _p("d4", "knight", True),
                    ((_p("c6", "rook"), "above"), (_p("e6", "queen"), "above")),
                )
            ]
        },
    ),
    "A4": ("4k3/8/2r1B3/8/3N4/8/8/4K3 w - - 0 1", {}),
    "A5": (
        "4k3/8/8/3q4/8/1n6/B7/4K3 w - - 0 1",
        {
            "rel": [(_p("a2", "bishop"), (1, 1), _p("b3", "knight"), _p("d5", "queen"))],
            "disc": [(_p("d5", "queen"), (-1, -1), _p("b3", "knight"), _p("a2", "bishop"))],
        },
    ),
    "A6": (
        "4k3/8/8/3b4/8/1n6/B7/4K3 w - - 0 1",
        {"disc": [(_p("d5", "bishop"), (-1, -1), _p("b3", "knight"), _p("a2", "bishop"))]},
    ),
    "A7": (
        "8/8/8/8/R2k3q/8/8/1K6 b - - 0 1",
        {
            "skw": [(_p("a4", "rook"), (1, 0), _p("d4", "king"), _p("h4", "queen"))],
            "disc": [(_p("h4", "queen"), (-1, 0), _p("d4", "king"), _p("a4", "rook"))],
        },
    ),
    "A8": (
        "4k3/8/8/8/R2q3r/8/8/4K3 w - - 0 1",
        {
            "skw": [(_p("a4", "rook"), (1, 0), _p("d4", "queen"), _p("h4", "rook"))],
            "disc": [(_p("h4", "rook"), (-1, 0), _p("d4", "queen"), _p("a4", "rook"))],
        },
    ),
    "A9": (
        "3qk3/8/8/8/3B4/8/8/3RK3 w - - 0 1",
        {
            "rel": [(_p("d8", "queen"), (0, -1), _p("d4", "bishop"), _p("d1", "rook"))],
            "disc": [(_p("d1", "rook"), (0, 1), _p("d4", "bishop"), _p("d8", "queen"))],
        },
    ),
    "A10": (
        "4k3/8/8/8/8/8/8/R2K3q w - - 0 1",
        {
            "skw": [(_p("h1", "queen"), (-1, 0), _p("d1", "king"), _p("a1", "rook"))],
            "disc": [(_p("a1", "rook"), (1, 0), _p("d1", "king"), _p("h1", "queen"))],
        },
    ),
    "A11": (
        "4k3/8/3p4/2n1b3/8/8/8/2R1R2K b - - 0 1",
        {"sole": [(_p("d6", "pawn"), (_p("c5", "knight"), _p("e5", "bishop", True)))]},
    ),
    "A12": ("4k3/q7/3p4/2n1b3/8/8/8/2R1R2K b - - 0 1", {}),
    "A13": (
        "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1",
        {"back": [(_p("g8", "king"), (_p("f7", "pawn"), _p("g7", "pawn"), _p("h7", "pawn")), ())]},
    ),
    "A14": ("6k1/5pp1/7p/8/8/8/8/R5K1 w - - 0 1", {}),
    "A15": (
        "6k1/5p1p/8/8/8/8/1B6/R5K1 w - - 0 1",
        {"back": [(_p("g8", "king"), (_p("f7", "pawn"), _p("h7", "pawn")), ("g7",))]},
    ),
    "A16": ("8/5ppp/6k1/8/8/8/8/R5K1 w - - 0 1", {}),
    "A17": (
        "3r3k/3r4/8/3N4/3K4/8/8/7r w - - 0 1",
        {"disc": [(_p("d8", "rook"), (0, -1), _p("d7", "rook"), _p("d5", "knight", True))]},
    ),
    # F3-D erratum: the design's A18 and A20 omitted one pattern each (F3 record §2).
    "A18": (
        "4k3/8/8/8/8/2b5/1N1N4/2K1r3 w - - 0 1",
        {
            "multi": [
                (_p("c3", "bishop"), ((_p("b2", "knight"), "equal"), (_p("d2", "knight"), "equal")))
            ],
            "sole": [(_p("c1", "king"), (_p("b2", "knight"), _p("d2", "knight")))],
        },
    ),
    "A19": (
        "k7/8/8/8/8/8/PP6/K7 w - - 0 1",
        {"back": [(_p("a1", "king"), (_p("a2", "pawn"), _p("b2", "pawn")), ())]},
    ),
    "A20": (
        "k5r1/8/8/8/8/8/5PnP/6K1 w - - 0 1",
        {
            "disc": [(_p("g8", "rook"), (0, -1), _p("g2", "knight"), _p("g1", "king"))],
            "back": [(_p("g1", "king"), (_p("f2", "pawn"), _p("h2", "pawn")), ("g2",))],
        },
    ),
    "A21": ("k7/8/8/8/8/8/5PnP/6K1 w - - 0 1", {}),
}


@pytest.mark.parametrize("case", sorted(FIXTURES, key=lambda c: int(c[1:])))
def test_fixture_is_the_complete_record(case: str) -> None:
    fen, expected = FIXTURES[case]
    view, root = _root(fen)
    assert plain_patterns(view.fact("patterns", root)) == {**EMPTY, **expected}


def test_a_pawn_attacking_the_king_and_a_piece() -> None:
    view, root = _root("8/8/8/2k1n3/3P4/8/8/4K3 b - - 0 1")
    assert plain_patterns(view.fact("patterns", root))["multi"] == [
        (_p("d4", "pawn"), ((_p("c5", "king"), "above"), (_p("e5", "knight"), "above")))
    ]


def test_a_king_actor_has_every_target_below() -> None:
    view, root = _root("8/8/8/8/8/2k5/1r6/Kn6 w - - 0 1")
    (multi,) = [
        m for m in view.fact("patterns", root).multi_target_attacks if m.actor.square == "a1"
    ]
    assert [(t.piece.square, t.order.value) for t in multi.targets] == [
        ("b1", "below"),
        ("b2", "below"),
    ]


def test_three_sliders_on_one_line_count_only_the_first_two_occupants() -> None:
    view, root = _root("4k3/8/8/3r4/8/3b4/8/3QK3 w - - 0 1")
    patterns = plain_patterns(view.fact("patterns", root))
    assert patterns["skw"] == []
    assert patterns["rel"] == [(_p("d1", "queen"), (0, 1), _p("d3", "bishop"), _p("d5", "rook"))]
    assert patterns["disc"] == [(_p("d5", "rook"), (0, -1), _p("d3", "bishop"), _p("d1", "queen"))]


def test_both_back_ranks_at_once() -> None:
    view, root = _root("6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 1")
    assert [b[0][0] for b in plain_patterns(view.fact("patterns", root))["back"]] == ["g1", "g8"]


def test_a_pinned_sole_defender_is_kept_and_flagged() -> None:
    # the e7 knight is pinned by the e1 rook and is the only defender of c6 (itself pinned by
    # the a4 bishop) and g6
    view, root = _root("4k3/4n3/2b3b1/8/B7/8/7K/4R1R1 b - - 0 1")
    assert plain_patterns(view.fact("patterns", root))["sole"] == [
        (_p("e7", "knight", True), (_p("c6", "bishop", True), _p("g6", "bishop")))
    ]


def test_an_empty_en_passant_target_square_is_never_a_target() -> None:
    _tree, view, nodes = _line("4k3/3p4/5n2/4P3/8/8/8/4K3 b - - 0 1", "d7d5")
    pawn = view.fact("pieces", nodes[1]).at("e5")
    assert "d6" in pawn.attacks.empty and pawn.attacks.enemy == ("f6",)
    assert view.fact("status", nodes[1]).legal_captures[0].en_passant
    assert plain_patterns(view.fact("patterns", nodes[1]))["multi"] == []


def test_a_promotion_creates_the_new_sliders_patterns() -> None:
    _tree, view, nodes = _line("1q2k3/P7/8/8/8/8/8/b3K3 w - - 0 1", "a7a8q")
    assert plain_patterns(view.fact("patterns", nodes[1]))["multi"] == [
        (_p("a8", "queen"), ((_p("a1", "bishop"), "below"), (_p("b8", "queen", True), "equal")))
    ]


# -- §4: DEFENCE_ENDED_UNDER_ATTACK ---------------------------------------------------------------

D_CASES = {
    "D1": (
        "4k3/8/2n5/4b3/B7/8/8/4R1K1 w - - 0 1",
        "a4c6",
        [("b.N.c6", "b.B.e5", "defender_captured")],
    ),
    "D2": ("4k3/8/2n5/4b3/8/8/8/4R1K1 b - - 0 1", "c6a5", [("b.N.c6", "b.B.e5", "defender_moved")]),
    "D3": ("3k4/8/2n5/4r3/8/8/8/4R1K1 b - - 0 1", "e5e4", [("b.N.c6", "b.R.e5", "defended_moved")]),
    "D4": ("4k3/8/8/r3b3/1N6/8/8/4R1K1 w - - 0 1", "b4d5", [("b.R.a5", "b.B.e5", "line_blocked")]),
    "D5": ("4k3/8/8/8/8/8/5PPP/4K2R w K - 0 1", "e1g1", []),
    "D6": ("4k3/8/3b4/8/8/8/7P/4K2R w K - 0 1", "e1g1", [("w.R.h1", "w.P.h2", "defender_moved")]),
    "D7": (
        "4k3/8/8/3pP3/4n3/8/8/4RK2 w - d6 0 1",
        "e5d6",
        [("b.P.d5", "b.N.e4", "defender_captured")],
    ),
    "D8": ("4k3/8/r5b1/3pP3/8/8/7K/6R1 w - d6 0 1", "e5d6", [("b.R.a6", "b.B.g6", "line_blocked")]),
    "D9": ("2R5/1P1k4/8/8/8/8/8/K7 w - - 0 1", "b7b8n", [("w.P.b7", "w.R.c8", "defender_moved")]),
    "D10": ("r3k3/8/8/8/8/8/8/2R1K3 w - - 0 1", "c1c8", []),
}


@pytest.mark.parametrize("case", sorted(D_CASES, key=lambda c: int(c[1:])))
def test_defence_ended_under_attack(case: str) -> None:
    fen, move, expected = D_CASES[case]
    _tree, view, nodes = _line(fen, move)
    assert plain_pattern_delta(view.fact("pattern_delta", nodes[1]))["ended"] == expected


# -- §4: every pattern_delta component -------------------------------------------------------------


def _delta(fen: str, *moves: str, at: int = -1) -> dict:
    _tree, view, nodes = _line(fen, *moves)
    return plain_pattern_delta(view.fact("pattern_delta", nodes[at]))


def test_a_multi_target_attack_begins_and_its_actor_is_captured() -> None:
    assert _delta("r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1", "b5c7")["multi"] == [
        ("w.N.b5", (), ("b.K.e8", "b.R.a8"))
    ]
    assert _delta("r3k3/1q6/8/1N6/8/8/8/4K3 w - - 0 1", "b5c7", "b7c7")["multi"] == [
        ("w.N.b5", ("b.K.e8", "b.R.a8"), "captured")
    ]


def test_a_promoted_actor_continues_under_its_id() -> None:
    assert _delta("r1n1k3/1P6/8/b7/8/8/8/K7 w - - 0 1", "b7a8q")["multi"] == [
        ("w.P.b7", ("b.N.c8", "b.R.a8"), ("b.B.a5", "b.N.c8"))
    ]


def test_a_sole_defender_is_captured() -> None:
    change = _delta("4k3/8/3p4/2n1b3/8/8/8/2RQR2K w - - 0 1", "d1d6")
    assert change["sole"] == [("b.P.d6", ("b.B.e5", "b.N.c5"), "captured")]


def test_back_rank_changes_on_castling() -> None:
    assert _delta("4k3/8/8/8/8/8/5PPP/4K2R w K - 0 1", "e1g1")["back"] == [
        ("w.K.e1", None, (("w.P.f2", "w.P.g2", "w.P.h2"), ()))
    ]


def test_a_skewer_turns_into_a_relative_pin_when_the_back_pawn_promotes_on_the_line() -> None:
    change = _delta("R7/8/7k/n7/8/8/p7/7K b - - 0 1", "a2a1q")
    triple = ("w.R.a8", "b.N.a5", "b.P.a2")
    assert change["skw"] == ([], [triple]) and change["rel"] == ([triple], [])


def test_pattern_delta_at_the_root_is_not_applicable() -> None:
    view, root = _root("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    assert isinstance(view.fact("pattern_delta", root), NotApplicable)


def test_pattern_delta_compares_id_projections_only() -> None:
    # the b5 rook keeps its target ids while the promoted target's order changes
    _tree, view, nodes = _line("7k/8/8/1R2n3/8/8/1p6/7K b - - 0 1", "b2b1q")
    multi = plain_pattern_delta(view.fact("pattern_delta", nodes[1]))["multi"]
    assert [c[0] for c in multi] == ["b.P.b2"]  # only the new queen's attack begins
    before = view.fact("patterns", nodes[0]).multi_target_attacks
    after = view.fact("patterns", nodes[1]).multi_target_attacks
    rook_before = next(m for m in before if m.actor.square == "b5")
    rook_after = next(m for m in after if m.actor.square == "b5")
    assert [t.order.value for t in rook_before.targets] == ["below", "below"]
    assert [t.order.value for t in rook_after.targets] == ["above", "below"]


# -- invariants (§7.2) ---------------------------------------------------------------------------


def _random_lines(seed: int, games: int, plies: int = 80) -> list[tuple[str, ...]]:
    rng = random.Random(seed)
    out = []
    for _ in range(games):
        board = chess.Board()
        moves = []
        while len(moves) < plies and not board.is_game_over():
            legal = list(board.legal_moves)
            captures = [
                m for m in legal if board.is_capture(m) or m.promotion or board.is_castling(m)
            ]
            move = rng.choice(captures if captures and rng.random() < 0.4 else legal)
            moves.append(move.uci())
            board.push(move)
        out.append(tuple(moves))
    return out


def test_side_independence() -> None:
    for moves in _random_lines(21, 6, plies=60):
        board = chess.Board()
        for uci in moves:
            board.push_uci(uci)
            flipped = board.copy(stack=False)
            flipped.turn = not flipped.turn
            flipped.ep_square = None
            if not flipped.is_valid():
                continue
            a, ra = _root(board.fen())
            b, rb = _root(flipped.fen())
            assert a.fact("patterns", ra) == b.fact("patterns", rb)


def test_pattern_invariants_on_random_games() -> None:
    for moves in _random_lines(13, 10):
        _tree, view, nodes = _line(None, *moves)
        for node_id in nodes:
            board = chess.Board(view.node(node_id).fen)
            pieces = view.fact("pieces", node_id)
            lines = view.fact("lines", node_id)
            patterns = view.fact("patterns", node_id)
            by = {p.square: p for p in pieces.pieces}
            # ray partition: every ray with two occupants lands in at most one recorded row, and
            # [enemy, enemy king] rays are exactly the absolute pins
            recorded = [
                (p.slider.square, p.line)
                for p in (*patterns.relative_pins, *patterns.skewers, *patterns.discovery_lines)
            ]
            assert len(recorded) == len(set(recorded))
            pins = set()
            for ray in lines.rays:
                if len(ray.occupants) < 2:
                    assert (ray.source, ray.direction) not in recorded
                    continue
                a, b = ray.occupants[0], ray.occupants[1]
                color = by[ray.source].color
                if a.color is not color and b.color is not color and b.piece_type is PieceType.KING:
                    pins.add((ray.source, a.square))
                kind = _row(color, a, b)
                assert ((ray.source, ray.direction) in recorded) == (kind is not None)
            assert pins == {
                (p.absolutely_pinned.pinner, p.square) for p in pieces.pieces if p.absolutely_pinned
            }
            for multi in patterns.multi_target_attacks:
                assert (
                    tuple(t.piece.square for t in multi.targets)
                    == by[multi.actor.square].attacks.enemy
                )
            actors = {m.actor.square for m in patterns.multi_target_attacks}
            assert actors == {p.square for p in pieces.pieces if len(p.attacks.enemy) >= 2}
            for sole in patterns.sole_defenders:
                for x in sole.defended:
                    facts = by[x.square]
                    assert (
                        facts.defender_count == 1
                        and facts.defenders[0].square == sole.defender.square
                    )
                    assert facts.attacker_count >= 1 and facts.piece_type is not PieceType.KING
            # a back-rank forward square is free exactly when the side to move's king may step there
            mover = Color.WHITE if board.turn else Color.BLACK
            king = (
                view.fact("king", node_id).white if board.turn else view.fact("king", node_id).black
            )
            square = chess.parse_square(king.square)
            first = 0 if board.turn else 7
            if chess.square_rank(square) == first:
                second = 1 if board.turn else 6
                legal = {
                    chess.square_name(m.to_square)
                    for m in board.legal_moves
                    if m.from_square == square
                }
                held = [b for b in patterns.back_ranks if b.king.square == king.square]
                forward = [
                    chess.square_name(chess.square(f, second))
                    for f in range(chess.square_file(square) - 1, chess.square_file(square) + 2)
                    if 0 <= f < 8
                ]
                free = [s for s in forward if s in legal]
                if held:
                    assert not free
                own = [s for s in forward if (p := by.get(s)) is not None and p.color is mover]
                assert bool(held) == (not free and bool(own))


def _row(color, a, b) -> str | None:
    if b.color is color:
        return None
    if a.color is color:
        return "disc"
    if b.piece_type is PieceType.KING:
        return None
    ra, rb = PIECE_ORDER_RANK[a.piece_type], PIECE_ORDER_RANK[b.piece_type]
    return "rel" if rb > ra else "skw" if ra > rb else None


def test_line_blocked_lands_between_the_defender_and_the_defended() -> None:
    seen = 0
    for moves in _random_lines(17, 12, plies=100):
        _tree, view, nodes = _line(None, *moves)
        for parent_id, child_id in pairwise(nodes):
            record = view.fact("pattern_delta", child_id)
            step = view.fact("move", child_id)
            landings = {step.to_square} | {
                e.to_square for e in step.events if hasattr(e, "to_square")
            }
            parent = view.node(parent_id)
            for ended in record.defences_ended_under_attack:
                if ended.reason is not DefenceEndReason.LINE_BLOCKED:
                    continue
                seen += 1
                d = chess.parse_square(parent.square_of(ended.defender))
                x = chess.parse_square(parent.square_of(ended.defended))
                between = chess.SquareSet(chess.between(d, x))
                assert any(chess.parse_square(s) in between for s in landings)
    assert seen > 0


def test_pattern_delta_applied_to_the_parent_gives_the_child() -> None:
    for moves in _random_lines(19, 8):
        _tree, view, nodes = _line(None, *moves)
        for parent_id, child_id in pairwise(nodes):
            change = view.fact("pattern_delta", child_id)
            parent, child = view.node(parent_id), view.node(child_id)
            for field in ("relative_pins", "skewers", "discovery_lines"):
                old = _triples(view, parent, field)
                new = _triples(view, child, field)
                diff = getattr(change, field)
                began = {(t.slider.value, t.front.value, t.back.value) for t in diff.began}
                ended = {(t.slider.value, t.front.value, t.back.value) for t in diff.ended}
                assert (old - ended) | began == new


def _triples(view, node, field):
    ids = {sq: pid.value for sq, pid in node.pieces}
    return {
        (ids[p.slider.square], ids[p.front.square], ids[p.back.square])
        for p in getattr(view.fact("patterns", node.node_id), field)
    }


# -- equivalences, mirror (§7.3, §7.4) -------------------------------------------------------------


def test_patterns_equal_across_transpositions_and_ensure() -> None:
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - {} 3"
    a, ra = _root(fen.format(2))
    b, rb = _root(fen.format(41))
    assert a.fact("patterns", ra) == b.fact("patterns", rb)
    tree, _view, nodes = _line(None, "e4", "e5", "Nf3", "Nc6", families=())
    ENGINE.ensure(tree, EnsureRequest(nodes, ("pattern_delta",)))
    view = tree.view()
    _full, full_view, same_nodes = _line(None, "e4", "e5", "Nf3", "Nc6")
    assert nodes == same_nodes
    for node_id in nodes:
        assert view.fact("patterns", node_id) == full_view.fact("patterns", node_id)
        assert view.fact("pattern_delta", node_id) == full_view.fact("pattern_delta", node_id)


def _m(square: str) -> str:
    return square[0] + str(9 - int(square[1]))


def _mid(pid: str) -> str:
    color, kind, square = pid.split(".")
    return f"{'b' if color == 'w' else 'w'}.{kind}.{_m(square)}"


def _mirror_patterns(p: dict) -> dict:
    def part(x):
        return (_m(x[0]), x[1], x[2])

    def key(x):
        return chess.parse_square(x[0][0])

    def line(row):
        slider, d, front, back = row
        return (part(slider), (d[0], -d[1]), part(front), part(back))

    def lines(rows):
        return sorted((line(r) for r in rows), key=lambda r: (chess.parse_square(r[0][0]), r[1]))

    return {
        "multi": sorted(
            (
                (
                    part(a),
                    tuple(
                        sorted(
                            ((part(t), o) for t, o in ts), key=lambda t: chess.parse_square(t[0][0])
                        )
                    ),
                )
                for a, ts in p["multi"]
            ),
            key=key,
        ),
        "rel": lines(p["rel"]),
        "skw": lines(p["skw"]),
        "disc": lines(p["disc"]),
        "sole": sorted(
            (
                (
                    part(d),
                    tuple(sorted((part(x) for x in xs), key=lambda x: chess.parse_square(x[0]))),
                )
                for d, xs in p["sole"]
            ),
            key=key,
        ),
        "back": sorted(
            (
                (
                    part(k),
                    tuple(sorted((part(b) for b in bl), key=lambda x: chess.parse_square(x[0]))),
                    tuple(sorted((_m(c) for c in cov), key=chess.parse_square)),
                )
                for k, bl, cov in p["back"]
            ),
            key=key,
        ),
    }


def test_colour_mirror_of_patterns_and_pattern_delta() -> None:
    for moves in _random_lines(23, 5, plies=50):
        _tree, view, nodes = _line(None, *moves)
        board = chess.Board()
        mirrored = []
        for uci in moves:
            move = chess.Move.from_uci(uci)
            mirrored.append(
                chess.Move(
                    chess.square_mirror(move.from_square),
                    chess.square_mirror(move.to_square),
                    move.promotion,
                ).uci()
            )
            board.push(move)
        _mtree, mview, mnodes = _line(chess.Board().mirror().fen(), *mirrored)
        for node_id, mnode_id in zip(nodes, mnodes, strict=True):
            ours = plain_patterns(view.fact("patterns", node_id))
            assert _mirror_patterns(ours) == plain_patterns(mview.fact("patterns", mnode_id))
            if node_id == nodes[0]:
                continue
            delta = plain_pattern_delta(view.fact("pattern_delta", node_id))
            mdelta = plain_pattern_delta(mview.fact("pattern_delta", mnode_id))
            assert sorted((_mid(d), _mid(x), r) for d, x, r in delta["ended"]) == sorted(
                mdelta["ended"]
            )
            for key in ("rel", "skw", "disc"):
                for part in (0, 1):
                    assert sorted(tuple(map(_mid, t)) for t in delta[key][part]) == sorted(
                        mdelta[key][part]
                    )


def test_explored_branch_shares_pattern_records_by_position() -> None:
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
    assert view.fact("patterns", a) is view.fact("patterns", b)
