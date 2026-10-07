"""MVP-P10 ClaimValidator for P8 and P9 claims.

Independently reconciles every claim with the P10 evidence it references.  It reads only
P10 evidence-domain values: never raw P8 results, engine scores, or chess rules.
"""

from __future__ import annotations

from collections.abc import Iterable

from calliope.domain.analysis import (
    BadMoveCauseKind,
    GoodMoveBenefitKind,
    MateEvidenceLevel,
    ProbeKind,
    ProbeResult,
    TacticalCandidate,
    TacticalCandidateKind,
    TerminalKind,
)
from calliope.domain.chess import ChessMove, PieceType
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
    evidence_record_type_rank,
    mint_claim_id,
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


def _validate_claim_values(claims: tuple[ExplanationClaim, ...]) -> None:
    """Re-check claim field types a tampered value could bypass; P10 never sets importance."""

    for claim in claims:
        if (
            type(claim.predicate) is not ClaimPredicate
            or type(claim.confidence) is not ClaimConfidence
            or type(claim.scope) is not ClaimScope
        ):
            raise _fail("claim predicate/confidence/scope must be closed-vocabulary enum members")
        if not isinstance(claim.objects, tuple) or not isinstance(claim.evidence_ids, tuple):
            raise _fail("claim objects and evidence_ids must be tuples")
        if claim.importance is not None:
            raise _fail("P10 claims carry no importance; selection belongs to P11")


def _validate_canonical_bundle(bundle: EvidenceBundle) -> None:
    """Frozen within-group evidence order (design §23.2).

    Group tuple order stays caller order: claim order is canonicalised independently of it.
    """

    records = {record.evidence_id: record for record in bundle.evidence}
    for group in bundle.groups:
        owned = [records[eid] for eid in group.evidence_ids]
        ranks = [evidence_record_type_rank(r) for r in owned]
        results = group.required_probe_results
        engines = [results.index(r.probe_result) for r in owned if isinstance(r, EngineEvidence)]
        variations = [
            next(i for i, result in enumerate(results) if result.probe == r.probe)
            for r in owned
            if isinstance(r, VariationEvidence)
        ]
        if ranks != sorted(ranks) or engines != sorted(engines) or variations != sorted(variations):
            raise _fail("group evidence must follow canonical type and retained probe order")


def _require_king_subject(group: EvidenceGroup, *, mover: bool) -> None:
    """Every mate source is about exactly one king, so a material group cannot be relabelled."""

    side = group.required_probe_results[0].probe.base.side_to_move
    if (
        len(group.source_subject) != 1
        or group.source_subject[0].piece_type is not PieceType.KING
        or (group.source_subject[0].color is side) is not mover
    ):
        owner = "mover" if mover else "opponent"
        raise _fail(f"{group.source_kind.value} subject must be the {owner} king only")


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


def _p9_mapping(group: EvidenceGroup) -> tuple[ClaimPredicate, ClaimConfidence, ClaimScope]:
    """Frozen P9 mappings; the validator separately checks the underlying provenance."""

    kind = group.source_kind
    form = group.evidence_form
    if kind in (GoodMoveBenefitKind.PREVENTS_MATE, GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS):
        if form is not EvidenceForm.PRESERVATION:
            raise _fail("preservation benefits require PRESERVATION form")
        predicate = (
            _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE
            if kind is GoodMoveBenefitKind.PREVENTS_MATE
            else _P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS
        )
        return predicate, ClaimConfidence.ENGINE_VERIFIED, ClaimScope.REPRESENTATIVE_ALTERNATIVES
    if not isinstance(kind, GoodMoveBenefitKind) or form not in (
        EvidenceForm.DIRECT,
        EvidenceForm.TESTED_RESPONSE,
    ):
        raise _fail("I3 requires a P9 STRONG benefit and DIRECT or TESTED_RESPONSE form")
    if kind is GoodMoveBenefitKind.FORCES_RESPONSE and form is EvidenceForm.DIRECT:
        return _P.FORCES_RESPONSE, ClaimConfidence.EXACT, ClaimScope.LOCAL
    if kind is GoodMoveBenefitKind.MATE_THREAT:
        if (
            group.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
            and form is EvidenceForm.DIRECT
        ):
            return _P.DELIVERS_CHECKMATE, ClaimConfidence.EXACT, ClaimScope.LOCAL
        if group.mate_evidence_level is MateEvidenceLevel.ENGINE_LINE:
            predicate = (
                _P.LEADS_TO_MATE if form is EvidenceForm.DIRECT else _P.THREATENS_MATE_IF_IGNORED
            )
            scope = ClaimScope.LOCAL if form is EvidenceForm.DIRECT else ClaimScope.TESTED_RESPONSE
            return predicate, ClaimConfidence.ENGINE_VERIFIED, scope
    if kind is GoodMoveBenefitKind.MATERIAL_THREAT:
        predicate = (
            _P.WINS_MATERIAL if form is EvidenceForm.DIRECT else _P.THREATENS_MATERIAL_IF_IGNORED
        )
        scope = ClaimScope.LOCAL if form is EvidenceForm.DIRECT else ClaimScope.TESTED_RESPONSE
        return predicate, ClaimConfidence.ENGINE_VERIFIED, scope
    raise _fail("unsupported P9 STRONG kind, form or mate level")


class ClaimValidator:
    """Rejects claims that the owned and referenced P10 evidence cannot justify."""

    def validate_good_move(
        self, bundle: EvidenceBundle, claims: tuple[ExplanationClaim, ...]
    ) -> tuple[ExplanationClaim, ...]:
        """Independently validate a complete STRONG or preservation claim package."""

        if not isinstance(bundle, EvidenceBundle):
            raise ExplanationClaimError("validate_good_move requires an EvidenceBundle")
        if not isinstance(claims, tuple) or any(
            not isinstance(c, ExplanationClaim) for c in claims
        ):
            raise ExplanationClaimError("claims must be a tuple of ExplanationClaim values")
        _validate_claim_values(claims)
        if len({c.claim_id for c in claims}) != len(claims):
            raise _fail("claim ids must be unique within one package")
        if len(claims) != len(bundle.groups):
            raise _fail("package requires exactly one claim per evidence group")
        records = {r.evidence_id: r for r in bundle.evidence}
        if len(records) != len(bundle.evidence):
            raise _fail("evidence ids must be unique")
        owners = {}
        for group in bundle.groups:
            if group.source_family is not EvidenceSourceFamily.GOOD_MOVE_BENEFIT:
                raise _fail("P9 validation requires GOOD_MOVE_BENEFIT groups")
            for eid in group.evidence_ids:
                if eid not in records or eid in owners:
                    raise _fail("evidence must resolve to exactly one owning group")
                owners[eid] = group
        if set(records) != set(owners):
            raise _fail("all package evidence must be group-owned")
        modes = {
            group.source_kind
            in (GoodMoveBenefitKind.PREVENTS_MATE, GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS)
            for group in bundle.groups
        }
        if len(modes) > 1:
            raise _fail("one P9 package cannot mix STRONG and preservation groups")
        resolved = []
        for claim in claims:
            if claim.base_position_id != bundle.base_position_id:
                raise _fail("claim belongs to another base position")
            if not claim.evidence_ids or any(eid not in owners for eid in claim.evidence_ids):
                raise _fail("claim references unknown or unowned evidence")
            groups = {id(owners[eid]) for eid in claim.evidence_ids}
            if len(groups) != 1:
                raise _fail("claim references evidence from more than one group")
            group = owners[claim.evidence_ids[0]]
            owned = [records[eid] for eid in group.evidence_ids]
            referenced = [records[eid] for eid in claim.evidence_ids]
            preservation = group.source_kind in (
                GoodMoveBenefitKind.PREVENTS_MATE,
                GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS,
            )
            if preservation:
                self._validate_preservation_group(bundle, group, owned)
            else:
                causal = self._validate_good_group(bundle, group, owned)
            if claim.confidence is ClaimConfidence.FORCED:
                raise _fail("FORCED claims are rejected unconditionally in MVP-P10")
            if (claim.predicate, claim.confidence, claim.scope) != _p9_mapping(group):
                raise _fail("claim predicate/confidence/scope differs from P9 STRONG mapping")
            if preservation:
                self._validate_preservation_entities(bundle, group, claim, owned, referenced)
                self._validate_preservation_engine(group, claim, owned)
            else:
                self._validate_good_entities(bundle, group, claim, owned, referenced)
                if claim.confidence is ClaimConfidence.EXACT:
                    self._validate_good_exact(group, claim, owned, causal)
                else:
                    self._validate_good_engine(group, claim, owned, causal)
            resolved.append(group)
        if len({id(group) for group in resolved}) != len(bundle.groups):
            raise _fail("package requires exactly one claim per evidence group")
        predicate_order = {p: i for i, p in enumerate(ClaimPredicate)}
        keys = [
            (predicate_order[c.predicate], tuple(claim_entity_sort_key(o) for o in c.objects))
            for c in claims
        ]
        if keys != sorted(keys):
            raise _fail("claims must be in canonical predicate and object order")
        if any(c.claim_id != mint_claim_id(i) for i, c in enumerate(claims, start=1)):
            raise _fail("claim ids must match canonical tuple positions")
        _validate_canonical_bundle(bundle)
        return claims

    def _validate_preservation_group(
        self, bundle: EvidenceBundle, group: EvidenceGroup, owned: list[EvidenceRecord]
    ) -> None:
        if (
            not isinstance(group.source_kind, GoodMoveBenefitKind)
            or group.evidence_form is not EvidenceForm.PRESERVATION
            or group.comparator_move is not None
            or group.response is not None
        ):
            raise _fail("preservation requires PRESERVATION form without comparator or response")
        if group.played_move.position_id != bundle.base_position_id or any(
            r.base_position_id != bundle.base_position_id for r in owned
        ):
            raise _fail("preservation evidence belongs to another base position")
        self._validate_preservation_protocol(bundle, group)
        counterfactuals = [r for r in owned if isinstance(r, CounterfactualEvidence)]
        if len(counterfactuals) != 1 or owned[-1] is not counterfactuals[0]:
            raise _fail("preservation requires exactly one final CounterfactualEvidence")
        (cf,) = counterfactuals
        if (
            cf.form is not EvidenceForm.PRESERVATION
            or cf.probe_results != group.required_probe_results
            or cf.comparator_move is not None
            or cf.tested_response is not None
            or cf.representative_alternatives != group.representative_alternatives
            or cf.failed_alternatives != group.failed_alternatives
            or cf.equivalent_alternative_benefit
            is not (len(group.failed_alternatives) < len(group.representative_alternatives))
        ):
            raise _fail(
                "CounterfactualEvidence differs from complete preservation provenance/equivalence"
            )
        ranks = [evidence_record_type_rank(r) for r in owned]
        boards = [r for r in owned if isinstance(r, BoardFactEvidence)]
        motifs = [r for r in owned if isinstance(r, MotifEvidence)]
        if (
            ranks != sorted(ranks)
            or len(boards) != 1
            or len(motifs) > 1
            or any(
                not m.candidates
                or m.moves
                or any(not isinstance(c, TacticalCandidate) for c in m.candidates)
                for m in motifs
            )
        ):
            raise _fail(
                "preservation requires canonical evidence order, one board and aggregate typed motifs"
            )
        (board,) = boards
        expected_moves = (
            group.played_move,
            *(
                MoveClaimEntity(a.move, bundle.base_position_id)
                for a in group.representative_alternatives
            ),
        )
        if (
            board.sole_response is not None
            or board.terminal is not None
            or [_move_key(m) for m in board.moves] != [_move_key(m) for m in expected_moves]
        ):
            raise _fail(
                "preservation board must retain played/representative moves without response/terminal"
            )
        for record in owned:
            if isinstance(record, (BoardFactEvidence, MotifEvidence, VariationEvidence)) and any(
                piece != base_frame_piece_entity(bundle.base_position_id, piece.base_ref)
                for piece in record.pieces
            ):
                raise _fail("preservation pieces must retain their exact base-frame presentation")
        self._validate_group_evidence(group, owned)
        variations = [r for r in owned if isinstance(r, VariationEvidence)]
        for variation in variations:
            index = next(
                i for i, r in enumerate(group.required_probe_results) if r.probe == variation.probe
            )
            if (
                variation.board_deltas
                or variation.replayed_pv_ends_in_checkmate is not None
                or not variation.material_evidence
                or variation.terminal != group.required_probe_results[index].terminal
                or [_move_key(m) for m in variation.moves] != [_move_key(expected_moves[index])]
            ):
                raise _fail(
                    "preservation variation needs concrete probe-bound material without aggregate deltas/flags"
                )
        if group.source_kind is GoodMoveBenefitKind.PREVENTS_MATE:
            if group.mate_evidence_level not in _MATE_CONFIDENCE or not isinstance(
                group.replayed_pv_ends_in_checkmate, bool
            ):
                raise _fail(
                    "PREVENTS_MATE requires mate level and boolean aggregate replay metadata"
                )
            if group.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE and (
                group.replayed_pv_ends_in_checkmate is not True or not board.board_deltas
            ):
                raise _fail(
                    "exact-immediate preservation requires aggregate deltas and replay flag True"
                )
            _require_king_subject(group, mover=True)
        else:
            if (
                group.mate_evidence_level is not None
                or group.replayed_pv_ends_in_checkmate is not None
                or not board.board_deltas
            ):
                raise _fail("material preservation requires aggregate deltas without mate metadata")
            for result in group.required_probe_results:
                matches = [v for v in variations if v.probe == result.probe]
                if len(matches) != 1 or len(matches[0].material_evidence) != 1:
                    raise _fail(
                        "material preservation needs exactly one material-backed variation per probe"
                    )

    @staticmethod
    def _validate_preservation_protocol(bundle: EvidenceBundle, group: EvidenceGroup) -> None:
        keys = [
            (alternative.rank, alternative.move.uci)
            for alternative in group.representative_alternatives
        ]
        ranks = [key[0] for key in keys]
        ucis = [key[1] for key in keys]
        if (
            len(keys) not in (1, 2)
            or ranks != sorted(set(ranks))
            or len(ucis) != len(set(ucis))
            or group.played_move.move.uci in ucis
        ):
            raise _fail(
                "preservation requires one or two distinct representative alternatives in rank order"
            )
        failed = [
            (alternative.rank, alternative.move.uci) for alternative in group.failed_alternatives
        ]
        if (
            not failed
            or failed != [key for key in keys if key in failed]
            or len({key[0] for key in failed}) != len(failed)
            or len({key[1] for key in failed}) != len(failed)
        ):
            raise _fail(
                "failed alternatives must be a nonempty exact representative subset in rank order"
            )
        results = group.required_probe_results
        if len(results) != 1 + len(keys):
            raise _fail("preservation requires exactly complete Batch A")
        for result, move in zip(
            results,
            (group.played_move.move, *(a.move for a in group.representative_alternatives)),
            strict=True,
        ):
            if (
                result.probe.base.position_id != bundle.base_position_id
                or result.probe.kind is not ProbeKind.REFUTATION
                or _probe_uci(result.probe.intervention_move) != move.uci
                or result.probe.execution_move is not None
            ):
                raise _fail(
                    "preservation requires ordered execution-free Batch-A REFUTATION probes"
                )

    @staticmethod
    def _validate_preservation_entities(
        bundle: EvidenceBundle,
        group: EvidenceGroup,
        claim: ExplanationClaim,
        owned: list[EvidenceRecord],
        referenced: list[EvidenceRecord],
    ) -> None:
        if not isinstance(claim.subject, MoveClaimEntity) or _move_key(claim.subject) != _move_key(
            group.played_move
        ):
            raise _fail("claim subject must be the group's played move")
        expected: list[ClaimEntity] = []
        for base in group.source_subject:
            piece = base_frame_piece_entity(bundle.base_position_id, base)
            found = {
                entity
                for record in owned
                for entity in _record_entities(record)
                if isinstance(entity, PieceClaimEntity) and entity.base_ref == base
            }
            if found != {piece}:
                raise _fail("source piece needs exactly one retained base-frame presentation")
            expected.append(piece)
        expected.extend(
            MoveClaimEntity(a.move, bundle.base_position_id) for a in group.failed_alternatives
        )
        expected.sort(key=claim_entity_sort_key)
        if [_object_key(o) for o in claim.objects] != [_object_key(o) for o in expected]:
            raise _fail(
                "preservation objects must be source pieces and exactly the failed alternative moves"
            )
        available = {_object_key(entity) for r in referenced for entity in _record_entities(r)}
        if any(_object_key(entity) not in available for entity in (claim.subject, *claim.objects)):
            raise _fail("preservation subject/object is absent from referenced evidence")

    @staticmethod
    def _validate_preservation_engine(
        group: EvidenceGroup, claim: ExplanationClaim, owned: list[EvidenceRecord]
    ) -> None:
        if claim.evidence_ids != group.evidence_ids:
            raise _fail("preservation claims must reference complete group evidence")
        engines = [r for r in owned if isinstance(r, EngineEvidence)]
        analyses = []
        for result in group.required_probe_results:
            if result.engine_analysis is not None:
                if sum(e.probe_result == result for e in engines) != 1:
                    raise _fail("each non-terminal probe needs exactly one EngineEvidence")
                analyses.append(result.engine_analysis)
        if any(a.engine != analyses[0].engine for a in analyses):
            raise _fail("preservation claim mixes engine identities")
        if any(a.settings != analyses[0].settings for a in analyses):
            raise _fail("preservation claim mixes engine settings")

    def _validate_good_group(
        self, bundle: EvidenceBundle, group: EvidenceGroup, owned: list[EvidenceRecord]
    ) -> int:
        if not isinstance(group.source_kind, GoodMoveBenefitKind) or group.source_kind not in (
            GoodMoveBenefitKind.FORCES_RESPONSE,
            GoodMoveBenefitKind.MATE_THREAT,
            GoodMoveBenefitKind.MATERIAL_THREAT,
        ):
            raise _fail("I3 requires a supported STRONG benefit kind")
        if group.comparator_move is not None or group.failed_alternatives:
            raise _fail("P9 STRONG has no singular comparator or failed alternatives")
        if group.played_move.position_id != bundle.base_position_id or any(
            r.base_position_id != bundle.base_position_id for r in owned
        ):
            raise _fail("P9 evidence belongs to another base position")
        if group.source_kind is GoodMoveBenefitKind.MATE_THREAT:
            if group.mate_evidence_level not in _MATE_CONFIDENCE or (
                group.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
                and group.evidence_form is not EvidenceForm.DIRECT
            ):
                raise _fail("MATE_THREAT needs a supported level; exact immediate is DIRECT only")
            if not isinstance(group.replayed_pv_ends_in_checkmate, bool):
                raise _fail("MATE_THREAT requires its boolean replayed-mate flag")
        elif (
            group.mate_evidence_level is not None or group.replayed_pv_ends_in_checkmate is not None
        ):
            raise _fail("mate metadata is only valid on MATE_THREAT")
        causal = self._validate_good_protocol(bundle, group)
        if group.source_kind is GoodMoveBenefitKind.MATE_THREAT:
            _require_king_subject(group, mover=False)
        counterfactuals = [r for r in owned if isinstance(r, CounterfactualEvidence)]
        if len(counterfactuals) != 1 or owned[-1] is not counterfactuals[0]:
            raise _fail("P9 group requires one final CounterfactualEvidence")
        (counterfactual,) = counterfactuals
        if (
            counterfactual.probe_results != group.required_probe_results
            or counterfactual.form is not group.evidence_form
            or counterfactual.comparator_move is not None
            or counterfactual.representative_alternatives != group.representative_alternatives
            or counterfactual.failed_alternatives
            or counterfactual.equivalent_alternative_benefit is not False
        ):
            raise _fail("CounterfactualEvidence differs from complete P9 STRONG provenance")
        if group.evidence_form is EvidenceForm.DIRECT:
            if counterfactual.tested_response is not None:
                raise _fail("DIRECT CounterfactualEvidence has no tested response")
        elif counterfactual.tested_response is None or _move_key(
            counterfactual.tested_response
        ) != _move_key(group.response):
            raise _fail("CounterfactualEvidence must retain the exact tested response")
        ranks = [evidence_record_type_rank(r) for r in owned]
        if ranks != sorted(ranks):
            raise _fail("P9 evidence must retain canonical type order")
        boards = [r for r in owned if isinstance(r, BoardFactEvidence)]
        motifs = [r for r in owned if isinstance(r, MotifEvidence)]
        if len(boards) != 1 or len(motifs) > 1 or any(not r.candidates for r in motifs):
            raise _fail("P9 group requires one BoardFactEvidence and at most one nonempty motif")
        self._validate_group_evidence(group, owned)
        expected_moves = [
            group.played_move,
            *(
                MoveClaimEntity(a.move, bundle.base_position_id)
                for a in group.representative_alternatives
            ),
        ]
        if group.response is not None:
            expected_moves.append(group.response)
        if [_move_key(m) for m in boards[0].moves] != [_move_key(m) for m in expected_moves]:
            raise _fail("BoardFact moves must retain played, alternatives and sole reply/tested Q")
        exact_mate = group.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
        if not exact_mate and boards[0].terminal is not None:
            raise _fail("only exact immediate mate retains a BoardFact terminal")
        if (
            group.source_kind is not GoodMoveBenefitKind.FORCES_RESPONSE
            and boards[0].sole_response is not None
        ):
            raise _fail("only FORCES_RESPONSE retains a BoardFact sole_response")
        for record in owned:
            if isinstance(record, (BoardFactEvidence, MotifEvidence, VariationEvidence)) and any(
                piece != base_frame_piece_entity(bundle.base_position_id, piece.base_ref)
                for piece in record.pieces
            ):
                raise _fail("P9 pieces must retain their exact base-frame presentation")
            if isinstance(record, MotifEvidence):
                motif_moves = [group.played_move, *([group.response] if group.response else [])]
                if [_move_key(m) for m in record.moves] != [_move_key(m) for m in motif_moves]:
                    raise _fail("P9 motif moves must retain played and response identities")
        for variation in (r for r in owned if isinstance(r, VariationEvidence)):
            index = next(
                i for i, r in enumerate(group.required_probe_results) if r.probe == variation.probe
            )
            if variation.terminal != group.required_probe_results[index].terminal:
                raise _fail("variation terminal differs from its required result")
            variation_moves = (
                [group.played_move, group.response]
                if index >= 1 + len(group.representative_alternatives)
                else [expected_moves[index]]
            )
            if [_move_key(m) for m in variation.moves] != [_move_key(m) for m in variation_moves]:
                raise _fail("variation moves must match its originating probe branch")
            if index != causal and (
                variation.board_deltas or variation.replayed_pv_ends_in_checkmate is not None
            ):
                raise _fail("only the causal variation may retain deltas or mate replay flag")
            if index == causal and (
                variation.board_deltas != boards[0].board_deltas
                or variation.replayed_pv_ends_in_checkmate
                is not group.replayed_pv_ends_in_checkmate
            ):
                raise _fail("causal variation must retain the group's board deltas and replay flag")
        if (
            boards[0].board_deltas
            or group.replayed_pv_ends_in_checkmate is not None
            or group.required_probe_results[causal].terminal is not None
        ) and not any(
            isinstance(r, VariationEvidence)
            and r.probe == group.required_probe_results[causal].probe
            for r in owned
        ):
            raise _fail("retained causal metadata requires its causal variation")
        return causal

    @staticmethod
    def _validate_good_protocol(bundle: EvidenceBundle, group: EvidenceGroup) -> int:
        alternatives = group.representative_alternatives
        ranks = [alternative.rank for alternative in alternatives]
        ucis = [a.move.uci for a in alternatives]
        if (
            len(alternatives) not in (1, 2)
            or ranks != sorted(set(ranks))
            or len(set(ucis)) != len(ucis)
            or group.played_move.move.uci in ucis
        ):
            raise _fail("P9 requires one or two distinct alternatives in ascending rank order")
        if group.evidence_form not in (EvidenceForm.DIRECT, EvidenceForm.TESTED_RESPONSE):
            raise _fail("P9 STRONG requires DIRECT or TESTED_RESPONSE")
        forces = group.source_kind is GoodMoveBenefitKind.FORCES_RESPONSE
        tested = group.evidence_form is EvidenceForm.TESTED_RESPONSE
        if forces and (tested or group.response is None):
            raise _fail("FORCES_RESPONSE requires DIRECT and its sole reply")
        if not forces and (
            (tested and group.response is None) or (not tested and group.response is not None)
        ):
            raise _fail("P9 response must agree with DIRECT / TESTED_RESPONSE form")
        results = group.required_probe_results
        batch_count = 1 + len(alternatives)
        if len(results) != batch_count + int(tested) or len(results) > 4:
            raise _fail("P9 probe count differs from Batch A and optional final IGNORE_THREAT")
        if any(r.probe.base.position_id != bundle.base_position_id for r in results):
            raise _fail("P9 probe belongs to another base position")
        moves = (group.played_move.move, *(a.move for a in alternatives))
        for r, move in zip(results[:batch_count], moves, strict=True):
            if (
                r.probe.kind is not ProbeKind.REFUTATION
                or _probe_uci(r.probe.intervention_move) != move.uci
                or r.probe.execution_move is not None
            ):
                raise _fail("P9 Batch A requires ordered execution-free REFUTATION UCIs")
        if (
            group.response is not None
            and group.response.position_id != results[0].analysis_position.position_id
        ):
            raise _fail("P9 response must be bound to the played branch position")
        if tested:
            final = results[-1]
            if (
                final.probe.kind is not ProbeKind.IGNORE_THREAT
                or _probe_uci(final.probe.intervention_move) != group.played_move.move.uci
                or _probe_uci(final.probe.execution_move) != group.response.move.uci
                or final.analysis_position.position_id != results[0].analysis_position.position_id
            ):
                raise _fail("P9 final IGNORE_THREAT must bind played move, Q and played branch")
        return len(results) - 1 if tested else 0

    def _validate_good_entities(
        self,
        bundle: EvidenceBundle,
        group: EvidenceGroup,
        claim: ExplanationClaim,
        owned: list[EvidenceRecord],
        referenced: list[EvidenceRecord],
    ) -> None:
        self._validate_entities(bundle, group, claim, referenced)
        for base in group.source_subject:
            found = {
                piece
                for r in owned
                if isinstance(r, (BoardFactEvidence, MotifEvidence, VariationEvidence))
                for piece in r.pieces
                if piece.base_ref == base
            }
            if found != {base_frame_piece_entity(bundle.base_position_id, base)}:
                raise _fail("source piece must have exactly one retained base-frame presentation")

    @staticmethod
    def _validate_good_exact(
        group: EvidenceGroup, claim: ExplanationClaim, owned: list[EvidenceRecord], causal: int
    ) -> None:
        (board,) = [r for r in owned if isinstance(r, BoardFactEvidence)]
        if group.source_kind is GoodMoveBenefitKind.FORCES_RESPONSE:
            if board.sole_response is None or _move_key(board.sole_response) != _move_key(
                group.response
            ):
                raise _fail("FORCES_RESPONSE requires the exact BoardFact sole_response")
            if board.terminal is not None or not any(
                _move_key(m) == _move_key(group.response) for m in board.moves
            ):
                raise _fail(
                    "FORCES_RESPONSE board moves must retain the sole reply without terminal"
                )
            candidates = [
                c
                for r in owned
                if isinstance(r, MotifEvidence)
                for c in r.candidates
                if c.kind is TacticalCandidateKind.FORCED_RESPONSE
                and len(c.responses) == 1
                and c.responses[0].uci == group.response.move.uci
            ]
            if len(candidates) != 1:
                raise _fail("FORCES_RESPONSE requires one matching forced-response candidate")
            selected = tuple(
                r.evidence_id for r in owned if isinstance(r, (BoardFactEvidence, MotifEvidence))
            )
        else:
            result = group.required_probe_results[causal]
            variations = [
                r for r in owned if isinstance(r, VariationEvidence) and r.probe == result.probe
            ]
            if (
                result.terminal is None
                or result.terminal.kind is not TerminalKind.CHECKMATE
                or result.terminal.winner is not result.probe.base.side_to_move
                or board.terminal != result.terminal
                or not board.board_deltas
                or group.replayed_pv_ends_in_checkmate is not True
                or len(variations) != 1
                or not variations[0].board_deltas
                or variations[0].replayed_pv_ends_in_checkmate is not True
            ):
                raise _fail("DELIVERS_CHECKMATE requires exact terminal and causal replay evidence")
            selected = tuple(
                r.evidence_id
                for r in owned
                if isinstance(r, (BoardFactEvidence, MotifEvidence)) or r is variations[0]
            )
        if claim.evidence_ids != selected:
            raise _fail("EXACT P9 claim must reference only its deterministic evidence selection")

    @staticmethod
    def _validate_good_engine(
        group: EvidenceGroup, claim: ExplanationClaim, owned: list[EvidenceRecord], causal: int
    ) -> None:
        if claim.evidence_ids != group.evidence_ids:
            raise _fail("ENGINE_VERIFIED P9 claims reference the complete group evidence")
        engines = [r for r in owned if isinstance(r, EngineEvidence)]
        analyses = []
        for result in group.required_probe_results:
            if result.engine_analysis is not None:
                if sum(e.probe_result == result for e in engines) != 1:
                    raise _fail("each non-terminal probe needs exactly one EngineEvidence")
                analyses.append(result.engine_analysis)
        if any(a.engine != analyses[0].engine for a in analyses):
            raise _fail("ENGINE_VERIFIED claim mixes engine identities")
        if any(a.settings != analyses[0].settings for a in analyses):
            raise _fail("ENGINE_VERIFIED claim mixes engine settings")
        variations = [r for r in owned if isinstance(r, VariationEvidence)]
        causal_variations = [
            v for v in variations if v.probe == group.required_probe_results[causal].probe
        ]
        if len(causal_variations) != 1:
            raise _fail("ENGINE_VERIFIED P9 claim requires its causal variation")
        if group.source_kind is GoodMoveBenefitKind.MATERIAL_THREAT:
            for result in group.required_probe_results:
                if not any(v.probe == result.probe and v.material_evidence for v in variations):
                    raise _fail(
                        "MATERIAL_THREAT requires material provenance for every required probe"
                    )
            if not causal_variations[0].board_deltas:
                raise _fail("MATERIAL_THREAT requires nonempty causal board deltas")
            if group.evidence_form is EvidenceForm.TESTED_RESPONSE and not any(
                c.kind
                in (
                    TacticalCandidateKind.DIRECT_ATTACK,
                    TacticalCandidateKind.FORK,
                    TacticalCandidateKind.DOUBLE_ATTACK,
                )
                for r in owned
                if isinstance(r, MotifEvidence)
                for c in r.candidates
            ):
                raise _fail("tested material requires a retained resource motif")

    def validate_bad_move(
        self, bundle: EvidenceBundle, claims: tuple[ExplanationClaim, ...]
    ) -> tuple[ExplanationClaim, ...]:
        if not isinstance(bundle, EvidenceBundle):
            raise ExplanationClaimError("validate_bad_move requires an EvidenceBundle")
        if not isinstance(claims, tuple) or any(
            not isinstance(claim, ExplanationClaim) for claim in claims
        ):
            raise ExplanationClaimError("claims must be a tuple of ExplanationClaim values")
        _validate_claim_values(claims)
        if len({claim.claim_id for claim in claims}) != len(claims):
            raise _fail("claim ids must be unique within one package")
        if len(claims) != len(bundle.groups):
            raise _fail("package requires exactly one claim per evidence group")
        for group in bundle.groups:
            if group.source_family is not EvidenceSourceFamily.BAD_MOVE_CAUSE:
                raise _fail("P8 claim validation requires BAD_MOVE_CAUSE evidence groups")

        records = {record.evidence_id: record for record in bundle.evidence}
        owners = {
            evidence_id: group for group in bundle.groups for evidence_id in group.evidence_ids
        }
        resolved = [self._validate(bundle, records, owners, claim) for claim in claims]
        if len(records) != len(bundle.evidence):
            raise _fail("evidence ids must be unique")
        if sum(len(group.evidence_ids) for group in bundle.groups) != len(owners):
            raise _fail("evidence must resolve to exactly one owning group")
        if set(records) != set(owners):
            raise _fail("all package evidence must be group-owned")
        if len({id(group) for group in resolved}) != len(bundle.groups):
            raise _fail("package requires exactly one claim per evidence group")
        predicate_order = {predicate: index for index, predicate in enumerate(ClaimPredicate)}
        order_keys = [
            (
                predicate_order[claim.predicate],
                tuple(claim_entity_sort_key(entity) for entity in claim.objects),
            )
            for claim in claims
        ]
        if order_keys != sorted(order_keys):
            raise _fail("claims must be in canonical predicate and object order")
        if any(claim.claim_id != mint_claim_id(i) for i, claim in enumerate(claims, start=1)):
            raise _fail("claim ids must match canonical tuple positions")
        _validate_canonical_bundle(bundle)
        return claims

    # -- per claim --

    def _validate(
        self,
        bundle: EvidenceBundle,
        records: dict[str, EvidenceRecord],
        owners: dict[str, EvidenceGroup],
        claim: ExplanationClaim,
    ) -> EvidenceGroup:
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
        return group

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
        if any(r.base_position_id != bundle.base_position_id for r in owned):
            raise _fail("P8 evidence belongs to another base position")

        if group.source_kind is _K.MATE_ALLOWED:
            if group.mate_evidence_level not in _MATE_CONFIDENCE:
                raise _fail("MATE_ALLOWED group needs a supported mate_evidence_level")
            if not isinstance(group.replayed_pv_ends_in_checkmate, bool):
                raise _fail("MATE_ALLOWED requires its boolean replayed-mate flag")
        elif (
            group.mate_evidence_level is not None or group.replayed_pv_ends_in_checkmate is not None
        ):
            raise _fail("mate metadata is only valid on MATE_ALLOWED groups")

        self._validate_probe_protocol(bundle, group)
        if group.source_kind is _K.MATE_ALLOWED:
            _require_king_subject(group, mover=True)

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
        if counterfactual.equivalent_alternative_benefit is not False:
            raise _fail("a supported P8 cause requires a comparator without equivalent resource")

        self._validate_group_evidence(group, owned)

    @staticmethod
    def _validate_group_evidence(group: EvidenceGroup, owned: list[EvidenceRecord]) -> None:
        """Bind all owned provenance, including records an EXACT claim does not reference."""

        engine_results = []
        variation_probes = []
        for record in owned:
            if isinstance(record, EngineEvidence):
                matches = [r for r in group.required_probe_results if r == record.probe_result]
                if (
                    len(matches) != 1
                    or matches[0].engine_analysis is None
                    or matches[0].terminal is not None
                ):
                    raise _fail(
                        "EngineEvidence must correspond only to non-terminal required results"
                    )
                if record.probe_result in engine_results:
                    raise _fail("a required result may have at most one EngineEvidence")
                engine_results.append(record.probe_result)
            elif isinstance(record, VariationEvidence):
                if sum(r.probe == record.probe for r in group.required_probe_results) != 1:
                    raise _fail("VariationEvidence must name exactly one required probe")
                if record.probe in variation_probes:
                    raise _fail("at most one VariationEvidence is allowed per required probe")
                variation_probes.append(record.probe)
                if any(material.probe != record.probe for material in record.material_evidence):
                    raise _fail("material probe must equal its VariationEvidence probe")

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
        if (
            group.response is not None
            and group.response.position_id != results[0].analysis_position.position_id
        ):
            raise _fail("P8 punishment must be bound to the actual refutation position")
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
