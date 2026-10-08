"""Schema-0.2 public projection of validated P10 claims and P12 commentary.

Copy/serialize only: enum ``.value``, canonical UCI, position ids and exact tuples, dispatched by
exact internal type.  No board access, no SAN, no reordering, no claim selection.
"""

from __future__ import annotations

from calliope.contracts import (
    ClaimEntityView,
    ClaimView,
    CommentaryView,
    MoveClaimEntityView,
    PieceClaimEntityView,
    SideClaimEntityView,
)
from calliope.domain.chess import Color, PieceType
from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    ExplanationClaim,
    MoveClaimEntity,
    PieceClaimEntity,
    RenderedCommentary,
    SideClaimEntity,
)
from calliope.errors import ClaimProjectionError


def _value(member: object, enum: type) -> str:
    if type(member) is not enum:
        raise ClaimProjectionError(f"expected an exact {enum.__name__} member")
    return member.value  # type: ignore[attr-defined]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ClaimProjectionError(f"{label} must be a non-empty string")
    return value


def _str_tuple(values: object, label: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or any(not isinstance(v, str) for v in values):
        raise ClaimProjectionError(f"{label} must be a tuple of strings")
    return values


def project_move(entity: MoveClaimEntity) -> MoveClaimEntityView:
    if type(entity) is not MoveClaimEntity:
        raise ClaimProjectionError(f"expected a MoveClaimEntity, got {type(entity).__name__}")
    return MoveClaimEntityView(
        move_uci=_text(entity.move.uci, "move uci"),
        position_id=_text(entity.position_id, "move position_id"),
    )


def project_entity(entity: object) -> ClaimEntityView:
    """Exact-type dispatch; an unknown entity fails closed rather than falling back to repr."""

    if type(entity) is MoveClaimEntity:
        return project_move(entity)
    if type(entity) is PieceClaimEntity:
        ref = entity.base_ref
        return PieceClaimEntityView(
            color=_value(ref.color, Color),
            base_piece_type=_value(ref.piece_type, PieceType),
            base_square=_text(ref.base_square, "piece base_square"),
            at_position_id=_text(entity.at_position_id, "piece at_position_id"),
            current_piece_type=_value(entity.current_piece_type, PieceType),
            current_square=_text(entity.current_square, "piece current_square"),
        )
    if type(entity) is SideClaimEntity:
        return SideClaimEntityView(color=_value(entity.color, Color))
    raise ClaimProjectionError(f"unsupported claim entity {type(entity).__name__}")


def project_claim(claim: ExplanationClaim) -> ClaimView:
    if type(claim) is not ExplanationClaim:
        raise ClaimProjectionError("public projection requires an ExplanationClaim")
    if not isinstance(claim.objects, tuple):
        raise ClaimProjectionError("claim objects must be a tuple")
    if claim.importance is not None and type(claim.importance) is not float:
        raise ClaimProjectionError("claim importance must be a float or None")
    return ClaimView(
        claim_id=_text(claim.claim_id, "claim_id"),
        base_position_id=_text(claim.base_position_id, "claim base_position_id"),
        confidence=_value(claim.confidence, ClaimConfidence),
        scope=_value(claim.scope, ClaimScope),
        subject=project_move(claim.subject),
        predicate=_value(claim.predicate, ClaimPredicate),
        objects=tuple(project_entity(entity) for entity in claim.objects),
        evidence_ids=_str_tuple(claim.evidence_ids, "claim evidence_ids"),
        importance=claim.importance,
    )


def project_claims(claims: tuple[ExplanationClaim, ...]) -> tuple[ClaimView, ...]:
    if not isinstance(claims, tuple):
        raise ClaimProjectionError("claims must be a tuple")
    return tuple(project_claim(claim) for claim in claims)


def project_selected_ids(
    claims: tuple[ClaimView, ...], selected_claim_ids: tuple[str, ...]
) -> tuple[str, ...]:
    ids = [claim.claim_id for claim in claims]
    selected = _str_tuple(selected_claim_ids, "selected_claim_ids")
    if any(ids.count(claim_id) != 1 for claim_id in selected):
        raise ClaimProjectionError("every selected claim id must resolve exactly once")
    return selected


def project_commentary(rendered: RenderedCommentary) -> CommentaryView:
    if type(rendered) is not RenderedCommentary:
        raise ClaimProjectionError("commentary projection requires a RenderedCommentary")
    return CommentaryView(
        text=rendered.text,
        sentences=_str_tuple(rendered.sentences, "commentary sentences"),
        used_claim_ids=_str_tuple(rendered.used_claim_ids, "commentary used_claim_ids"),
    )
