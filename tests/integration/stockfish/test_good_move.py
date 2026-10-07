"""P9-I8: real Stockfish evidence through the complete internal good-move path.

Base MultiPV analysis, the root-restricted played analysis and the MoveJudge judgement are all
real; P9 then builds deterministic branches, runs real P7 probes and replays every PV.  Only
quality, forcedness level and rank are read from P2, because they select P9 applicability.

Limits are depth-bounded: with a node limit Stockfish can stop mid-iteration and report a
bound-only score, which the adapter correctly rejects.  A fixed depth with one thread and a
fresh engine process (clean hash) per observation is deterministic.  Every observation is
repeated three times and must produce the same semantic signature.
"""

import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import pairwise

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.domain.analysis import (
    AlternativeScope,
    BasePieceRef,
    CounterfactualBatchRequest,
    CounterfactualBatchResult,
    GoodMoveBenefitKind,
    GoodMoveBenefitStatus,
    GoodMoveExplanationResult,
    GoodMoveExplanationStatus,
    GoodMoveMode,
    MateEvidenceLevel,
    ProbeKind,
    TacticalCandidateKind,
    TacticalCandidateStatus,
)
from calliope.domain.chess import Color, PieceType
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineSettings,
    ForcednessLevel,
    MoveJudgement,
    MoveQuality,
)
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import GoodMoveExplainer, good_move
from calliope.services.explanation.good_move import (
    GoodMoveCounterfactualContext,
    GoodMovePreparedContext,
    GoodMoveReplayContext,
)
from calliope.services.judgement.move_judge import MoveJudge
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.tactics import TacticalDetector

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH") or shutil.which("stockfish")
pytestmark = pytest.mark.skipif(STOCKFISH is None, reason="Stockfish binary not available")

# One frozen limit for base, played and P7 analyses (P7 caps time_ms at 2000).
LIMIT = EngineLimit(depth=12, time_ms=2000)
BASE_SETTINGS = EngineSettings(limit=LIMIT, multipv=3, threads=1, hash_mb=16)
PLAYED_SETTINGS = EngineSettings(limit=LIMIT, multipv=1, threads=1, hash_mb=16)
P7_SETTINGS = EngineSettings(limit=LIMIT, multipv=1, threads=1, hash_mb=16)
RUNS = 3

# S1: Kc7 leaves Black's king exactly one legal reply; the alternatives also mate, so
# MATE_THREAT is not unique, but the one-reply forcing structure is.
S1_FEN = "k7/8/2K5/8/8/8/8/1R6 w - - 0 1"
# S2: Black threatens mate; only Ra1+ parries it.  The representative alternatives are mated.
S2_FEN = "R1K5/4r3/8/8/8/8/7q/7k w - - 0 1"
# S3: Qf8# mates, and the other serious queen moves mate too: no unique mating benefit.
S3_FEN = "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1"
# S4: the quiet initial position.
S4_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FIXTURES = {"S1": S1_FEN, "S2": S2_FEN, "S3": S3_FEN, "S4": S4_FEN}

K = GoodMoveBenefitKind
S = GoodMoveBenefitStatus
rules = PythonChessAdapter()


class RecordingP7:
    """Transparent observation of real P7 requests and results; evidence is never altered."""

    def __init__(self, analyzer: CounterfactualAnalyzer) -> None:
        self.analyzer = analyzer
        self.requests: list[CounterfactualBatchRequest] = []
        self.results: list[CounterfactualBatchResult] = []

    def execute(self, request: CounterfactualBatchRequest) -> CounterfactualBatchResult:
        self.requests.append(request)
        result = self.analyzer.execute(request)
        self.results.append(result)
        return result


@dataclass
class Observation:
    fen: str
    position_analysis: EngineAnalysis
    played_analysis: EngineAnalysis
    judgement: MoveJudgement
    prepared: GoodMovePreparedContext
    context: GoodMoveCounterfactualContext
    replay: GoodMoveReplayContext
    result: GoodMoveExplanationResult
    p7: RecordingP7
    identity: EngineIdentity


def observe(fen: str, monkeypatch: pytest.MonkeyPatch) -> Observation:
    """One complete real observation in a fresh engine process (clean hash)."""

    base = rules.position_from_fen(fen)
    with StockfishAdapter.start(STOCKFISH) as stockfish:  # type: ignore[arg-type]
        position_analysis = stockfish.analyze(base, BASE_SETTINGS)
        played = position_analysis.best_line.first_move
        played_analysis = stockfish.analyze(base, PLAYED_SETTINGS, root_moves=(played,))
        assert position_analysis.engine == played_analysis.engine
        assert position_analysis.position_id == played_analysis.position_id == base.position_id
        assert played_analysis.best_line.first_move.uci == played.uci
        judgement = MoveJudge().judge(
            mover=base.side_to_move,
            move=played,
            position_analysis=position_analysis,
            played_analysis=played_analysis,
        )

        facts = PositionFactExtractor(rules)
        p7 = RecordingP7(CounterfactualAnalyzer(rules, stockfish, rules, rules))
        explainer = GoodMoveExplainer(
            chess=rules,
            facts=facts,
            delta=BoardDeltaAnalyzer(rules, facts),
            tactical_rules=rules,
            detector=TacticalDetector(),
            counterfactual=p7,  # type: ignore[arg-type]
        )
        prepared = explainer.prepare(base, played, judgement, position_analysis)
        assert isinstance(prepared, GoodMovePreparedContext)
        assert prepared.position_analysis is position_analysis
        context = explainer.verify_counterfactuals(explainer.build_branches(prepared), P7_SETTINGS)

        replays: list[GoodMoveReplayContext] = []
        original = GoodMoveExplainer.replay_lines

        def observe_replay(self, retained):
            replay = original(self, retained)
            replays.append(replay)
            return replay

        # Observe the replay performed by the explanation itself; no P7 call is repeated.
        with monkeypatch.context() as patch:
            patch.setattr(GoodMoveExplainer, "replay_lines", observe_replay)
            if prepared.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE:
                result = explainer.explain_only_move(context)
            else:
                result = explainer.explain_strong_move(context)
        identity = position_analysis.engine
    assert replays, "the explanation must replay its retained evidence"
    return Observation(
        fen=fen,
        position_analysis=position_analysis,
        played_analysis=played_analysis,
        judgement=judgement,
        prepared=prepared,
        context=replays[-1].counterfactual,
        replay=replays[-1],
        result=result,
        p7=p7,
        identity=identity,
    )


@pytest.fixture(scope="module")
def observations() -> Iterator[dict[str, list[Observation]]]:
    patch = pytest.MonkeyPatch()
    try:
        yield {name: [observe(fen, patch) for _ in range(RUNS)] for name, fen in FIXTURES.items()}
    finally:
        patch.undo()


def signature(o: Observation) -> tuple:
    result = o.result
    return (
        o.judgement.quality,
        o.judgement.forcedness.level,
        o.judgement.rank,
        o.prepared.mode,
        tuple((a.rank, a.move.uci) for a in o.prepared.alternatives),
        result.status,
        tuple(
            (
                b.kind,
                b.status,
                tuple(a.rank for a in b.failed_alternatives),
                b.equivalent_alternative_benefit,
                b.subject,
                b.mate_evidence_level,
            )
            for b in result.benefits
        ),
        result.literal_only_move_proven,
        o.context.probe_count,
        len(o.p7.requests),
    )


# ---- shared invariants -----------------------------------------------------------------------


def assert_protocol(o: Observation) -> None:
    requests, results = o.p7.requests, o.p7.results
    assert 1 <= len(requests) <= 2 and len(results) == len(requests)
    batch_a = requests[0]
    assert [p.kind for p in batch_a.probes] == [ProbeKind.REFUTATION] * len(batch_a.probes)
    assert [p.intervention_move.uci for p in batch_a.probes] == [
        o.prepared.played_move.uci,
        *(a.move.uci for a in o.prepared.alternatives),
    ]
    assert 1 <= len(batch_a.probes) <= 3
    if len(requests) == 2:
        assert [p.kind for p in requests[1].probes] == [ProbeKind.IGNORE_THREAT]
    assert o.context.probe_count == sum(len(r.probes) for r in requests) <= 4
    for request, result in zip(requests, results, strict=True):
        assert request.settings == result.settings == P7_SETTINGS
        for probe_result in result.results:
            if probe_result.engine_analysis is not None:
                assert probe_result.engine_analysis.settings == P7_SETTINGS


def assert_engine_identity(o: Observation) -> None:
    assert "stockfish" in o.identity.name.lower()
    identities = {
        r.engine_analysis.engine
        for batch in o.p7.results
        for r in batch.results
        if r.engine_analysis is not None
    }
    assert len(identities) <= 1
    for identity in identities:
        assert "stockfish" in identity.name.lower()
        assert identity == o.identity


def assert_replay_integrity(o: Observation) -> None:
    replay = o.replay
    d = o.context.deterministic
    base = d.prepared.base
    mover = base.side_to_move
    lines = [(replay.played, d.played)]
    lines += [
        (a.evidence, b.branch) for a, b in zip(replay.alternatives, d.alternatives, strict=True)
    ]
    if replay.ignored_response is not None:
        lines.append((replay.ignored_response, d.played))
    for evidence, branch in lines:
        plies = evidence.line.plies
        assert [step.ply for step in plies] == list(range(1, len(plies) + 1))
        first = plies[0]
        assert (first.move, first.position, first.facts, first.delta) == (
            branch.move,
            branch.position,
            branch.facts,
            branch.delta,
        )
        assert first.identity == branch.identity and first.before == base
        assert first.before_identity == d.root_identity
        for previous, step in pairwise(plies):
            # Never trusted because it came from Stockfish: re-check legality independently.
            assert rules.legal_move_from_uci(previous.position, step.move.uci).uci == step.move.uci
            assert step.before == previous.position
            assert step.before_identity == previous.identity
        for step in plies:
            assert step.identity.base_position_id == base.position_id
            assert (
                step.position.position_id
                == step.facts.position_id
                == step.rules.position_id
                == step.delta.after_position_id
                == step.detection.after_position_id
                == step.identity.position_id
            )
            assert step.delta.before_position_id == step.before.position_id
            assert all(
                c.status is TacticalCandidateStatus.DETECTED for c in step.detection.candidates
            )
        # Material evidence is exactly the replayed P4/P5 measurement.
        recomputed = good_move._material_evidence(evidence.line, d.base_facts, mover)
        assert evidence.material == recomputed


def assert_representative_only(o: Observation) -> None:
    result = o.result
    assert result.literal_only_move_proven is False
    assert result.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
    assert result.mode is o.prepared.mode
    assert result.alternatives == o.prepared.alternatives
    assert 0 <= len(result.alternatives) <= 2
    for benefit in result.benefits:
        assert benefit.alternative_scope is AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES


def assert_all(o: Observation) -> None:
    assert_protocol(o)
    assert_engine_identity(o)
    assert_replay_integrity(o)
    assert_representative_only(o)


def by_kind(result: GoodMoveExplanationResult) -> dict:
    return {benefit.kind: benefit for benefit in result.benefits}


# ---- semantic gates --------------------------------------------------------------------------


def test_real_supported_strong_move(observations) -> None:
    for o in observations["S1"]:
        assert_all(o)
        assert o.judgement.quality in (MoveQuality.BEST, MoveQuality.EXCELLENT, MoveQuality.GOOD)
        assert o.judgement.forcedness.level is not ForcednessLevel.ONLY_MOVE
        assert o.prepared.mode is GoodMoveMode.STRONG_MOVE
        assert o.result.status is GoodMoveExplanationStatus.SUPPORTED
        forces = by_kind(o.result)[K.FORCES_RESPONSE]
        assert forces.status is S.SUPPORTED
        played = o.context.deterministic.played
        (sole,) = played.rules.legal_moves
        assert not played.facts.side_to_move_checkmated
        forced = [
            c
            for c in played.detection.candidates
            if c.kind is TacticalCandidateKind.FORCED_RESPONSE
        ]
        assert forced == list(forces.tactical_candidates) and len(forced) == 1
        assert forced[0].responses[0].uci == sole.uci == forces.tested_response.uci
        assert forces.subject == (BasePieceRef(Color.WHITE, PieceType.KING, "c6"),)
        # Every representative alternative also mates: no uniqueness is claimed for the mate.
        mate = by_kind(o.result).get(K.MATE_THREAT)
        if mate is not None:
            assert mate.status is not S.SUPPORTED


def test_real_only_move_preservation(observations) -> None:
    for o in observations["S2"]:
        assert_all(o)
        # The ONLY_MOVE hint comes from MoveJudge over the real base MultiPV.
        assert o.judgement.quality is MoveQuality.BEST
        assert o.judgement.forcedness.level is ForcednessLevel.ONLY_MOVE
        assert o.prepared.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE
        assert o.result.status is GoodMoveExplanationStatus.SUPPORTED
        prevents = by_kind(o.result)[K.PREVENTS_MATE]
        assert prevents.status is S.SUPPORTED
        assert prevents.failed_alternatives
        assert prevents.subject == (BasePieceRef(Color.WHITE, PieceType.KING, "c8"),)
        assert prevents.mate_evidence_level in (
            MateEvidenceLevel.EXACT_IMMEDIATE,
            MateEvidenceLevel.ENGINE_LINE,
        )
        failed = {a.rank for a in prevents.failed_alternatives}
        for alternative in o.replay.alternatives:
            if alternative.alternative.rank in failed:
                line = alternative.evidence.line
                score = line.probe_result.engine_analysis
                exact = line.ends_in_checkmate and line.final.position.side_to_move is Color.WHITE
                engine_mate = (
                    score is not None
                    and score.best_line.score.mate is not None
                    and score.best_line.score.mate.winner is Color.BLACK
                )
                assert exact or engine_mate
        # Even when every representative alternative fails, nothing is exhaustive.
        assert o.result.literal_only_move_proven is False
        assert all(b.tested_response is None for b in o.result.benefits)


def test_real_equivalent_moves_do_not_overstate_uniqueness(observations) -> None:
    for o in observations["S3"]:
        assert_all(o)
        assert o.prepared.mode is GoodMoveMode.STRONG_MOVE
        assert len(o.prepared.alternatives) >= 1
        mate = by_kind(o.result)[K.MATE_THREAT]
        assert mate.status is S.REFUTED and mate.equivalent_alternative_benefit is True
        assert mate.subject == (BasePieceRef(Color.BLACK, PieceType.KING, "h8"),)
        assert o.context.deterministic.played.facts.side_to_move_checkmated
        assert all(b.status is not S.SUPPORTED for b in o.result.benefits)
        assert o.result.status is not GoodMoveExplanationStatus.SUPPORTED
        assert o.result.literal_only_move_proven is False


def test_real_quiet_best_is_inconclusive(observations) -> None:
    for o in observations["S4"]:
        assert_all(o)
        assert o.judgement.quality is MoveQuality.BEST
        assert o.prepared.mode is GoodMoveMode.STRONG_MOVE
        assert o.result.status is GoodMoveExplanationStatus.INCONCLUSIVE
        assert o.result.benefits == ()


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_real_p9_repeatability(observations, name) -> None:
    signatures = {signature(o) for o in observations[name]}
    assert len(observations[name]) == RUNS and len(signatures) == 1
    identities = {o.identity for o in observations[name]}
    assert len(identities) == 1
