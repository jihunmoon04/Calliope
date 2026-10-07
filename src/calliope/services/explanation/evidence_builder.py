"""MVP-P10 EvidenceBuilder: supported P8 causes -> typed P10 evidence.

This is a pure deterministic mapper over final P8 records.  It retains and normalizes
provenance that P8 already produced; it never replays moves, runs rules or engines, reads
scores, or decides whether a cause is true.
"""

from __future__ import annotations

from collections.abc import Iterable

from calliope.domain.analysis import (
    BadMoveCauseKind,
    BadMoveCauseResult,
    BadMoveCauseStatus,
    BadMoveExplanationResult,
    BadMoveExplanationStatus,
    BasePieceRef,
    MaterialLineEvidence,
    ProbeKind,
    ProbeResult,
)
from calliope.domain.chess import ChessMove
from calliope.domain.explanation import (
    EVIDENCE_RECORD_TYPE_ORDER,
    BoardFactEvidence,
    CounterfactualEvidence,
    EngineEvidence,
    EvidenceBundle,
    EvidenceForm,
    EvidenceGroup,
    EvidenceRecord,
    EvidenceSourceFamily,
    MotifEvidence,
    MoveClaimEntity,
    PieceClaimEntity,
    VariationEvidence,
    base_frame_piece_entity,
    base_piece_sort_key,
    claim_entity_identity,
    mint_evidence_id,
)
from calliope.errors import ExplanationEvidenceError

_KIND_ORDER = {kind: index for index, kind in enumerate(BadMoveCauseKind)}


def _fail(message: str) -> ExplanationEvidenceError:
    return ExplanationEvidenceError(message)


def _uci(move: ChessMove | None) -> str | None:
    return None if move is None else move.uci


def _unique_moves(moves: Iterable[MoveClaimEntity | None]) -> tuple[MoveClaimEntity, ...]:
    """Drop absent moves and canonical (position_id, UCI) repeats, keeping first order."""

    seen: set[tuple[object, ...]] = set()
    kept = []
    for move in moves:
        if move is None:
            continue
        identity = claim_entity_identity(move)
        if identity not in seen:
            seen.add(identity)
            kept.append(move)
    return tuple(kept)


def _cause_key(cause: BadMoveCauseResult) -> tuple[int, tuple[tuple[int, str, str], ...]]:
    subject = sorted(cause.subject, key=base_piece_sort_key)
    return (_KIND_ORDER[cause.kind], tuple(base_piece_sort_key(base) for base in subject))


class _P8Provenance:
    """Validated shape of one supported cause's retained P7 provenance."""

    def __init__(self, cause: BadMoveCauseResult) -> None:
        results = cause.probe_results
        if any(not isinstance(result, ProbeResult) for result in results):
            raise _fail("P8 probe_results must contain ProbeResult values")
        if len(results) not in (2, 3):
            raise _fail("P8 provenance must be REFUTATION(B,M), REFUTATION(B,A)[, IGNORE_THREAT]")
        if any(result.probe.base.position_id != cause.base_position_id for result in results):
            raise _fail("P8 probe belongs to another base position")

        self.actual_index = self._refutation(results, cause.played_move, "actual")
        comparator_index = self._refutation(results, cause.comparator_move, "comparator")
        if (self.actual_index, comparator_index) != (0, 1):
            raise _fail("P8 provenance must start REFUTATION(B,M), REFUTATION(B,A)")
        self.actual = results[self.actual_index]

        ignores = [result for result in results if result.probe.kind is ProbeKind.IGNORE_THREAT]
        if len(results) == 3:
            final = results[2]
            if len(ignores) != 1 or final.probe.kind is not ProbeKind.IGNORE_THREAT:
                raise _fail("P8 third probe must be the single same-punishment IGNORE_THREAT")
            if cause.punishment_move is None:
                raise _fail("P8 same-punishment probe requires a punishment move")
            if _uci(final.probe.intervention_move) != cause.comparator_move.uci:
                raise _fail("P8 same-punishment probe must intervene with the comparator")
            if _uci(final.probe.execution_move) != cause.punishment_move.uci:
                raise _fail("P8 same-punishment probe must execute the punishment move")

    @staticmethod
    def _refutation(results: tuple[ProbeResult, ...], move: ChessMove, label: str) -> int:
        matches = [
            index
            for index, result in enumerate(results)
            if result.probe.kind is ProbeKind.REFUTATION
            and _uci(result.probe.intervention_move) == move.uci
        ]
        if len(matches) != 1:
            raise _fail(f"P8 needs exactly one {label} REFUTATION probe, found {len(matches)}")
        if results[matches[0]].probe.execution_move is not None:
            raise _fail(f"P8 {label} REFUTATION probe must not carry an execution move")
        return matches[0]


def _materials_by_probe(
    cause: BadMoveCauseResult,
) -> tuple[tuple[MaterialLineEvidence, ...], ...]:
    """Material entries per probe-result index, associated by exact originating probe."""

    grouped: list[list[MaterialLineEvidence]] = [[] for _ in cause.probe_results]
    for material in cause.material_evidence:
        if not isinstance(material, MaterialLineEvidence):
            raise _fail("P8 material_evidence must contain MaterialLineEvidence values")
        matches = [
            index
            for index, result in enumerate(cause.probe_results)
            if result.probe == material.probe
        ]
        if len(matches) != 1:
            raise _fail(f"P8 material evidence matches {len(matches)} retained probes, not 1")
        grouped[matches[0]].append(material)
    return tuple(tuple(materials) for materials in grouped)


class EvidenceBuilder:
    """Deterministic P8 -> P10 evidence mapper; it holds no dependencies."""

    def build_bad_move(self, result: BadMoveExplanationResult) -> EvidenceBundle:
        if not isinstance(result, BadMoveExplanationResult):
            raise _fail("build_bad_move requires a BadMoveExplanationResult")
        empty = EvidenceBundle(base_position_id=result.base_position_id, evidence=(), groups=())
        if result.status is not BadMoveExplanationStatus.SUPPORTED:
            return empty

        supported = [
            cause for cause in result.causes if cause.status is BadMoveCauseStatus.SUPPORTED
        ]
        for cause in supported:
            self._bind(result, cause)

        evidence: list[EvidenceRecord] = []
        groups: list[EvidenceGroup] = []
        for cause in sorted(supported, key=_cause_key):
            group, records = self._group(cause, first_ordinal=len(evidence) + 1)
            groups.append(group)
            evidence.extend(records)
        return EvidenceBundle(
            base_position_id=result.base_position_id,
            evidence=tuple(evidence),
            groups=tuple(groups),
        )

    @staticmethod
    def _bind(result: BadMoveExplanationResult, cause: BadMoveCauseResult) -> None:
        if cause.base_position_id != result.base_position_id:
            raise _fail("P8 cause belongs to another base position")
        if cause.played_move.uci != result.played_move.uci:
            raise _fail("P8 cause played move differs from the parent result")
        if cause.comparator_move.uci != result.comparator_move.uci:
            raise _fail("P8 cause comparator move differs from the parent result")

    def _group(
        self, cause: BadMoveCauseResult, first_ordinal: int
    ) -> tuple[EvidenceGroup, tuple[EvidenceRecord, ...]]:
        base_id = cause.base_position_id
        provenance = _P8Provenance(cause)
        materials = _materials_by_probe(cause)

        played = MoveClaimEntity(cause.played_move, base_id)
        comparator = MoveClaimEntity(cause.comparator_move, base_id)
        punishment = (
            None
            if cause.punishment_move is None
            else MoveClaimEntity(
                cause.punishment_move, provenance.actual.analysis_position.position_id
            )
        )
        subject = tuple(sorted(cause.subject, key=base_piece_sort_key))
        pieces = self._pieces(base_id, (*cause.subject, *cause.affected_pieces))

        # Each draft is (record type, field values); ids are minted after canonical ordering.
        drafts: list[tuple[type, dict[str, object]]] = [
            (
                BoardFactEvidence,
                {
                    "moves": _unique_moves((played, comparator, punishment)),
                    "pieces": pieces,
                    "board_deltas": cause.board_deltas,
                },
            )
        ]
        if cause.tactical_candidates:
            drafts.append(
                (
                    MotifEvidence,
                    {
                        "candidates": cause.tactical_candidates,
                        "pieces": pieces,
                        "moves": _unique_moves((played, punishment)),
                    },
                )
            )
        for result in cause.probe_results:
            if result.engine_analysis is not None:
                drafts.append((EngineEvidence, {"probe_result": result}))
        drafts.extend(
            self._variations(cause, provenance, materials, played, comparator, punishment, pieces)
        )
        drafts.append(
            (
                CounterfactualEvidence,
                {
                    "form": EvidenceForm.DIRECT,
                    "probe_results": cause.probe_results,
                    "comparator_move": comparator,
                    "tested_response": None,
                    "representative_alternatives": (),
                    "failed_alternatives": (),
                    "equivalent_alternative_benefit": cause.comparator_has_equivalent_resource,
                },
            )
        )

        # Frozen I0 type order; the sort is stable, so draft order fixes order within a type.
        drafts.sort(key=lambda draft: EVIDENCE_RECORD_TYPE_ORDER.index(draft[0]))
        records = tuple(
            record_type(mint_evidence_id(first_ordinal + offset), base_id, **values)
            for offset, (record_type, values) in enumerate(drafts)
        )
        group = EvidenceGroup(
            source_family=EvidenceSourceFamily.BAD_MOVE_CAUSE,
            source_kind=cause.kind,
            source_subject=subject,
            played_move=played,
            evidence_form=EvidenceForm.DIRECT,
            evidence_ids=tuple(record.evidence_id for record in records),
            required_probe_results=cause.probe_results,
            comparator_move=comparator,
            response=punishment,
            representative_alternatives=(),
            failed_alternatives=(),
            mate_evidence_level=cause.mate_evidence_level,
            replayed_pv_ends_in_checkmate=cause.replayed_pv_ends_in_checkmate,
        )
        return group, records

    @staticmethod
    def _pieces(base_id: str, refs: Iterable[BasePieceRef]) -> tuple[PieceClaimEntity, ...]:
        unique = {ref: None for ref in refs}  # BasePieceRef identity; order fixed below
        return tuple(
            base_frame_piece_entity(base_id, ref) for ref in sorted(unique, key=base_piece_sort_key)
        )

    @staticmethod
    def _variations(
        cause: BadMoveCauseResult,
        provenance: _P8Provenance,
        materials: tuple[tuple[MaterialLineEvidence, ...], ...],
        played: MoveClaimEntity,
        comparator: MoveClaimEntity,
        punishment: MoveClaimEntity | None,
        pieces: tuple[PieceClaimEntity, ...],
    ) -> list[tuple[type, dict[str, object]]]:
        """Actual-line replay provenance, then material-bearing other probes in probe order."""

        drafts: list[tuple[type, dict[str, object]]] = []
        for index, result in enumerate(cause.probe_results):
            if index == provenance.actual_index:
                if not (
                    cause.board_deltas
                    or materials[index]
                    or cause.replayed_pv_ends_in_checkmate is not None
                    or result.terminal is not None
                ):
                    continue
                values: dict[str, object] = {
                    "probe": result.probe,
                    "moves": _unique_moves((played, punishment)),
                    "pieces": pieces,
                    "board_deltas": cause.board_deltas,
                    "material_evidence": materials[index],
                    "terminal": result.terminal,
                    "replayed_pv_ends_in_checkmate": cause.replayed_pv_ends_in_checkmate,
                }
            else:
                # P8 retains causal deltas only for the actual line; never attribute them here.
                if not materials[index]:
                    continue
                values = {
                    "probe": result.probe,
                    "moves": (comparator,),
                    "pieces": (),
                    "board_deltas": (),
                    "material_evidence": materials[index],
                    "terminal": result.terminal,
                    "replayed_pv_ends_in_checkmate": None,
                }
            drafts.append((VariationEvidence, values))
        return drafts
