"""ST-D over the synthetic engine: the scene before the move (§2), since when (§3), pawn structure
and files (§4), the caps (§7), the notes off (§6)."""

from __future__ import annotations

import pytest
from agent_helpers import session

from calliope.agent import Limits
from calliope.agent.board import SCENE_ITEMS, SINCE_PLIES, _scene_order
from calliope.agent.propositions import Refused, Verifier
from calliope.agent.remarks import ITEM_CAP, OPPONENT_FIRST, appended, with_opponent_first
from calliope.agent.session import CHECK, _notes
from calliope.reasoning.piece_relations import MOVE, Piece, PieceRelation


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    yield s
    s.close()


@pytest.fixture
def wide(tmp_path):
    s = session(
        tmp_path, Limits(max_uncached_plies=64, max_uncached_plies_per_call=32, max_searches=10_000)
    )
    yield s
    s.close()


def _open(s, fen: str, moves: str, plies: int) -> str:
    return s.open_game(pgn=f'[FEN "{fen}"]\n\n{moves} *\n', plies=f"1-{plies}")["game"]


def _board(s, fen: str, moves: str, ply: int) -> dict:
    return s.ply(_open(s, fen, moves, ply), ply)["board"]


def _item(board: dict, kind: str) -> dict:
    (item,) = [c for c in [*board["changes"], *board.get("scene", ())] if c["kind"] == kind]
    return item


# -- §2: the scene before the move ----------------------------------------------------------------

ATTACKED = "r3k3/8/8/8/8/8/8/1R3RK1 b - - 0 1"  # 1...Rb8 attacks the b1 rook, defended by f1


def test_the_scene_says_what_the_last_move_began_and_that_it_stands(s) -> None:
    board = _board(s, ATTACKED, "1... Rb8 2. Kh1", 2)
    (scene,) = board["scene"]
    assert scene["kind"] == "scene" and scene["relation"] == "attack" and scene["part"] == "reason"
    assert scene["owner"] == "white" and scene["good_for"] == "black"
    assert scene["proves"] == ("[수 전 상황: 상대의 직전 수가 만든 것] 1...Rb8 뒤 흑 룩(b8)이 백 "
                               "룩(b1)을 공격하기 시작했다. 2.Kh1 뒤: 백 룩(b1)은 흑 룩(b8)의 공격을 "
                               "계속 받는다")  # fmt: skip
    assert scene["propositions"] == [
        {
            "kind": "attack",
            "position": {"ply": 2, "at": "before"},
            "attacker": "b8",
            "target": "b1",
        },
        {"kind": "attack", "position": {"ply": 2, "at": "after"}, "attacker": "b8", "target": "b1"},
    ]
    assert scene["ref"].startswith("b")
    assert all(c["kind"] != "scene" for c in board["changes"])  # its own list (§2.6)


def test_the_scene_says_an_attack_ended_by_that_attacker_only(s) -> None:
    board = _board(s, ATTACKED, "1... Rb8 2. Rbc1", 2)
    scene = board["scene"][0]
    assert scene["proves"].endswith(
        "2.Rbc1 뒤: 백 룩(b1)은 c1로 옮겨 흑 룩(b8)의 공격을 더는 받지 않는다"
    )
    assert len(scene["propositions"]) == 1  # "더는" is the facts' reading, no proposition


def test_the_scene_says_the_attacker_was_taken(s) -> None:
    board = _board(s, ATTACKED, "1... Rb8 2. Rxb8+", 2)
    assert board["scene"][0]["proves"].endswith("2.Rxb8+ 뒤: 공격하던 흑 룩(b8)을 잡았다")


def test_no_scene_at_the_first_ply_of_the_path(s) -> None:
    assert "scene" not in _board(s, ATTACKED, "1... Rb8", 1)


def test_a_scene_exposure_on_a_held_piece_is_said_by_the_held_item(s) -> None:
    """1...Rb8 makes the b1 rook capturable; 2.Rb2 keeps it so: the `held` item says it."""

    board = _board(s, "r3k3/8/8/8/8/8/8/1R4K1 b - - 0 1", "1... Rb8 2. Rb2", 2)
    held = _item(board, "held")
    assert "흑 룩(b8)의 이 공격은 1...Rb8 뒤부터 이어졌고" in held["proves"]
    assert not [c for c in board.get("scene", ()) if c["relation"] in ("attack", "exposed")]


def test_a_scene_exposure_names_its_attacker_and_count(s) -> None:
    board = _board(s, "r3k3/8/8/8/8/8/8/1R4K1 b - - 0 1", "1... Rb8 2. Rc1", 2)
    (scene,) = board["scene"]
    assert scene["relation"] == "exposed"
    assert ("1...Rb8 뒤 백 룩(b1)은 잡힐 수 있게 됐다: 흑 룩(b8)이 공격하고, 그 칸의 잡고 되잡기만 "
            "셈하면 백이 5점을 잃는다") in scene["proves"]  # fmt: skip
    assert [p["kind"] for p in scene["propositions"]] == ["exposed", "attack"]


def test_the_scene_of_a_move_not_played_is_the_positions_with_its_own_fate(s) -> None:
    game = _open(s, ATTACKED, "1... Rb8 2. Kh1", 2)
    played = s.ply(game, 2)["board"]["scene"][0]
    judged = s.judge_move(game, {"ply": 2, "at": "before"}, "Rbc1")["board"]["scene"][0]
    head = played["proves"].split(". 2.")[0]
    assert judged["proves"].startswith(head)
    assert judged["proves"].endswith(
        "2.Rbc1 뒤: 백 룩(b1)은 c1로 옮겨 흑 룩(b8)의 공격을 더는 받지 않는다"
    )
    assert judged["propositions"][0]["position"] == {"from_root": ["a8b8"]}


def test_citing_a_scene_item_allows_its_previous_move(s) -> None:
    game = _open(s, ATTACKED, "1... Rb8 2. Kh1", 2)
    ref = s.ply(game, 2)["board"]["scene"][0]["ref"]
    allowed = s.board_tokens[s.game(game).key][ref]
    assert ("a8b8", ATTACKED) in allowed.moves and {"b8", "b1"} <= allowed.squares


def test_the_scene_order_puts_a_check_first_then_the_stake() -> None:
    def rel(kind, roles, data=()):
        return PieceRelation(kind, roles, MOVE, "began", "white", data)

    queen = Piece("w.Q.d1", "white", "queen", "d4")
    pawn = Piece("w.P.a2", "white", "pawn", "a4")
    rook = Piece("b.R.a8", "black", "rook", "a8")
    check = rel("check", (("checker", rook),))
    on_queen = rel("attack", (("attacker", rook), ("target", queen)))
    on_pawn = rel("exposed", (("piece", pawn),), (("gain", 1),))
    ordered = sorted([on_queen, on_pawn, check], key=_scene_order)
    assert ordered == [check, on_pawn, on_queen] and SCENE_ITEMS == 3


# -- §3: since when -------------------------------------------------------------------------------

KNIGHT = "1r2k3/8/8/8/N7/8/8/R5K1 b - - 0 1"  # 1...Ra8 attacks the a4 knight the a1 rook defends


def test_a_lost_defence_says_since_when_with_its_propositions(s) -> None:
    board = _board(s, KNIGHT, "1... Ra8 2. Kh1 Ke7 3. Rb1", 4)
    lost = _item(board, "lost_defence")
    assert ("흑 룩(a8)의 백 나이트(a4) 공격은 이 수 전에도 있었다(1...Ra8 뒤부터). 3.Rb1로 새로 생긴 "
            "것은 공격이 아니라 수비가 사라진 것이다") in lost["proves"]  # fmt: skip
    attacks = [p for p in lost["propositions"] if p["kind"] == "attack"]
    assert attacks == [
        {"kind": "attack", "position": {"ply": 4, "at": "after"}, "attacker": "a8", "target": "a4"},
        {
            "kind": "attack",
            "position": {"ply": 4, "at": "before"},
            "attacker": "a8",
            "target": "a4",
        },
        {"kind": "attack", "position": {"ply": 1, "at": "after"}, "attacker": "a8", "target": "a4"},
    ]


def test_a_new_attack_on_a_lost_defence_says_so(s) -> None:
    """1.Rb5: the rook leaves a5, where it defended a4 and blocked the a8 rook."""

    lost = _item(_board(s, "r3k3/8/8/R7/N7/8/8/6K1 w - - 0 1", "1. Rb5", 1), "lost_defence")
    assert lost["proves"].endswith("흑 룩(a8)의 이 공격은 1.Rb5로 새로 생겼다")
    assert len(lost["propositions"]) == 2  # nothing added for "new"


def test_an_attack_from_the_start_says_so_at_ply_1_before(s) -> None:
    board = _board(s, "r3k3/8/8/8/N7/8/8/R5K1 w - - 0 1", "1. Rb1", 1)
    lost = _item(board, "lost_defence")
    assert "이 수 전에도 있었다(시작 국면부터)" in lost["proves"]
    weak = _item(board, "weakness")  # the knight is capturable now: since when, as well
    assert (
        "흑 룩(a8)의 이 공격은 이 수 전에도 있었다(시작 국면부터). 1.Rb1로 바뀐 것은"
        in weak["proves"]
    )


def test_an_attack_from_the_start_verifies_after_some_plies(s) -> None:
    """Re-review C1: the run's first position, the root, is written as ply 1 before."""

    board = _board(s, "r3k3/8/8/8/N7/8/8/R5K1 w - - 0 1", "1. Kh1 Ke7 2. Rb1", 3)
    lost = _item(board, "lost_defence")
    assert "(시작 국면부터)" in lost["proves"] and board.get("refused") is None
    assert {"kind": "attack", "position": {"ply": 1, "at": "before"}, "attacker": "a8",
            "target": "a4"} in lost["propositions"]  # fmt: skip


SHUFFLE = "2. Kh1 Ke7 3. Kg1 Ke8 4. Kh1 Ke7 5. Kg1 Ke8 6. Kh1 Ke7 7. Kg1 Ke8 8. Kh1 Ke7 9. Kg1 Ke8"


def test_a_run_of_exactly_the_bound_is_since_its_move(wide) -> None:
    """1...Ra8 then 16 plies: the walk stops at its bound on ply 1, before which the attack did not
    hold — since 1...Ra8."""

    lost = _item(_board(wide, KNIGHT, f"1... Ra8 {SHUFFLE} 10. Rb1", 18), "lost_defence")
    assert SINCE_PLIES == 16 and "(1...Ra8 뒤부터)" in lost["proves"]


def test_a_longer_run_says_at_least_since_its_bound(wide) -> None:
    """Two plies more: the attack still held below the bound (ply 3), so only "at least"."""

    moves = f"1... Ra8 {SHUFFLE} 10. Kh1 Ke7 11. Rb1"
    lost = _item(_board(wide, KNIGHT, moves, 20), "lost_defence")
    assert "(적어도 2...Ke7 뒤부터)" in lost["proves"]
    assert {"kind": "attack", "position": {"ply": 3, "at": "after"}, "attacker": "a8",
            "target": "a4"} in lost["propositions"]  # fmt: skip


def test_a_promotion_ends_the_walk(s) -> None:
    """1.b8=Q: the queen attacks c8 since its promotion, though the b7 pawn attacked it before."""

    board = _board(s, "2nk4/1P6/8/8/8/8/8/6K1 w - - 0 1", "1. b8=Q Ke7", 2)
    lost = _item(board, "lost_defence")
    assert "공격은 이 수 전에도 있었다(1.b8=Q 뒤부터)" in lost["proves"]


def test_an_exposed_threat_names_its_attacker_since_when(s) -> None:
    """1.cxb5 takes the b5 pawn that defended the a4 knight the a1 rook attacks from the start."""

    board = _board(s, "5k2/8/8/1p6/n1P5/8/8/R5K1 w - - 0 1", "1. cxb5", 1)
    threat = next(c for c in board["changes"] if c["kind"] == "threat"
                  and c["propositions"][0]["kind"] == "exposed")  # fmt: skip
    assert ("그 기물을 공격하는 백 룩(a1)의 공격은 이 수 전에도 있었다(시작 국면부터). 1.cxb5로 바뀐 "
            "것은 공격이 아니라 그 칸의 잡고 되잡기 셈이다") in threat["proves"]  # fmt: skip
    attacks = [p["position"] for p in threat["propositions"] if p["kind"] == "attack"]
    assert attacks == [{"ply": 1, "at": "after"}, {"ply": 1, "at": "before"}]


def test_a_weakness_whose_attacker_is_new_says_nothing_more(s) -> None:
    board = _board(s, "4k3/8/1p6/8/8/8/8/R5K1 w - - 0 1", "1. Ra5", 1)
    (weak,) = board["changes"]
    assert weak["proves"].endswith("(수 전에는 아니었다)") and len(weak["propositions"]) == 2


def test_since_moves_are_tokens_of_the_item_only(s) -> None:
    game = _open(s, KNIGHT, "1... Ra8 2. Kh1 Ke7 3. Rb1", 4)
    board = s.ply(game, 4)["board"]
    lost = _item(board, "lost_defence")
    tokens = s.board_tokens[s.game(game).key]
    assert any(u == "b8a8" for u, _ in tokens[lost["ref"]].moves)
    for item in [*board["changes"], *board.get("scene", ())]:  # only items that name the move
        named = any(u == "b8a8" for u, _ in tokens[item["ref"]].moves)
        assert named == ("1...Ra8" in item["proves"]), item["proves"]


# -- §4: pawn structure, files ----------------------------------------------------------------------


def test_structure_and_file_items_after_the_relation_items(s) -> None:
    """1.exd5: the e-file opens for White... the d-pawns double."""

    board = _board(s, "4k3/8/8/3p4/4P3/8/3P4/4K3 w - - 0 1", "1. exd5", 1)
    kinds = [c["kind"] for c in board["changes"]]
    assert "structure" in kinds and "file" in kinds
    assert kinds.index("structure") > max((i for i, k in enumerate(kinds)
                                           if k not in ("structure", "file")), default=-1)  # fmt: skip
    doubled = next(c for c in board["changes"] if c["kind"] == "structure"
                   and "더블 폰" in c["proves"])  # fmt: skip
    assert doubled["owner"] == "white" and doubled["good_for"] == "black"
    e_file = next(c for c in board["changes"] if c["kind"] == "file" and "e파일" in c["proves"])
    assert e_file["good_for"] is None
    assert [p["kind"] for p in e_file["propositions"]] == ["file", "file"]


def test_pawn_and_file_propositions_verify_and_refuse(s) -> None:
    game = _open(s, "4k3/8/8/3p4/4P3/8/3P4/4K3 w - - 0 1", "1. exd5", 1)
    verifier = Verifier(s, s.game(game))
    after = {"ply": 1, "at": "after"}
    record, _ = verifier.verify({"id": "p", "kind": "pawn", "position": after, "square": "d5",
                                 "flag": "doubled", "value": True})  # fmt: skip
    assert record["color"] == "white"
    with pytest.raises(Refused):
        verifier.verify({"id": "p", "kind": "pawn", "position": after, "square": "e4",
                         "flag": "doubled", "value": True})  # fmt: skip
    with pytest.raises(Refused):
        verifier.verify({"id": "p", "kind": "pawn", "position": after, "square": "d5",
                         "flag": "lonely", "value": True})  # fmt: skip
    record, _ = verifier.verify({"id": "f", "kind": "file", "position": after, "file": "e",
                                 "state": "open"})  # fmt: skip
    assert record["state"] == "open"
    with pytest.raises(Refused):
        verifier.verify({"id": "f", "kind": "file", "position": after, "file": "e",
                         "state": "closed"})  # fmt: skip


def test_others_are_shown_with_their_lines(s) -> None:
    game = _open(s, ATTACKED, "1... Rb8 2. Kh1", 2)
    d = s.ply(game, 2)
    assert "others" not in d["not_shown"]
    for other in d.get("others", ()):
        assert other["ref"].startswith("s") and other["move"].startswith("2.")
        assert len(other["pv"].split()) <= 6


# -- §7: caps -------------------------------------------------------------------------------------


def test_a_part_goes_in_whole_or_not_at_all() -> None:
    assert appended("a" * 100, "b" * 50) == "a" * 100 + "b" * 50
    assert appended("a" * (ITEM_CAP - 10), "b" * 11) is None
    assert appended("a" * (ITEM_CAP - 60), "b" * 50, reserve=len(OPPONENT_FIRST)) is None
    room = "a" * (ITEM_CAP - len(OPPONENT_FIRST))
    assert with_opponent_first(room) == room + OPPONENT_FIRST


# -- §6: the notes off ----------------------------------------------------------------------------


def test_no_notes_and_the_check_version() -> None:
    assert CHECK == "commentary_check_v6"
    sentence = {"text": "…", "class": "interpretation", "cites": []}
    assert _notes([sentence], [set()], {"reason": True, "items": []}) == []


# -- §7 at the board: parts appended in order, whole or not at all (implementation review N1) ----


def _fake():
    from types import SimpleNamespace

    from calliope.agent.board import Board

    fake = SimpleNamespace(extra_moves={})
    fake._append = lambda item, part, *a, **k: Board._append(fake, item, part, *a, **k)
    return fake


SINCE = {"at_p": {"kind": "attack", "position": "p"}, "first": {"kind": "attack", "position": "k"},
         "move": ("a7a8", "fen"), "when": "1...Ra8 뒤부터"}  # fmt: skip


def test_a_part_that_does_not_fit_takes_its_propositions_and_token(monkeypatch) -> None:
    from calliope.agent import remarks

    monkeypatch.setattr(remarks, "ITEM_CAP", 60)
    fake = _fake()
    item = {"kind": "lost_defence", "proves": "가" * 40, "propositions": [{"kind": "defence"}]}
    assert not fake._append(item, "나" * 30, SINCE, at_p=True)
    assert item["proves"] == "가" * 40 and item["propositions"] == [{"kind": "defence"}]
    assert fake.extra_moves == {}
    assert fake._append(item, "나" * 10, SINCE, at_p=True)
    assert [p["position"] for p in item["propositions"][1:]] == ["p", "k"]
    assert fake.extra_moves[id(item)] == [("a7a8", "fen")]
    assert not fake._append(item, "다" * 15)  # a link remark after it: no room, left out whole
    assert item["proves"] == "가" * 40 + "나" * 10


def test_a_threat_keeps_room_for_opponent_first(monkeypatch) -> None:
    from calliope.agent import remarks

    monkeypatch.setattr(remarks, "ITEM_CAP", 100)
    room = 100 - len(OPPONENT_FIRST)
    fake = _fake()
    threat = {"kind": "threat", "proves": "가" * (room - 5), "propositions": []}
    weakness = {"kind": "weakness", "proves": "가" * (room - 5), "propositions": []}
    assert not fake._append(threat, "나" * 10) and fake._append(weakness, "나" * 10)
    text = remarks.with_opponent_first(threat["proves"])
    assert text.endswith(OPPONENT_FIRST) and "…" not in text and len(text) <= 100


def test_a_real_boards_items_stay_under_the_cap_uncut(s) -> None:
    """Every item with its since sentence under ITEM_CAP, nothing cut (the synthetic board gives no
    link remark; the order since → link is the unit test's above)."""

    board = _board(s, KNIGHT, "1... Ra8 2. Kh1 Ke7 3. Rb1", 4)
    for item in [*board["changes"], *board.get("scene", ())]:
        assert len(item["proves"]) <= ITEM_CAP and "…" not in item["proves"], item["proves"]


# -- §7: step 0 and step 2 with the new kinds (implementation review N2) --------------------------


def test_step_0_cuts_files_then_structure_then_the_scene_before_todays_kinds() -> None:
    from test_digest import _claim, _glossary, _record

    from calliope.agent.digest import bounded, digest, size

    def item(kind, ref):
        return {"ref": ref, "kind": kind, "part": "reason", "owner": "white", "good_for": "black",
                "proves": "p" * 300, "propositions": []}  # fmt: skip

    d = digest(_record([_claim(1, "consequence", "supported")]), _glossary())
    d["grade"] = "good"
    d["board"] = {"v": "board_v4", "mover": "white",
                  "changes": [item("threat", "t1"), item("structure", "s1"), item("structure", "s2"),
                              item("file", "f1"), item("file", "f2")],
                  "scene": [item("scene", "c1"), item("scene", "c2")]}  # fmt: skip
    one_item = size(item("file", "fx")) + 1
    cut = bounded(d, size(d) - 2 * one_item + 20)  # two items' worth: the files go
    assert [c["ref"] for c in cut["board"]["changes"]] == ["t1", "s1", "s2"]
    assert [c["ref"] for c in cut["board"]["scene"]] == ["c1", "c2"]
    cut = bounded(d, size(d) - 4 * one_item + 20)  # then the second structure, the second scene
    assert [c["ref"] for c in cut["board"]["changes"]] == ["t1", "s1"]
    assert [c["ref"] for c in cut["board"]["scene"]] == ["c1"]


def test_step_2_shortens_the_other_candidates_lines_too() -> None:
    from test_digest import _claim, _glossary, _record

    from calliope.agent.digest import bounded, digest, size

    d = digest(_record([_claim(1, "consequence", "supported")]), _glossary())
    d["others"] = [{"ref": f"s{i}.x", "move": "1.Nbd2", "score": None, "score_text": "+0.10",
                    "pv": "1.Nbd2 Nbd7 2.Ngf3 Ngf6 3.Bxf7+ Kxf7"} for i in range(3)]  # fmt: skip
    cut = bounded(d, size(d) - 40)
    assert "short_pv" in cut["not_shown"]["steps"]
    assert all(o["pv"] == "1.Nbd2 Nbd7 2.Ngf3 Ngf6" for o in cut["others"])


# -- test 4: a submission citing a scene item may write its previous move (review N3) -------------


def test_a_sentence_citing_the_scene_writes_its_previous_move(s) -> None:
    game = _open(s, ATTACKED, "1... Rb8 2. Kh1", 2)
    d = s.ply(game, 2)
    scene = d["board"]["scene"][0]["ref"]

    def submit(cites):
        return s.submit_commentary(game, ply=2, agent={"name": "t"}, propositions=[
            {"id": "j", "kind": "judgement", "judgement": d["judgement"]}], sentences=[
            {"text": "2.Kh1은 판정을 받은 수다.", "class": "sourced", "cites": ["j"]},
            {"text": "1...Rb8로 흑 룩이 b1의 룩을 노렸다.", "class": "sourced", "cites": cites}])  # fmt: skip

    assert submit(["j", scene])["accepted"]
    refused = submit(["j"])
    assert not refused["accepted"] and {v["rule"] for v in refused["violations"]} == {"S3"}
