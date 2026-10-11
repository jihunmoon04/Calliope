"""Round 0 against real Stockfish 19 (gated on `CALLIOPE_STOCKFISH_PATH`): judgements and cost.

The Opera game (Morphy, 1858). 17.Qb8+ forces mate (17…Nxb8 18.Rd8#), so it is rank 1 of its
parent's search and graded BEST with a mate score; the cost is recorded against R0-D §17.
"""

from __future__ import annotations

import os
import time

import pytest

from calliope.facts import Color, EngineProfile, FactEngine, Mate, RootSpec
from calliope.facts.search import StockfishEngine
from calliope.reasoning import AnalysisRequest, Controller, Grade, GradingSpec, JudgementStatus

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")
pytestmark = pytest.mark.skipif(not STOCKFISH, reason="CALLIOPE_STOCKFISH_PATH is not set")

OPERA = (
    "e4", "e5", "Nf3", "d6", "d4", "Bg4", "dxe5", "Bxf3", "Qxf3", "dxe5", "Bc4", "Nf6",
    "Qb3", "Qe7", "Nc3", "c6", "Bg5", "b5", "Nxb5", "cxb5", "Bxb5+", "Nbd7", "O-O-O", "Rd8",
    "Rxd7", "Rxd7", "Rd1", "Qe6", "Bxd7+", "Nxd7", "Qb8+", "Nxb8", "Rd8#",
)  # fmt: skip


def test_round_zero_on_the_opera_game() -> None:
    target = OPERA.index("Qb8+") + 1
    with StockfishEngine.start(STOCKFISH) as port:
        controller = Controller(FactEngine(engine=port))
        started = time.perf_counter()
        result = controller.round_zero(
            AnalysisRequest(
                RootSpec(), OPERA, target, EngineProfile(), grading=GradingSpec("quality_v1")
            )
        )
        elapsed = time.perf_counter() - started
    judgement, previous = result.judgements
    assert judgement.status is JudgementStatus.DECIDED
    assert judgement.grade is Grade.BEST
    assert judgement.played.score == Mate(Color.WHITE, 2)
    assert previous.status is JudgementStatus.DECIDED  # 16…Nxd7, Black's move
    view = result.tree.view(result.rev)
    print(
        f"\nround 0: {elapsed:.2f} s, {len(view.nodes())} nodes, rev {result.rev}, "
        f"grade {judgement.grade.value}, previous {previous.grade.value} "
        f"(loss {previous.loss}), reproducible {result.reproducible}"
    )
    assert elapsed < 10  # R0-D §17 targets ≤ 3 s of engine work; generous for slow hosts
