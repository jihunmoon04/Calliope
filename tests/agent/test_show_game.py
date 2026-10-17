"""AG3-D D10 and §5 (MCP), as AG6-D §6.1 amends them: `show_game` over a game of 41 cached plies —
the board of one ply and of 40, the whole game's moves and states in each — its limits (200 plies
of records, a game of 600 plies) and a ply whose files do not load; nothing charged."""

from __future__ import annotations

import pytest
from agent_helpers import gid, session

from calliope.agent import AgentError, Limits
from calliope.agent.session import SHOW_LIMIT, _check_game_path
from calliope.results import schema_errors

LONG = ("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O "
        "9. h3 Nb8 10. d4 Nbd7 11. c4 c6 12. cxb5 axb5 13. Nc3 Bb7 14. Bg5 b4 15. Nb1 h6 "
        "16. Bh4 c5 17. dxe5 Nxe4 18. Bxe7 Qxe7 19. exd6 Qf6 20. Nbd2 Nxd6 21. Nc4 *\n")  # fmt: skip
G = gid(LONG)


@pytest.fixture(scope="module")
def s(tmp_path_factory):
    """A session whose game has all 41 plies cached (about a minute on the synthetic engine)."""

    s = session(
        tmp_path_factory.mktemp("long"),
        Limits(max_uncached_plies=50, max_uncached_plies_per_call=50, max_searches=10**6),
    )
    opened = s.open_game(pgn=LONG, plies="1-41")
    assert len(opened["moves"]) == 41 and all(m["cached"] for m in opened["moves"])
    yield s
    s.close()


def test_a_range_carries_its_records_and_the_whole_games_states(s) -> None:
    assert SHOW_LIMIT == 200
    left = s.budget.left()
    one, text = s.show_game(G, "17")
    assert [p["ply"] for p in one["result"]["plies"]] == [17] and schema_errors(one["result"]) == []
    assert len(one["plies"]) == 41 and {e["state"] for e in one["plies"]} == {"analysed"}
    assert text.splitlines()[:2] == [f"게임 {G}: 41수 가운데 41수가 분석되어 있습니다.",
                                     "판에 수 17의 분석을 보여 줍니다."]  # fmt: skip
    forty, text = s.show_game(G, "2-41")
    assert [p["ply"] for p in forty["result"]["plies"]] == list(range(2, 42))
    assert "분석되지 않은 수" not in text
    whole, _ = s.show_game(G)  # the default range: the first 200, here the whole game
    assert [p["ply"] for p in whole["result"]["plies"]] == list(range(1, 42))
    assert s.budget.left() == left


def test_the_limits_of_the_board_and_of_the_game_path(s) -> None:
    with pytest.raises(AgentError, match=r"show_game는 한 번에 200수까지 .* [(]요청 201수[)]"):
        s._range("1-201", 600, SHOW_LIMIT, "show_game")
    with pytest.raises(AgentError, match="at most 600 plies, not 601"):
        _check_game_path(601)
    _check_game_path(600)


def test_a_ply_whose_files_do_not_load_is_not_analysed(s) -> None:
    key, *_ = s._key(s.game(G).parsed, 41)
    graph = s.cache.paths(key)[1]
    kept = graph.read_bytes()
    try:
        graph.write_bytes(b"damaged")
        view, text = s.show_game(G)
        assert [p["ply"] for p in view["result"]["plies"]] == list(range(1, 41))
        assert view["plies"][40] == {"ply": 41, "state": "none"}
        assert "분석되지 않은 수: 41." in text
    finally:
        graph.write_bytes(kept)
