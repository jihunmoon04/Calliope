"""AG-D §11 test 10 with Stockfish 19 (gated): the 2026-10-14 game's 17.Ne3 (`g1014`, from its
position, no names) — `ply`, `judge_move` of 17.Kd1, a search after 17.Ne3, the budget each step
used, and a commentary with `check`, `engine_score`, `claim` (`line_fact` for the exchange, not
`result`) and one interpretation, accepted."""

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
        record = s.ply(game["game"], 1, view="full")
        assert record["cached"] and record["analysis"]["claims"]
        gain = [c for c in record["analysis"]["claims"] if c["template"] == "material_gain_v3"]
        assert any(c["status"] == "supported" for c in gain)  # the exchange along the line
        assert all(any(k["kind"] == "attributed" and not k["passed"] for k in c["checks"])
                   for c in gain if c["status"] == "supported")  # fmt: skip
        kd1 = s.judge_move(game["game"], {"ply": 1, "at": "before"}, "Kd1", view="full")
        assert not kd1["played"] and kd1["evaluation"]["played"] is not None
        after = s.explore(game["game"], {"ply": 1, "at": "after"}, [], search=True)
        assert len(after["search"]["lines"]) == 5
        assert all(p["by"] == "engine" for line in after["search"]["lines"] for p in line["pv"])
        used = s.budget.meter.used
        assert s.budget.uncached.used == 2 and 3 <= used <= 2 * 10 + 1  # two analyses and a search
        j = record["analysis"]["judgements"][0]
        exchange = next(c for c in gain if c["status"] == "supported")
        claim = {"id": "p3", "kind": "claim", "claim": exchange["ref"],
                 "scopes": exchange["effective_scopes"]}  # fmt: skip
        propositions = [
            {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": "Ne3",
             "grade": j["grade"], "label": j["label"], "best_move": j["best"]["move"]["uci"]},
            {"id": "p2", "kind": "check", "position": {"from_root": []}, "checkers": ["e8"]},
            claim | {"use": "line_fact"},
            {"id": "p4", "kind": "engine_score", "line": j["best"]["ref"],
             "move": j["best"]["move"]["uci"], "score": j["best"]["score"]},
        ]  # fmt: skip
        cp = j["best"]["score"]["cp"]
        sentences = [
            {"text": "17.Ne3는 e8의 룩이 건 체크를 막는다.", "class": "sourced",
             "cites": ["p1", "p2"]},
            {"text": f"엔진은 17.Ne3에 {cp / 100:+.2f}을 준다.", "class": "sourced",
             "cites": ["p1", "p4"]},
            {"text": "엔진 라인에서 기물이 오가지만, 이 수가 얻어 낸 것은 아니다.",
             "class": "sourced", "cites": ["p3"]},
            {"text": "체크를 막으면서 기물을 중앙에 두는 실용적인 선택으로 보인다.",
             "class": "interpretation", "cites": ["p1", "p2"]},
        ]  # fmt: skip
        as_result = [*propositions[:2], claim | {"use": "result"}, propositions[3]]
        refused = s.submit_commentary(game["game"], ply=1, agent={"name": "t"},
                                      propositions=as_result, sentences=sentences)  # fmt: skip
        assert [v["field"] for v in refused["violations"] if "field" in v] == ["use"]
        answer = s.submit_commentary(game["game"], ply=1, agent={"name": "t"},
                                     propositions=propositions, sentences=sentences)  # fmt: skip
        assert answer["accepted"], answer
    finally:
        s.close()
