from dataclasses import dataclass

import pytest

from calliope import (
    AnalyzeGameRequest,
    AnalyzeMoveRequest,
    CalliopeEngine,
    GameAnalysisResult,
    MoveAnalysisResult,
)
from calliope.contracts import PUBLIC_SCHEMA_VERSION, JudgementSummary
from calliope.errors import CalliopeClosedError


@dataclass
class FakeMoveUseCase:
    calls: int = 0

    def execute(self, request: AnalyzeMoveRequest) -> MoveAnalysisResult:
        self.calls += 1
        return MoveAnalysisResult(
            schema_version=PUBLIC_SCHEMA_VERSION,
            position_fen=request.fen,
            judgement=JudgementSummary(
                move_uci=request.move_uci,
                best_move_uci=request.move_uci,
                quality="BEST",
            ),
            claims=(),
        )


@dataclass
class FakeGameUseCase:
    calls: int = 0

    def execute(self, request: AnalyzeGameRequest) -> GameAnalysisResult:
        self.calls += 1
        return GameAnalysisResult(schema_version=PUBLIC_SCHEMA_VERSION, moves=())


def test_engine_is_single_facade_over_move_and_game_use_cases() -> None:
    move = FakeMoveUseCase()
    game = FakeGameUseCase()
    engine = CalliopeEngine(move, game)

    move_result = engine.analyze_move(
        AnalyzeMoveRequest(fen="8/8/8/8/8/8/8/K6k w - - 0 1", move_uci="a1a2")
    )
    game_result = engine.analyze_game(AnalyzeGameRequest(pgn="*"))

    assert move_result.judgement.quality == "BEST"
    assert game_result.schema_version == PUBLIC_SCHEMA_VERSION
    assert move.calls == 1
    assert game.calls == 1


def test_close_is_idempotent_and_calls_hook_once():
    hooks = []
    move, game = FakeMoveUseCase(), FakeGameUseCase()
    engine = CalliopeEngine(move, game, lambda: hooks.append(1))
    engine.close()
    engine.close()
    assert hooks == [1]


def test_analyze_after_close_fails_without_calling_use_cases():
    move, game = FakeMoveUseCase(), FakeGameUseCase()
    engine = CalliopeEngine(move, game)
    engine.close()
    with pytest.raises(CalliopeClosedError):
        engine.analyze_move(AnalyzeMoveRequest(fen="x", move_uci="a1a2"))
    with pytest.raises(CalliopeClosedError):
        engine.analyze_game(AnalyzeGameRequest(pgn="*"))
    assert (move.calls, game.calls) == (0, 0)


def test_context_manager_closes():
    hooks = []
    with CalliopeEngine(FakeMoveUseCase(), FakeGameUseCase(), lambda: hooks.append(1)):
        assert hooks == []
    assert hooks == [1]
