"""WS-D over the synthetic engine: where the pieces of a since sentence stood (§2), the count on the
scene's kept target (§3)."""

from __future__ import annotations

import pytest
from agent_helpers import session

from calliope.agent import Limits
from calliope.agent.remarks import board_tokens, link_remark, since_held, subject


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


def _board(s, fen: str, moves: str, ply: int) -> dict:
    game = s.open_game(pgn=f'[FEN "{fen}"]\n\n{moves} *\n', plies=f"1-{ply}")["game"]
    board = s.ply(game, ply)["board"]
    assert board.get("refused") is None  # every proposition verifies (Board._verify)
    return board


def _item(board: dict, kind: str) -> dict:
    (item,) = [c for c in [*board["changes"], *board.get("scene", ())] if c["kind"] == kind]
    return item


def _attacks(item: dict) -> list[tuple[dict, str, str]]:
    return [(p["position"], p["attacker"], p["target"]) for p in item["propositions"]
            if p["kind"] == "attack"]  # fmt: skip


# -- §2.1: where they stood at the run's first position -------------------------------------------

DEFENDED = "7k/8/4p3/3n4/8/8/8/K1R5 b - - 0 1"  # the d5 knight, defended by e6


def test_a_since_sentence_names_where_the_attacker_stood_when_the_run_began(s) -> None:
    """2.Rd1 attacks d5, 3.Rd2 keeps it, 3...e5 drops the defence: the rook stood on d1 then."""

    board = _board(s, DEFENDED, "1... Kg8 2. Rd1 Kh8 3. Rd2 e5", 5)
    for kind in ("weakness", "lost_defence"):
        item = _item(board, kind)
        assert (
            "이 수 전에도 있었다(2.Rd1 뒤부터). 2.Rd1 뒤에는 백 룩이 d1에 있었다. 3...e5로"
            in item["proves"]
        )
        assert ({"ply": 2, "at": "after"}, "d1", "d5") in _attacks(item)  # the square written
        # a sentence citing the item may write it (board_tokens reads the text's squares)
        assert (
            "d1"
            in board_tokens(item["proves"], "e6e5", "7k/8/4p3/3n4/8/8/3R4/K7 b - - 4 3").squares
        )


def test_from_the_start_says_where_in_the_start_position(s) -> None:
    board = _board(s, "7k/8/4p3/3n4/8/8/8/K2R4 b - - 0 1", "1... Kg8 2. Rd2 e5", 3)
    assert ("(시작 국면부터). 시작 국면에서는 백 룩이 d1에 있었다. 2...e5로 바뀐 것은"
            in _item(board, "weakness")["proves"])  # fmt: skip


def test_no_square_sentence_when_the_pieces_stood_where_they_stand(s) -> None:
    board = _board(s, "r3k3/8/8/8/N7/8/8/R5K1 w - - 0 1", "1. Kh1 Ke7 2. Rb1", 3)
    proves = _item(board, "lost_defence")["proves"]
    assert "에 있었다" not in proves and "(시작 국면부터). 2.Rb1로" in proves


def test_at_least_since_names_where_the_attacker_stood_at_the_bound(wide) -> None:
    moves, number = "1... Ra8", 2
    for i in range(10):
        moves += f" {number}. {('Kh1', 'Kg1')[i % 2]} {('Ra7', 'Ra6', 'Ra8')[i % 3]}"
        number += 1
    board = _board(wide, "1r2k3/8/8/8/N7/8/8/R5K1 b - - 0 1", f"{moves} {number}. Rb1", 22)
    lost = _item(board, "lost_defence")
    assert ("(적어도 3...Ra6 뒤부터). 3...Ra6 뒤에는 흑 룩이 a6에 있었다. 12.Rb1로"
            in lost["proves"])  # fmt: skip
    assert ({"ply": 5, "at": "after"}, "a6", "a4") in _attacks(lost)


# -- §2.2–2.3: where they stood before the move ---------------------------------------------------


def test_a_weakness_whose_piece_moved_into_the_attack_names_both_squares(s) -> None:
    """1...Na6: the knight leaves c5, defended by d6, for a6 on the same rook's file."""

    weak = _item(_board(s, "7k/8/3p4/R1n5/8/8/8/K7 b - - 0 1", "1... Na6", 1), "weakness")
    assert weak["proves"].endswith(
        "백 룩(a5)의 이 공격은 이 수 전에도 있었다(시작 국면부터). 이 수 전에는 흑 나이트가 c5에 "
        "있었다. 1...Na6로 바뀐 것은 공격이 아니라 흑 나이트가 옮겨 간 a6의 잡고 되잡기 셈이다"
    )
    assert _attacks(weak) == [({"ply": 1, "at": "after"}, "a5", "a6"),
                              ({"ply": 1, "at": "before"}, "a5", "c5")]  # fmt: skip


def test_a_threat_whose_attacker_moved_names_where_it_stood(s) -> None:
    """1.Qxd7 takes the bishop that defended e8; the queen attacked e8 from f7 before."""

    board = _board(s, "4r2k/3b1Q2/8/8/8/8/8/K7 w - - 0 1", "1. Qxd7", 1)
    threat = next(c for c in board["changes"] if c["kind"] == "threat"
                  and c["propositions"][0]["kind"] == "exposed")  # fmt: skip
    assert ("(시작 국면부터). 이 수 전에는 백 퀸이 f7에 있었다. 1.Qxd7로 바뀐 것은 공격이 아니라 그 "
            "칸의 잡고 되잡기 셈이다") in threat["proves"]  # fmt: skip
    assert ({"ply": 1, "at": "before"}, "f7", "e8") in _attacks(threat)


def test_a_held_item_gets_no_before_sentence(s) -> None:
    held = _item(_board(s, "r3k3/8/8/8/8/8/8/1R4K1 b - - 0 1", "1... Rb8 2. Rb2", 2), "held")
    assert "이 수 전에는" not in held["proves"] and "옮겨 간" not in held["proves"]


# -- review B2: a piece is named by its type at that position --------------------------------------

PROMOTE = "8/4P3/3K4/8/8/8/k7/4r3 w - - 0 1"  # the e1 rook attacks the e7 pawn from the start


def test_a_promoted_piece_is_named_a_pawn_before_the_move(s) -> None:
    weak = _item(_board(s, PROMOTE, "1. e8=Q", 1), "weakness")
    assert "이 수 전에는 백 폰이 e7에 있었다" in weak["proves"]
    assert "백 폰이 옮겨 간 e8의 잡고 되잡기 셈이다" in weak["proves"]
    assert "퀸이 e7" not in weak["proves"]


def test_a_held_items_run_names_the_pawn_in_brackets_before_its_last_clause(s) -> None:
    held = _item(_board(s, PROMOTE, "1. e8=Q Kb3 2. Kc7", 3), "held")
    assert held["proves"].endswith(
        "흑 룩(e1)의 이 공격은 시작 국면부터 이어졌고(시작 국면에서는 백 폰이 e7에 있었다), 이 수는 "
        "그 공격을 피하지 못했다"
    )
    assert ({"ply": 1, "at": "before"}, "e1", "e7") in _attacks(held)


def test_a_link_remark_follows_the_held_attacks_clause() -> None:
    """Review N3: the link attaches to "피하지 못했다", not to where a piece stood."""

    text = since_held("흑 룩(e1)", "시작 국면부터", ["시작 국면에서는 백 폰이 e7에 있었다"])
    text += link_remark({"link": "explains", "to_template": "material_loss_v2"})
    assert "있었다), 이 수는 그 공격을 피하지 못했다, 이 변화가" in text


def test_the_subject_particle() -> None:
    assert subject("white", "knight") == "백 나이트가" and subject("black", "queen") == "흑 퀸이"
    assert subject("black", "pawn") == "흑 폰이" and subject("white", "rook") == "백 룩이"


# -- §3: the count on a kept target ---------------------------------------------------------------

ATTACKED = "r3k3/8/8/8/8/8/8/1R3RK1 b - - 0 1"  # 1...Rb8 attacks the b1 rook, defended by f1


def test_a_kept_defended_target_says_nothing_is_lost(s) -> None:
    scene = _board(s, ATTACKED, "1... Rb8 2. Kh1", 2)["scene"][0]
    assert scene["proves"].endswith(
        "2.Kh1 뒤: 백 룩(b1)은 흑 룩(b8)의 공격을 계속 받는다(그 칸의 잡고 되잡기만 셈하면 잃는 것이 "
        "없다)"
    )
    assert scene["propositions"][-1] == {"kind": "exposed", "position": {"ply": 2, "at": "after"},
                                         "piece": "b1", "exposed": "not_exposed", "gain": 0}  # fmt: skip


def test_a_kept_exposed_target_says_its_owner_loses(s) -> None:
    scene = _board(s, ATTACKED, "1... Rb8 2. Rf2", 2)["scene"][0]
    assert scene["proves"].endswith("계속 받는다(그 칸의 잡고 되잡기만 셈하면 백이 5점을 잃는다)")
    assert scene["propositions"][-1]["exposed"] == "exposed"


def test_after_a_check_the_kept_target_gets_no_count(s) -> None:
    """Review B1: after 2.Rf8+ Black's captures on b1 are illegal, so the count would read 0."""

    scene = _board(s, ATTACKED, "1... Rb8 2. Rf8+", 2)["scene"][0]
    assert scene["proves"].endswith("2.Rf8+ 뒤: 백 룩(b1)은 흑 룩(b8)의 공격을 계속 받는다")
    assert [p["kind"] for p in scene["propositions"]] == ["attack", "attack"]


def test_a_moved_kept_target_names_its_square(s) -> None:
    scene = _board(s, ATTACKED, "1... Rb8 2. Rb2", 2)
    (scene,) = [c for c in scene["scene"] if c["relation"] == "attack"]
    assert scene["proves"].endswith(
        "백 룩(b1)은 b2로 옮겼지만 흑 룩(b8)의 공격을 계속 받는다(b2의 잡고 되잡기만 셈하면 백이 "
        "5점을 잃는다)"
    )


def test_a_double_attacks_kept_targets_each_get_a_count(s) -> None:
    board = _board(s, "4k3/8/5n2/8/8/2B1B3/1P3P2/6K1 b - - 0 1", "1... Nd5 2. Kh1", 2)
    (scene,) = board["scene"]
    assert scene["proves"].count("(그 칸의 잡고 되잡기만 셈하면 잃는 것이 없다)") == 2
    assert [(p["piece"], p["exposed"]) for p in scene["propositions"]
            if p["kind"] == "exposed"] == [("c3", "not_exposed"), ("e3", "not_exposed")]  # fmt: skip


# -- review N1: whole or nothing ------------------------------------------------------------------


def test_a_part_that_does_not_fit_leaves_its_also_propositions_out(monkeypatch) -> None:
    from test_st import _fake

    from calliope.agent import remarks

    monkeypatch.setattr(remarks, "ITEM_CAP", 60)
    item = {"kind": "scene", "proves": "가" * 40, "propositions": [{"kind": "attack"}]}
    assert not _fake()._append(item, "나" * 30, also=[{"kind": "exposed"}])
    assert item == {"kind": "scene", "proves": "가" * 40, "propositions": [{"kind": "attack"}]}


def test_a_fate_that_does_not_fit_takes_its_count_with_it(tmp_path, monkeypatch) -> None:
    from calliope.agent import remarks

    first = session(tmp_path / "a")
    scene = _board(first, ATTACKED, "1... Rb8 2. Kh1", 2)["scene"][0]
    first.close()
    monkeypatch.setattr(remarks, "ITEM_CAP", scene["proves"].index(". 2.Kh1 뒤:") + 10)
    second = session(tmp_path / "b")
    cut = _board(second, ATTACKED, "1... Rb8 2. Kh1", 2)["scene"][0]
    second.close()
    assert "계속 받는다" not in cut["proves"]
    assert cut["propositions"] == scene["propositions"][:1]  # the attack before the move only
