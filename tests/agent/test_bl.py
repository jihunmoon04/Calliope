"""BL-D over the synthetic engine and as pure rules: the mover's held pieces from the facts and
their gate (§2), the attackers in the items (§3), the played line's points (§4), the order, step 0
and the reason flag (§4, §5)."""

from __future__ import annotations

import pytest
from agent_helpers import GAME, session

from calliope.agent.board import HELD_GAIN, _gated, _stake, played_points
from calliope.agent.digest import bounded, size
from calliope.agent.remarks import OPPONENT_FIRST, PROVES_CAP, held_proves, with_opponent_first
from calliope.reasoning.piece_relations import MOVE, Piece, PieceRelation


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    yield s
    s.close()


def _board(s, fen: str, moves: str, ply: int = 1) -> dict:
    game = s.open_game(pgn=f'[FEN "{fen}"]\n\n{moves} *\n', plies=f"1-{ply}")["game"]
    return s.ply(game, ply)["board"]


def _kinds(board: dict) -> list[tuple[str, str]]:
    return [(c["kind"], c["owner"]) for c in board["changes"]]


# -- §2, §3: the mover's held pieces from the facts, with their attackers -------------------------


def test_a_piece_exposed_before_and_after_is_held_with_its_attacker(s) -> None:
    """1.Kg2: the rook on a1 stays where the rook on a8 takes it (gain 5, any grade)."""

    board = _board(s, "r3k3/8/8/8/8/8/8/R5K1 w - - 0 1", "1. Kg2")
    held = [c for c in board["changes"] if c["kind"] == "held"]
    assert len(held) == 1 and held[0]["owner"] == "white" and held[0]["good_for"] == "black"
    kinds = [(p["kind"], p.get("piece") or p.get("attacker")) for p in held[0]["propositions"]]
    assert kinds == [("exposed", "a1"), ("attack", "a8"), ("exposed", "a1"), ("attack", "a8")]
    text = held[0]["proves"]
    assert text.startswith("[백의 약점: 수 전에도 수 뒤에도 백의 기물이 위험하다]")
    assert "a1에서 수 전에도 뒤에도 흑 룩(a8)이 공격한다" in text and "5점" in text
    assert "방치" not in text and "둔 채로" not in text  # review B3: exposure, not neglect


def test_a_moved_piece_attacked_by_the_same_piece_names_both_squares(s) -> None:
    """1.Ra2: the rook moves along the a-file the rook on a8 holds — 34...Qb3's shape."""

    board = _board(s, "r3k3/8/8/8/8/8/8/R5K1 w - - 0 1", "1. Ra2")
    held = next(c for c in board["changes"] if c["kind"] == "held")
    assert "수 전 a1에서도 수 뒤 a2에서도 흑 룩(a8)이 공격한다" in held["proves"]
    assert [p.get("piece") for p in held["propositions"] if p["kind"] == "exposed"] == ["a1", "a2"]
    assert not [c for c in board["changes"] if c["kind"] == "weakness"]  # one relation, held


def test_after_a_check_the_piece_is_a_weakness_said_with_the_check(s) -> None:
    """1.Kd2 out of the rook's check: the a1 rook's gain before is IN_CHECK, so it is `began` and
    no `held` (review B2), and the text does not say it was safe before (review N14)."""

    board = _board(s, "r3k3/8/8/8/8/8/8/R3K2r w - - 0 1", "1. Kd2")
    assert not [c for c in board["changes"] if c["kind"] == "held"]
    weak = [c for c in board["changes"] if c["kind"] == "weakness"
            and c["propositions"][0].get("piece") == "a1"]  # fmt: skip
    assert len(weak) == 1 and "수 전에는 체크 중이었다" in weak[0]["proves"]
    assert weak[0]["propositions"][1]["kind"] == "attack"


def test_a_new_weakness_names_its_attacker(s) -> None:
    board = _board(s, "4k3/8/1p6/8/8/8/8/R5K1 w - - 0 1", "1. Ra5")
    (weak,) = board["changes"]
    assert [p["kind"] for p in weak["propositions"]] == ["exposed", "attack"]
    assert weak["propositions"][1] == {"kind": "attack", "position": {"ply": 1, "at": "after"},
                                       "attacker": "b6", "target": "a5"}  # fmt: skip
    assert "흑 폰(b6)이 공격하고" in weak["proves"] and "수 전에는 아니었다" in weak["proves"]


def _relation(time: str, gain: int, kind: str = "rook") -> PieceRelation:
    piece = Piece("w.R.a1", "white", kind, "a1")
    return PieceRelation("exposed", (("piece", piece),), MOVE, time, "white", (("gain", gain),))


def test_the_gate_keeps_a_held_piece_from_gain_3_or_on_a_weak_move() -> None:
    assert HELD_GAIN == 3
    assert _gated(_relation("held", 3), weak=False) and _gated(_relation("held", 9), weak=False)
    assert not _gated(_relation("held", 1, "pawn"), weak=False)  # a recapture, a gambit pawn
    assert _gated(_relation("held", 1, "pawn"), weak=True)  # on a mistake it can be the reason
    assert _gated(_relation("began", 1, "pawn"), weak=False)  # began: unchanged


def test_the_held_texts_for_one_and_two_attackers() -> None:
    two = held_proves("white", "34.Qxd6", "queen", "e7", "d6", 9, ("흑 비숍(d6)", "흑 폰(c7)"),
                      False)  # fmt: skip
    assert "수 전 e7은 흑 비숍(d6)이, 수 뒤 d6는 흑 폰(c7)이 공격한다" in two and "9점" in two
    same = held_proves("black", "34...Qb3", "queen", "e3", "b3", 9, ("백 룩(f3)", "백 룩(f3)"),
                       True)  # fmt: skip
    assert "수 전 e3에서도 수 뒤 b3에서도 백 룩(f3)이 공격한다" in same
    assert same.startswith("[흑의 약점: 수 전에도 수 뒤에도 흑의 기물이 위험하다]")


# -- §4: the played line's points -----------------------------------------------------------------

QB3 = [0, -9, -9, -9, -9, -10, -9, -9]  # 34...Qb3's line, plies 1–8
QUIET = [True, False, True, True, True, False, False, True]


def test_the_points_of_34_qb3() -> None:
    best = [0, 0, 0, 0, 1, 1, 1, 1]
    assert played_points(QB3, QUIET, best, [True] * 8) == (2, 8)


def test_no_points_when_the_line_ends_on_a_capture_or_not_behind() -> None:
    best = [0] * 8
    assert played_points(QB3, [*QUIET[:-1], False], best, [True] * 8) is None  # mid-exchange
    assert played_points([0, 0, 0, 1], [True] * 4, best, [True] * 4) is None  # not behind
    assert played_points([-1], [True], best, [True] * 8) is None  # one ply


def test_no_points_when_the_best_line_ends_as_far_behind() -> None:
    assert played_points([0, -1, -1, -1], [True] * 4, [0, 0, -1, -1], [True] * 4) is None  # 13.Rb1


def test_the_best_line_is_read_at_its_last_quiet_ply() -> None:
    """Review N12: a best line cut after its own capture is read before it; owner's review O1:
    with no quiet ply the comparison is undecided, and no item."""

    played = [0, -9, -9, -9]
    assert played_points(played, [True] * 4, [0, 9, 9, -9], [True, False, True, False]) == (2, 4)
    assert played_points(played, [True] * 4, [0, 0, -9, 0], [True, True, True, False]) is None
    assert played_points(played, [True] * 4, [9, 9, 9, 9], [False] * 4) is None


def test_k_is_where_the_line_stays_at_most_its_end() -> None:
    assert played_points([0, -1, -1, -1, 0, 0, 0, -1], [True] * 8, [3] * 8, [True] * 8) == (8, 8)


# -- §5: the order, step 0, opponent_first --------------------------------------------------------


def test_the_stake_of_an_item() -> None:
    assert _stake(_relation("held", 9, "queen")) == 9
    pawn = Piece("b.P.c5", "black", "pawn", "c5")
    defence = PieceRelation("defence", (("defender", Piece("b.Q.d8", "black", "queen", "e3")),
                                        ("defended", pawn),
                                        ("attacker", Piece("w.R.a1", "white", "rook", "c4"))),
                            MOVE, "ended", "black")  # fmt: skip
    assert _stake(defence) == 1


def test_the_suffix_keeps_the_proves_within_its_cap() -> None:
    long = "가" * PROVES_CAP
    out = with_opponent_first(long)
    assert len(out) == PROVES_CAP and out.endswith(OPPONENT_FIRST)
    assert with_opponent_first("위협") == "위협" + OPPONENT_FIRST


def _item(kind: str, ref: str, owner: str = "black") -> dict:
    return {"ref": ref, "kind": kind, "part": "reason", "owner": owner, "good_for": "white",
            "proves": "p" * 200, "propositions": []}  # fmt: skip


def test_step_0_keeps_the_first_item_and_the_target_on_a_weak_move() -> None:
    from test_digest import _claim, _glossary, _record

    from calliope.agent.digest import digest

    d = digest(_record([_claim(1, "consequence", "supported")]), _glossary())
    d["grade"] = "blunder"
    first, target = _item("held", "b1.x"), _item("weakness", "b2.x")
    threats = [_item("threat", f"b{i}.x", "white") | {"opponent_first": "b2.x"} for i in (3, 4, 5)]
    d["board"] = {"v": "board_v3", "mover": "black",
                  "changes": [first, target, *threats]}  # fmt: skip
    small = bounded(d, size(d) - 200)  # one item to go: the third threat (2 kept)
    refs = [c["ref"] for c in small["board"]["changes"]]
    assert refs == ["b1.x", "b2.x", "b3.x", "b4.x"]  # held 0 and weakness 0 do not take them
    d["grade"] = "good"
    for threat in threats:
        threat.pop("opponent_first")
    other = bounded(d, size(d) - 3 * 240)  # not weak, no pointer: today's counts
    assert [c["ref"] for c in other["board"]["changes"]] == ["b3.x", "b4.x"]


# -- §4: the reason flag (owner's review O2) ------------------------------------------------------


def test_the_reason_flag_counts_reason_items_and_supported_reason_claims(s) -> None:
    game = s.game(s.open_game(pgn=GAME, plies="1-1")["game"])
    played = {"kind": "played_material", "part": "consequence", "propositions": [{"k": 1}]}
    board = {"changes": [], "played_material": played}
    served = [{"part": "consequence", "canonical": [{"k": 1}]}]
    subject = ("e2e4",)

    def flag(claims: list[dict], b: dict = board, srv: list = served) -> dict:
        s._keep_board(game, subject, b, b, srv, {"claims": claims})
        return s.boards[game.key][subject]

    kept = flag([{"part": "reason", "status": "inconclusive"}])
    assert kept["reason"] is False and [i["index"] for i in kept["items"]] == [0]
    assert flag([{"part": "reason", "status": "supported"}])["reason"] is True
    item = {"kind": "held", "part": "reason", "propositions": []}
    with_item = {"changes": [item], "played_material": played}
    srv = [{"part": "reason", "canonical": []}, *served]
    assert flag([], with_item, srv)["reason"] is True
