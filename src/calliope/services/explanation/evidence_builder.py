"""MVP-P10 EvidenceBuilder: supported P8 causes and P9 benefits -> evidence.

This is a pure deterministic mapper over final P8/P9 records.  It retains and normalizes
provenance already produced upstream; it never replays moves, runs rules or engines, reads
scores, or decides whether a cause is true.
"""

from __future__ import annotations

from collections.abc import Iterable

from calliope.domain.analysis import (
    AlternativeScope,
    BadMoveCauseKind,
    BadMoveCauseResult,
    BadMoveCauseStatus,
    BadMoveExplanationResult,
    BadMoveExplanationStatus,
    BasePieceRef,
    GoodMoveBenefitKind,
    GoodMoveBenefitResult,
    GoodMoveBenefitStatus,
    GoodMoveExplanationResult,
    GoodMoveExplanationStatus,
    GoodMoveMode,
    MateEvidenceLevel,
    MaterialLineEvidence,
    ProbeKind,
    ProbeResult,
    TacticalCandidateKind,
    TerminalKind,
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
    """Deterministic P8/P9 -> P10 evidence mapper; it holds no dependencies."""

    def build_good_move(self, result: GoodMoveExplanationResult) -> EvidenceBundle:
        """Map only supported P9 STRONG_MOVE children, without executing analysis."""

        if not isinstance(result, GoodMoveExplanationResult):
            raise _fail("build_good_move requires a GoodMoveExplanationResult")
        if result.literal_only_move_proven is not False:
            raise _fail("literal_only_move_proven must be False")
        if result.status is not GoodMoveExplanationStatus.SUPPORTED:
            return EvidenceBundle(result.base_position_id, (), ())
        if result.mode is GoodMoveMode.ONLY_MOVE_CANDIDATE:
            return self._build_preservation(result)
        if result.mode is not GoodMoveMode.STRONG_MOVE:
            raise _fail("I3 requires supported STRONG_MOVE input")
        supported = [b for b in result.benefits if b.status is GoodMoveBenefitStatus.SUPPORTED]
        for benefit in supported:
            self._bind_good(result, benefit)
        kind_order = {kind: index for index, kind in enumerate(GoodMoveBenefitKind)}
        supported.sort(
            key=lambda b: (
                kind_order[b.kind],
                tuple(
                    base_piece_sort_key(ref) for ref in sorted(b.subject, key=base_piece_sort_key)
                ),
            )
        )
        evidence: list[EvidenceRecord] = []
        groups: list[EvidenceGroup] = []
        for benefit in supported:
            group, records = self._good_group(benefit, len(evidence) + 1)
            groups.append(group)
            evidence.extend(records)
        return EvidenceBundle(result.base_position_id, tuple(evidence), tuple(groups))

    def _build_preservation(self, result: GoodMoveExplanationResult) -> EvidenceBundle:
        supported = [b for b in result.benefits if b.status is GoodMoveBenefitStatus.SUPPORTED]
        for benefit in supported:
            if benefit.kind not in (
                GoodMoveBenefitKind.PREVENTS_MATE,
                GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS,
            ):
                raise _fail("ONLY_MOVE_CANDIDATE accepts preservation benefits only")
            if (
                benefit.base_position_id != result.base_position_id
                or benefit.played_move.uci != result.played_move.uci
                or benefit.mode is not GoodMoveMode.ONLY_MOVE_CANDIDATE
                or benefit.alternatives != result.alternatives
                or benefit.alternative_scope != result.alternative_scope
                or benefit.alternative_scope is not AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
                or benefit.tested_response is not None
            ):
                raise _fail("P9 preservation benefit differs from its parent binding")
        kind_order = {kind: index for index, kind in enumerate(GoodMoveBenefitKind)}
        supported.sort(
            key=lambda b: (
                kind_order[b.kind],
                tuple(
                    base_piece_sort_key(ref) for ref in sorted(b.subject, key=base_piece_sort_key)
                ),
            )
        )
        evidence: list[EvidenceRecord] = []
        groups: list[EvidenceGroup] = []
        for benefit in supported:
            group, records = self._preservation_group(benefit, len(evidence) + 1)
            groups.append(group)
            evidence.extend(records)
        return EvidenceBundle(result.base_position_id, tuple(evidence), tuple(groups))

    @staticmethod
    def _preservation_provenance(benefit: GoodMoveBenefitResult) -> None:
        alternatives = benefit.alternatives
        keys = [(alternative.rank, alternative.move.uci) for alternative in alternatives]
        ranks = [key[0] for key in keys]
        ucis = [key[1] for key in keys]
        if (
            len(keys) not in (1, 2)
            or ranks != sorted(set(ranks))
            or len(set(ucis)) != len(ucis)
            or benefit.played_move.uci in ucis
        ):
            raise _fail(
                "preservation requires one or two distinct representative alternatives in rank order"
            )
        failed = [
            (alternative.rank, alternative.move.uci) for alternative in benefit.failed_alternatives
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
        if benefit.equivalent_alternative_benefit is not (len(failed) < len(keys)):
            raise _fail("preservation equivalence must agree with the failed representative subset")
        results = benefit.probe_results
        if len(results) != 1 + len(alternatives):
            raise _fail("preservation requires exactly complete Batch A")
        for result, move in zip(
            results, (benefit.played_move, *(a.move for a in alternatives)), strict=True
        ):
            if (
                result.probe.base.position_id != benefit.base_position_id
                or result.probe.kind is not ProbeKind.REFUTATION
                or _uci(result.probe.intervention_move) != move.uci
                or result.probe.execution_move is not None
            ):
                raise _fail(
                    "preservation requires ordered execution-free Batch-A REFUTATION probes"
                )
        if benefit.kind is GoodMoveBenefitKind.PREVENTS_MATE:
            if benefit.mate_evidence_level not in (
                MateEvidenceLevel.EXACT_IMMEDIATE,
                MateEvidenceLevel.ENGINE_LINE,
            ) or not isinstance(benefit.replayed_pv_ends_in_checkmate, bool):
                raise _fail(
                    "PREVENTS_MATE requires retained mate level and boolean replay metadata"
                )
            if benefit.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE and (
                benefit.replayed_pv_ends_in_checkmate is not True or not benefit.board_deltas
            ):
                raise _fail(
                    "exact-immediate preservation requires aggregate deltas and replay flag True"
                )
        elif (
            benefit.mate_evidence_level is not None
            or benefit.replayed_pv_ends_in_checkmate is not None
            or not benefit.board_deltas
        ):
            raise _fail("material preservation requires aggregate deltas without mate metadata")

    def _preservation_group(
        self, benefit: GoodMoveBenefitResult, first_ordinal: int
    ) -> tuple[EvidenceGroup, tuple[EvidenceRecord, ...]]:
        self._preservation_provenance(benefit)
        base_id = benefit.base_position_id
        played = MoveClaimEntity(benefit.played_move, base_id)
        moves = (played, *(MoveClaimEntity(a.move, base_id) for a in benefit.alternatives))
        pieces = self._pieces(base_id, (*benefit.subject, *benefit.affected_pieces))
        materials: list[list[MaterialLineEvidence]] = [[] for _ in benefit.probe_results]
        for material in benefit.material_evidence:
            matches = [i for i, r in enumerate(benefit.probe_results) if r.probe == material.probe]
            if len(matches) != 1:
                raise _fail("preservation material must match exactly one retained probe")
            materials[matches[0]].append(material)
        if benefit.kind is GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS and any(
            len(m) != 1 for m in materials
        ):
            raise _fail(
                "material preservation requires exactly one material entry per required probe"
            )
        drafts: list[tuple[type, dict[str, object]]] = [
            (
                BoardFactEvidence,
                {
                    "moves": _unique_moves(moves),
                    "pieces": pieces,
                    "board_deltas": benefit.board_deltas,
                    "sole_response": None,
                    "terminal": None,
                },
            )
        ]
        if benefit.tactical_candidates:
            drafts.append(
                (
                    MotifEvidence,
                    {
                        "candidates": benefit.tactical_candidates,
                        "pieces": pieces,
                        "moves": (),
                    },
                )
            )
        for result in benefit.probe_results:
            if result.engine_analysis is not None:
                drafts.append((EngineEvidence, {"probe_result": result}))
        for index, result in enumerate(benefit.probe_results):
            # Only material has explicit probe ownership. Aggregate mate deltas/flags do not.
            if materials[index]:
                drafts.append(
                    (
                        VariationEvidence,
                        {
                            "probe": result.probe,
                            "moves": (moves[index],),
                            "pieces": (),
                            "material_evidence": tuple(materials[index]),
                            "terminal": result.terminal,
                            "board_deltas": (),
                            "replayed_pv_ends_in_checkmate": None,
                        },
                    )
                )
        drafts.append(
            (
                CounterfactualEvidence,
                {
                    "form": EvidenceForm.PRESERVATION,
                    "probe_results": benefit.probe_results,
                    "comparator_move": None,
                    "tested_response": None,
                    "representative_alternatives": benefit.alternatives,
                    "failed_alternatives": benefit.failed_alternatives,
                    "equivalent_alternative_benefit": benefit.equivalent_alternative_benefit,
                },
            )
        )
        records = tuple(
            record_type(mint_evidence_id(first_ordinal + i), base_id, **values)
            for i, (record_type, values) in enumerate(drafts)
        )
        return EvidenceGroup(
            source_family=EvidenceSourceFamily.GOOD_MOVE_BENEFIT,
            source_kind=benefit.kind,
            source_subject=tuple(sorted(benefit.subject, key=base_piece_sort_key)),
            played_move=played,
            evidence_form=EvidenceForm.PRESERVATION,
            evidence_ids=tuple(r.evidence_id for r in records),
            required_probe_results=benefit.probe_results,
            representative_alternatives=benefit.alternatives,
            failed_alternatives=benefit.failed_alternatives,
            mate_evidence_level=benefit.mate_evidence_level,
            replayed_pv_ends_in_checkmate=benefit.replayed_pv_ends_in_checkmate,
        ), records

    @staticmethod
    def _bind_good(result: GoodMoveExplanationResult, benefit: GoodMoveBenefitResult) -> None:
        if benefit.kind not in (
            GoodMoveBenefitKind.FORCES_RESPONSE,
            GoodMoveBenefitKind.MATE_THREAT,
            GoodMoveBenefitKind.MATERIAL_THREAT,
        ):
            raise _fail("I3 supports only STRONG benefit kinds")
        if (
            benefit.base_position_id != result.base_position_id
            or benefit.played_move.uci != result.played_move.uci
            or benefit.mode is not GoodMoveMode.STRONG_MOVE
            or benefit.alternatives != result.alternatives
            or benefit.alternative_scope != result.alternative_scope
            or benefit.alternative_scope is not AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
        ):
            raise _fail("P9 supported benefit differs from its parent binding")
        if benefit.failed_alternatives or benefit.equivalent_alternative_benefit is not False:
            raise _fail("P9 STRONG benefit requires no failed alternatives and equivalence False")

    def _good_group(
        self, benefit: GoodMoveBenefitResult, first_ordinal: int
    ) -> tuple[EvidenceGroup, tuple[EvidenceRecord, ...]]:
        base_id = benefit.base_position_id
        form, causal_index = self._good_provenance(benefit)
        materials: list[list[MaterialLineEvidence]] = [[] for _ in benefit.probe_results]
        for material in benefit.material_evidence:
            matches = [i for i, r in enumerate(benefit.probe_results) if r.probe == material.probe]
            if len(matches) != 1:
                raise _fail("P9 material evidence must match exactly one retained probe")
            materials[matches[0]].append(material)
        if benefit.kind is GoodMoveBenefitKind.MATERIAL_THREAT:
            if not all(materials) or not benefit.board_deltas:
                raise _fail("MATERIAL_THREAT requires material for every probe and causal deltas")
            if form is EvidenceForm.TESTED_RESPONSE and not any(
                c.kind
                in (
                    TacticalCandidateKind.DIRECT_ATTACK,
                    TacticalCandidateKind.FORK,
                    TacticalCandidateKind.DOUBLE_ATTACK,
                )
                for c in benefit.tactical_candidates
            ):
                raise _fail("tested material requires a retained resource motif")
        played = MoveClaimEntity(benefit.played_move, base_id)
        alternatives = tuple(MoveClaimEntity(a.move, base_id) for a in benefit.alternatives)
        response = (
            None
            if benefit.tested_response is None
            else MoveClaimEntity(
                benefit.tested_response, benefit.probe_results[0].analysis_position.position_id
            )
        )
        pieces = self._pieces(base_id, (*benefit.subject, *benefit.affected_pieces))
        causal = benefit.probe_results[causal_index]
        exact_mate = benefit.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE
        if exact_mate and (
            causal.terminal is None
            or causal.terminal.kind is not TerminalKind.CHECKMATE
            or causal.terminal.winner is not causal.probe.base.side_to_move
            or benefit.replayed_pv_ends_in_checkmate is not True
            or not benefit.board_deltas
        ):
            raise _fail("exact immediate mate lacks exact terminal/replay evidence")
        if benefit.kind is GoodMoveBenefitKind.FORCES_RESPONSE:
            matching = [
                c
                for c in benefit.tactical_candidates
                if c.kind is TacticalCandidateKind.FORCED_RESPONSE
                and len(c.responses) == 1
                and c.responses[0].uci == response.move.uci
            ]
            if len(matching) != 1:
                raise _fail("FORCES_RESPONSE requires one matching forced-response candidate")
        drafts: list[tuple[type, dict[str, object]]] = [
            (
                BoardFactEvidence,
                {
                    "moves": _unique_moves((played, *alternatives, response)),
                    "pieces": pieces,
                    "board_deltas": benefit.board_deltas,
                    "sole_response": response
                    if benefit.kind is GoodMoveBenefitKind.FORCES_RESPONSE
                    else None,
                    "terminal": causal.terminal if exact_mate else None,
                },
            )
        ]
        if benefit.tactical_candidates:
            drafts.append(
                (
                    MotifEvidence,
                    {
                        "candidates": benefit.tactical_candidates,
                        "pieces": pieces,
                        "moves": _unique_moves((played, response)),
                    },
                )
            )
        for probe_result in benefit.probe_results:
            if probe_result.engine_analysis is not None:
                drafts.append((EngineEvidence, {"probe_result": probe_result}))
        for index, probe_result in enumerate(benefit.probe_results):
            is_causal = index == causal_index
            if not materials[index] and not (
                is_causal
                and (
                    benefit.board_deltas
                    or benefit.replayed_pv_ends_in_checkmate is not None
                    or probe_result.terminal is not None
                )
            ):
                continue
            moves = (
                (played, response)
                if index >= 1 + len(alternatives)
                else ((played,) if index == 0 else (alternatives[index - 1],))
            )
            drafts.append(
                (
                    VariationEvidence,
                    {
                        "probe": probe_result.probe,
                        "moves": _unique_moves(moves),
                        "pieces": pieces if is_causal else (),
                        "material_evidence": tuple(materials[index]),
                        "terminal": probe_result.terminal,
                        "board_deltas": benefit.board_deltas if is_causal else (),
                        "replayed_pv_ends_in_checkmate": benefit.replayed_pv_ends_in_checkmate
                        if is_causal
                        else None,
                    },
                )
            )
        drafts.append(
            (
                CounterfactualEvidence,
                {
                    "form": form,
                    "probe_results": benefit.probe_results,
                    "comparator_move": None,
                    "tested_response": response if form is EvidenceForm.TESTED_RESPONSE else None,
                    "representative_alternatives": benefit.alternatives,
                    "failed_alternatives": (),
                    "equivalent_alternative_benefit": benefit.equivalent_alternative_benefit,
                },
            )
        )
        records = tuple(
            record_type(mint_evidence_id(first_ordinal + i), base_id, **values)
            for i, (record_type, values) in enumerate(drafts)
        )
        return EvidenceGroup(
            source_family=EvidenceSourceFamily.GOOD_MOVE_BENEFIT,
            source_kind=benefit.kind,
            source_subject=tuple(sorted(benefit.subject, key=base_piece_sort_key)),
            played_move=played,
            evidence_form=form,
            evidence_ids=tuple(r.evidence_id for r in records),
            required_probe_results=benefit.probe_results,
            response=response,
            representative_alternatives=benefit.alternatives,
            mate_evidence_level=benefit.mate_evidence_level,
            replayed_pv_ends_in_checkmate=benefit.replayed_pv_ends_in_checkmate,
        ), records

    @staticmethod
    def _good_provenance(benefit: GoodMoveBenefitResult) -> tuple[EvidenceForm, int]:
        alternatives = benefit.alternatives
        ranks = [alternative.rank for alternative in alternatives]
        ucis = [a.move.uci for a in alternatives]
        if (
            len(alternatives) not in (1, 2)
            or ranks != sorted(set(ranks))
            or len(set(ucis)) != len(ucis)
            or benefit.played_move.uci in ucis
        ):
            raise _fail("P9 requires one or two distinct alternatives in ascending rank order")
        results = benefit.probe_results
        batch_count = 1 + len(alternatives)
        forces = benefit.kind is GoodMoveBenefitKind.FORCES_RESPONSE
        tested = not forces and benefit.tested_response is not None
        if len(results) != batch_count + int(tested) or len(results) > 4:
            raise _fail("P9 probe count differs from Batch A and optional final IGNORE_THREAT")
        if forces and benefit.tested_response is None:
            raise _fail("FORCES_RESPONSE requires its sole reply")
        if any(r.probe.base.position_id != benefit.base_position_id for r in results):
            raise _fail("P9 probe belongs to another base position")
        for r, move in zip(
            results[:batch_count],
            (benefit.played_move, *(a.move for a in alternatives)),
            strict=True,
        ):
            if (
                r.probe.kind is not ProbeKind.REFUTATION
                or _uci(r.probe.intervention_move) != move.uci
                or r.probe.execution_move is not None
            ):
                raise _fail("P9 Batch A requires ordered execution-free REFUTATION UCIs")
        if tested:
            final = results[-1]
            if (
                final.probe.kind is not ProbeKind.IGNORE_THREAT
                or _uci(final.probe.intervention_move) != benefit.played_move.uci
                or _uci(final.probe.execution_move) != benefit.tested_response.uci
                or final.analysis_position.position_id != results[0].analysis_position.position_id
            ):
                raise _fail("P9 final IGNORE_THREAT must bind played move, Q and played branch")
        if benefit.kind is GoodMoveBenefitKind.MATE_THREAT:
            if benefit.mate_evidence_level not in (
                MateEvidenceLevel.EXACT_IMMEDIATE,
                MateEvidenceLevel.ENGINE_LINE,
            ) or (tested and benefit.mate_evidence_level is MateEvidenceLevel.EXACT_IMMEDIATE):
                raise _fail("MATE_THREAT needs a supported level; exact immediate is DIRECT only")
        elif (
            benefit.mate_evidence_level is not None
            or benefit.replayed_pv_ends_in_checkmate is not None
        ):
            raise _fail("mate metadata is only valid on MATE_THREAT")
        return (
            (EvidenceForm.TESTED_RESPONSE, len(results) - 1) if tested else (EvidenceForm.DIRECT, 0)
        )

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
