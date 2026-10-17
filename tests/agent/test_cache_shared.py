"""CC-D §3.3 and the implementation checks N1, N2: a pair the ply cache keeps is shared with the
session's readers, never copied, and unchanged by them; and CC-D §6's final round trip through the
agent: what a session answers from the pairs it wrote equals what a new process answers from the
files (review F3)."""

from __future__ import annotations

import json
import re

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


def _neutral(value):
    """An answer without what differs by run: handles' process tokens, `cached`, the budget."""

    if isinstance(value, dict):
        value = {k: v for k, v in value.items() if k not in ("cached", "budget_left")}
    text = re.sub(
        r"([a-z])(\d+)\.[0-9a-f]{24}", r"\1\2.<token>", json.dumps(value, ensure_ascii=False)
    )
    return json.loads(text)


def test_answers_from_written_pairs_equal_answers_from_the_files(tmp_path) -> None:
    """Review F3: the full answer, the digest and the board with a commentary, from the pairs the
    first session wrote (`written`) and from a new process reading the files (`replayed`)."""

    first = session(tmp_path)
    try:
        first.open_game(pgn=GAME)
        written = {ply: (first.ply(G1, ply, view="full"), first.ply(G1, ply)) for ply in (1, 3, 5)}
        assert first.cache.counts["written"] == 3 and first.cache.counts["replayed"] == 0
        d = written[3][1]
        accepted = first.submit_commentary(
            G1, agent={"name": "t"}, ply=3,
            propositions=[{"id": "p1", "kind": "judgement", "judgement": d["judgement"]}],
            sentences=[{"text": f"{d['move']}로 이어졌다.", "class": "sourced", "cites": ["p1"]}],
        )  # fmt: skip
        assert accepted["accepted"]
        board_first, text_first = first.show_game(G1, None)
    finally:
        first.close()
    second = session(tmp_path)  # a new process: every pair is loaded from its files
    try:
        second.open_game(pgn=GAME)
        for ply, (full, digest) in written.items():
            assert _neutral(second.ply(G1, ply, view="full")) == _neutral(full)
            assert _neutral(second.ply(G1, ply)) == _neutral(digest)
        assert second.cache.counts["written"] == 0 and second.cache.counts["replayed"] == 3
        board_second, text_second = second.show_game(G1, None)
        assert board_second == board_first and text_second == text_first
        assert "ai_commentary" in next(p for p in board_second["plies"] if p["ply"] == 3)
    finally:
        second.close()
