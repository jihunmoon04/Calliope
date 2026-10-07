"""Controlled hypothetical-experiment requests and results.

These models only preserve what was asked and what was observed.  They never carry a
verdict about tactics, causes, or move quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.chess import ChessMove, Color, PositionSnapshot
from calliope.domain.engine import EngineAnalysis, EngineSettings


class ProbeKind(StrEnum):
    BEST_RESPONSE = "best_response"
    ALTERNATIVE_MOVE = "alternative_move"
    REFUTATION = "refutation"
    IGNORE_THREAT = "ignore_threat"


class TerminalKind(StrEnum):
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"


@dataclass(frozen=True, slots=True)
class TerminalOutcome:
    kind: TerminalKind
    winner: Color | None


@dataclass(frozen=True, slots=True)
class CounterfactualProbe:
    """One experiment.  Move identity is the UCI string; SAN is presentation only."""

    kind: ProbeKind
    base: PositionSnapshot
    intervention_move: ChessMove | None = None
    execution_move: ChessMove | None = None


@dataclass(frozen=True, slots=True)
class ProbeResult:
    probe: CounterfactualProbe
    analysis_position: PositionSnapshot
    intervention_position: PositionSnapshot | None
    root_moves: tuple[ChessMove, ...] | None
    engine_analysis: EngineAnalysis | None
    terminal: TerminalOutcome | None

    def __post_init__(self) -> None:
        if (self.engine_analysis is None) == (self.terminal is None):
            raise ValueError("exactly one of engine_analysis or terminal must be set")
        if self.terminal is not None and self.root_moves is not None:
            raise ValueError("terminal results have no engine root moves")
        if (
            self.engine_analysis is not None
            and self.engine_analysis.position_id != self.analysis_position.position_id
        ):
            raise ValueError("engine analysis must belong to the analysis position")


@dataclass(frozen=True, slots=True)
class CounterfactualBatchRequest:
    probes: tuple[CounterfactualProbe, ...]
    settings: EngineSettings


@dataclass(frozen=True, slots=True)
class CounterfactualBatchResult:
    settings: EngineSettings
    results: tuple[ProbeResult, ...]
