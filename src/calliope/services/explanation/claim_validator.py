"""MVP-P10 ClaimValidator for P8-backed claims.

Independently reconciles every claim with the P10 evidence it references.  It reads only
P10 evidence-domain values: never raw P8 results, engine scores, or chess rules.
"""

from __future__ import annotations

from collections.abc import Iterable

from calliope.domain.analysis import (
    BadMoveCauseKind,
    MateEvidenceLevel,
    ProbeKind,
    ProbeResult,
)
from calliope.domain.chess import ChessMove
from calliope.domain.explanation import (
    BoardFactEvidence,
    ClaimConfidence,
    ClaimEntity,
    ClaimPredicate,
    ClaimScope,
    CounterfactualEvidence,
    EngineEvidence,
    EvidenceBundle,
    EvidenceForm,
    EvidenceGroup,
    EvidenceRecord,
    EvidenceSourceFamily,
    ExplanationClaim,
    MotifEvidence,
    MoveClaimEntity,
    PieceClaimEntity,
    SideClaimEntity,
    VariationEvidence,
    base_frame_piece_entity,
    claim_entity_sort_key,
)
from calliope.errors import ExplanationClaimError, IncompatibleClaimEvidenceError

_K = BadMoveCauseKind
_P = ClaimPredicate

P8_PREDICATES: dict[BadMoveCauseKind, ClaimPredicate] = {
    _K.NEWLY_HANGING_PIECE: _P.LEAVES_PIECE_HANGING,
    _K.REMOVED_DEFENDER: _P.REMOVES_DEFENDER,
    _K.FORK_ALLOWED: _P.ALLOWS_FORK,
    _K.MATE_ALLOWED: _P.ALLOWS_CHECKMATE,
    _K.MATERIAL_LOSS_LINE: _P.ALLOWS_MATERIAL_LOSS,
}
"""Frozen P8 cause -> predicate mapping (design §18); every P8 claim is LOCAL."""

_MATE_CONFIDENCE = {
    MateEvidenceLevel.EXACT_IMMEDIATE: ClaimConfidence.EXACT,
    MateEvidenceLevel.ENGINE_LINE: ClaimConfidence.ENGINE_VERIFIED,
}
_MATERIAL_BACKED = frozenset({_K.NEWLY_HANGING_PIECE, _K.REMOVED_DEFENDER, _K.MATERIAL_LOSS_LINE})


def _fail(message: str) -> IncompatibleClaimEvidenceError:
    return IncompatibleClaimEvidenceError(message)


def p8_confidence(group: EvidenceGroup) -> ClaimConfidence:
    """Confidence fixed by the source kind and retained mate level, never by a score."""

    if group.source_kind is _K.MATE_ALLOWED:
        confidence = _MATE_CONFIDENCE.get(group.mate_evidence_level)
        if confidence is None:
            raise _fail("MATE_ALLOWED group needs a supported mate_evidence_level")
        return confidence
    return ClaimConfidence.ENGINE_VERIFIED


def _move_key(move: MoveClaimEntity) -> tuple[str, str]:
    """Canonical move identity: legal-source position plus UCI; SAN is presentation."""

    return (move.position_id, move.move.uci)


def _object_key(entity: ClaimEntity) -> tuple[object, ...]:
    """Move by canonical identity; a piece by identity plus its exact presentation frame."""

    if isinstance(entity, MoveClaimEntity):
        return ("move", *_move_key(entity))
    if isinstance(entity, PieceClaimEntity):
        return ("piece", entity)
    if isinstance(entity, SideClaimEntity):
        return ("side", entity.color)
    raise _fail(f"unsupported claim entity: {type(entity).__name__}")


def _record_entities(record: EvidenceRecord) -> Iterable[ClaimEntity]:
    if isinstance(record, (BoardFactEvidence, MotifEvidence, VariationEvidence)):
        yield from record.moves
        yield from record.pieces
    if isinstance(record, BoardFactEvidence) and record.sole_response is not None:
        yield record.sole_response
    if isinstance(record, CounterfactualEvidence):
        for move in (record.comparator_move, record.tested_response):
            if move is not None:
                yield move


def _probe_uci(move: ChessMove | None) -> str | None:
    return None if move is None else move.uci


class ClaimValidator:
    """Rejects any P8 claim its referenced P10 evidence cannot justify."""

    def validate_bad_move(
        self, bundle: EvidenceBundle, claims: tuple[ExplanationClaim, ...]
    ) -> tuple[ExplanationClaim, ...]:
        if not isinstance(bundle, EvidenceBundle):
            raise ExplanationClaimError("validate_bad_move requires an EvidenceBundle")
        if not isinstance(claims, tuple) or any(
            not isinstance(claim, ExplanationClaim) for claim in claims
        ):
            raise ExplanationClaimError("claims must be a tuple of ExplanationClaim values")
        if len({claim.claim_id for claim in claims}) != len(claims):
            raise _fail("claim ids must be unique within one package")
        for group in bundle.groups:
            if group.source_family is not EvidenceSourceFamily.BAD_MOVE_CAUSE:
                raise _fail("P8 claim validation requires BAD_MOVE_CAUSE evidence groups")

        records = {record.evidence_id: record for record in bundle.evidence}
        owners = {
            evidence_id: group for group in bundle.groups for evidence_id in group.evidence_ids
        }
        for claim in claims:
            self._validate(bundle, records, owners, claim)
        return claims

    # -- per claim --

    def _validate(
        self,
        bundle: EvidenceBundle,
        records: dict[str, EvidenceRecord],
        owners: dict[str, EvidenceGroup],
        claim: ExplanationClaim,
    ) -> None:
        if claim.base_position_id != bundle.base_position_id:
            raise _fail(f"{claim.claim_id} belongs to another base position")
        unknown = [eid for eid in claim.evidence_ids if eid not in records or eid not in owners]
        if unknown:
            raise _fail(f"{claim.claim_id} references unowned evidence {unknown[0]}")
        groups = {id(owners[eid]) for eid in claim.evidence_ids}
        if len(groups) != 1:
            raise _fail(f"{claim.claim_id} references evidence from more than one group")
        group = owners[claim.evidence_ids[0]]
        owned = [records[eid] for eid in group.evidence_ids]
        referenced = [records[eid] for eid in claim.evidence_ids]

        self._validate_group(bundle, group, owned)
        self._validate_mapping(group, claim)
        self._validate_entities(bundle, group, claim, referenced)
        if claim.confidence is ClaimConfidence.EXACT:
            self._validate_exact_mate(group, claim, owned)
        else:
            self._validate_engine_verified(group, claim, owned, referenced)

    # -- group --

    def _validate_group(
        self, bundle: EvidenceBundle, group: EvidenceGroup, owned: list[EvidenceRecord]
    ) -> None:
        if group.source_family is not EvidenceSourceFamily.BAD_MOVE_CAUSE:
            raise _fail("P8 claims require a BAD_MOVE_CAUSE group")
        if not isinstance(group.source_kind, BadMoveCauseKind):
            raise _fail("P8 group source_kind must be a BadMoveCauseKind")
        if group.evidence_form is not EvidenceForm.DIRECT:
            raise _fail("P8 groups are always DIRECT")
        if group.comparator_move is None:
            raise _fail("P8 group requires its comparator move")
        if group.representative_alternatives or group.failed_alternatives:
            raise _fail("P8 groups carry no representative alternatives")
        if not group.required_probe_results:
            raise _fail("P8 group requires its upstream probe results")
        if group.played_move.position_id != bundle.base_position_id:
            raise _fail("P8 played move must be legal from the bundle base")
        if group.comparator_move.position_id != bundle.base_position_id:
            raise _fail("P8 comparator move must be legal from the bundle base")

        if group.source_kind is _K.MATE_ALLOWED:
            if group.mate_evidence_level not in _MATE_CONFIDENCE:
                raise _fail("MATE_ALLOWED group needs a supported mate_evidence_level")
        elif (
            group.mate_evidence_level is not None or group.replayed_pv_ends_in_checkmate is not None
        ):
            raise _fail("mate metadata is only valid on MATE_ALLOWED groups")

        self._validate_probe_protocol(bundle, group)

        counterfactuals = [r for r in owned if isinstance(r, CounterfactualEvidence)]
        if len(counterfactuals) != 1:
            raise _fail("P8 group must own exactly one CounterfactualEvidence")
        (counterfactual,) = counterfactuals
        if counterfactual.probe_results != group.required_probe_results:
            raise _fail("CounterfactualEvidence differs from required_probe_results")
        if counterfactual.form is not EvidenceForm.DIRECT:
            raise _fail("P8 CounterfactualEvidence must be DIRECT")
        if counterfactual.comparator_move is None or _move_key(
            counterfactual.comparator_move
        ) != _move_key(group.comparator_move):
            raise _fail("CounterfactualEvidence comparator differs from the group")
        if counterfactual.tested_response is not None:
            raise _fail("P8 CounterfactualEvidence has no tested response")
        if counterfactual.representative_alternatives or counterfactual.failed_alternatives:
            raise _fail("P8 CounterfactualEvidence carries no representative alternatives")

    @staticmethod
    def _validate_probe_protocol(bundle: EvidenceBundle, group: EvidenceGroup) -> None:
        """REFUTATION(B,M), REFUTATION(B,A)[, IGNORE_THREAT(B,A,P)] — repeated on purpose."""

        results: tuple[ProbeResult, ...] = group.required_probe_results
        if len(results) not in (2, 3):
            raise _fail("P8 provenance must contain two or three probe results")
        if any(result.probe.base.position_id != bundle.base_position_id for result in results):
            raise _fail("P8 probe belongs to another base position")
        expected = ((group.played_move, "actual"), (group.comparator_move, "comparator"))
        for result, (move, label) in zip(results[:2], expected, strict=True):
            probe = result.probe
            if (
                probe.kind is not ProbeKind.REFUTATION
                or _probe_uci(probe.intervention_move) != move.move.uci
                or probe.execution_move is not None
            ):
                raise _fail(f"P8 {label} probe must be an execution-free REFUTATION")
        if len(results) == 3:
            probe = results[2].probe
            if probe.kind is not ProbeKind.IGNORE_THREAT:
                raise _fail("P8 third probe must be the same-punishment IGNORE_THREAT")
            if group.response is None:
                raise _fail("P8 same-punishment probe requires the punishment response")
            if _probe_uci(probe.intervention_move) != group.comparator_move.move.uci:
                raise _fail("P8 same-punishment probe must intervene with the comparator")
            if _probe_uci(probe.execution_move) != group.response.move.uci:
                raise _fail("P8 same-punishment probe must execute the punishment")

    # -- mapping --

    @staticmethod
    def _validate_mapping(group: EvidenceGroup, claim: ExplanationClaim) -> None:
        if claim.confidence is ClaimConfidence.FORCED:
            raise _fail("FORCED claims are rejected unconditionally in MVP-P10")
        if claim.predicate is not P8_PREDICATES[group.source_kind]:
            raise _fail(f"{group.source_kind.value} cannot support {claim.predicate.value}")
        if claim.scope is not ClaimScope.LOCAL:
            raise _fail("P8 claims are LOCAL")
        if claim.confidence is not p8_confidence(group):
            raise _fail(f"{claim.predicate.value} confidence does not match its P8 evidence")

    # -- entities --

    @staticmethod
    def _validate_entities(
        bundle: EvidenceBundle,
        group: EvidenceGroup,
        claim: ExplanationClaim,
        referenced: list[EvidenceRecord],
    ) -> None:
        if not isinstance(claim.subject, MoveClaimEntity) or _move_key(claim.subject) != _move_key(
            group.played_move
        ):
            raise _fail("claim subject must be the group's played move")

        expected = [
            base_frame_piece_entity(bundle.base_position_id, base) for base in group.source_subject
        ]
        if group.response is not None:
            expected.append(group.response)
        expected.sort(key=claim_entity_sort_key)
        if [_object_key(o) for o in claim.objects] != [_object_key(o) for o in expected]:
            raise _fail("claim objects must be the source pieces plus punishment, in order")

        available = {_object_key(entity) for r in referenced for entity in _record_entities(r)}
        for entity in (claim.subject, *claim.objects):
            if _object_key(entity) not in available:
                raise _fail(f"{claim.claim_id} entity is absent from referenced evidence")

    # -- confidence-specific --

    @staticmethod
    def _validate_exact_mate(
        group: EvidenceGroup, claim: ExplanationClaim, owned: list[EvidenceRecord]
    ) -> None:
        if group.mate_evidence_level is not MateEvidenceLevel.EXACT_IMMEDIATE:
            raise _fail("EXACT P8 claims require exact-immediate mate evidence")
        if group.replayed_pv_ends_in_checkmate is not True:
            raise _fail("EXACT mate requires a replayed line ending in checkmate")
        actual_probe = group.required_probe_results[0].probe
        boards = [r for r in owned if isinstance(r, BoardFactEvidence)]
        actual = [r for r in owned if isinstance(r, VariationEvidence) and r.probe == actual_probe]
        if len(boards) != 1 or not boards[0].board_deltas:
            raise _fail("EXACT mate requires board-fact deltas")
        if len(actual) != 1:
            raise _fail("EXACT mate requires exactly one actual-line variation")
        if actual[0].replayed_pv_ends_in_checkmate is not True or not actual[0].board_deltas:
            raise _fail("EXACT mate requires the exact replayed checkmate variation")
        selected = tuple(
            r.evidence_id
            for r in owned
            if isinstance(r, (BoardFactEvidence, MotifEvidence)) or r is actual[0]
        )
        if claim.evidence_ids != selected:
            raise _fail("EXACT mate evidence must be board fact, motif and actual variation")

    @staticmethod
    def _validate_engine_verified(
        group: EvidenceGroup,
        claim: ExplanationClaim,
        owned: list[EvidenceRecord],
        referenced: list[EvidenceRecord],
    ) -> None:
        if claim.evidence_ids != group.evidence_ids:
            raise _fail("ENGINE_VERIFIED P8 claims reference the complete group evidence")
        if [type(r) for r in owned].count(BoardFactEvidence) != 1:
            raise _fail("ENGINE_VERIFIED P8 claim requires one BoardFactEvidence")

        non_terminal = [r for r in group.required_probe_results if r.engine_analysis is not None]
        engines = [r for r in referenced if isinstance(r, EngineEvidence)]
        for result in non_terminal:
            if sum(1 for e in engines if e.probe_result == result) != 1:
                raise _fail("each non-terminal probe needs exactly one EngineEvidence")
        if len(engines) != len(non_terminal):
            raise _fail("EngineEvidence must correspond only to non-terminal required probes")

        analyses = [result.engine_analysis for result in non_terminal]
        if any(a.engine != analyses[0].engine for a in analyses):
            raise _fail("ENGINE_VERIFIED claim mixes engine identities")
        if any(a.settings != analyses[0].settings for a in analyses):
            raise _fail("ENGINE_VERIFIED claim mixes engine settings")

        variations = [r for r in referenced if isinstance(r, VariationEvidence)]
        if not variations:
            raise _fail("ENGINE_VERIFIED P8 claim requires replay provenance")
        if group.source_kind in _MATERIAL_BACKED and not any(
            v.material_evidence for v in variations
        ):
            raise _fail(f"{claim.predicate.value} requires material replay provenance")
