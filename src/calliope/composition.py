"""Composition root wiring the canonical Calliope engine."""

from __future__ import annotations

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.application.analyze_game import AnalyzeGameUnavailable
from calliope.application.analyze_move import AnalyzeMoveService
from calliope.application.explanation import MoveExplanationPipeline
from calliope.application.observe_move import ObservedMoveService
from calliope.engine import CalliopeEngine
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import (
    BadMoveExplainer,
    DeterministicExplanationRenderer,
    GoodMoveExplainer,
)
from calliope.services.judgement.move_judge import MoveJudge
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer
from calliope.services.position.scenario import ScenarioLineAnalyzer
from calliope.services.tactics import TacticalDetector


def create_calliope_engine(
    stockfish_command: str | list[str] = "stockfish",
    *,
    startup_timeout_s: float = 10.0,
    default_depth: int = 12,
    default_multipv: int = 5,
) -> CalliopeEngine:
    """Build a facade that owns one Stockfish process; call ``close()`` when done.

    One python-chess adapter serves every rules/observation port, and the same Stockfish
    process serves both the judgement analyses and every P7 counterfactual probe. The opt-in
    observation path reuses the same adapter, fact extractor and board-delta analyzer and has
    no engine port.

    Raises ``EngineStartupError`` if Stockfish cannot be started.
    """
    stockfish = StockfishAdapter.start(stockfish_command, timeout_s=startup_timeout_s)
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    delta = BoardDeltaAnalyzer(rules, facts)
    explainer_ports = {
        "chess": rules,
        "facts": facts,
        "delta": delta,
        "tactical_rules": rules,
        "detector": TacticalDetector(),
        "counterfactual": CounterfactualAnalyzer(
            chess=rules, engine=stockfish, tactical_rules=rules, position_rules=rules
        ),
    }
    move_service = AnalyzeMoveService(
        chess=rules,
        engine=stockfish,
        sessions=stockfish,
        judge=MoveJudge(),
        explanations=MoveExplanationPipeline(
            bad_moves=BadMoveExplainer(**explainer_ports),
            good_moves=GoodMoveExplainer(**explainer_ports),
        ),
        renderer=DeterministicExplanationRenderer(),
        default_depth=default_depth,
        default_multipv=default_multipv,
    )
    positions = PositionAnalyzer(facts)
    scenarios = ScenarioLineAnalyzer(
        ActivityLineAnalyzer(
            LineAnalyzer(TransitionAnalyzer(rules, positions, delta)),
            ActivityAnalyzer(positions, rules),
        )
    )
    observations = ObservedMoveService(legacy=move_service, chess=rules, scenarios=scenarios)
    return CalliopeEngine(move_service, AnalyzeGameUnavailable(), stockfish.close, observations)
