"""P2-C1 real regression: the known cross-search inversion now reconciles through the public path.

The system under test is CalliopeEngine.analyze_move() from the production composition root.  A
transparent wrapper around the production StockfishAdapter records each returned observation and
its request game token; it delegates unchanged.  Loss expectations are recomputed from the
observed paired lines, never from historical centipawn values.

With the reviewed Stockfish 19 build the paired search ranks the reference best above f4h6, so
this fixture proves the positive-loss branch.  The played-better floor branch (loss 0, EXCELLENT,
never BEST) is proven by deterministic MoveJudge unit tests.
"""

import os
import shutil
import threading

import chess.engine
import pytest

from calliope import AnalysisBudget, AnalysisOptions, AnalyzeMoveRequest, OutputMode
from calliope.adapters.stockfish import StockfishAdapter
from calliope.application.explanation import COUNTERFACTUAL_SETTINGS
from calliope.composition import create_calliope_engine
from calliope.domain.chess import Color
from calliope.services.judgement.move_judge import MoveJudgementPolicy

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH") or shutil.which("stockfish")
pytestmark = pytest.mark.skipif(STOCKFISH is None, reason="Stockfish binary not available")

FEN = "r1b2rk1/pp3p1p/3n2p1/3BR3/5QP1/P4N1P/1q4PK/3R4 w - - 1 26"
MOVE = "f4h6"
BUDGET = AnalysisBudget(depth=12, multipv=3)  # the public default MultiPV 5 does not reproduce
POLICY = MoveJudgementPolicy()
MOVER = Color.WHITE


@pytest.fixture(scope="module")
def observed():
    calls: list = []
    counts = {"newgame": 0}
    lock = threading.Lock()
    patch = pytest.MonkeyPatch()
    analyze, newgame = StockfishAdapter.analyze, chess.engine.UciProtocol._ucinewgame

    def observe(self, position, settings, root_moves=None):
        result = analyze(self, position, settings, root_moves)
        with lock:
            calls.append((id(self._session_game), settings, root_moves, result))
        return result

    def observe_newgame(self):
        with lock:
            counts["newgame"] += 1
        return newgame(self)

    patch.setattr(StockfishAdapter, "analyze", observe)
    patch.setattr(chess.engine.UciProtocol, "_ucinewgame", observe_newgame)
    runs = {}
    try:
        with create_calliope_engine(STOCKFISH) as engine:  # type: ignore[arg-type]
            for mode in (OutputMode.STRUCTURED, OutputMode.COMMENTARY):
                calls.clear()
                counts["newgame"] = 0
                options = AnalysisOptions(budget=BUDGET, output_mode=mode)
                result = engine.analyze_move(AnalyzeMoveRequest(FEN, MOVE, options))
                runs[mode] = (result, list(calls), counts["newgame"])
    finally:
        patch.undo()
    return runs


def _judgement_calls(calls):
    return [c for c in calls if c[1] != COUNTERFACTUAL_SETTINGS]


@pytest.mark.parametrize("mode", list(OutputMode))
def test_known_inversion_reconciles_instead_of_failing(observed, mode):
    result, calls, newgames = observed[mode]
    base, played, paired = _judgement_calls(calls)  # exactly three judgement observations
    base_analysis, played_analysis, paired_analysis = base[3], played[3], paired[3]

    # The original two observations really are the cross-search inversion (else no PASS).
    best = base_analysis.best_line
    assert MOVE not in {line.first_move.uci for line in base_analysis.lines}
    assert base[2] is None and played[2] is not None and played[2][0].uci == MOVE
    played_line = played_analysis.best_line
    cp_inversion = played_line.score.centipawns_for(MOVER) - best.score.centipawns_for(MOVER)
    wdl_inversion = (
        played_line.wdl.expected_score(MOVER) - best.wdl.expected_score(MOVER)
        if played_line.wdl and best.wdl
        else 0.0
    )
    assert (
        cp_inversion > POLICY.cp_noise_tolerance or wdl_inversion > POLICY.expected_noise_tolerance
    ), "the engine no longer reproduces the cross-search inversion"

    # Exactly one paired same-search reanalysis: original limit, MultiPV 2, (best, played).
    settings = base[1]
    assert paired[1].limit == settings.limit and paired[1].multipv == 2
    assert (paired[1].threads, paired[1].hash_mb) == (1, 16)
    assert [m.uci for m in paired[2]] == [best.first_move.uci, MOVE]
    assert {line.rank for line in paired_analysis.lines} == {1, 2}

    # One request session/game token, one new-game boundary, paired call before any P7 probe.
    assert len({c[0] for c in calls}) == 1 and newgames == 1
    assert calls[2] is paired

    # The final judgement follows the frozen paired-loss policy recomputed from the observation.
    by_move = {line.first_move.uci: line for line in paired_analysis.lines}
    reference, candidate = by_move[best.first_move.uci], by_move[MOVE]
    expected_cp = max(
        0, reference.score.centipawns_for(MOVER) - candidate.score.centipawns_for(MOVER)
    )
    judgement = result.judgement
    assert judgement.cp_loss == expected_cp
    if reference.wdl and candidate.wdl:
        expected_wdl = max(
            0.0, reference.wdl.expected_score(MOVER) - candidate.wdl.expected_score(MOVER)
        )
        assert judgement.expected_score_loss == pytest.approx(expected_wdl)
    assert judgement.rank is None and judgement.quality != "best"
    assert judgement.best_move_uci == best.first_move.uci
    # Reviewed Stockfish 19 behaviour: the positive-loss branch.
    assert reference.score.centipawns_for(MOVER) > candidate.score.centipawns_for(MOVER)
    assert result.schema_version == "0.2"


def test_both_modes_do_identical_p0_p11_work(observed):
    structured, s_calls, _ = observed[OutputMode.STRUCTURED]
    commentary, c_calls, _ = observed[OutputMode.COMMENTARY]
    shape = [(c[1], c[2], c[3].position_id) for c in s_calls]
    assert shape == [(c[1], c[2], c[3].position_id) for c in c_calls]
    assert structured.judgement == commentary.judgement
    assert structured.claims == commentary.claims
    assert structured.selected_claim_ids == commentary.selected_claim_ids
    assert structured.metadata == commentary.metadata
    assert structured.commentary is None and commentary.commentary is not None
    assert commentary.commentary.used_claim_ids == commentary.selected_claim_ids
