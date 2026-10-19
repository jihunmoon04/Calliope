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
    assert not [c for c in board["changes"] if c["owner"] == "black" and c["kind"] != "threat"]
    text = held[0]["proves"]  # the a8 rook, Black's, exposed before and after: no relation
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
    two = held_proves("white", "34.Qxd6", ("queen", "queen"), "e7", "d6", 9,
                      ("흑 비숍(d6)", "흑 폰(c7)"), False)  # fmt: skip
    assert "수 전에는 e7에서 흑 비숍(d6)이, 수 뒤에는 d6에서 흑 폰(c7)이 공격한다" in two
    assert "백 퀸은 교환으로" in two and "9점" in two
    same = held_proves("black", "34...Qb3", ("queen", "queen"), "e3", "b3", 9,
                       ("백 룩(f3)", "백 룩(f3)"), True)  # fmt: skip
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
    """A cut that reaches the costs (review N1): on a weak move the first item (a weakness) and the
    pointer target stay, the held items go; on another grade the weakness goes as today."""

    from test_digest import _claim, _glossary, _record

    from calliope.agent.digest import digest

    def board_of(grade: str, pointer: bool) -> dict:
        d = digest(_record([_claim(1, "consequence", "supported")]), _glossary())
        d["grade"] = grade
        threats = [_item("threat", f"b{i}.x", "white") for i in (3, 4, 5)]
        if pointer:
            threats = [t | {"opponent_first": "b6.x"} for t in threats]
        d["board"] = {"v": "board_v3", "mover": "black",
                      "changes": [_item("weakness", "b2.x"), _item("held", "b1.x"),
                                  _item("held", "b6.x"), *threats]}  # fmt: skip
        return d

    weak = board_of("blunder", pointer=True)
    refs = [c["ref"] for c in bounded(weak, size(weak) - 500)["board"]["changes"]]
    assert "b2.x" in refs and "b6.x" in refs and "b1.x" not in refs
    other = board_of("good", pointer=False)
    refs = [c["ref"] for c in bounded(other, size(other) - 500)["board"]["changes"]]
    assert "b2.x" not in refs


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


def test_a_promotion_names_the_pawn_before_and_the_new_piece_after(s) -> None:
    """Review B1: identity survives a promotion; the text names each position's own piece."""

    board = _board(s, "8/1Pk5/8/8/8/8/8/7K w - - 0 1", "1. b8=Q+")
    (held,) = [c for c in board["changes"] if c["kind"] == "held"]
    assert "수 전 b7의 백 폰도, 수 뒤 b8의 백 퀸도 교환으로 잃을 수 있다" in held["proves"]
    assert "전에도 뒤에도 백 퀸" not in held["proves"]


def test_the_topic_particle_follows_the_last_syllable() -> None:
    from calliope.agent.remarks import topic

    assert [topic(w) for w in ("폰", "나이트", "비숍", "룩", "퀸")] == [
        "폰은", "나이트는", "비숍은", "룩은", "퀸은"]  # fmt: skip


def test_played_material_says_a_change_against_before_the_move() -> None:
    from calliope.agent.remarks import played_material_proves

    two = played_material_proves("black", "35.Rxb3", 9, "38.Rd3", 8, 9)
    assert "흑의 물질 차이는 수 전보다 9점 나빠지고, 엔진 라인 8수째 38.Rd3 뒤에도 9점" in two
    one = played_material_proves("white", None, 0, "19.O-O", 13, 1)
    assert "엔진 라인 13수째 19.O-O 뒤 백의 물질 차이는 수 전보다 1점 나빠져 있다" in one
    assert "뒤진다" not in two + one and "우위" not in two + one


# -- §5 (3): opponent_first, on a fake board's facts ------------------------------------------------


def _fake(in_check: bool):
    from types import SimpleNamespace

    status = SimpleNamespace(in_check=in_check)
    return SimpleNamespace(mover="black", child="c",
                           facts=SimpleNamespace(fact=lambda family, node: status))  # fmt: skip


def _kept(gains: list[int], threat_kinds: list[str]) -> list[tuple[dict, PieceRelation]]:
    kept = []
    for i, gain in enumerate(gains):
        piece = Piece(f"b.Q.{i}", "black", "queen", f"b{i + 1}")
        rel = PieceRelation(
            "exposed", (("piece", piece),), MOVE, "held", "black", (("gain", gain),)
        )
        kept.append((_item("held", f"h{i}.x") | {"proves": "h"}, rel))
    for i, kind in enumerate(threat_kinds):
        piece = Piece(f"w.R.{i}", "white", "rook", f"c{i + 1}")
        rel = PieceRelation(kind, (("target", piece),), MOVE, "began", "white")
        kept.append((_item("threat", f"t{i}.x", "white") | {"proves": "t"}, rel))
    return kept


def test_opponent_first_points_at_the_largest_and_skips_a_check() -> None:
    from calliope.agent.board import Board

    kept = _kept([3, 9, 9], ["attack", "check"])
    Board._opponent_first(_fake(False), kept)
    attack, check = kept[3][0], kept[4][0]
    assert attack["opponent_first"] == "h1.x"  # the largest gain, the first of a tie
    assert attack["proves"].endswith(OPPONENT_FIRST)
    assert "opponent_first" not in check  # the opponent must answer the check first


def test_no_opponent_first_in_check_or_below_gain_3() -> None:
    from calliope.agent.board import Board

    in_check = _kept([9], ["attack"])
    Board._opponent_first(_fake(True), in_check)
    small = _kept([2], ["attack"])
    Board._opponent_first(_fake(False), small)
    assert "opponent_first" not in in_check[1][0] and "opponent_first" not in small[1][0]


def test_played_material_needs_an_inconclusive_loss_and_a_best_line_of_another_move() -> None:
    from types import SimpleNamespace

    from calliope.agent.board import Board

    def fake(claims: list[dict], best_rank: int = 1):
        played = {"rank": 2, "pv": [{"uci": "e3b3"}, {"uci": "f3b3"}], "ref": "s1.x"}
        best = {"rank": best_rank, "pv": [{"uci": "e3e5"}]}
        record = {"analysis": {"judgements": [{"played": played, "best": best}],
                               "claims": claims}}  # fmt: skip
        return SimpleNamespace(record=record, mover="black", digest={"fen_before": "x"})

    loss = {"template": "material_loss_v2", "status": "inconclusive", "reason": "LINE_TOO_SHORT"}
    assert Board._played_material(fake([])) == (None, None)  # no material claim
    assert Board._played_material(fake([loss | {"reason": "MATE_LINE"}])) == (None, None)
    assert Board._played_material(fake([loss | {"status": "supported"}])) == (None, None)
    assert Board._played_material(fake([loss], best_rank=2)) == (None, None)  # best is played


# -- review 2 N10: a fault with no attacker read; a second claim on one held piece --------------


def test_an_exposed_piece_with_no_attacker_read_is_a_fault(s, monkeypatch) -> None:
    from calliope.agent.board import Board

    monkeypatch.setattr(Board, "_attacker", lambda self, node, square: None)
    board = _board(s, "r3k3/8/8/8/8/8/8/R5K1 w - - 0 1", "1. Kg2")
    assert not [c for c in board["changes"] if c["kind"] == "held"]
    assert board["refused"] >= 1  # counted, never served without its attack (BL-D §3)


def test_a_second_claim_on_one_held_piece_stays_listed(monkeypatch) -> None:
    """The first claim's link stays on the held item; the second claim is returned unmatched, so
    it stays in `claims` (I4), and the text gets no second link (review N2)."""

    from types import SimpleNamespace

    import calliope.agent.board as board_module
    from calliope.agent.board import Board
    from calliope.reasoning.piece_relations import ClaimRelation, Link

    relation = _relation("held", 5)
    item = _item("held", "b1.x", "white") | {"proves": "held"}
    groups = {"threat": [], "weakness": [], "held": [(item, relation)], "lost_defence": []}
    claims = [SimpleNamespace(id=f"c{i}", hypothesis=SimpleNamespace(template="left_en_prise_v2"))
              for i in (1, 2)]  # fmt: skip
    record = {"analysis": {"claims": [{"id": c.id, "ref": f"r{c.id}", "template": "t"}
                                      for c in claims]}}  # fmt: skip
    fake = SimpleNamespace(record=record)
    analysis = SimpleNamespace(claims=claims, rev=0, tree=SimpleNamespace(view=lambda rev: None))
    monkeypatch.setattr(board_module, "claim_relation", lambda *a: ClaimRelation(
        relation, Link("explains", "c9")))  # fmt: skip
    unmatched = Board._link(fake, analysis, None, None, None, groups)
    assert item["leads_to"]["claim"] == "rc1" and unmatched == ["c2"]
    assert item["proves"].count("설명한다") == 1 and len(groups["held"]) == 1
