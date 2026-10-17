"""CC-D §3.3 and the implementation checks N1, N2: a pair the ply cache keeps is shared with the
session's readers, never copied, and unchanged by them."""

from __future__ import annotations

from agent_helpers import G1, GAME, session

from calliope.facts import EngineProfile
from calliope.reasoning.storage import save
from calliope.server import cache as cache_module
from calliope.server import normalized_ply

PROFILE = EngineProfile()


def test_a_kept_pair_is_unchanged_by_its_readers(tmp_path) -> None:
    s = session(tmp_path)
    try:
        s.open_game(pgn=GAME)
        s.ply(G1, 3)  # the digest
        full = s.ply(G1, 3, view="full")
        d = s.ply(G1, 3)
        s.submit_commentary(G1, agent={"name": "t"}, ply=3,
                            propositions=[{"id": "p1", "kind": "judgement",
                                           "judgement": d["judgement"]}],
                            sentences=[{"text": f"{d['move']}로 이어졌다.", "class": "sourced",
                                        "cites": ["p1"]}])  # fmt: skip
        s.show_game(G1, None)
        game = s.game(G1)
        expected = normalized_ply(game.parsed, 3, PROFILE)
        key, *_ = s._key(game.parsed, 3)
        tree_path, graph_path = s.cache.paths(key)
        kept = s.cache._kept_pair(key, cache_module._bundle(tree_path.read_bytes(),
                                                            graph_path.read_bytes()))  # fmt: skip
        assert kept is not None and kept.analysis.round_zero.request == expected
        assert save(kept.analysis, kept.rendered) == (
            tree_path.read_bytes(),
            graph_path.read_bytes(),
        )
        # implementation check N2: the session's projected analyses hold the same object
        held = s.analyses[f"{full['bundle']['tree']}:{full['bundle']['graph']}"][1]
        assert held is kept.analysis
    finally:
        s.close()
