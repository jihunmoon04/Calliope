"""Stable public DTOs for Calliope integrations.

These models are intentionally distinct from internal domain objects.  Python callers,
agent tools, MCP/HTTP adapters, and future transports should depend on this module rather
than on analysis-service internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


PUBLIC_SCHEMA_VERSION = "0.1"


class OutputMode(StrEnum):
    """How much presentation the caller requests."""

    STRUCTURED = "structured"
    COMMENTARY = "commentary"


@dataclass(frozen=True, slots=True)
class AnalysisBudget:
    """Transport-neutral analysis limits.

    Concrete Stockfish/UCI translation belongs in the Stockfish adapter.  Fields are optional
    so hosts can provide their own defaults.
    """

    depth: int | None = None
    nodes: int | None = None
    time_ms: int | None = None
    multipv: int | None = None


@dataclass(frozen=True, slots=True)
class AnalysisOptions:
    """Public analysis policy.

    Strict mode is the default: heuristic claims are not eligible for final commentary.
    """

    budget: AnalysisBudget = field(default_factory=AnalysisBudget)
    output_mode: OutputMode = OutputMode.STRUCTURED
    allow_heuristic_claims: bool = False


@dataclass(frozen=True, slots=True)
class AnalyzeMoveRequest:
    fen: str
    move_uci: str
    options: AnalysisOptions = field(default_factory=AnalysisOptions)


@dataclass(frozen=True, slots=True)
class AnalyzeGameRequest:
    pgn: str
    options: AnalysisOptions = field(default_factory=AnalysisOptions)


@dataclass(frozen=True, slots=True)
class JudgementSummary:
    move_uci: str
    best_move_uci: str | None
    quality: str
    rank: int | None = None
    cp_loss: int | None = None
    expected_score_loss: float | None = None
    forcedness: str | None = None


@dataclass(frozen=True, slots=True)
class VariationView:
    """A verified line exposed to callers in canonical move notation."""

    moves_uci: tuple[str, ...]
    purpose: str | None = None


@dataclass(frozen=True, slots=True)
class ClaimView:
    """Serializable projection of an evidence-backed ExplanationClaim."""

    claim_id: str
    confidence: str
    subject: str
    predicate: str
    objects: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    importance: float | None = None


@dataclass(frozen=True, slots=True)
class CommentaryView:
    text: str
    used_claim_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MoveAnalysisResult:
    schema_version: str
    position_fen: str
    judgement: JudgementSummary
    claims: tuple[ClaimView, ...]
    variations: tuple[VariationView, ...] = ()
    commentary: CommentaryView | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GameAnalysisResult:
    schema_version: str
    moves: tuple[MoveAnalysisResult, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
