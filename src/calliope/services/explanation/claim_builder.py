"""MVP-P10 ClaimBuilder for P8 and P9 evidence groups.

Builds closed-vocabulary claims from a validated ``EvidenceBundle`` only; it never re-reads
raw P8/P9 results, scores, or chess rules.  Every built tuple passes ``ClaimValidator`` before
it is returned.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.domain.analysis import BasePieceRef
from calliope.domain.explanation import (
    BoardFactEvidence,
    ClaimConfidence,
    ClaimEntity,
    ClaimPredicate,
    ClaimScope,
    EvidenceBundle,
    EvidenceForm,
    EvidenceGroup,
    EvidenceRecord,
    EvidenceSourceFamily,
    ExplanationClaim,
    MotifEvidence,
    MoveClaimEntity,
    PieceClaimEntity,
    VariationEvidence,
    claim_entity_sort_key,
    mint_claim_id,
)
from calliope.errors import ExplanationClaimError, IncompatibleClaimEvidenceError
from calliope.services.explanation.claim_validator import (
    P8_PREDICATES,
    ClaimValidator,
    _p9_mapping,
    p8_confidence,
)

_PREDICATE_ORDER = {predicate: index for index, predicate in enumerate(ClaimPredicate)}


def _fail(message: str) -> IncompatibleClaimEvidenceError:
    return IncompatibleClaimEvidenceError(message)


@dataclass(frozen=True, slots=True)
class _Draft:
    subject: ClaimEntity
    predicate: ClaimPredicate
    objects: tuple[ClaimEntity, ...]
    confidence: ClaimConfidence
    evidence_ids: tuple[str, ...]

    @property
    def order_key(self) -> tuple[int, tuple[tuple[object, ...], ...]]:
        return (
            _PREDICATE_ORDER[self.predicate],
            tuple(claim_entity_sort_key(entity) for entity in self.objects),
        )


class ClaimBuilder:
    """One validated claim per supported P8 or P9 evidence group."""

    def __init__(self) -> None:
        self._validator = ClaimValidator()

    def build_good_move(self, bundle: EvidenceBundle) -> tuple[ExplanationClaim, ...]:
        """Build one independently validated claim per P9 evidence group."""

        if not isinstance(bundle, EvidenceBundle):
            raise ExplanationClaimError("build_good_move requires an EvidenceBundle")
        records = {record.evidence_id: record for record in bundle.evidence}
        drafts = []
        for group in bundle.groups:
            if group.source_family is not EvidenceSourceFamily.GOOD_MOVE_BENEFIT:
                raise _fail("P9 claim building requires GOOD_MOVE_BENEFIT groups")
            predicate, confidence, scope = _p9_mapping(group)
            owned = [records[eid] for eid in group.evidence_ids]
            objects: list[ClaimEntity] = [
                self._source_piece(bundle, owned, ref) for ref in group.source_subject
            ]
            if group.response is not None:
                objects.append(group.response)
            if group.evidence_form is EvidenceForm.PRESERVATION:
                objects.extend(
                    self._failed_move(bundle, owned, a.move.uci) for a in group.failed_alternatives
                )
            objects.sort(key=claim_entity_sort_key)
            if confidence is ClaimConfidence.EXACT:
                evidence_ids = tuple(
                    r.evidence_id
                    for r in owned
                    if isinstance(r, (BoardFactEvidence, MotifEvidence))
                    or (
                        predicate is ClaimPredicate.DELIVERS_CHECKMATE
                        and isinstance(r, VariationEvidence)
                        and r.probe == group.required_probe_results[0].probe
                    )
                )
            else:
                evidence_ids = group.evidence_ids
            drafts.append(
                (
                    _Draft(group.played_move, predicate, tuple(objects), confidence, evidence_ids),
                    scope,
                )
            )
        drafts.sort(key=lambda item: item[0].order_key)
        claims = tuple(
            ExplanationClaim(
                claim_id=mint_claim_id(i),
                base_position_id=bundle.base_position_id,
                subject=draft.subject,
                predicate=draft.predicate,
                objects=draft.objects,
                confidence=draft.confidence,
                scope=scope,
                evidence_ids=draft.evidence_ids,
                importance=None,
            )
            for i, (draft, scope) in enumerate(drafts, start=1)
        )
        return self._validator.validate_good_move(bundle, claims)

    @staticmethod
    def _failed_move(
        bundle: EvidenceBundle, owned: list[EvidenceRecord], uci: str
    ) -> MoveClaimEntity:
        """Use the retained base-position move; never fill an absent alternative entity."""
        found = [
            move
            for record in owned
            if isinstance(record, (BoardFactEvidence, MotifEvidence, VariationEvidence))
            for move in record.moves
            if move.position_id == bundle.base_position_id and move.move.uci == uci
        ]
        if not found:
            raise _fail("failed alternative move is absent from retained evidence")
        return found[0]

    def build_bad_move(self, bundle: EvidenceBundle) -> tuple[ExplanationClaim, ...]:
        if not isinstance(bundle, EvidenceBundle):
            raise ExplanationClaimError("build_bad_move requires an EvidenceBundle")
        records = {record.evidence_id: record for record in bundle.evidence}
        drafts = [self._draft(bundle, group, records) for group in bundle.groups]
        drafts.sort(key=lambda draft: draft.order_key)
        claims = tuple(
            ExplanationClaim(
                claim_id=mint_claim_id(index),
                base_position_id=bundle.base_position_id,
                subject=draft.subject,
                predicate=draft.predicate,
                objects=draft.objects,
                confidence=draft.confidence,
                scope=ClaimScope.LOCAL,
                evidence_ids=draft.evidence_ids,
                importance=None,
            )
            for index, draft in enumerate(drafts, start=1)
        )
        return self._validator.validate_bad_move(bundle, claims)

    def _draft(
        self, bundle: EvidenceBundle, group: EvidenceGroup, records: dict[str, EvidenceRecord]
    ) -> _Draft:
        if group.source_family is not EvidenceSourceFamily.BAD_MOVE_CAUSE:
            raise _fail("P8 claim building requires BAD_MOVE_CAUSE evidence groups")
        owned = [records[evidence_id] for evidence_id in group.evidence_ids]
        confidence = p8_confidence(group)

        objects: list[ClaimEntity] = [
            self._source_piece(bundle, owned, base) for base in group.source_subject
        ]
        if group.response is not None:
            objects.append(group.response)
        objects.sort(key=claim_entity_sort_key)

        if confidence is ClaimConfidence.EXACT:
            actual_probe = group.required_probe_results[0].probe
            evidence_ids = tuple(
                record.evidence_id
                for record in owned
                if isinstance(record, (BoardFactEvidence, MotifEvidence))
                or (
                    isinstance(record, VariationEvidence)
                    and record.probe == actual_probe
                    and record.replayed_pv_ends_in_checkmate is True
                )
            )
        else:
            evidence_ids = group.evidence_ids

        return _Draft(
            subject=group.played_move,
            predicate=P8_PREDICATES[group.source_kind],
            objects=tuple(objects),
            confidence=confidence,
            evidence_ids=evidence_ids,
        )

    @staticmethod
    def _source_piece(
        bundle: EvidenceBundle, owned: list[EvidenceRecord], base: BasePieceRef
    ) -> PieceClaimEntity:
        """The single retained base-frame entity for one source piece; never reconstructed."""

        found = {
            piece
            for record in owned
            if isinstance(record, (BoardFactEvidence, MotifEvidence, VariationEvidence))
            for piece in record.pieces
            if piece.base_ref == base
        }
        if len(found) != 1:
            raise _fail(f"source piece {base} has {len(found)} retained presentations, not 1")
        (piece,) = found
        if (
            piece.at_position_id != bundle.base_position_id
            or piece.current_square != base.base_square
            or piece.current_piece_type is not base.piece_type
        ):
            raise _fail(f"source piece {base} is not in the current P8 base frame")
        return piece
