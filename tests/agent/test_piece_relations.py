"""MS-D §4.2 over the synthetic engine: `move_relations` reads, in the reasoning layer, the
relations AG8's `board` reads — compared with the digest's `board` item by item — and keeps their
kinds, sides, times and identities."""

from __future__ import annotations

import pytest
from agent_helpers import G1, GAME, session

from calliope.agent.board import WEAK_GRADES, _gated
from calliope.reasoning.piece_relations import (
    FAMILIES,
    FORMAT,
    MOVE,
    limited,
    move_relations,
)


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    s.open_game(pgn=GAME, plies="1-4")
    yield s
    s.close()


def relations(s, game_id: str, ply: int):
    """The move's relations on the session's facts tree, its records ensured as `board` ensures."""

    game = s.game(game_id)
    view, nodes = s._node(game, tuple(game.parsed.uci[:ply]))
    s._records(game, view, nodes[-2], ("pieces", "patterns", "exchange", "status"))
    s._records(game, view, nodes[-1], FAMILIES)
    return move_relations(game.facts.view(), nodes[-2], nodes[-1])


def of_board(item: dict) -> tuple:
    p = item["propositions"]
    kind = p[0]["kind"]
    if item["kind"] == "lost_defence":
        return ("defence", p[0]["defender"], p[0]["defended"], p[1]["attacker"])
    if kind == "check":
        return ("check", tuple(p[0]["checkers"]))
    if kind == "pattern":
        parts = p[0]["participants"]
        return ("double_attack", parts["actor"], tuple(sorted(parts["targets"])))
    if kind == "attack":
        return ("attack", p[0]["attacker"], p[0]["target"])
    if kind == "exposed":  # a held item: its piece after the move (BL-D §3: exposed, attack, ...)
        return ("exposed", p[2]["piece"] if item["kind"] == "held" else p[0]["piece"])
    return ("absolute_pin", p[0]["pinned"], p[0]["pinner"])


def of_relation(r) -> tuple:
    sq = {name: p.square for name, p in r.roles}
    if r.kind == "defence":
        return ("defence", sq["defender"], sq["defended"], sq["attacker"])
    if r.kind == "check":
        return ("check", tuple(p.square for _n, p in r.roles))
    if r.kind == "double_attack":
        return ("double_attack", sq["actor"],
                tuple(sorted(p.square for n, p in r.roles if n == "target")))  # fmt: skip
    if r.kind == "attack":
        return ("attack", sq["attacker"], sq["target"])
    if r.kind == "exposed":
        return ("exposed", sq["piece"])
    return ("absolute_pin", sq["pinned"], sq["slider"])


def same_as_board(s, game_id: str, ply: int) -> tuple[list, list]:
    """The board's items and the move's relations, gated and limited as the board does (BL-D §2:
    a held item is the facts' relation, or a claim's when the facts give none)."""

    digest = s.ply(game_id, ply)
    board, weak = digest["board"], digest["grade"] in WEAK_GRADES
    read = limited(tuple(r for r in relations(s, game_id, ply) if _gated(r, weak)),
                   board["mover"])  # fmt: skip
    facts_held = {of_relation(r) for r in read if r.time == "held"}
    return (sorted(of_board(c) for c in board["changes"]
                   if c["kind"] != "held" or of_board(c) in facts_held),
            sorted(of_relation(r) for r in read))  # fmt: skip


def test_the_relations_are_the_boards_at_each_ply(s) -> None:
    assert FORMAT == "piece_relations_v2"
    for ply in (1, 2, 3, 4):
        board, read = same_as_board(s, G1, ply)
        assert board == read, ply


def test_a_relation_names_its_kind_side_place_time_and_pieces(s) -> None:
    found = relations(s, G1, 2)  # 1...d5: Black attacks White's pawn on e4
    assert found and all(r.place == MOVE and r.time == "began" for r in found)
    attack = next(r for r in found if r.kind == "attack")
    assert attack.side == "white" and attack.role("attacker").color == "black"
    assert attack.role("target").id.startswith("w.P.")
    assert attack.identity() == (attack.kind, tuple((n, p.id) for n, p in attack.roles), MOVE,
                                 "began")  # fmt: skip


def test_a_relation_that_moved_with_its_piece_is_no_relation_of_the_move(tmp_path) -> None:
    """AG8 rev. 3 (B1), now in the reasoning layer: by identity, not by square."""

    s = session(tmp_path)
    game = s.open_game(pgn='[FEN "4k3/n3r3/8/8/8/8/8/R3R1K1 w - - 0 1"]\n\n1. Ra2 Re6 *\n',
                       plies="1-2")["game"]  # fmt: skip
    assert not [r for r in relations(s, game, 1) if r.kind in ("attack", "exposed")
                and "a7" in (r.role("target") or r.role("piece")).square]  # fmt: skip
    assert not [r for r in relations(s, game, 2) if r.kind == "absolute_pin"]
    for ply in (1, 2):
        board, read = same_as_board(s, game, ply)
        assert board == read
    s.close()


def test_a_double_attack_that_gains_a_target_is_no_new_double_attack(tmp_path) -> None:
    """AG8 rev. 4 (B4): the rook on d4 attacked a4 and d7 before 1.Bc1, and h4 after it."""

    s = session(tmp_path)
    game = s.open_game(pgn='[FEN "4k3/3n4/8/8/n2R1B1n/8/8/7K w - - 0 1"]\n\n1. Bc1 *\n',
                       plies="1-1")["game"]  # fmt: skip
    found = relations(s, game, 1)
    assert not [r for r in found if r.kind == "double_attack"]
    assert ("attack", "d4", "h4") in [of_relation(r) for r in found if r.kind == "attack"]
    board, read = same_as_board(s, game, 1)
    assert board == read
    s.close()


def test_a_moved_piece_newly_exposed_is_the_movers_exposed_relation(tmp_path) -> None:
    s = session(tmp_path)
    game = s.open_game(pgn='[FEN "4k3/8/1p6/8/8/8/8/R5K1 w - - 0 1"]\n\n1. Ra5 *\n',
                       plies="1-1")["game"]  # fmt: skip
    (exposed,) = [r for r in relations(s, game, 1) if r.kind == "exposed"]
    assert exposed.side == "white" and exposed.role("piece").square == "a5"
    assert dict(exposed.data)["gain"] > 0
    s.close()


def test_the_limits_are_the_boards() -> None:
    from calliope.reasoning.piece_relations import Piece, PieceRelation

    def attack(i: int) -> PieceRelation:
        p = Piece(f"w.R.a{i}", "white", "rook", f"a{i}")
        return PieceRelation("attack", (("attacker", p), ("target", p)), MOVE, "began", "black")

    def exposed(i: int, side: str) -> PieceRelation:
        p = Piece(f"x.N.b{i}", side, "knight", f"b{i}")
        return PieceRelation("exposed", (("piece", p),), MOVE, "began", side, (("gain", 3),))

    many = (*(attack(i) for i in range(1, 6)), *(exposed(i, "black") for i in range(1, 5)),
            *(exposed(i, "white") for i in range(5, 9)))  # fmt: skip
    kept = limited(many, "white")
    assert [r.kind for r in kept].count("attack") == 3
    assert sum(r.kind == "exposed" and r.side == "black" for r in kept) == 3
    assert sum(r.kind == "exposed" and r.side == "white" for r in kept) == 3


def test_one_relation_at_one_ply_of_two_engine_lines_is_two_relations() -> None:
    """MS-a re-review: a line's place names its search and rank, so the same pieces at the same
    ply of two lines are two relations; of one line, one."""

    from calliope.reasoning.piece_relations import Piece, PieceRelation, Place

    actor = Piece("w.N.g1", "white", "knight", "c7")
    targets = (Piece("b.K.e8", "black", "king", "e8"), Piece("b.R.a8", "black", "rook", "a8"))

    def fork(place: Place) -> PieceRelation:
        roles = (("actor", actor), *(("target", t) for t in targets))
        return PieceRelation("double_attack", roles, place, "began", "black")

    first = fork(Place("line", 3, "s7", 1))
    assert first.identity() == fork(Place("line", 3, "s7", 1)).identity()
    assert first.identity() != fork(Place("line", 3, "s7", 2)).identity()  # another rank
    assert first.identity() != fork(Place("line", 3, "s8", 1)).identity()  # another search
    assert first.identity() != fork(Place("line", 4, "s7", 1)).identity()  # another ply
    assert first.identity() != fork(MOVE).identity()
