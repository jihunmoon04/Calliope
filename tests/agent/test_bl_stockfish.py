"""BL-D §8 with Stockfish 19 (gated), on issue #123's game: 34...Qb3's held queen attacked by the
rook on f3 before and after, first on the board, the threats pointing at it and the played line's
material; 7...Bxe2's held queen; 13.Rb1's held pawn and no played material (the best line loses it
too); every served proposition verifying as given."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from test_board_stockfish import _all_verify

from calliope.agent import Limits, Session

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")
GAME = (Path(__file__).resolve().parent / "fixtures" / "hung_queen.pgn").read_text()
pytestmark = pytest.mark.skipif(not STOCKFISH or not os.path.exists(STOCKFISH),
                                reason="needs Stockfish 19")  # fmt: skip


@pytest.fixture
def s(tmp_path):
    from calliope.facts.search import StockfishEngine

    s = Session(tmp_path, lambda: StockfishEngine.start(STOCKFISH),
                Limits(max_searches=400, max_uncached_plies=64))  # fmt: skip
    yield s
    s.close()


def _digest(s, ply: int) -> tuple[str, dict]:
    game = s.open_game(pgn=GAME, plies=f"{ply}-{ply}")["game"]
    return game, s.ply(game, ply)


def _attacks(item: dict) -> list[tuple[str, str]]:
    return [(p["attacker"], p["target"]) for p in item["propositions"] if p["kind"] == "attack"]


def test_34_qb3_the_queen_the_rook_holds_comes_first(s) -> None:
    game, qb3 = _digest(s, 68)
    assert qb3["grade"] == "blunder"
    board = qb3["board"]
    first = board["changes"][0]
    assert first["kind"] == "held" and first["owner"] == "black"
    assert _attacks(first) == [("f3", "e3"), ("f3", "b3")]
    assert (
        "수 전 e3에서 이미 백 룩(f3)이 공격했고, 수 뒤 b3에서도 공격한다" in first["proves"]
    )  # PW
    assert "흑이 9점을 잃는다" in first["proves"] and "교환" not in first["proves"]
    threats = [c for c in board["changes"] if c["kind"] == "threat"]
    assert threats and all(c["opponent_first"] == first["ref"] for c in threats)
    played = board["played_material"]
    assert [(p["to"], p["balance"]) for p in played["propositions"]] == [(2, -9), (8, -9)]
    assert "35.Rxb3 뒤 흑의 물질 차이는 수 전보다 9점 나빠지고" in played["proves"]  # review B2
    assert "엔진 라인 8수째 38.Rd3 뒤에도 9점 나빠져 있다" in played["proves"]  # review N7
    assert played["part"] == "consequence" and "뒤진다" not in played["proves"]
    _all_verify(s, game, 68, qb3)


def test_7_bxe2_leaves_the_queen_the_pawn_attacks(s) -> None:
    game, bxe2 = _digest(s, 14)
    held = [c for c in bxe2["board"]["changes"] if c["kind"] == "held"]
    assert len(held) == 1 and _attacks(held[0]) == [("f4", "e5"), ("f4", "e5")]
    assert bxe2["board"]["changes"][0]["kind"] == "held"  # the queen (9) before the bishop (3)
    _all_verify(s, game, 14, bxe2)


def test_13_rb1_holds_the_pawn_and_serves_no_played_material(s) -> None:
    game, rb1 = _digest(s, 25)
    assert rb1["grade"] == "mistake"
    held = [c for c in rb1["board"]["changes"] if c["kind"] == "held"]
    assert [c["propositions"][2]["piece"] for c in held] == ["c5"]  # any gain on a weak move
    assert "played_material" not in rb1["board"]  # the best line ends a pawn down as well
    _all_verify(s, game, 25, rb1)


def test_34_rf3_a_best_move_keeps_todays_order(s) -> None:
    _game, rf3 = _digest(s, 67)
    assert rf3["grade"] == "best" and "played_material" not in rf3["board"]
    assert all("opponent_first" not in c for c in rf3["board"]["changes"])


def test_11_d3_a_best_move_leaves_a_one_point_pawn_out(s) -> None:
    """BL-D §2's gate end to end: the c5 pawn is exposed before and after 11.d3 (gain 1), a best
    move, so no item; at 13.Rb1, a mistake, the same pawn is one."""

    _game, d3 = _digest(s, 21)
    assert d3["grade"] == "best"
    assert not [c for c in d3["board"]["changes"] if c["kind"] == "held"]


def test_the_items_cite_by_handle_and_a_judged_move_reads_the_same(s) -> None:
    """The `b` handles expand to the items' propositions (MS-D §9.1), `played_material`'s moves
    and points citable through it; `judge_move` of the played move gives the same board."""

    game, qb3 = _digest(s, 68)
    board = qb3["board"]
    held, played = board["changes"][0], board["played_material"]
    answer = s.submit_commentary(game, ply=68, agent={"name": "t"}, sentences=[
        {"text": "34...Qb3는 블런더 판정을 받았다.", "class": "sourced", "cites": [qb3["judgement"]]},
        {"text": "흑 퀸은 수 전 e3에서도 수 뒤 b3에서도 백 룩 f3의 공격을 받는다.", "class": "sourced",
         "cites": [held["ref"]]},
        {"text": "엔진 라인에서 35.Rxb3 뒤 흑의 물질 차이는 수 전보다 9점 나빠진다.", "class": "sourced",
         "cites": [played["ref"]]},
    ])  # fmt: skip
    assert answer["accepted"], answer
    judged = s.judge_move(game, {"ply": 68, "at": "before"}, "Qb3")["board"]
    assert [c["ref"] for c in judged["changes"]] == [c["ref"] for c in board["changes"]]
    assert judged["played_material"]["ref"] == played["ref"]
