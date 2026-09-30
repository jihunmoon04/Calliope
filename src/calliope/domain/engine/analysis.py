"""Normalized Stockfish analysis observations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.chess.move import ChessMove
from calliope.domain.engine.score import EngineScore, WDL


@dataclass(frozen=True, slots=True)
class EngineIdentity:
    name: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class EngineLimit:
    """Exact limit used for one engine analysis."""

    depth: int | None = None
    nodes: int | None = None
    time_ms: int | None = None

    def __post_init__(self) -> None:
        if self.depth is not None and self.depth < 1:
            raise ValueError("depth must be positive")
        if self.nodes is not None and self.nodes < 1:
            raise ValueError("nodes must be positive")
        if self.time_ms is not None and self.time_ms < 1:
            raise ValueError("time_ms must be positive")
        if self.depth is None and self.nodes is None and self.time_ms is None:
            raise ValueError("at least one engine limit must be set")


@dataclass(frozen=True, slots=True)
class EngineSettings:
    limit: EngineLimit
    multipv: int = 1
    threads: int | None = None
    hash_mb: int | None = None

    def __post_init__(self) -> None:
        if self.multipv < 1:
            raise ValueError("multipv must be positive")


class StabilityLevel(StrEnum):
    UNKNOWN = "unknown"
    STABLE = "stable"
    UNSTABLE = "unstable"


@dataclass(frozen=True, slots=True)
class EngineStability:
    level: StabilityLevel = StabilityLevel.UNKNOWN
    samples: int = 1
    best_move_switches: int = 0
    max_cp_swing: int | None = None

    def __post_init__(self) -> None:
        if self.samples < 1:
            raise ValueError("samples must be positive")
        if self.best_move_switches < 0:
            raise ValueError("best_move_switches must be non-negative")
        if self.max_cp_swing is not None and self.max_cp_swing < 0:
            raise ValueError("max_cp_swing must be non-negative")


@dataclass(frozen=True, slots=True)
class EngineLine:
    rank: int
    first_move: ChessMove
    score: EngineScore
    pv: tuple[ChessMove, ...]
    wdl: WDL | None = None
    depth: int | None = None
    seldepth: int | None = None
    nodes: int | None = None

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError("rank must be positive")
        if not self.pv:
            raise ValueError("pv must contain at least the first move")
        if self.pv[0].uci != self.first_move.uci:
            raise ValueError("first_move must equal the first PV move")


@dataclass(frozen=True, slots=True)
class EngineAnalysis:
    position_id: str
    engine: EngineIdentity
    settings: EngineSettings
    lines: tuple[EngineLine, ...]
    stability: EngineStability = EngineStability()

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError("engine analysis must contain at least one line")
        ranks = [line.rank for line in self.lines]
        if len(ranks) != len(set(ranks)):
            raise ValueError("engine line ranks must be unique")
        if min(ranks) != 1:
            raise ValueError("engine analysis must contain rank 1")

    @property
    def best_line(self) -> EngineLine:
        return next(line for line in self.lines if line.rank == 1)
