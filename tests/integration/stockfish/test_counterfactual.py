import os
import shutil
from collections.abc import Iterator

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.domain.analysis import CounterfactualBatchRequest, CounterfactualProbe, ProbeKind
from calliope.domain.chess import ChessMove
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.counterfactual.analyzer import DEFAULT_SETTINGS

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH") or shutil.which("stockfish")

pytestmark = pytest.mark.skipif(STOCKFISH is None, reason="Stockfish binary not available")

rules = PythonChessAdapter()
START = rules.position_from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
BEFORE_MATE = rules.position_from_fen(
    "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
)
SETTINGS = DEFAULT_SETTINGS.__class__(
    limit=DEFAULT_SETTINGS.limit.__class__(time_ms=200), multipv=1, threads=1
)


@pytest.fixture(scope="module")
def analyzer() -> Iterator[CounterfactualAnalyzer]:
    with StockfishAdapter.start(STOCKFISH) as stockfish:  # type: ignore[arg-type]
        yield CounterfactualAnalyzer(rules, stockfish, rules, rules)


def execute(analyzer, *probes):
    return analyzer.execute(CounterfactualBatchRequest(tuple(probes), SETTINGS)).results


def legal(position, uci):
    return rules.legal_move_from_uci(position, uci)


def test_best_response(analyzer):
    (r,) = execute(analyzer, CounterfactualProbe(ProbeKind.BEST_RESPONSE, START))
    assert r.analysis_position == START and r.root_moves is None
    assert r.engine_analysis.position_id == START.position_id
    assert r.engine_analysis.settings == SETTINGS
    rules.legal_move_from_uci(START, r.engine_analysis.best_line.first_move.uci)


def test_alternative_move(analyzer):
    (r,) = execute(
        analyzer, CounterfactualProbe(ProbeKind.ALTERNATIVE_MOVE, START, ChessMove("a2a3"))
    )
    assert r.engine_analysis.position_id == START.position_id
    assert r.root_moves == (legal(START, "a2a3"),)
    assert r.engine_analysis.best_line.first_move.uci == "a2a3"


def test_refutation(analyzer):
    (r,) = execute(analyzer, CounterfactualProbe(ProbeKind.REFUTATION, START, ChessMove("e2e4")))
    after = rules.apply_move(START, legal(START, "e2e4"))
    assert r.analysis_position == after and r.intervention_position == after
    assert r.engine_analysis.position_id == after.position_id
    rules.legal_move_from_uci(after, r.engine_analysis.best_line.first_move.uci)


def test_ignore_threat(analyzer):
    probe = CounterfactualProbe(
        ProbeKind.IGNORE_THREAT, START, ChessMove("e2e4"), ChessMove("e7e5")
    )
    (r,) = execute(analyzer, probe)
    after = rules.apply_move(START, legal(START, "e2e4"))
    assert r.analysis_position == after
    assert r.root_moves == (legal(after, "e7e5"),)
    assert r.engine_analysis.best_line.first_move.uci == "e7e5"


def test_terminal_branch(analyzer):
    (r,) = execute(
        analyzer, CounterfactualProbe(ProbeKind.REFUTATION, BEFORE_MATE, ChessMove("d8h4"))
    )
    assert r.engine_analysis is None and r.terminal is not None


def test_mixed_batch(analyzer):
    probes = (
        CounterfactualProbe(ProbeKind.BEST_RESPONSE, START),
        CounterfactualProbe(ProbeKind.ALTERNATIVE_MOVE, START, ChessMove("d2d4")),
        CounterfactualProbe(ProbeKind.REFUTATION, BEFORE_MATE, ChessMove("d8h4")),
        CounterfactualProbe(ProbeKind.IGNORE_THREAT, START, ChessMove("e2e4"), ChessMove("c7c5")),
    )
    results = execute(analyzer, *probes)
    assert [r.probe for r in results] == list(probes)
    assert [r.terminal is not None for r in results] == [False, False, True, False]
    engines = {r.engine_analysis.engine for r in results if r.engine_analysis}
    assert len(engines) == 1
