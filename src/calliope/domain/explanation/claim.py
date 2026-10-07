"""Internal immutable MVP-P10 claim values.

These values are the trust boundary between chess analysis and language.  They validate
structural shape only; evidence resolution and semantic compatibility belong to later
P10 builders/validators.  Nothing here performs chess analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.analysis.bad_move import BasePieceRef
from calliope.domain.chess import ChessMove, Color, PieceType, square_index
from calliope.errors import CalliopeError, ExplanationClaimError


class ClaimConfidence(StrEnum):
    EXACT = "exact"
    FORCED = "forced"
    ENGINE_VERIFIED = "engine_verified"


class ClaimScope(StrEnum):
    LOCAL = "local"
    TESTED_RESPONSE = "tested_response"
    REPRESENTATIVE_ALTERNATIVES = "representative_alternatives"


class ClaimPredicate(StrEnum):
    LEAVES_PIECE_HANGING = "leaves_piece_hanging"
    REMOVES_DEFENDER = "removes_defender"
    ALLOWS_FORK = "allows_fork"
    ALLOWS_CHECKMATE = "allows_checkmate"
    ALLOWS_MATERIAL_LOSS = "allows_material_loss"

    FORCES_RESPONSE = "forces_response"
    DELIVERS_CHECKMATE = "delivers_checkmate"
    LEADS_TO_MATE = "leads_to_mate"
    WINS_MATERIAL = "wins_material"
    THREATENS_MATE_IF_IGNORED = "threatens_mate_if_ignored"
    THREATENS_MATERIAL_IF_IGNORED = "threatens_material_if_ignored"

    AVOIDS_REPRESENTATIVE_MATE_FAILURE = "avoids_representative_mate_failure"
    AVOIDS_REPRESENTATIVE_MATERIAL_LOSS = "avoids_representative_material_loss"


_REPRESENTATIVE_PREDICATES = frozenset(
    {
        ClaimPredicate.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
        ClaimPredicate.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS,
    }
)
_TESTED_RESPONSE_PREDICATES = frozenset(
    {
        ClaimPredicate.THREATENS_MATE_IF_IGNORED,
        ClaimPredicate.THREATENS_MATERIAL_IF_IGNORED,
    }
)


def required_claim_scope(predicate: ClaimPredicate) -> ClaimScope:
    """The only structurally compatible scope for a predicate."""

    if predicate in _REPRESENTATIVE_PREDICATES:
        return ClaimScope.REPRESENTATIVE_ALTERNATIVES
    if predicate in _TESTED_RESPONSE_PREDICATES:
        return ClaimScope.TESTED_RESPONSE
    return ClaimScope.LOCAL


# -- request-local ordinal ids --

_ID_PATTERN = re.compile(r"(ev|cl)_([0-9]{3,})")


def _mint_ordinal_id(prefix: str, index: int, error: type[CalliopeError]) -> str:
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise error(f"{prefix} id ordinal must be an integer of at least 1")
    return f"{prefix}_{index:03d}"


def _is_ordinal_id(value: object, prefix: str) -> bool:
    """True only for the exact canonical form a mint helper produces."""

    if not isinstance(value, str):
        return False
    match = _ID_PATTERN.fullmatch(value)
    if match is None or match.group(1) != prefix:
        return False
    ordinal = int(match.group(2))
    return ordinal >= 1 and value == f"{prefix}_{ordinal:03d}"


def mint_claim_id(index: int) -> str:
    """Request-local claim id for the given 1-based canonical ordinal."""

    return _mint_ordinal_id("cl", index, ExplanationClaimError)


def _require_evidence_ids(
    evidence_ids: tuple[str, ...], label: str, error: type[CalliopeError]
) -> None:
    if not evidence_ids:
        raise error(f"{label} must not be empty")
    if any(not _is_ordinal_id(evidence_id, "ev") for evidence_id in evidence_ids):
        raise error(f"{label} must contain canonical evidence ids")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise error(f"{label} must be unique")


# -- structured entities --


@dataclass(frozen=True, slots=True)
class MoveClaimEntity:
    """A move plus the exact position from which it is legal."""

    move: ChessMove
    position_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.move, ChessMove):
            raise ExplanationClaimError("move entity requires a ChessMove")
        if not self.position_id:
            raise ExplanationClaimError("move entity position_id must not be empty")


_PROMOTION_ROLES = frozenset(
    {PieceType.PAWN, PieceType.KNIGHT, PieceType.BISHOP, PieceType.ROOK, PieceType.QUEEN}
)


@dataclass(frozen=True, slots=True)
class PieceClaimEntity:
    """One physical piece plus its presentation state at ``at_position_id``.

    ``base_ref`` is the only physical identity.  The other fields are presentation context
    and never decide piece equivalence.
    """

    base_ref: BasePieceRef
    at_position_id: str
    current_square: str
    current_piece_type: PieceType

    def __post_init__(self) -> None:
        if not isinstance(self.base_ref, BasePieceRef):
            raise ExplanationClaimError("piece entity requires a BasePieceRef")
        if not self.at_position_id:
            raise ExplanationClaimError("piece entity at_position_id must not be empty")
        try:
            square_index(self.current_square)
        except ValueError as exc:
            raise ExplanationClaimError(f"piece entity {exc}") from exc
        base_type = self.base_ref.piece_type
        allowed = _PROMOTION_ROLES if base_type is PieceType.PAWN else {base_type}
        if self.current_piece_type not in allowed:
            raise ExplanationClaimError(
                f"{base_type.value} cannot be presented as {self.current_piece_type}"
            )


@dataclass(frozen=True, slots=True)
class SideClaimEntity:
    color: Color


ClaimEntity = MoveClaimEntity | PieceClaimEntity | SideClaimEntity


def base_frame_piece_entity(base_position_id: str, base_ref: BasePieceRef) -> PieceClaimEntity:
    """The frozen current-P8/P9 presentation frame: the piece as it stands in the base."""

    return PieceClaimEntity(
        base_ref=base_ref,
        at_position_id=base_position_id,
        current_square=base_ref.base_square,
        current_piece_type=base_ref.piece_type,
    )


# -- canonical ordering --


def base_piece_sort_key(ref: BasePieceRef) -> tuple[int, str, str]:
    """Same semantics as the deployed P8/P9 ``piece_identity._base_key``."""

    return (square_index(ref.base_square), ref.color.value, ref.piece_type.value)


def claim_entity_sort_key(entity: ClaimEntity) -> tuple[object, ...]:
    """Ordering key; the leading tags sort in the frozen Move < Piece < Side order."""

    if isinstance(entity, MoveClaimEntity):
        return ("move", entity.position_id, entity.move.uci)
    if isinstance(entity, PieceClaimEntity):
        return (
            "piece",
            base_piece_sort_key(entity.base_ref),
            entity.at_position_id,
            entity.current_square,
            entity.current_piece_type.value,
        )
    if isinstance(entity, SideClaimEntity):
        return ("side", entity.color.value)
    raise ExplanationClaimError(f"unsupported claim entity: {type(entity).__name__}")


def claim_entity_identity(entity: ClaimEntity) -> tuple[object, ...]:
    """Duplicate-detection identity: UCI for moves, ``BasePieceRef`` only for pieces."""

    if isinstance(entity, MoveClaimEntity):
        return ("move", entity.position_id, entity.move.uci)
    if isinstance(entity, PieceClaimEntity):
        return ("piece", entity.base_ref)
    if isinstance(entity, SideClaimEntity):
        return ("side", entity.color)
    raise ExplanationClaimError(f"unsupported claim entity: {type(entity).__name__}")


def _has_duplicate_entities(entities: tuple[ClaimEntity, ...]) -> bool:
    identities = [claim_entity_identity(entity) for entity in entities]
    return len(identities) != len(set(identities))


# -- claim --


@dataclass(frozen=True, slots=True)
class ExplanationClaim:
    """One closed-vocabulary proposition; ``FORCED`` policy belongs to the later validator."""

    claim_id: str
    base_position_id: str
    subject: ClaimEntity
    predicate: ClaimPredicate
    objects: tuple[ClaimEntity, ...]
    confidence: ClaimConfidence
    scope: ClaimScope
    evidence_ids: tuple[str, ...]
    importance: float | None = None

    def __post_init__(self) -> None:
        if not _is_ordinal_id(self.claim_id, "cl"):
            raise ExplanationClaimError("claim_id must be a canonical claim id")
        if not self.base_position_id:
            raise ExplanationClaimError("base_position_id must not be empty")
        if not isinstance(self.subject, MoveClaimEntity):
            raise ExplanationClaimError("claim subject must be a MoveClaimEntity")
        if self.subject.position_id != self.base_position_id:
            raise ExplanationClaimError("claim subject move must be legal from the claim base")
        if not isinstance(self.predicate, ClaimPredicate):
            raise ExplanationClaimError("claim predicate must be a ClaimPredicate")
        if not isinstance(self.confidence, ClaimConfidence):
            raise ExplanationClaimError("claim confidence must be a ClaimConfidence")
        if not isinstance(self.scope, ClaimScope):
            raise ExplanationClaimError("claim scope must be a ClaimScope")
        if _has_duplicate_entities(self.objects):
            raise ExplanationClaimError("claim objects must not contain duplicates")
        _require_evidence_ids(self.evidence_ids, "claim evidence_ids", ExplanationClaimError)
        required = required_claim_scope(self.predicate)
        if self.scope is not required:
            raise ExplanationClaimError(f"{self.predicate.value} requires {required.value} scope")
