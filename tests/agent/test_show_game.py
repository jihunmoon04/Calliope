"""AG3-D D10 and §5 (MCP): `show_game`'s limit of 40 plies over a game of 41 cached plies — one
document of 1 and of 40 plies, an error naming the limit for 41 — and nothing charged."""

from __future__ import annotations

import pytest
from agent_helpers import session

from calliope.agent import AgentError, Limits
from calliope.agent.session import SHOW_LIMIT
from calliope.results import schema_errors

LONG = ("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O "
        "9. h3 Nb8 10. d4 Nbd7 11. c4 c6 12. cxb5 axb5 13. Nc3 Bb7 14. Bg5 b4 15. Nb1 h6 "
        "16. Bh4 c5 17. dxe5 Nxe4 18. Bxe7 Qxe7 19. exd6 Qf6 20. Nbd2 Nxd6 21. Nc4 *\n")  # fmt: skip


@pytest.fixture(scope="module")
def s(tmp_path_factory):
    """A session whose game has all 41 plies cached (about a minute on the synthetic engine)."""

    s = session(tmp_path_factory.mktemp("long"), Limits(50, 10**6, 10**6))
    opened = s.open_game(pgn=LONG, plies="1-41")
    assert len(opened["moves"]) == 41 and all(m["cached"] for m in opened["moves"])
    yield s
    s.close()


def test_one_and_forty_plies_are_shown(s) -> None:
    assert SHOW_LIMIT == 40
    left = s.budget.left()
    one, text = s.show_game("g1", "17")
    assert [p["ply"] for p in one["plies"]] == [17] and schema_errors(one) == []
    assert text.splitlines()[0] == "게임 g1: 분석된 수 1개를 판에 보여 줍니다 (수 17)."
    forty, text = s.show_game("g1", "2-41")
    assert [p["ply"] for p in forty["plies"]] == list(range(2, 42)) and schema_errors(forty) == []
    assert len(text.splitlines()) == 41 and "빠진 수" not in text
    assert s.budget.left() == left


def test_forty_one_plies_name_the_limit(s) -> None:
    with pytest.raises(AgentError, match=r"한 번에 40수까지 .* \(요청 41수\)"):
        s.show_game("g1", "1-41")
    with pytest.raises(AgentError, match=r"캐시된 수가 41개라 .* \(최대 40수\).*\"1-40\""):
        s.show_game("g1")  # without `plies`: the game's 41 cached plies
