"""Stable public DTOs for Calliope integrations.

These models are intentionally distinct from internal domain objects.  Python callers,
agent tools, MCP/HTTP adapters, and future transports should depend on this module rather
than on analysis-service internals.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

PUBLIC_SCHEMA_VERSION = "0.2"


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


class ClaimEntityKind(StrEnum):
    """Discriminator of a public claim entity."""

    MOVE = "move"
    PIECE = "piece"
    SIDE = "side"


@dataclass(frozen=True, slots=True)
class MoveClaimEntityView:
    """A move in canonical UCI plus the exact position it is legal from (never SAN)."""

    move_uci: str
    position_id: str
    kind: ClaimEntityKind = field(default=ClaimEntityKind.MOVE, init=False)


@dataclass(frozen=True, slots=True)
class PieceClaimEntityView:
    """One physical base-frame piece plus its presentation state at ``at_position_id``."""

    color: str
    base_piece_type: str
    base_square: str
    at_position_id: str
    current_piece_type: str
    current_square: str
    kind: ClaimEntityKind = field(default=ClaimEntityKind.PIECE, init=False)


@dataclass(frozen=True, slots=True)
class SideClaimEntityView:
    color: str
    kind: ClaimEntityKind = field(default=ClaimEntityKind.SIDE, init=False)


ClaimEntityView = MoveClaimEntityView | PieceClaimEntityView | SideClaimEntityView


@dataclass(frozen=True, slots=True)
class ClaimView:
    """Lossless projection of one validated evidence-backed claim, scope included."""

    claim_id: str
    base_position_id: str
    confidence: str
    scope: str
    subject: MoveClaimEntityView
    predicate: str
    objects: tuple[ClaimEntityView, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    importance: float | None = None


@dataclass(frozen=True, slots=True)
class CommentaryView:
    """Deterministic commentary; ``sentences`` pair 1:1 with ``used_claim_ids``."""

    text: str
    sentences: tuple[str, ...]
    used_claim_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MoveAnalysisResult:
    schema_version: str
    position_fen: str
    judgement: JudgementSummary
    claims: tuple[ClaimView, ...]
    selected_claim_ids: tuple[str, ...] = ()
    variations: tuple[VariationView, ...] = ()
    commentary: CommentaryView | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GameAnalysisResult:
    schema_version: str
    moves: tuple[MoveAnalysisResult, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


# ---- explicit opt-in observation envelope (schema 0.3) ------------------------------------
#
# Only ``CalliopeEngine.analyze_move_with_observations`` returns these; ``analyze_move`` and
# every schema-0.2 DTO above are unchanged. Observations are noncausal source-linked facts,
# never claims, and never appear in ``CommentaryView`` or ``used_claim_ids``.

OBSERVATION_SCHEMA_VERSION = "0.3"


@dataclass(frozen=True, slots=True)
class SuppliedExchangeObservationRequest:
    """One explicit supplied line (0-8 canonical UCI moves) observed at ``focus_square``."""

    focus_square: str
    moves_uci: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObservedMoveRequest:
    """The unchanged legacy request plus the observation sections to add to it."""

    base: AnalyzeMoveRequest
    include_played: bool = True
    exchange_lines: tuple[SuppliedExchangeObservationRequest, ...] = ()


@dataclass(frozen=True, slots=True)
class ObservationSourceView:
    """Closed projection of one validated internal source reference."""

    kind: str
    anchor_kind: str
    index: int | None
    position_ids: tuple[str, ...]
    selectors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservationSentenceView:
    observation_id: str
    template_id: str
    text: str
    source_refs: tuple[ObservationSourceView, ...]


@dataclass(frozen=True, slots=True)
class ObservationSectionView:
    label: str
    scope: str
    supplied_line_uci: tuple[str, ...]
    focus_square: str | None
    status: str | None
    focus_capture_count: int | None
    sentences: tuple[ObservationSentenceView, ...]


@dataclass(frozen=True, slots=True)
class ObservedMoveAnalysisResult:
    """Schema 0.3 envelope around the exact schema-0.2 result of the same request."""

    schema_version: str
    base_result: MoveAnalysisResult
    played: ObservationSectionView | None
    exchange_lines: tuple[ObservationSectionView, ...]
