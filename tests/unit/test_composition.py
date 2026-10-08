"""G0 composition root: one PythonChess adapter, one Stockfish process, one request session port."""

import dataclasses
from pathlib import Path

import pytest

from calliope import composition
from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.application.explanation import COUNTERFACTUAL_SETTINGS, MoveExplanationPipeline
from calliope.domain.engine import EngineIdentity
from calliope.services.explanation import DeterministicExplanationRenderer

SRC = Path(composition.__file__).resolve().parent


class FakeProcess:
    def __init__(self):
        self.quit_count = 0
        self.options = {}

    def quit(self):
        self.quit_count += 1

    def close(self):
        pass


@pytest.fixture
def composed(monkeypatch):
    started = []

    def start(command, *, timeout_s=10.0):
        process = FakeProcess()
        adapter = StockfishAdapter(process, EngineIdentity("Stockfish 17"))  # type: ignore[arg-type]
        started.append((adapter, process))
        return adapter

    monkeypatch.setattr(StockfishAdapter, "start", staticmethod(start))
    engine = composition.create_calliope_engine("stockfish")
    return engine, started


def test_one_process_serves_judgement_sessions_and_p7(composed):
    engine, started = composed
    ((stockfish, _),) = started
    service = engine._move_analysis
    pipeline = service.explanations
    assert type(pipeline) is MoveExplanationPipeline
    assert type(service.renderer) is DeterministicExplanationRenderer
    assert service.engine is stockfish and service.sessions is stockfish
    assert pipeline.bad_moves.counterfactual.engine is stockfish
    assert pipeline.good_moves.counterfactual.engine is stockfish
    assert pipeline.settings == COUNTERFACTUAL_SETTINGS


def test_one_python_chess_adapter_is_shared(composed):
    engine, _ = composed
    service = engine._move_analysis
    rules = service.chess
    assert type(rules) is PythonChessAdapter
    for explainer in (service.explanations.bad_moves, service.explanations.good_moves):
        assert explainer.chess is rules and explainer.tactical_rules is rules
        assert explainer.facts.observations is rules
        assert explainer.delta.chess is rules and explainer.delta.facts is explainer.facts
        counterfactual = explainer.counterfactual
        assert counterfactual.chess is rules
        assert counterfactual.tactical_rules is rules and counterfactual.position_rules is rules
    bad, good = service.explanations.bad_moves, service.explanations.good_moves
    assert bad.counterfactual is good.counterfactual and bad.detector is good.detector


def test_close_quits_the_one_process_once(composed):
    engine, started = composed
    engine.close()
    engine.close()
    ((_, process),) = started
    assert process.quit_count == 1


def test_no_hidden_engine_constructor_outside_the_composition_root():
    allowed = {SRC / "composition.py", SRC / "adapters" / "stockfish" / "adapter.py"}
    for path in SRC.rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in ("StockfishAdapter.start", "popen_uci", "SimpleEngine"):
            assert needle not in text, (path, needle)


def test_observation_path_reuses_the_exact_rules_facts_and_delta(composed):
    engine, started = composed
    ((stockfish, _),) = started
    service = engine._move_analysis
    observed = engine._observed_move_analysis
    explainer = service.explanations.bad_moves
    assert observed.legacy is service
    assert observed.chess is service.chess is explainer.chess
    activity_lines = observed.scenarios.activity_lines
    transitions = activity_lines.lines.transitions
    assert transitions.chess is service.chess
    assert transitions.deltas is explainer.delta is service.explanations.good_moves.delta
    assert transitions.positions.facts is explainer.facts
    assert activity_lines.activity.positions is transitions.positions
    assert activity_lines.activity.tactics is service.chess
    # Below the legacy use case, the observation graph holds no engine or session port.
    reachable = [observed.scenarios, activity_lines, activity_lines.lines, transitions]
    reachable += [transitions.positions, transitions.positions.facts, transitions.deltas]
    reachable += [activity_lines.activity]
    for node in reachable:
        for field in dataclasses.fields(node):
            assert getattr(node, field.name) is not stockfish, (type(node).__name__, field.name)
