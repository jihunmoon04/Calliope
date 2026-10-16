"""AG3-D D10 and §5 (MCP): `show_game`'s limit of 40 plies over a game of 41 cached plies — one
document of 1 and of 40 plies, an error naming the limit for 41 — and nothing charged."""

from __future__ import annotations

import pytest
from agent_helpers import gid, session

from calliope.agent import AgentError, Limits
from calliope.agent.session import SHOW_LIMIT
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


def test_one_and_forty_plies_are_shown(s) -> None:
    assert SHOW_LIMIT == 40
    left = s.budget.left()
    one, text = s.show_game(G, "17")
    assert [p["ply"] for p in one["plies"]] == [17] and schema_errors(one) == []
    assert text.splitlines()[0] == f"게임 {G}: 분석된 수 1개를 판에 보여 줍니다 (수 17)."
    forty, text = s.show_game(G, "2-41")
    assert [p["ply"] for p in forty["plies"]] == list(range(2, 42)) and schema_errors(forty) == []
    assert len(text.splitlines()) == 41 and "빠진 수" not in text
    assert s.budget.left() == left


def test_forty_one_plies_name_the_limit(s) -> None:
    with pytest.raises(AgentError, match=r"한 번에 40수까지 .* \(요청 41수\)"):
        s.show_game(G, "1-41")
    with pytest.raises(AgentError, match=r"분석된 수가 40개를 넘어 .*\"1-40\""):
        s.show_game(G)  # without `plies`: the game's 41 cached plies


def test_the_limit_counts_the_plies_that_load(s) -> None:
    """Review recommendation: 41 cached plies, one of them damaged, are 40 that can be shown."""

    key, *_ = s._key(s.game(G).parsed, 41)
    graph = s.cache.paths(key)[1]
    kept = graph.read_bytes()
    try:
        graph.write_bytes(b"damaged")
        document, text = s.show_game(G)
        assert [p["ply"] for p in document["plies"]] == list(range(1, 41))
        assert "분석되지 않아 빠진 수: 41" in text
    finally:
        graph.write_bytes(kept)
