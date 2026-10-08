"""Deterministic G0 application fakes over one shared event log (not collected).

The explanation outcome is a real P10/P11 package from the reviewed unit scenario corpus
(python-chess rules + scripted P7), so projection and rendering run on validated values.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "explanation"))

import _p8_claim_scenarios as p8

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.application.analyze_move import AnalyzeMoveService
from calliope.application.explanation import (
    COUNTERFACTUAL_SETTINGS as P7_MARKER,
)
from calliope.application.explanation import MoveExplanationOutcome
from calliope.contracts import (
    AnalysisBudget,
    AnalysisOptions,
    AnalyzeMoveRequest,
    OutputMode,
)
from calliope.domain.chess import ChessMove
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLine,
    EngineScore,
    Forcedness,
    ForcednessLevel,
    MoveJudgement,
    MoveQuality,
)
from calliope.domain.explanation import EvidenceBundle
from calliope.errors import CrossSearchInversionError, EngineAnalysisError
from calliope.services.explanation import (
    DeterministicExplanationRenderer,
    ExplanationSelector,
    GraphBuilder,
)

FEN = p8.KNIGHT  # "4k3/8/8/3p4/8/2N5/8/4K3 w - - 0 1"
MOVE = ChessMove("c3e4")
BEST = ChessMove("c3b5")  # the unrestricted analysis' rank-1 move
ENGINE_ID = EngineIdentity("Stockfish", "17")
rules = PythonChessAdapter()


def position():
    return rules.position_from_fen(FEN)


def knight_outcome() -> MoveExplanationOutcome:
    bundle = p8.evidence(p8.knight())
    claims = p8.claims(bundle)
    graph = GraphBuilder().build(bundle, claims)
    return MoveExplanationOutcome(claims, graph, ExplanationSelector().select(graph))


def empty_outcome() -> MoveExplanationOutcome:
    graph = GraphBuilder().build(EvidenceBundle(position().position_id, (), ()), ())
    return MoveExplanationOutcome((), graph, ExplanationSelector().select(graph))


@dataclass
class FakeChess:
    log: list
    fen_error: Exception | None = None
    move_error: Exception | None = None

    def position_from_fen(self, fen):
        self.log.append(("fen", fen))
        if self.fen_error:
            raise self.fen_error
        return position()

    def legal_move_from_uci(self, base, move_uci):
        self.log.append(("move", move_uci))
        if self.move_error:
            raise self.move_error
        return MOVE


@dataclass
class FakeSessions:
    log: list
    active: bool = False

    def request_session(self):
        sessions = self

        class _Session:
            def __enter__(self):
                assert not sessions.active, "nested request session"
                sessions.active = True
                sessions.log.append(("acquire",))

            def __exit__(self, *exc):
                sessions.active = False
                sessions.log.append(("release",))
                return False

        return _Session()


@dataclass
class FakeEngine:
    log: list
    sessions: FakeSessions
    fail_on_call: int | None = None
    calls: list = field(default_factory=list)

    def analyze(self, base, settings, root_moves=None):
        assert self.sessions.active, "engine call outside the request session"
        self.calls.append((base.position_id, settings, root_moves))
        self.log.append(("engine", settings, root_moves))
        if self.fail_on_call == len(self.calls):
            raise EngineAnalysisError("boom")
        roots = root_moves or (BEST,)
        lines = tuple(
            EngineLine(rank=i, first_move=m, score=EngineScore.cp(10), pv=(m,))
            for i, m in enumerate(roots, 1)
        )
        return EngineAnalysis(base.position_id, ENGINE_ID, settings, lines)


@dataclass
class FakeJudge:
    log: list
    error: Exception | None = None
    quality: MoveQuality = MoveQuality.BLUNDER
    inversion: bool = False  # initial judge() raises the P2-C1 retry signal
    reconcile_error: Exception | None = None
    reconciled: list = field(default_factory=list)

    def judge(self, **kwargs):
        self.log.append(("judge",))
        if self.error:
            raise self.error
        if self.inversion:
            raise CrossSearchInversionError("separate played search outranked best")
        return self._judgement(kwargs, self.quality)

    def judge_reconciled(self, **kwargs):
        self.log.append(("judge_reconciled",))
        self.reconciled.append(kwargs)
        if self.reconcile_error:
            raise self.reconcile_error
        return self._judgement(kwargs, MoveQuality.EXCELLENT)

    @staticmethod
    def _judgement(kwargs, quality):
        return MoveJudgement(
            position_id=kwargs["position_analysis"].position_id,
            mover=kwargs["mover"],
            move=MOVE,
            best_move=BEST,
            quality=quality,
            rank=None,
            best_score=EngineScore.cp(10),
            played_score=EngineScore.cp(-300),
            cp_loss=310,
            expected_score_loss=0.3,
            forcedness=Forcedness(ForcednessLevel.FLEXIBLE, 3, 20),
        )


@dataclass
class FakeExplanations:
    """Stands in for P4-P11; ``p7_calls`` engine analyses imitate counterfactual probes."""

    log: list
    engine: FakeEngine
    outcome: MoveExplanationOutcome = field(default_factory=knight_outcome)
    error: Exception | None = None
    p7_calls: int = 2

    def explain(self, base, played, judgement, position_analysis):
        self.log.append(("explain", judgement.quality))
        for _ in range(self.p7_calls):
            self.engine.analyze(base, P7_MARKER, (played,))
        if self.error:
            raise self.error
        return self.outcome


@dataclass
class SpyRenderer:
    log: list
    error: Exception | None = None
    inner: DeterministicExplanationRenderer = field(
        default_factory=DeterministicExplanationRenderer
    )

    def render(self, graph, selection):
        self.log.append(("render",))
        if self.error:
            raise self.error
        return self.inner.render(graph, selection)


@dataclass
class World:
    log: list
    chess: FakeChess
    sessions: FakeSessions
    engine: FakeEngine
    judge: FakeJudge
    explanations: FakeExplanations
    renderer: SpyRenderer
    service: AnalyzeMoveService


def build(**outcome) -> World:
    log: list = []
    sessions = FakeSessions(log)
    engine = FakeEngine(log, sessions)
    chess = FakeChess(log)
    judge = FakeJudge(log)
    explanations = FakeExplanations(log, engine, **outcome)
    renderer = SpyRenderer(log)
    service = AnalyzeMoveService(
        chess=chess,  # type: ignore[arg-type]
        engine=engine,  # type: ignore[arg-type]
        sessions=sessions,  # type: ignore[arg-type]
        judge=judge,  # type: ignore[arg-type]
        explanations=explanations,  # type: ignore[arg-type]
        renderer=renderer,  # type: ignore[arg-type]
    )
    return World(log, chess, sessions, engine, judge, explanations, renderer, service)


def request(budget=None, mode=OutputMode.STRUCTURED, heuristic=False):
    options = AnalysisOptions(
        budget=budget or AnalysisBudget(), output_mode=mode, allow_heuristic_claims=heuristic
    )
    return AnalyzeMoveRequest(fen=FEN, move_uci=MOVE.uci, options=options)
