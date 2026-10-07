"""Internal evidence-bearing models for MVP-P8 bad-move explanation.

These values preserve verified analysis inputs and outcomes. They do not decide move quality,
perform engine analysis, or render prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.analysis.counterfactual import CounterfactualProbe, ProbeResult
from calliope.domain.analysis.delta import BoardDelta
from calliope.domain.analysis.tactics import TacticalCandidate
from calliope.domain.chess import ChessMove, Color, PieceType, square_index


class BadMoveExplanationStatus(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


class BadMoveCauseStatus(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class BadMoveCauseKind(StrEnum):
    NEWLY_HANGING_PIECE = "newly_hanging_piece"
    REMOVED_DEFENDER = "removed_defender"
    FORK_ALLOWED = "fork_allowed"
    MATE_ALLOWED = "mate_allowed"
    MATERIAL_LOSS_LINE = "material_loss_line"


class MateEvidenceLevel(StrEnum):
    EXACT_IMMEDIATE = "exact_immediate"
    ENGINE_LINE = "engine_line"


@dataclass(frozen=True, slots=True)
class BasePieceRef:
    """Identity of one physical piece anchored to the common base position."""

    color: Color
    piece_type: PieceType
    base_square: str

    def __post_init__(self) -> None:
        square_index(self.base_square)


@dataclass(frozen=True, slots=True)
class MaterialLineEvidence:
    """Weighted material measurement of one replayed counterfactual line.

    ``material_delta`` is the mover's material-advantage change relative to the base position;
    negative is a deficit.  ``stable_at_ply`` is the replay ply at which the measurement became
    stable, or ``None`` when the line ended before a stable point.  Comparator equivalence is
    decided by the explainer, not by this value.
    """

    probe: CounterfactualProbe
    material_delta: int
    stable_at_ply: int | None
    terminal_checkmate: bool = False

    def __post_init__(self) -> None:
        if self.stable_at_ply is not None and self.stable_at_ply < 0:
            raise ValueError("stable_at_ply must be non-negative")
        if self.terminal_checkmate and self.stable_at_ply is None:
            raise ValueError("a checkmate endpoint is a stable point")

    @property
    def stable_deficit(self) -> int | None:
        """Magnitude of a stable mover deficit, or ``None`` if none was established."""

        if self.stable_at_ply is None or self.material_delta >= 0:
            return None
        return -self.material_delta


@dataclass(frozen=True, slots=True)
class BadMoveCauseResult:
    """Machine-readable evidence record for one P8 cause candidate."""

    kind: BadMoveCauseKind
    status: BadMoveCauseStatus
    subject: tuple[BasePieceRef, ...]

    base_position_id: str
    played_move: ChessMove
    comparator_move: ChessMove
    punishment_move: ChessMove | None = None

    affected_pieces: tuple[BasePieceRef, ...] = ()
    board_deltas: tuple[BoardDelta, ...] = ()
    tactical_candidates: tuple[TacticalCandidate, ...] = ()
    probe_results: tuple[ProbeResult, ...] = ()
    material_evidence: tuple[MaterialLineEvidence, ...] = ()

    same_punishment_legal_after_comparator: bool | None = None
    comparator_has_equivalent_resource: bool | None = None

    mate_evidence_level: MateEvidenceLevel | None = None
    replayed_pv_ends_in_checkmate: bool | None = None

    def __post_init__(self) -> None:
        if not self.base_position_id:
            raise ValueError("base_position_id must not be empty")
        if self.played_move.uci == self.comparator_move.uci:
            raise ValueError("comparator must differ from the played move")
        if not self.subject:
            raise ValueError("cause subject must not be empty")
        if len(self.subject) != len(set(self.subject)):
            raise ValueError("cause subject must not contain duplicate base pieces")
        if len(self.affected_pieces) != len(set(self.affected_pieces)):
            raise ValueError("affected_pieces must not contain duplicate base pieces")
        if self.replayed_pv_ends_in_checkmate is not None and self.mate_evidence_level is None:
            raise ValueError("exact replayed-PV mate flag requires mate_evidence_level")
        if self.mate_evidence_level is not None and self.kind is not BadMoveCauseKind.MATE_ALLOWED:
            raise ValueError("mate evidence is only valid for MATE_ALLOWED")
        if (
            self.kind is BadMoveCauseKind.MATE_ALLOWED
            and self.status is BadMoveCauseStatus.SUPPORTED
            and self.mate_evidence_level is None
        ):
            raise ValueError("supported MATE_ALLOWED requires mate_evidence_level")


@dataclass(frozen=True, slots=True)
class BadMoveExplanationResult:
    """Aggregate P8 result; it never changes the underlying MoveJudgement."""

    status: BadMoveExplanationStatus
    base_position_id: str
    played_move: ChessMove
    comparator_move: ChessMove
    causes: tuple[BadMoveCauseResult, ...] = ()

    def __post_init__(self) -> None:
        if not self.base_position_id:
            raise ValueError("base_position_id must not be empty")

        for cause in self.causes:
            if cause.base_position_id != self.base_position_id:
                raise ValueError("cause belongs to another base position")
            if cause.played_move.uci != self.played_move.uci:
                raise ValueError("cause played move differs from aggregate result")
            if cause.comparator_move.uci != self.comparator_move.uci:
                raise ValueError("cause comparator move differs from aggregate result")
        punishments = {c.punishment_move.uci for c in self.causes if c.punishment_move}
        if len(punishments) > 1:
            raise ValueError("causes disagree on the opponent punishment move")
        candidates = [(c.kind, c.subject) for c in self.causes]
        if len(candidates) != len(set(candidates)):
            raise ValueError("duplicate cause candidate")

        statuses = tuple(cause.status for cause in self.causes)
        if self.status is BadMoveExplanationStatus.NOT_APPLICABLE:
            if self.causes:
                raise ValueError("NOT_APPLICABLE result must not contain causes")
            return

        # Every eligible result compares the played move with a distinct comparator.
        if self.played_move.uci == self.comparator_move.uci:
            raise ValueError("comparator must differ from the played move")

        if self.status is BadMoveExplanationStatus.SUPPORTED:
            if BadMoveCauseStatus.SUPPORTED not in statuses:
                raise ValueError("SUPPORTED result requires a supported cause")
            return

        if self.status is BadMoveExplanationStatus.REFUTED:
            if not statuses or any(status is not BadMoveCauseStatus.REFUTED for status in statuses):
                raise ValueError("REFUTED result requires one or more wholly refuted causes")
            return

        # INCONCLUSIVE: no supported cause, and a non-empty cause set may not be wholly refuted.
        if BadMoveCauseStatus.SUPPORTED in statuses:
            raise ValueError("INCONCLUSIVE result must not contain a supported cause")
        if statuses and all(status is BadMoveCauseStatus.REFUTED for status in statuses):
            raise ValueError("wholly refuted causes require a REFUTED aggregate result")
