import json
from dataclasses import dataclass, field

import pytest

from calliope.application.analyze_move import AnalyzeMoveService
from calliope.contracts import (
    PUBLIC_SCHEMA_VERSION,
    AnalysisBudget,
    AnalysisOptions,
    AnalyzeMoveRequest,
    OutputMode,
)
from calliope.domain.chess import ChessMove, Color, PositionSnapshot
from calliope.domain.engine import (
    EngineAnalysis,
    EngineIdentity,
    EngineLimit,
    EngineLine,
    EngineScore,
    EngineSettings,
    Forcedness,
    ForcednessLevel,
    MoveJudgement,
    MoveQuality,
)
from calliope.errors import (
    EngineAnalysisError,
    IllegalMoveError,
    IncompatibleAnalysisError,
    InvalidAnalysisBudgetError,
    InvalidFenError,
    UnsupportedOutputModeError,
)

FEN = "4k3/8/8/8/8/8/8/4K2R w K - 0 1"
MOVE = ChessMove("h1h2")
ENGINE_ID = EngineIdentity("Stockfish", "17")


@dataclass
class FakeChess:
    calls: list = field(default_factory=list)
    fen_error: Exception | None = None
    move_error: Exception | None = None

    def position_from_fen(self, fen):
        self.calls.append(("fen", fen))
        if self.fen_error:
            raise self.fen_error
        return _position()

    def legal_move_from_uci(self, position, move_uci):
        self.calls.append(("move", move_uci))
        if self.move_error:
            raise self.move_error
        return MOVE

    def apply_move(self, position, move):
        raise AssertionError("apply_move must not be called in P3")


def _position() -> PositionSnapshot:
    from calliope.adapters.python_chess import PythonChessAdapter

    return PythonChessAdapter().position_from_fen(FEN)


@dataclass
class FakeEngine:
    calls: list = field(default_factory=list)
    fail_on_call: int | None = None

    def analyze(self, position, settings, root_moves=None):
        self.calls.append((position, settings, root_moves))
        if self.fail_on_call == len(self.calls):
            raise EngineAnalysisError("boom")
        line = EngineLine(
            rank=1, first_move=MOVE, score=EngineScore.cp(10), pv=(MOVE,), wdl=None
        )
        return EngineAnalysis(
            position_id=position.position_id,
            engine=ENGINE_ID,
            settings=settings,
            lines=(line,),
        )


@dataclass
class FakeJudge:
    calls: list = field(default_factory=list)
    error: Exception | None = None

    def judge(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return MoveJudgement(
            position_id=kwargs["position_analysis"].position_id,
            mover=kwargs["mover"],
            move=MOVE,
            best_move=MOVE,
            quality=MoveQuality.BEST,
            rank=1,
            best_score=EngineScore.cp(10),
            played_score=EngineScore.cp(10),
            cp_loss=0,
            expected_score_loss=0.0,
            forcedness=Forcedness(ForcednessLevel.ONLY_MOVE, 1, 120),
        )


def build():
    chess, engine, judge = FakeChess(), FakeEngine(), FakeJudge()
    return AnalyzeMoveService(chess, engine, judge), chess, engine, judge  # type: ignore[arg-type]


def request(budget=None, mode=OutputMode.STRUCTURED):
    options = AnalysisOptions(budget=budget or AnalysisBudget(), output_mode=mode)
    return AnalyzeMoveRequest(fen=FEN, move_uci="h1h2", options=options)


def test_orchestration_order_and_default_budget():
    service, chess, engine, judge = build()
    result = service.execute(request())

    assert [c[0] for c in chess.calls] == ["fen", "move"]
    assert len(engine.calls) == 2
    _, first, first_roots = engine.calls[0]
    _, second, second_roots = engine.calls[1]
    assert first == EngineSettings(limit=EngineLimit(depth=12), multipv=5)
    assert first_roots is None
    assert second == EngineSettings(limit=EngineLimit(depth=12), multipv=1)
    assert second_roots == (MOVE,)
    assert len(judge.calls) == 1
    assert judge.calls[0]["mover"] is Color.WHITE
    assert judge.calls[0]["move"] == MOVE
    assert result.schema_version == PUBLIC_SCHEMA_VERSION


def test_custom_budget_preserved_and_played_analysis_shares_limits():
    service, _, engine, _ = build()
    service.execute(
        request(AnalysisBudget(depth=16, nodes=100000, time_ms=500, multipv=3))
    )
    first, second = engine.calls[0][1], engine.calls[1][1]
    assert first.limit == EngineLimit(depth=16, nodes=100000, time_ms=500)
    assert first.multipv == 3
    assert second.limit == first.limit
    assert (second.threads, second.hash_mb) == (first.threads, first.hash_mb)
    assert second.multipv == 1


def test_default_depth_not_added_when_explicit_limit():
    service, _, engine, _ = build()
    service.execute(request(AnalysisBudget(nodes=100000, multipv=3)))
    settings = engine.calls[0][1]
    assert settings.limit == EngineLimit(depth=None, nodes=100000, time_ms=None)
    assert settings.multipv == 3


@pytest.mark.parametrize(
    "budget",
    [
        AnalysisBudget(depth=0),
        AnalysisBudget(nodes=0),
        AnalysisBudget(time_ms=0),
        AnalysisBudget(multipv=0),
        AnalysisBudget(depth=-1),
        AnalysisBudget(nodes=-5),
        AnalysisBudget(time_ms=-1),
        AnalysisBudget(multipv=-2),
        AnalysisBudget(depth=10, multipv=0),
    ],
)
def test_invalid_budget_rejected_without_engine_calls(budget):
    service, _, engine, judge = build()
    with pytest.raises(InvalidAnalysisBudgetError):
        service.execute(request(budget))
    assert engine.calls == []
    assert judge.calls == []


@pytest.mark.parametrize(
    "attr, error",
    [("fen_error", InvalidFenError("x")), ("move_error", IllegalMoveError("x"))],
)
def test_invalid_chess_input_short_circuits(attr, error):
    service, chess, engine, judge = build()
    setattr(chess, attr, error)
    with pytest.raises(type(error)):
        service.execute(request())
    assert engine.calls == []
    assert judge.calls == []


def test_commentary_rejected_before_any_work():
    service, chess, engine, judge = build()
    with pytest.raises(UnsupportedOutputModeError):
        service.execute(request(mode=OutputMode.COMMENTARY))
    assert chess.calls == []
    assert engine.calls == []
    assert judge.calls == []


def test_dto_projection_and_metadata():
    service, _, _, _ = build()
    result = service.execute(request())
    pos = _position()

    assert result.position_fen == pos.fen
    j = result.judgement
    assert (j.move_uci, j.best_move_uci) == ("h1h2", "h1h2")
    assert j.quality == "best"
    assert j.forcedness == "only_move"
    assert (j.rank, j.cp_loss, j.expected_score_loss) == (1, 0, 0.0)
    assert result.claims == ()
    assert result.variations == ()
    assert result.commentary is None
    assert result.metadata == {
        "position_id": pos.position_id,
        "engine": {"name": "Stockfish", "version": "17"},
        "analysis": {
            "depth": 12,
            "nodes": None,
            "time_ms": None,
            "multipv": 5,
            "threads": None,
            "hash_mb": None,
        },
        "forcedness": {"acceptable_move_count": 1, "best_to_second_gap_cp": 120},
    }
    json.dumps(result.metadata)


def test_played_analysis_failure_yields_no_result_and_preserves_error():
    service, _, engine, judge = build()
    engine.fail_on_call = 2
    with pytest.raises(EngineAnalysisError):
        service.execute(request())
    assert len(engine.calls) == 2
    assert judge.calls == []


def test_judge_error_propagates_unwrapped():
    service, _, _, judge = build()
    judge.error = IncompatibleAnalysisError("nope")
    with pytest.raises(IncompatibleAnalysisError):
        service.execute(request())
