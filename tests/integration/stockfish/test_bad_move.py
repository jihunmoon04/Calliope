"""P8-I6: semantic evidence from real Stockfish through the complete internal P8 path.

Judgement scores are fixture-only: these tests exercise P8, not P2. The comparator
relationship is independently established by real, identically budgeted P7 probes.
"""

import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.domain.analysis import (
    BadMoveCauseKind,
    BadMoveCauseStatus,
    BadMoveExplanationResult,
    BadMoveExplanationStatus,
    BasePieceRef,
    CounterfactualBatchRequest,
    CounterfactualBatchResult,
    MateEvidenceLevel,
    ProbeKind,
)
from calliope.domain.chess import Color, PieceType
from calliope.domain.engine import (
    EngineLimit,
    EngineScore,
    EngineSettings,
    MoveJudgement,
    MoveQuality,
)
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import BadMoveExplainer
from calliope.services.explanation.bad_move import BadMoveCounterfactualContext, ReplayedLines
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH") or shutil.which("stockfish")
pytestmark = pytest.mark.skipif(STOCKFISH is None, reason="Stockfish binary not available")

I6_SETTINGS = EngineSettings(
    limit=EngineLimit(nodes=10_000, time_ms=2000), multipv=1, threads=1, hash_mb=16
)

# The original bare knight/pawn candidate is drawable even after losing the knight.
# The extra wing pawns make the concrete loss valuable to the real engine.
S1_FEN = "4k3/p6p/8/3p4/8/2N5/P6P/4K3 w - - 0 1"
S2_FEN = "4r1k1/8/8/8/8/8/5PPP/3R2K1 w - - 0 1"
# Kd1 loses king activity versus Kd2. The real PVs retain the pawn, without
# hanging/removed-defender/fork/mate/material-loss causes in P8's vocabulary.
S3_FEN = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"

rules = PythonChessAdapter()


class RecordingP7:
    """Transparent observation of real P7 requests/results; no altered evidence."""

    def __init__(self, analyzer: CounterfactualAnalyzer) -> None:
        self.analyzer = analyzer
        self.requests: list[CounterfactualBatchRequest] = []
        self.results: list[CounterfactualBatchResult] = []

    def execute(self, request: CounterfactualBatchRequest) -> CounterfactualBatchResult:
        self.requests.append(request)
        result = self.analyzer.execute(request)
        self.results.append(result)
        return result


@pytest.fixture(scope="module")
def stockfish() -> Iterator[StockfishAdapter]:
    with StockfishAdapter.start(STOCKFISH) as engine:  # type: ignore[arg-type]
        yield engine


@dataclass
class Observation:
    result: BadMoveExplanationResult
    context: BadMoveCounterfactualContext
    lines: ReplayedLines
    p7: RecordingP7


def explain(stockfish, monkeypatch, fen: str, played: str, comparator: str) -> Observation:
    facts = PositionFactExtractor(rules)
    p7 = RecordingP7(CounterfactualAnalyzer(rules, stockfish, rules, rules))
    explainer = BadMoveExplainer(
        chess=rules,
        facts=facts,
        delta=BoardDeltaAnalyzer(rules, facts),
        tactical_rules=rules,
        detector=TacticalDetector(),
        counterfactual=p7,  # type: ignore[arg-type]
    )
    base = rules.position_from_fen(fen)
    judgement = MoveJudgement(
        position_id=base.position_id,
        mover=base.side_to_move,
        move=rules.legal_move_from_uci(base, played),
        best_move=rules.legal_move_from_uci(base, comparator),
        quality=MoveQuality.BLUNDER,
        rank=None,
        best_score=EngineScore.cp(0),  # Fixture metadata, never causal evidence.
        played_score=EngineScore.cp(-300),
        cp_loss=300,
        expected_score_loss=0.3,
    )
    observed = []
    original = BadMoveExplainer.replay_lines

    def observe_replay(self, context):
        lines = original(self, context)
        observed.append((context, lines))
        return lines

    # Observe the actual replay performed by explain(), without a second probe run.
    with monkeypatch.context() as patch:
        patch.setattr(BadMoveExplainer, "replay_lines", observe_replay)
        result = explainer.explain(base, judgement.move, judgement, I6_SETTINGS)
    assert len(observed) == 1
    context, lines = observed[0]
    observation = Observation(result, context, lines, p7)
    assert_protocol_and_replay(observation)
    return observation


def assert_protocol_and_replay(observation: Observation) -> None:
    context, p7 = observation.context, observation.p7
    prepared = context.prepared
    assert context.comparator_strictly_better is True
    assert len(p7.requests) in (1, 2)
    assert len(p7.requests[0].probes) == 2
    assert [p.kind for p in p7.requests[0].probes] == [ProbeKind.REFUTATION] * 2
    assert [p.intervention_move.uci for p in p7.requests[0].probes] == [
        prepared.played_move.uci,
        prepared.comparator_move.uci,
    ]
    if len(p7.requests) == 2:
        assert len(p7.requests[1].probes) == 1
        assert p7.requests[1].probes[0].kind is ProbeKind.IGNORE_THREAT
    count = sum(len(request.probes) for request in p7.requests)
    assert 0 < count == context.probe_count <= 3
    assert all(request.settings == I6_SETTINGS for request in p7.requests)
    assert all(result.settings == I6_SETTINGS for result in p7.results)
    analyses = [
        probe.engine_analysis
        for batch in p7.results
        for probe in batch.results
        if probe.engine_analysis is not None
    ]
    assert analyses
    assert all(analysis.settings == I6_SETTINGS for analysis in analyses)
    assert {analysis.engine for analysis in analyses} == {context.engine_identity}
    assert "stockfish" in context.engine_identity.name.lower()

    for line in (
        observation.lines.actual,
        observation.lines.comparator,
        observation.lines.same_punishment,
    ):
        if line is None:
            continue
        previous = prepared.base
        pv = line.probe_result.engine_analysis.best_line.pv
        assert tuple(step.move.uci for step in line.plies[1:]) == tuple(m.uci for m in pv)
        for ply, step in enumerate(line.plies, start=1):
            assert step.ply == ply
            assert step.before == previous
            canonical = rules.legal_move_from_uci(previous, step.move.uci)
            assert canonical.uci == step.move.uci
            assert rules.apply_move(previous, canonical) == step.position
            assert step.before_identity.position_id == previous.position_id
            assert step.identity.position_id == step.position.position_id
            assert step.identity.base_position_id == prepared.base.position_id
            assert set(step.identity.base_pieces) == set(prepared.root_identity.base_pieces)
            previous = step.position


def supported_cause(result: BadMoveExplanationResult, kind: BadMoveCauseKind):
    assert result.status is BadMoveExplanationStatus.SUPPORTED
    return next(
        cause
        for cause in result.causes
        if cause.kind is kind and cause.status is BadMoveCauseStatus.SUPPORTED
    )


def test_newly_hanging_knight_has_real_capture_and_stable_material(stockfish, monkeypatch):
    observation = explain(stockfish, monkeypatch, S1_FEN, "c3e4", "c3b5")
    cause = supported_cause(observation.result, BadMoveCauseKind.NEWLY_HANGING_PIECE)
    subject = BasePieceRef(Color.WHITE, PieceType.KNIGHT, "c3")
    assert cause.subject == (subject,)
    assert cause.probe_results and cause.board_deltas and cause.tactical_candidates
    assert cause.material_evidence[0].stable_deficit is not None
    assert cause.comparator_has_equivalent_resource is False
    captures = [
        step
        for step in observation.lines.actual.plies
        if step.delta.capture is not None
        and step.before_identity.base_ref_for(step.delta.capture.captured) == subject
    ]
    assert captures
    assert all(step.delta in cause.board_deltas for step in captures)
    assert 2 <= observation.context.probe_count <= 3


def test_back_rank_mate_is_exact_board_truth(stockfish, monkeypatch):
    observation = explain(stockfish, monkeypatch, S2_FEN, "d1d7", "h2h3")
    cause = supported_cause(observation.result, BadMoveCauseKind.MATE_ALLOWED)
    assert cause.subject == (BasePieceRef(Color.WHITE, PieceType.KING, "g1"),)
    assert cause.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
    assert cause.replayed_pv_ends_in_checkmate is True
    assert observation.lines.actual.ends_in_checkmate
    assert cause.comparator_has_equivalent_resource is False
    assert not observation.lines.comparator.ends_in_checkmate
    assert cause.probe_results and cause.board_deltas


def test_inferior_king_activity_has_no_invented_cause(stockfish, monkeypatch):
    observation = explain(stockfish, monkeypatch, S3_FEN, "e1d1", "e1d2")
    assert observation.context.comparator_strictly_better is True
    assert observation.result.status is BadMoveExplanationStatus.INCONCLUSIVE
    assert observation.result.causes == ()
