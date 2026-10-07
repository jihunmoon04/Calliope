"""Internal immutable evidence values for MVP-P9 good/only-move explanation.

These records retain representative evidence, never exhaustive uniqueness proof.
They validate model shape and context binding without performing chess analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from calliope.domain.analysis.bad_move import BasePieceRef, MateEvidenceLevel, MaterialLineEvidence
from calliope.domain.analysis.counterfactual import ProbeResult
from calliope.domain.analysis.delta import BoardDelta
from calliope.domain.analysis.tactics import TacticalCandidate
from calliope.domain.chess import ChessMove


class GoodMoveExplanationStatus(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


class GoodMoveBenefitStatus(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class GoodMoveMode(StrEnum):
    STRONG_MOVE = "strong_move"
    ONLY_MOVE_CANDIDATE = "only_move_candidate"


class GoodMoveBenefitKind(StrEnum):
    FORCES_RESPONSE = "forces_response"
    MATE_THREAT = "mate_threat"
    MATERIAL_THREAT = "material_threat"
    PREVENTS_MATE = "prevents_mate"
    PREVENTS_MATERIAL_LOSS = "prevents_material_loss"


class AlternativeScope(StrEnum):
    REPRESENTATIVE_TOP_ENGINE_LINES = "representative_top_engine_lines"


@dataclass(frozen=True, slots=True)
class RepresentativeAlternative:
    """Rank and canonical move selection identity, without engine scores."""

    rank: int
    move: ChessMove

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError("alternative rank must be at least 1")


def _alternative_keys(
    alternatives: tuple[RepresentativeAlternative, ...], label: str
) -> tuple[tuple[int, str], ...]:
    """Validate retained order; SAN is not alternative membership identity."""

    ranks = tuple(alternative.rank for alternative in alternatives)
    ucis = tuple(alternative.move.uci for alternative in alternatives)
    if len(ranks) != len(set(ranks)):
        raise ValueError(f"{label} must contain unique ranks")
    if len(ucis) != len(set(ucis)):
        raise ValueError(f"{label} must contain unique move UCIs")
    if any(left >= right for left, right in pairwise(ranks)):
        raise ValueError(f"{label} must be sorted by ascending rank")
    return tuple(zip(ranks, ucis, strict=True))


@dataclass(frozen=True, slots=True)
class GoodMoveBenefitResult:
    """Evidence record for one benefit candidate against representative alternatives."""

    kind: GoodMoveBenefitKind
    status: GoodMoveBenefitStatus
    mode: GoodMoveMode
    subject: tuple[BasePieceRef, ...]
    base_position_id: str
    played_move: ChessMove
    alternatives: tuple[RepresentativeAlternative, ...]
    failed_alternatives: tuple[RepresentativeAlternative, ...] = ()
    tested_response: ChessMove | None = None
    affected_pieces: tuple[BasePieceRef, ...] = ()
    board_deltas: tuple[BoardDelta, ...] = ()
    tactical_candidates: tuple[TacticalCandidate, ...] = ()
    probe_results: tuple[ProbeResult, ...] = ()
    material_evidence: tuple[MaterialLineEvidence, ...] = ()
    equivalent_alternative_benefit: bool | None = None
    mate_evidence_level: MateEvidenceLevel | None = None
    replayed_pv_ends_in_checkmate: bool | None = None
    alternative_scope: AlternativeScope = AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES

    def __post_init__(self) -> None:
        if not self.base_position_id:
            raise ValueError("base_position_id must not be empty")
        if not self.subject:
            raise ValueError("benefit subject must not be empty")
        if len(self.subject) != len(set(self.subject)):
            raise ValueError("benefit subject must contain unique base pieces")
        if len(self.affected_pieces) != len(set(self.affected_pieces)):
            raise ValueError("affected_pieces must contain unique base pieces")

        alternatives = _alternative_keys(self.alternatives, "alternatives")
        failed = _alternative_keys(self.failed_alternatives, "failed_alternatives")
        if not set(failed).issubset(alternatives):
            raise ValueError("failed_alternatives must be a subset of alternatives by rank and UCI")
        if self.alternative_scope is not AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES:
            raise ValueError("benefit requires representative alternative scope")

        prevention_kinds = (
            GoodMoveBenefitKind.PREVENTS_MATE,
            GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS,
        )
        if self.kind in prevention_kinds and self.mode is not GoodMoveMode.ONLY_MOVE_CANDIDATE:
            raise ValueError("prevention benefits require ONLY_MOVE_CANDIDATE mode")

        mate_kinds = (GoodMoveBenefitKind.MATE_THREAT, GoodMoveBenefitKind.PREVENTS_MATE)
        if self.mate_evidence_level is not None and self.kind not in mate_kinds:
            raise ValueError("mate_evidence_level is only valid for mate benefits")
        if self.replayed_pv_ends_in_checkmate is not None and self.mate_evidence_level is None:
            raise ValueError("replayed mate flag requires mate_evidence_level")
        if (
            self.kind in mate_kinds
            and self.status is GoodMoveBenefitStatus.SUPPORTED
            and self.mate_evidence_level is None
        ):
            raise ValueError("supported mate benefit requires mate_evidence_level")

        material_kinds = (
            GoodMoveBenefitKind.MATERIAL_THREAT,
            GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS,
        )
        if (
            self.kind in material_kinds
            and self.status is GoodMoveBenefitStatus.SUPPORTED
            and not self.material_evidence
        ):
            raise ValueError("supported material benefit requires material_evidence")


@dataclass(frozen=True, slots=True)
class GoodMoveExplanationResult:
    """Aggregate internal P9 evidence; literal-only-move proof is forbidden in MVP."""

    status: GoodMoveExplanationStatus
    base_position_id: str
    played_move: ChessMove
    mode: GoodMoveMode | None = None
    alternatives: tuple[RepresentativeAlternative, ...] = ()
    alternative_scope: AlternativeScope | None = None
    literal_only_move_proven: bool = False
    benefits: tuple[GoodMoveBenefitResult, ...] = ()

    def __post_init__(self) -> None:
        if not self.base_position_id:
            raise ValueError("base_position_id must not be empty")
        if self.literal_only_move_proven is not False:
            raise ValueError("literal_only_move_proven must always be False in MVP-P9")
        _alternative_keys(self.alternatives, "alternatives")

        if self.status is GoodMoveExplanationStatus.NOT_APPLICABLE:
            if (
                self.mode is not None
                or self.alternatives
                or self.alternative_scope is not None
                or self.benefits
            ):
                raise ValueError(
                    "NOT_APPLICABLE requires no mode, alternatives, scope, or benefits"
                )
            return

        if self.mode is None:
            raise ValueError("eligible result requires mode")
        if self.alternative_scope is not AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES:
            raise ValueError("eligible result requires representative alternative scope")

        for benefit in self.benefits:
            if benefit.base_position_id != self.base_position_id:
                raise ValueError("benefit belongs to another base position")
            if benefit.played_move.uci != self.played_move.uci:
                raise ValueError("benefit played move differs from aggregate result")
            if benefit.mode != self.mode:
                raise ValueError("benefit mode differs from aggregate result")
            if benefit.alternative_scope != self.alternative_scope:
                raise ValueError("benefit alternative scope differs from aggregate result")
            if benefit.alternatives != self.alternatives:
                raise ValueError("benefit alternatives differ from aggregate result")

        candidates = [(benefit.kind, benefit.subject) for benefit in self.benefits]
        if len(candidates) != len(set(candidates)):
            raise ValueError("duplicate benefit candidate")

        statuses = tuple(benefit.status for benefit in self.benefits)
        if self.status is GoodMoveExplanationStatus.SUPPORTED:
            if GoodMoveBenefitStatus.SUPPORTED not in statuses:
                raise ValueError("SUPPORTED result requires a supported benefit")
            return
        if self.status is GoodMoveExplanationStatus.REFUTED:
            if not statuses or any(
                status is not GoodMoveBenefitStatus.REFUTED for status in statuses
            ):
                raise ValueError("REFUTED result requires one or more wholly refuted benefits")
            return
        if GoodMoveBenefitStatus.SUPPORTED in statuses:
            raise ValueError("INCONCLUSIVE result must not contain a supported benefit")
        if statuses and all(status is GoodMoveBenefitStatus.REFUTED for status in statuses):
            raise ValueError("wholly refuted benefits require a REFUTED aggregate result")
