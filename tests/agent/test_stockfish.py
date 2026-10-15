"""AG-D §11 test 10, the AG1 part, with Stockfish 19 (gated): the 2026-10-14 game's 17.Ne3
(`g1014`, from its position, no names) — `ply`, `judge_move` of 17.Kd1, a search after 17.Ne3,
the budget each step used."""

from __future__ import annotations

import os

import pytest

from calliope.agent import Limits, Session

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")
FEN = "rn2r3/p2p1k1p/b7/1pp2N2/8/2P5/P2N1PPP/R1B1KB1R w KQ - 3 17"


@pytest.mark.skipif(not STOCKFISH or not os.path.exists(STOCKFISH), reason="needs Stockfish 19")
def test_17_ne3_and_17_kd1(tmp_path) -> None:
    from calliope.facts.search import StockfishEngine

    s = Session(tmp_path, lambda: StockfishEngine.start(STOCKFISH), Limits())
    try:
        game = s.open_game(fen=FEN, moves=["Ne3"], plies="1")
        assert game["moves"][0]["grade"] is not None
        record = s.ply("g1", 1)
        assert record["cached"] and record["analysis"]["claims"]
        gain = [c for c in record["analysis"]["claims"] if c["template"] == "material_gain_v3"]
        assert all(any(k["kind"] == "attributed" and not k["passed"] for k in c["checks"])
                   for c in gain if c["status"] == "supported")  # fmt: skip
        kd1 = s.judge_move("g1", {"ply": 1, "at": "before"}, "Kd1")
        assert not kd1["played"] and kd1["evaluation"]["played"] is not None
        after = s.explore("g1", {"ply": 1, "at": "after"}, [], search=True)
        assert len(after["search"]["lines"]) == 5
        assert all(p["by"] == "engine" for line in after["search"]["lines"] for p in line["pv"])
        used = s.budget.meter.used
        assert s.budget.uncached == 2 and 3 <= used <= 2 * 10 + 1  # two analyses and a search
    finally:
        s.close()
